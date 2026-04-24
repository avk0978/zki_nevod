"""
End-to-end tests for CellClient.

Covers:
- Cell connects to node (mutual auth + CELL_REGISTER)
- cell.connected property
- Cell entry and presence set in node storage after connect
- Two cells on same node exchange E2E encrypted messages
- Buffered messages delivered when cell comes online
- Invalid / unsigned node packets dropped by cell
- Two cells on different nodes communicate via inter-node routing
"""

import asyncio
import time

import pytest

from node.client import CellClient
from node.crypto import gen_signing
from node.identity import CellIdentity
from node.node import Node
from node.protocol import Packet, T, encode_payload, pack, sign_packet
from node.storage import NodeEntry


BASE_PORT = 19700


def addr(offset: int) -> str:
    return f"127.0.0.1:{BASE_PORT + offset}"


async def make_node(tmp_path, offset: int) -> Node:
    return await Node.create_genesis(
        addr(offset),
        str(tmp_path / f"n{offset}.json"),
        str(tmp_path / f"n{offset}.db"),
    )


# ─── connect / disconnect ─────────────────────────────────────────────────────

class TestCellConnect:
    async def test_connected_after_connect(self, tmp_path):
        node = await make_node(tmp_path, 0)
        await node.start()
        cell = CellClient(CellIdentity.generate("Alice"))
        try:
            assert not cell.connected
            await cell.connect(addr(0))
            assert cell.connected
        finally:
            await cell.disconnect()
            await node.stop()

    async def test_not_connected_after_disconnect(self, tmp_path):
        node = await make_node(tmp_path, 1)
        await node.start()
        cell = CellClient(CellIdentity.generate("Bob"))
        try:
            await cell.connect(addr(1))
            assert cell.connected
            await cell.disconnect()
            assert not cell.connected
        finally:
            await node.stop()

    async def test_cell_registered_in_storage(self, tmp_path):
        node = await make_node(tmp_path, 2)
        await node.start()
        idt = CellIdentity.generate("Carol")
        cell = CellClient(idt)
        try:
            await cell.connect(addr(2))
            await asyncio.sleep(0.1)

            entry = await node.storage.get_cell(idt.cell_id)
            assert entry is not None
            assert entry.signing_pubkey == idt.signing.public
            assert entry.enc_pubkey == idt.encryption.public
        finally:
            await cell.disconnect()
            await node.stop()

    async def test_presence_set_after_connect(self, tmp_path):
        node = await make_node(tmp_path, 3)
        await node.start()
        idt = CellIdentity.generate("Dave")
        cell = CellClient(idt)
        try:
            await cell.connect(addr(3))
            await asyncio.sleep(0.1)

            presence = await node.storage.get_presence(idt.cell_id)
            assert presence is not None
            assert presence.home_node_id == node.identity.node_id
        finally:
            await cell.disconnect()
            await node.stop()

    async def test_node_registry_has_cell_connection(self, tmp_path):
        """ConnectionRegistry must contain the cell entry after CELL_REGISTER."""
        node = await make_node(tmp_path, 4)
        await node.start()
        idt = CellIdentity.generate("Eve")
        cell = CellClient(idt)
        try:
            await cell.connect(addr(4))
            await asyncio.sleep(0.1)

            conn = await node.transport.connections.get(idt.cell_id)
            assert conn is not None
            assert conn.peer_node_id == idt.cell_id
            assert conn.peer_signing_pubkey == idt.signing.public
        finally:
            await cell.disconnect()
            await node.stop()


# ─── E2E messaging on same node ──────────────────────────────────────────────

