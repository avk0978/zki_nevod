"""Tests for node/protocol.py"""

import pytest

from node.protocol import (
    Packet, T,
    pack, unpack,
    encode_payload, decode_payload,
    make_ping, make_pong, make_gossip,
    make_auth_challenge, make_auth_response,
)


class TestPackUnpack:
    def test_roundtrip_all_fields(self):
        pkt = Packet(
            type=T.MSG,
            payload=b"encrypted-blob",
            from_addr="aabb@node1",
            to_addr="ccdd@node2",
            sig=b"\x01\x02\x03",
            ts=1_700_000_000,
        )
        raw = pack(pkt)
        restored = unpack(raw)

        assert restored.type == pkt.type
        assert restored.payload == pkt.payload
        assert restored.from_addr == pkt.from_addr
        assert restored.to_addr == pkt.to_addr
        assert restored.sig == pkt.sig
        assert restored.ts == pkt.ts
        assert restored.id == pkt.id
        assert restored.v == 1

    def test_empty_payload(self):
        pkt = Packet(type=T.PING, payload=b"")
        raw = pack(pkt)
        restored = unpack(raw)
        assert restored.payload == b""

    def test_binary_payload_preserved(self):
        payload = bytes(range(256))
        pkt = Packet(type=T.MSG, payload=payload)
        assert unpack(pack(pkt)).payload == payload

    def test_unique_ids(self):
        ids = {Packet(type=T.PING, payload=b"").id for _ in range(100)}
        assert len(ids) == 100

    def test_timestamp_auto_set(self):
        import time
        before = int(time.time())
        pkt = Packet(type=T.PING, payload=b"")
        after = int(time.time())
        assert before <= pkt.ts <= after

    def test_pack_produces_bytes(self):
        pkt = Packet(type=T.PING, payload=b"")
        assert isinstance(pack(pkt), bytes)

    def test_compact_size(self):
        pkt = make_ping("a" * 64, "b" * 64)
        assert len(pack(pkt)) < 300


class TestPayloadHelpers:
    def test_encode_decode_dict(self):
        data = {"key": "value", "num": 42, "bytes": b"\x00\xff"}
        assert decode_payload(encode_payload(data)) == data

    def test_nested_dict(self):
        data = {"outer": {"inner": [1, 2, 3]}}
        assert decode_payload(encode_payload(data)) == data

    def test_empty_dict(self):
        assert decode_payload(encode_payload({})) == {}


class TestPacketConstructors:
    def test_make_ping(self):
        pkt = make_ping("node_a", "node_b")
        assert pkt.type == T.PING
        assert pkt.from_addr == "node_a"
        assert pkt.to_addr == "node_b"
        assert pkt.payload == b""

    def test_make_pong(self):
        pkt = make_pong("node_b", "node_a", ping_id="ping-123")
        assert pkt.type == T.PONG
        data = decode_payload(pkt.payload)
        assert data["ping_id"] == "ping-123"

    def test_make_gossip(self):
        entries = [{"node_id": "aabb", "address": "1.2.3.4:8765"}]
        pkt = make_gossip("node_a", entries)
        assert pkt.type == T.GOSSIP
        data = decode_payload(pkt.payload)
        assert data["nodes"] == entries

    def test_make_auth_challenge(self):
        nonce = b"\x01" * 32
        pkt = make_auth_challenge("node_a", "node_b", nonce)
        assert pkt.type == T.AUTH_CHALLENGE
        data = decode_payload(pkt.payload)
        assert data["nonce"] == nonce

    def test_make_auth_response(self):
        nonce = b"\x02" * 32
        sig = b"\x03" * 64
        signing_pub = b"\x04" * 32
        enc_pub = b"\x05" * 32
        pkt = make_auth_response("node_b", "node_a", nonce, sig, signing_pub, enc_pub)
        assert pkt.type == T.AUTH_RESPONSE
        data = decode_payload(pkt.payload)
        assert data["nonce"] == nonce
        assert data["sig"] == sig
        assert data["signing_pubkey"] == signing_pub
        assert data["enc_pubkey"] == enc_pub


class TestSignData:
    def test_sign_data_changes_with_payload(self):
        p1 = Packet(type=T.MSG, payload=b"one", id="same-id", ts=1000)
        p2 = Packet(type=T.MSG, payload=b"two", id="same-id", ts=1000)
        assert p1.sign_data() != p2.sign_data()

    def test_sign_data_changes_with_type(self):
        p1 = Packet(type=T.MSG, payload=b"x", id="same-id", ts=1000)
        p2 = Packet(type=T.ACK, payload=b"x", id="same-id", ts=1000)
        assert p1.sign_data() != p2.sign_data()

    def test_sign_data_is_bytes(self):
        pkt = Packet(type=T.PING, payload=b"")
        assert isinstance(pkt.sign_data(), bytes)
