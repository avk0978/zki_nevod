#!/usr/bin/env python3
"""
nevod — Nevod node & cell CLI

Node commands:
  nevod init    <address>                         Generate node keypair
  nevod genesis <address>                         Init first node in a new network
  nevod start                                     Start node
  nevod join    <bootstrap_addr>                  Start and join via bootstrap
  nevod info                                      Print node identity

Cell commands:
  nevod cell init   <name>                        Generate cell identity
  nevod cell info   <identity.cell.json>          Print cell info
  nevod cell connect <identity.cell.json> <addr>  Connect and chat

Examples:
  python nevod.py genesis 127.0.0.1:8765
  python nevod.py cell init alice
  python nevod.py cell connect alice.cell.json 127.0.0.1:8765
"""

import asyncio
import logging
import signal
import sys

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
def cli():
    """Nevod — Zero Knowledge Infrastructure node."""


@cli.command()
@click.argument("address")
@click.option("--out", default="node.json", show_default=True, help="Identity file path")
@click.option("--type", "node_type", default="permanent",
              type=click.Choice(["permanent", "temporary"]), show_default=True)
@click.option("--access", default="closed",
              type=click.Choice(["open", "closed"]), show_default=True)
def init(address, out, node_type, access):
    """Generate a new node identity (keypair) and save to file."""
    from node.identity import NodeIdentity
    identity = NodeIdentity.generate(address, node_type=node_type, access=access)
    identity.save(out)
    click.echo(f"node_id : {identity.node_id}")
    click.echo(f"address : {address}")
    click.echo(f"type    : {node_type} / {access}")
    click.echo(f"saved   : {out}")


@cli.command()
@click.argument("address")
@click.option("--identity", default="node.json", show_default=True)
@click.option("--db", default="node.db", show_default=True)
@click.option("--access", default="open",
              type=click.Choice(["open", "closed"]), show_default=True)
def genesis(address, identity, db, access):
    """Create the first node in a new Nevod network."""
    asyncio.run(_genesis(address, identity, db, access))


async def _genesis(address, identity_path, db_path, access):
    from node.node import Node
    node = await Node.create_genesis(address, identity_path, db_path, access=access)
    click.echo(f"genesis node: {node.identity.node_id}")
    click.echo(f"address     : {address}")
    click.echo(f"identity    → {identity_path}")
    click.echo(f"database    → {db_path}")
    await node.start()
    click.echo("node running — Ctrl+C to stop")
    await _run_until_signal(node)


@cli.command()
@click.option("--identity", default="node.json", show_default=True)
@click.option("--db", default="node.db", show_default=True)
def start(identity, db):
    """Start a node (already initialised, existing network)."""
    asyncio.run(_start(identity, db))


async def _start(identity_path, db_path):
    from node.node import Node
    node = await Node.create(identity_path, db_path)
    await node.start()
    click.echo(f"node : {node.identity.node_id[:16]}...")
    click.echo("running — Ctrl+C to stop")
    await _run_until_signal(node)


@cli.command()
@click.argument("bootstrap")
@click.option("--identity", default="node.json", show_default=True)
@click.option("--db", default="node.db", show_default=True)
def join(bootstrap, identity, db):
    """Start node and join existing network via bootstrap address (host:port)."""
    asyncio.run(_join(bootstrap, identity, db))


async def _join(bootstrap_addr, identity_path, db_path):
    from node.node import Node
    node = await Node.create(identity_path, db_path)
    await node.start()
    await node.join(bootstrap_addr)
    click.echo(f"node : {node.identity.node_id[:16]}...")
    click.echo(f"joined via {bootstrap_addr}")
    click.echo("running — Ctrl+C to stop")
    await _run_until_signal(node)


@cli.command()
@click.option("--identity", default="node.json", show_default=True)
def info(identity):
    """Print identity info without starting the node."""
    from node.identity import NodeIdentity
    try:
        idt = NodeIdentity.load(identity)
    except FileNotFoundError:
        click.echo(f"not found: {identity}", err=True)
        sys.exit(1)
    click.echo(f"node_id : {idt.node_id}")
    click.echo(f"address : {idt.address}")
    click.echo(f"type    : {idt.node_type} / {idt.access}")
    click.echo(f"enc_pub : {idt.encryption.public.hex()}")


# ─── cell commands ────────────────────────────────────────────────────────────

@cli.group()
def cell():
    """Cell (user / AI agent) identity and E2E messaging."""


@cell.command("init")
@click.argument("name")
@click.option("--out", default=None,
              help="Output file (default: <name>.cell.json)")
def cell_init(name, out):
    """Generate a new cell identity (keypair) and save to file."""
    from node.identity import CellIdentity
    if out is None:
        out = f"{name}.cell.json"
    idt = CellIdentity.generate(name)
    idt.save(out)
    click.echo(f"name    : {name}")
    click.echo(f"cell_id : {idt.cell_id}")
    click.echo(f"enc_pub : {idt.encryption.public.hex()}")
    click.echo(f"saved   : {out}")


@cell.command("info")
@click.argument("identity")
def cell_info(identity):
    """Print cell identity info (cell_id, enc_pub)."""
    from node.identity import CellIdentity
    try:
        idt = CellIdentity.load(identity)
    except FileNotFoundError:
        click.echo(f"not found: {identity}", err=True)
        sys.exit(1)
    click.echo(f"name    : {idt.name}")
    click.echo(f"cell_id : {idt.cell_id}")
    click.echo(f"enc_pub : {idt.encryption.public.hex()}")


