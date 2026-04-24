#!/usr/bin/env python3
"""
nevod — Nevod node CLI

Commands:
  nevod init    <address>            Generate keypair, save identity
  nevod genesis <address>            Init first node in a new network
  nevod start   <identity> <db>      Start node (existing network)
  nevod join    <identity> <db> <bootstrap_addr>  Start and join via bootstrap

Examples:
  python nevod.py genesis 127.0.0.1:8765
  python nevod.py start node.json node.db
  python nevod.py join node.json node.db 192.168.1.1:8765
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
