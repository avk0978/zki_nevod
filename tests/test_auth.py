"""Tests for node/auth.py"""

import os
import pytest

from node.auth import make_challenge, make_response, verify_response
from node.crypto import gen_signing, gen_encryption
from node.identity import NodeIdentity
from node.protocol import T, decode_payload


def make_identity(address="localhost:8765"):
    return NodeIdentity.generate(address)


class TestMakeChallenge:
    def test_returns_packet_and_nonce(self):
        pkt, nonce = make_challenge("node_a", "node_b")
        assert pkt.type == T.AUTH_CHALLENGE
        assert len(nonce) == 32

    def test_nonce_in_payload(self):
        pkt, nonce = make_challenge("node_a", "node_b")
        data = decode_payload(pkt.payload)
        assert data["nonce"] == nonce

    def test_unique_nonces(self):
        nonces = {make_challenge("a", "b")[1] for _ in range(50)}
        assert len(nonces) == 50

    def test_from_addr_set(self):
        pkt, _ = make_challenge("my_node", "peer_node")
        assert pkt.from_addr == "my_node"


class TestMakeResponse:
    def test_creates_auth_response(self):
        idt = make_identity()
        nonce = os.urandom(32)
        pkt = make_response(idt.node_id, "peer", nonce, idt.signing, idt.encryption)
        assert pkt.type == T.AUTH_RESPONSE

    def test_response_contains_required_fields(self):
        idt = make_identity()
        nonce = os.urandom(32)
        pkt = make_response(idt.node_id, "peer", nonce, idt.signing, idt.encryption)
        data = decode_payload(pkt.payload)
        assert "nonce" in data
        assert "sig" in data
        assert "signing_pubkey" in data
        assert "enc_pubkey" in data

    def test_signing_pubkey_matches_identity(self):
        idt = make_identity()
        nonce = os.urandom(32)
        pkt = make_response(idt.node_id, "peer", nonce, idt.signing, idt.encryption)
        data = decode_payload(pkt.payload)
        assert data["signing_pubkey"] == idt.signing.public

    def test_enc_pubkey_matches_identity(self):
        idt = make_identity()
        nonce = os.urandom(32)
        pkt = make_response(idt.node_id, "peer", nonce, idt.signing, idt.encryption)
        data = decode_payload(pkt.payload)
        assert data["enc_pubkey"] == idt.encryption.public


class TestVerifyResponse:
    def _make_valid_response(self, idt=None, nonce=None):
        if idt is None:
            idt = make_identity()
        if nonce is None:
            nonce = os.urandom(32)
        pkt = make_response(idt.node_id, "verifier", nonce, idt.signing, idt.encryption)
        return pkt, nonce, idt

    def test_valid_response(self):
        pkt, nonce, idt = self._make_valid_response()
        result = verify_response(pkt, nonce)
        assert result is not None
        assert result.node_id == idt.node_id

    def test_result_contains_enc_pubkey(self):
        pkt, nonce, idt = self._make_valid_response()
        result = verify_response(pkt, nonce)
        assert result.enc_pubkey == idt.encryption.public

    def test_result_contains_signing_pubkey(self):
        pkt, nonce, idt = self._make_valid_response()
        result = verify_response(pkt, nonce)
        assert result.signing_pubkey == idt.signing.public

    def test_wrong_nonce_fails(self):
        pkt, nonce, _ = self._make_valid_response()
        wrong_nonce = bytes(b ^ 1 for b in nonce)
        assert verify_response(pkt, wrong_nonce) is None

    def test_expected_node_id_matches(self):
        pkt, nonce, idt = self._make_valid_response()
        result = verify_response(pkt, nonce, expected_node_id=idt.node_id)
        assert result is not None

    def test_expected_node_id_mismatch_fails(self):
        pkt, nonce, _ = self._make_valid_response()
        fake_node_id = "a" * 64
        assert verify_response(pkt, nonce, expected_node_id=fake_node_id) is None

    def test_tampered_signature_fails(self):
        pkt, nonce, _ = self._make_valid_response()
        data = decode_payload(pkt.payload)
        bad_sig = bytearray(data["sig"])
        bad_sig[0] ^= 0xFF
        data["sig"] = bytes(bad_sig)
        from node.protocol import Packet, encode_payload, T
        bad_pkt = Packet(type=T.AUTH_RESPONSE, payload=encode_payload(data))
        assert verify_response(bad_pkt, nonce) is None

    def test_tampered_signing_pubkey_fails(self):
        pkt, nonce, _ = self._make_valid_response()
        data = decode_payload(pkt.payload)
        data["signing_pubkey"] = gen_signing().public   # different key
        from node.protocol import Packet, encode_payload, T
        bad_pkt = Packet(type=T.AUTH_RESPONSE, payload=encode_payload(data))
        assert verify_response(bad_pkt, nonce) is None

    def test_malformed_payload_returns_none(self):
        from node.protocol import Packet, T
        bad_pkt = Packet(type=T.AUTH_RESPONSE, payload=b"not-msgpack-garbage")
        assert verify_response(bad_pkt, b"\x00" * 32) is None

    def test_missing_fields_returns_none(self):
        from node.protocol import Packet, encode_payload, T
        bad_pkt = Packet(
            type=T.AUTH_RESPONSE,
            payload=encode_payload({"nonce": b"\x00" * 32}),
        )
        assert verify_response(bad_pkt, b"\x00" * 32) is None


class TestMutualAuth:
    def test_both_sides_authenticate(self):
        """Simulate full challenge-response exchange between two identities."""
        a = make_identity("localhost:8001")
        b = make_identity("localhost:8002")

        # A challenges B
        challenge_a, nonce_a = make_challenge(a.node_id, b.node_id)

        # B challenges A
        challenge_b, nonce_b = make_challenge(b.node_id, a.node_id)

        # B responds to A's challenge
        response_b = make_response(b.node_id, a.node_id, nonce_a, b.signing, b.encryption)

        # A responds to B's challenge
        response_a = make_response(a.node_id, b.node_id, nonce_b, a.signing, a.encryption)

        # A verifies B
        result_a = verify_response(response_b, nonce_a, expected_node_id=b.node_id)
        assert result_a is not None
        assert result_a.node_id == b.node_id

        # B verifies A
        result_b = verify_response(response_a, nonce_b, expected_node_id=a.node_id)
        assert result_b is not None
        assert result_b.node_id == a.node_id