class TestCellMessaging:
    async def test_two_cells_same_node(self, tmp_path):
        """Cell A encrypts message → node routes → Cell B decrypts correctly."""
        node = await make_node(tmp_path, 10)
        await node.start()

        idt_a = CellIdentity.generate("Alice")
        idt_b = CellIdentity.generate("Bob")

        received: list = []

        async def on_b(from_addr: str, plaintext: bytes):
            received.append((from_addr, plaintext))

        cell_a = CellClient(idt_a)
        cell_b = CellClient(idt_b, on_message=on_b)
        try:
            await cell_a.connect(addr(10))
            await cell_b.connect(addr(10))
            await asyncio.sleep(0.1)

            await cell_a.send(
                to_cell_id=idt_b.cell_id,
                to_node_id=node.identity.node_id,
                recipient_enc_pubkey=idt_b.encryption.public,
                plaintext=b"hello from alice",
            )
            await asyncio.sleep(0.2)

            assert len(received) == 1
            assert received[0][1] == b"hello from alice"
        finally:
            await cell_a.disconnect()
            await cell_b.disconnect()
            await node.stop()

    async def test_from_addr_correct(self, tmp_path):
        """on_message from_addr must be 'cell_a@node_id'."""
        node = await make_node(tmp_path, 11)
        await node.start()

        idt_a = CellIdentity.generate("Alice")
        idt_b = CellIdentity.generate("Bob")
        received_from: list = []

        async def on_b(from_addr: str, plaintext: bytes):
            received_from.append(from_addr)

        cell_a = CellClient(idt_a)
        cell_b = CellClient(idt_b, on_message=on_b)
        try:
            await cell_a.connect(addr(11))
            await cell_b.connect(addr(11))
            await asyncio.sleep(0.1)

            await cell_a.send(
                idt_b.cell_id, node.identity.node_id,
                idt_b.encryption.public, b"ping",
            )
            await asyncio.sleep(0.2)

            assert len(received_from) == 1
            assert received_from[0] == f"{idt_a.cell_id}@{node.identity.node_id}"
        finally:
            await cell_a.disconnect()
            await cell_b.disconnect()
            await node.stop()

    async def test_message_not_delivered_to_wrong_cell(self, tmp_path):
        """A message addressed to Cell B must not reach Cell C."""
        node = await make_node(tmp_path, 12)
        await node.start()

        idt_a = CellIdentity.generate("Alice")
        idt_b = CellIdentity.generate("Bob")
        idt_c = CellIdentity.generate("Charlie")

        received_c: list = []

        async def on_c(from_addr, pt):
            received_c.append(pt)

        cell_a = CellClient(idt_a)
        cell_b = CellClient(idt_b)
        cell_c = CellClient(idt_c, on_message=on_c)
        try:
            await cell_a.connect(addr(12))
            await cell_b.connect(addr(12))
            await cell_c.connect(addr(12))
            await asyncio.sleep(0.1)

            await cell_a.send(
                idt_b.cell_id, node.identity.node_id,
                idt_b.encryption.public, b"only for bob",
            )
            await asyncio.sleep(0.2)

            assert len(received_c) == 0
        finally:
            await cell_a.disconnect()
            await cell_b.disconnect()
            await cell_c.disconnect()
            await node.stop()

    async def test_multiple_messages_delivered_in_order(self, tmp_path):
        node = await make_node(tmp_path, 13)
        await node.start()

        idt_a = CellIdentity.generate("Alice")
        idt_b = CellIdentity.generate("Bob")
        received: list = []

        async def on_b(from_addr, pt):
            received.append(pt)

        cell_a = CellClient(idt_a)
        cell_b = CellClient(idt_b, on_message=on_b)
        try:
            await cell_a.connect(addr(13))
            await cell_b.connect(addr(13))
            await asyncio.sleep(0.1)

            for i in range(5):
                await cell_a.send(
                    idt_b.cell_id, node.identity.node_id,
                    idt_b.encryption.public, f"msg{i}".encode(),
                )
            await asyncio.sleep(0.4)

            assert len(received) == 5
            assert received == [f"msg{i}".encode() for i in range(5)]
        finally:
            await cell_a.disconnect()
            await cell_b.disconnect()
            await node.stop()


# ─── buffered messages ────────────────────────────────────────────────────────

class TestCellBuffered:
    async def test_buffered_message_delivered_on_connect(self, tmp_path):
        """
        Message sent while cell is offline is buffered.
        Cell receives it when it connects later.
        """
        node = await make_node(tmp_path, 20)
        await node.start()

        idt_b = CellIdentity.generate("Bob")

        # Register cell so send_message can find its enc_pubkey
        await node.storage.register_cell(
            idt_b.cell_id, idt_b.signing.public, idt_b.encryption.public, is_home=True
        )
        # Point presence to an offline node → message will be buffered
        await node.storage.update_presence(
            idt_b.cell_id,
            home_node_id="ghost_node_id",
            visiting_node_id=None,
        )
        await node.storage.upsert_node(NodeEntry(
            node_id="ghost_node_id",
            address="1.2.3.4:9999",
            status="offline",
            last_seen=int(time.time()) - 1000,
            added_at=int(time.time()),
        ))

        await node.send_message(
            f"{idt_b.cell_id}@ghost_node_id", b"buffered hello"
        )

        buffered = await node.storage.get_buffered(idt_b.cell_id)
        assert len(buffered) == 1

        # Cell connects → CELL_REGISTER → flush_buffer → delivered
        received: list = []

        async def on_b(from_addr, pt):
            received.append(pt)

        cell_b = CellClient(idt_b, on_message=on_b)
        try:
            await cell_b.connect(addr(20))
            await asyncio.sleep(0.3)

            assert len(received) == 1
            assert received[0] == b"buffered hello"

            leftover = await node.storage.get_buffered(idt_b.cell_id)
            assert len(leftover) == 0
        finally:
            await cell_b.disconnect()
            await node.stop()


