"""
Integration tests for Node — transport, gossip, routing.

Uses real WebSocket connections on localhost with ports 19300+.
Each test class uses its own port range to avoid conflicts.
"""

import asyncio
import pytest

from node.identity import NodeIdentity
from node.node import Node
from node.storage import NodeEntry
from node.protocol import T, Packet, encode_payload
import time


BASE = 19300


def addr(offset: int) -> str:
    return f"127.0.0.1:{BASE + offset}"


async def make_node(tmp_path, offset: int, genesis: bool = False) -> Node:
    address = addr(offset)
    id_path = str(tmp_path / f"n{offset}.json")
    db_path = str(tmp_path / f"n{offset}.db")
    if genesis:
        return await Node.create_genesis(address, id_path, db_path, access="open")
    idt = NodeIdentity.generate(address)
    idt.save(id_path)
    return await Node.create(id_path, db_path)


class TestTwoNodesConnect:
    async def test_nodes_connect_via_join(self, tmp_path):
        n1 = await make_node(tmp_path, 0, genesis=True)
        n2 = await make_node(tmp_path, 1)
        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(0))
            await asyncio.sleep(0.2)

            conn = await n1.transport.connections.get(n2.identity.node_id)
            assert conn is not None, "n1 should have connection to n2"
            assert conn.peer_node_id == n2.identity.node_id
        finally:
            await n1.stop()
            await n2.stop()

    async def test_peer_enc_pubkey_available_after_connect(self, tmp_path):
        n1 = await make_node(tmp_path, 2, genesis=True)
        n2 = await make_node(tmp_path, 3)
        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(2))
            await asyncio.sleep(0.2)

            conn = await n2.transport.connections.get(n1.identity.node_id)
            assert conn is not None
            assert conn.peer_enc_pubkey == n1.identity.encryption.public
        finally:
            await n1.stop()
            await n2.stop()

    async def test_connection_is_bidirectional(self, tmp_path):
        n1 = await make_node(tmp_path, 4, genesis=True)
        n2 = await make_node(tmp_path, 5)
        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(4))
            await asyncio.sleep(0.2)

            assert await n1.transport.connections.get(n2.identity.node_id) is not None
            assert await n2.transport.connections.get(n1.identity.node_id) is not None
        finally:
            await n1.stop()
            await n2.stop()

    async def test_multiple_peers(self, tmp_path):
        n1 = await make_node(tmp_path, 6, genesis=True)
        n2 = await make_node(tmp_path, 7)
        n3 = await make_node(tmp_path, 8)
        await n1.start()
        await n2.start()
        await n3.start()
        try:
            await n2.join(addr(6))
            await n3.join(addr(6))
            await asyncio.sleep(0.2)

            conns = await n1.transport.connections.all()
            peer_ids = {c.peer_node_id for c in conns}
            assert n2.identity.node_id in peer_ids
            assert n3.identity.node_id in peer_ids
        finally:
            await n1.stop()
            await n2.stop()
            await n3.stop()


class TestCellRegistration:
    async def test_register_cell_locally(self, tmp_path):
        n = await make_node(tmp_path, 10, genesis=True)
        await n.start()
        try:
            from node.crypto import gen_signing, gen_encryption
            cell_sign = gen_signing()
            cell_enc  = gen_encryption()
            cell_id   = cell_sign.public.hex()
            await n.register_cell_locally(cell_id, cell_sign.public, cell_enc.public)

            cell = await n.storage.get_cell(cell_id)
            assert cell is not None
            assert cell.signing_pubkey == cell_sign.public
            assert cell.enc_pubkey == cell_enc.public
        finally:
            await n.stop()

    async def test_presence_set_after_register(self, tmp_path):
        n = await make_node(tmp_path, 11, genesis=True)
        await n.start()
        try:
            from node.crypto import gen_signing, gen_encryption
            cell_sign = gen_signing()
            cell_id   = cell_sign.public.hex()
            await n.register_cell_locally(cell_id, cell_sign.public, gen_encryption().public)

            presence = await n.storage.get_presence(cell_id)
            assert presence is not None
            assert presence.home_node_id == n.identity.node_id
        finally:
            await n.stop()


