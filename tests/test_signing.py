"""
Tests for packet signing and verification.

Covers:
- sign_packet / verify_packet in protocol.py
- Transport signs all outgoing packets automatically
- Transport drops packets with invalid signatures
- Transport drops packets with missing signatures
"""

import asyncio
import pytest

from node.protocol import Packet, T, sign_packet, verify_packet, pack, unpack
from node.crypto import gen_signing, gen_encryption
from node.identity import NodeIdentity
from node.transport import Transport, PeerConnection


BASE_PORT = 19500


def addr(offset: int) -> str:
    return f"127.0.0.1:{BASE_PORT + offset}"


# ─── unit: sign_packet / verify_packet ────────────────────────────────────────

class TestSignPacket:
    def test_sign_sets_sig_field(self):
        kp  = gen_signing()
        pkt = Packet(type=T.PING, payload=b"")
        assert pkt.sig == b""
        sign_packet(pkt, kp)
        assert len(pkt.sig) == 64

    def test_sign_returns_same_packet(self):
        kp  = gen_signing()
        pkt = Packet(type=T.PING, payload=b"")
        result = sign_packet(pkt, kp)
        assert result is pkt

    def test_verify_signed_packet(self):
        kp  = gen_signing()
        pkt = Packet(type=T.MSG, payload=b"hello", from_addr="a", to_addr="b")
        sign_packet(pkt, kp)
        assert verify_packet(pkt, kp.public)

    def test_verify_wrong_key_fails(self):
        kp1 = gen_signing()
        kp2 = gen_signing()
        pkt = Packet(type=T.MSG, payload=b"hello")
        sign_packet(pkt, kp1)
        assert not verify_packet(pkt, kp2.public)

    def test_verify_unsigned_packet_fails(self):
        kp  = gen_signing()
        pkt = Packet(type=T.PING, payload=b"")
        assert not verify_packet(pkt, kp.public)

    def test_verify_tampered_payload_fails(self):
        kp  = gen_signing()
        pkt = Packet(type=T.MSG, payload=b"original")
        sign_packet(pkt, kp)
        pkt.payload = b"tampered"
        assert not verify_packet(pkt, kp.public)

    def test_verify_tampered_from_addr_fails(self):
        kp  = gen_signing()
        pkt = Packet(type=T.MSG, payload=b"x", from_addr="alice")
        sign_packet(pkt, kp)
        pkt.from_addr = "mallory"
        assert not verify_packet(pkt, kp.public)

    def test_verify_tampered_type_fails(self):
        kp  = gen_signing()
        pkt = Packet(type=T.PING, payload=b"")
        sign_packet(pkt, kp)
        pkt.type = T.PONG
        assert not verify_packet(pkt, kp.public)

    def test_sign_preserves_all_other_fields(self):
        kp  = gen_signing()
        pkt = Packet(type=T.MSG, payload=b"data", from_addr="a@n1",
                     to_addr="b@n2", ts=1_700_000_000)
        sign_packet(pkt, kp)
        assert pkt.type       == T.MSG
        assert pkt.payload    == b"data"
        assert pkt.from_addr  == "a@n1"
        assert pkt.to_addr    == "b@n2"
        assert pkt.ts         == 1_700_000_000

    def test_sign_survives_pack_unpack(self):
        kp  = gen_signing()
        pkt = Packet(type=T.MSG, payload=b"wire test", from_addr="n1")
        sign_packet(pkt, kp)
        restored = unpack(pack(pkt))
        assert verify_packet(restored, kp.public)

    def test_different_packets_different_sigs(self):
        kp = gen_signing()
        p1 = Packet(type=T.MSG, payload=b"one")
        p2 = Packet(type=T.MSG, payload=b"two")
        sign_packet(p1, kp)
        sign_packet(p2, kp)
        assert p1.sig != p2.sig


# ─── integration: Transport signs and verifies ────────────────────────────────

async def make_transport(offset: int) -> Transport:
    idt = NodeIdentity.generate(addr(offset))
    received: list[Packet] = []

    async def on_packet(pkt, conn):
        received.append(pkt)

    t = Transport(idt, on_packet=on_packet)
    t._received = received
    return t