# ─── security ─────────────────────────────────────────────────────────────────

class TestCellSecurity:
    async def test_invalid_node_sig_dropped(self, tmp_path):
        """
        A MSG packet injected with the wrong signing key must be silently dropped.
        Cell's on_message must not be called.
        """
        node = await make_node(tmp_path, 30)
        await node.start()

        idt = CellIdentity.generate("Alice")
        received: list = []

        async def on_msg(from_addr, pt):
            received.append(pt)

        cell = CellClient(idt, on_message=on_msg)
        try:
            await cell.connect(addr(30))
            await asyncio.sleep(0.1)

            # Get server-side connection handle so we can inject raw bytes
            cell_conn = await node.transport.connections.get(idt.cell_id)
            assert cell_conn is not None

            count_before = len(received)

            impostor_kp = gen_signing()
            bad_pkt = Packet(
                type=T.MSG,
                payload=encode_payload({
                    "ephemeral_pubkey": bytes(32),
                    "nonce":            bytes(12),
                    "ciphertext":       b"fake",
                }),
                from_addr="impostor",
                to_addr=f"{idt.cell_id}@{node.identity.node_id}",
            )
            sign_packet(bad_pkt, impostor_kp)

            # Send directly via server-side WebSocket, bypassing Transport.send_via
            await cell_conn.ws.send(pack(bad_pkt))
            await asyncio.sleep(0.2)

            assert len(received) == count_before
        finally:
            await cell.disconnect()
            await node.stop()

    async def test_unsigned_msg_dropped(self, tmp_path):
        """An unsigned MSG packet injected from the node side must be dropped."""
        node = await make_node(tmp_path, 31)
        await node.start()

        idt = CellIdentity.generate("Alice")
        received: list = []

        async def on_msg(from_addr, pt):
            received.append(pt)

        cell = CellClient(idt, on_message=on_msg)
        try:
            await cell.connect(addr(31))
            await asyncio.sleep(0.1)

            cell_conn = await node.transport.connections.get(idt.cell_id)
            assert cell_conn is not None

            count_before = len(received)

            unsigned_pkt = Packet(
                type=T.MSG,
                payload=encode_payload({
                    "ephemeral_pubkey": bytes(32),
                    "nonce":            bytes(12),
                    "ciphertext":       b"unsigned",
                }),
                from_addr=node.identity.node_id,
                to_addr=f"{idt.cell_id}@{node.identity.node_id}",
            )
            # No sign_packet call
            await cell_conn.ws.send(pack(unsigned_pkt))
            await asyncio.sleep(0.2)

            assert len(received) == count_before
        finally:
            await cell.disconnect()
            await node.stop()


# ─── inter-node routing ───────────────────────────────────────────────────────

class TestTwoNodeMessaging:
    async def test_cells_on_different_nodes(self, tmp_path):
        """
        Cell A on Node 1 sends to Cell B on Node 2.
        Message is forwarded via the inter-node connection and E2E decrypted by B.
        """
        n1 = await make_node(tmp_path, 40)
        n2 = await make_node(tmp_path, 41)
        await n1.start()
        await n2.start()

        idt_a = CellIdentity.generate("Alice")
        idt_b = CellIdentity.generate("Bob")
        received: list = []

        async def on_b(from_addr, pt):
            received.append((from_addr, pt))

        cell_a = CellClient(idt_a)
        cell_b = CellClient(idt_b, on_message=on_b)
        try:
            # Establish inter-node connection (n2 joins n1)
            await n2.join(addr(40))
            await asyncio.sleep(0.2)

            # Connect cells to their respective nodes
            await cell_a.connect(addr(40))
            await cell_b.connect(addr(41))
            await asyncio.sleep(0.1)

            # Tell n1 where cell_b lives (in production, gossip propagates this)
            await n1.storage.update_presence(
                idt_b.cell_id,
                home_node_id=n2.identity.node_id,
            )

            await cell_a.send(
                to_cell_id=idt_b.cell_id,
                to_node_id=n2.identity.node_id,
                recipient_enc_pubkey=idt_b.encryption.public,
                plaintext=b"cross-node hello",
            )
            await asyncio.sleep(0.3)

            assert len(received) == 1
            _, plaintext = received[0]
            assert plaintext == b"cross-node hello"
        finally:
            await cell_a.disconnect()
            await cell_b.disconnect()
            await n1.stop()
            await n2.stop()