@cell.command("connect")
@click.argument("identity")
@click.argument("node_addr")
def cell_connect_cmd(identity, node_addr):
    """Connect cell to a node and start interactive chat.

    \b
    Inside the REPL:
      /add <alias> <cell_id>[@<node_id>] <enc_pub_hex>   — save contact
      /contacts                                           — list contacts
      <alias>: <message>                                  — send to contact
      <cell_id>[@<node_id>] <enc_pub_hex>: <message>     — send directly
      /quit                                               — disconnect
    """
    asyncio.run(_cell_connect(identity, node_addr))


async def _cell_connect(identity_path: str, node_addr: str):
    from node.identity import CellIdentity
    from node.client import CellClient

    try:
        idt = CellIdentity.load(identity_path)
    except FileNotFoundError:
        click.echo(f"not found: {identity_path}", err=True)
        sys.exit(1)

    # in-session contact book: alias → (cell_id, node_id, enc_pubkey)
    contacts: dict = {}

    async def on_message(from_addr: str, plaintext: bytes):
        text = plaintext.decode(errors="replace")
        click.echo(f"\n  [{from_addr[:24]}]: {text}")
        click.echo("> ", nl=False)

    cell = CellClient(idt, on_message=on_message)
    try:
        await cell.connect(node_addr)
    except Exception as e:
        click.echo(f"connect failed: {e}", err=True)
        sys.exit(1)

    click.echo(f"connected : {node_addr}")
    click.echo(f"cell_id   : {idt.cell_id}")
    click.echo(f"enc_pub   : {idt.encryption.public.hex()}")
    click.echo()
    click.echo("  /add <alias> <cell_id>[@<node>] <enc_pub>")
    click.echo("  /contacts")
    click.echo("  <alias>: <msg>   OR   <cell_id>[@<node>] <enc_pub>: <msg>")
    click.echo("  /quit")
    click.echo()

    loop = asyncio.get_event_loop()

    try:
        while cell.connected:
            click.echo("> ", nl=False)
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                break
            if not line:          # EOF (pipe closed / Ctrl+D)
                break
            line = line.strip()
            if not line:
                continue

            # ── /quit ──────────────────────────────────────────────────────
            if line in ("/quit", "/exit", "quit", "exit"):
                break

            # ── /contacts ──────────────────────────────────────────────────
            if line == "/contacts":
                if not contacts:
                    click.echo("  (no contacts)")
                else:
                    for alias, (cid, nid, _) in contacts.items():
                        click.echo(f"  {alias}: {cid[:16]}...@{nid[:16]}...")
                continue

            # ── /add <alias> <addr> <enc_pub> ─────────────────────────────
            if line.startswith("/add "):
                parts = line[5:].split()
                if len(parts) != 3:
                    click.echo("  usage: /add <alias> <cell_id>[@<node_id>] <enc_pub_hex>")
                    continue
                alias, addr_str, enc_hex = parts
                to_cell_id, to_node_id = _split_addr(addr_str, cell._node_id)
                try:
                    enc_pub = bytes.fromhex(enc_hex)
                    if len(enc_pub) != 32:
                        raise ValueError("enc_pub must be 32 bytes")
                except ValueError as e:
                    click.echo(f"  bad enc_pub: {e}")
                    continue
                contacts[alias] = (to_cell_id, to_node_id, enc_pub)
                click.echo(f"  saved: {alias}")
                continue

            # ── <alias>: <msg>   OR   <addr> <enc_pub>: <msg> ─────────────
            if ": " in line:
                head, message = line.split(": ", 1)
                head = head.strip()

                if head in contacts:
                    to_cell_id, to_node_id, enc_pub = contacts[head]
                elif " " in head:
                    addr_str, enc_hex = head.split(" ", 1)
                    to_cell_id, to_node_id = _split_addr(addr_str, cell._node_id)
                    try:
                        enc_pub = bytes.fromhex(enc_hex.strip())
                        if len(enc_pub) != 32:
                            raise ValueError("enc_pub must be 32 bytes")
                    except ValueError as e:
                        click.echo(f"  bad enc_pub: {e}")
                        continue
                else:
                    click.echo(f"  unknown alias '{head}' — use /add or provide enc_pub")
                    continue

                try:
                    await cell.send(to_cell_id, to_node_id, enc_pub,
                                    message.encode())
                    click.echo("  [sent]")
                except Exception as e:
                    click.echo(f"  send error: {e}")
                continue

            click.echo("  ?  type /quit to exit or see usage above")

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        click.echo("\ndisconnecting...")
        await cell.disconnect()


def _split_addr(addr_str: str, default_node_id: str):
    """Split 'cell_id@node_id' or 'cell_id' into (cell_id, node_id)."""
    if "@" in addr_str:
        cell_id, node_id = addr_str.split("@", 1)
        return cell_id, node_id
    return addr_str, default_node_id


# ─── signal / shutdown ────────────────────────────────────────────────────────

async def _run_until_signal(node):
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    def _signal_handler():
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows: signals not supported in asyncio event loop
            pass

    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        click.echo("\nstopping...")
        await node.stop()


if __name__ == "__main__":
    cli()