class TestTransportSigning:
    async def test_send_to_signs_packet(self, tmp_path):
        """Packet arriving at peer must have a valid signature."""
        from node.node import Node

        n1 = await Node.create_genesis(
            addr(0), str(tmp_path / "n1.json"), str(tmp_path / "n1.db")
        )
        n2 = await Node.create_genesis(
            addr(1), str(tmp_path / "n2.json"), str(tmp_path / "n2.db")
        )

        await n1.start()
        await n2.start()

        # Wrap transport.on_packet AFTER start so _recv_loop picks it up next time
        received = []
        original_on_packet = n2.transport.on_packet

        async def capturing_on_packet(pkt, conn):
            received.append((pkt, conn.peer_signing_pubkey))
            await original_on_packet(pkt, conn)

        n2.transport.on_packet = capturing_on_packet

        try:
            await n2.join(addr(0))
            await asyncio.sleep(0.2)

            pkt = Packet(
                type=T.PING,
                payload=b"",
                from_addr=n1.identity.node_id,
                to_addr=n2.identity.node_id,
            )
            await n1.transport.send_to(n2.identity.node_id, pkt)
            await asyncio.sleep(0.2)

            assert len(received) >= 1
            arrived_pkt, peer_signing_pub = received[-1]
            assert verify_packet(arrived_pkt, peer_signing_pub)
            assert arrived_pkt.sig != b""
        finally:
            await n1.stop()
            await n2.stop()

    async def test_unsigned_packet_dropped(self, tmp_path):
        """A packet sent without a signature must be silently dropped."""
        from node.node import Node

        n1 = await Node.create_genesis(
            addr(2), str(tmp_path / "n1.json"), str(tmp_path / "n1.db")
        )
        n2 = await Node.create_genesis(
            addr(3), str(tmp_path / "n2.json"), str(tmp_path / "n2.db")
        )

        received = []
        original_dispatch = n2._dispatch

        async def counting_dispatch(pkt, conn):
            received.append(pkt)
            await original_dispatch(pkt, conn)

        n2._dispatch = counting_dispatch

        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(2))
            await asyncio.sleep(0.2)

            conn = await n2.transport.connections.get(n1.identity.node_id)
            assert conn is not None

            count_before = len(received)

            # send raw unsigned packet (bypass Transport.send_via)
            unsigned = Packet(
                type=T.PING,
                payload=b"",
                from_addr=n1.identity.node_id,
                to_addr=n2.identity.node_id,
            )
            await conn.ws.send(pack(unsigned))
            await asyncio.sleep(0.2)

            # dispatcher must NOT have been called for the unsigned packet
            assert len(received) == count_before
        finally:
            await n1.stop()
            await n2.stop()

    async def test_wrong_signature_dropped(self, tmp_path):
        """A packet signed with a different key must be dropped."""
        from node.node import Node

        n1 = await Node.create_genesis(
            addr(4), str(tmp_path / "n1.json"), str(tmp_path / "n1.db")
        )
        n2 = await Node.create_genesis(
            addr(5), str(tmp_path / "n2.json"), str(tmp_path / "n2.db")
        )

        received = []
        original_dispatch = n2._dispatch

        async def counting_dispatch(pkt, conn):
            received.append(pkt)
            await original_dispatch(pkt, conn)

        n2._dispatch = counting_dispatch

        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(4))
            await asyncio.sleep(0.2)

            conn = await n2.transport.connections.get(n1.identity.node_id)
            assert conn is not None

            count_before = len(received)

            # sign with a random key (not n1's key)
            impostor_kp = gen_signing()
            bad_pkt = Packet(
                type=T.PING,
                payload=b"",
                from_addr=n1.identity.node_id,
                to_addr=n2.identity.node_id,
            )
            sign_packet(bad_pkt, impostor_kp)
            await conn.ws.send(pack(bad_pkt))
            await asyncio.sleep(0.2)

            assert len(received) == count_before
        finally:
            await n1.stop()
            await n2.stop()

    async def test_peer_signing_pubkey_stored_on_connection(self, tmp_path):
        """After auth, PeerConnection must store the peer's signing pubkey."""
        from node.node import Node

        n1 = await Node.create_genesis(
            addr(6), str(tmp_path / "n1.json"), str(tmp_path / "n1.db")
        )
        n2 = await Node.create_genesis(
            addr(7), str(tmp_path / "n2.json"), str(tmp_path / "n2.db")
        )
        await n1.start()
        await n2.start()
        try:
            await n2.join(addr(6))
            await asyncio.sleep(0.2)

            conn_at_n2 = await n2.transport.connections.get(n1.identity.node_id)
            assert conn_at_n2 is not None
            assert conn_at_n2.peer_signing_pubkey == n1.identity.signing.public

            conn_at_n1 = await n1.transport.connections.get(n2.identity.node_id)
            assert conn_at_n1 is not None
            assert conn_at_n1.peer_signing_pubkey == n2.identity.signing.public
        finally:
            await n1.stop()
            await n2.stop()