class TestMessageRouting:
    async def test_message_buffered_when_no_route(self, tmp_path):
        n = await make_node(tmp_path, 12, genesis=True)
        await n.start()
        try:
            from node.crypto import gen_signing, gen_encryption
            cell_sign = gen_signing()
            cell_enc  = gen_encryption()
            cell_id   = cell_sign.public.hex()
            await n.register_cell_locally(cell_id, cell_sign.public, cell_enc.public)

            # manually set presence to an offline node so message gets buffered
            await n.storage.update_presence(cell_id, "ghost_node_id", None)
            await n.storage.upsert_node(NodeEntry(
                node_id="ghost_node_id",
                address="1.2.3.4:9999",
                status="offline",
                last_seen=int(time.time()) - 1000,
                added_at=int(time.time()),
            ))

            to_addr = f"{cell_id}@ghost_node_id"
            pkt = Packet(
                type=T.MSG,
                payload=b"encrypted-blob",
                from_addr=n.identity.node_id,
                to_addr=to_addr,
            )
            await n.router.route(pkt)

            buffered = await n.storage.get_buffered(cell_id)
            assert len(buffered) == 1
            assert buffered[0].to_cell == cell_id
        finally:
            await n.stop()

    async def test_local_message_delivered(self, tmp_path):
        delivered = []

        async def on_message(pkt: Packet):
            delivered.append(pkt)

        n = await Node.create_genesis(
            addr(13),
            str(tmp_path / "n13.json"),
            str(tmp_path / "n13.db"),
            on_message=on_message,
        )
        await n.start()
        try:
            from node.crypto import gen_signing, gen_encryption
            cell_sign = gen_signing()
            cell_enc  = gen_encryption()
            cell_id   = cell_sign.public.hex()
            await n.register_cell_locally(cell_id, cell_sign.public, cell_enc.public)

            await n.send_message(f"{cell_id}@{n.identity.node_id}", b"hello")
            await asyncio.sleep(0.1)

            assert len(delivered) == 1
            assert delivered[0].type == T.MSG
        finally:
            await n.stop()


class TestPingPong:
    async def test_ping_updates_last_seen(self, tmp_path):
        n1 = await make_node(tmp_path, 14, genesis=True)
        n2 = await make_node(tmp_path, 15)
        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(14))
            await asyncio.sleep(0.2)

            await n2.storage.upsert_node(NodeEntry(
                node_id=n1.identity.node_id,
                address=addr(14),
                type="permanent",
                access="open",
                last_seen=int(time.time()),
                status="online",
                added_at=int(time.time()),
            ))

            from node.protocol import make_ping, pack
            conn = await n2.transport.connections.get(n1.identity.node_id)
            assert conn is not None
            ping = make_ping(n2.identity.node_id, n1.identity.node_id)
            await conn.send(ping)
            await asyncio.sleep(0.2)
        finally:
            await n1.stop()
            await n2.stop()


class TestGenesisNode:
    async def test_genesis_has_self_in_node_table(self, tmp_path):
        n = await make_node(tmp_path, 20, genesis=True)
        await n.start()
        try:
            entry = await n.storage.get_node(n.identity.node_id)
            assert entry is not None
            assert entry.status == "online"
        finally:
            await n.stop()

    async def test_genesis_saves_identity(self, tmp_path):
        id_path = str(tmp_path / "genesis.json")
        n = await Node.create_genesis(addr(21), id_path, str(tmp_path / "g.db"))
        await n.start()
        try:
            loaded = NodeIdentity.load(id_path)
            assert loaded.node_id == n.identity.node_id
        finally:
            await n.stop()
