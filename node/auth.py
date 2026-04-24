"""
Node-to-node authentication.

Protocol: challenge-response over Ed25519.
Both nodes authenticate each other (mutual auth) at WebSocket connection start.

  A → B: AUTH_CHALLENGE  { nonce: 32 random bytes }
  B → A: AUTH_RESPONSE   { nonce, sig=Sign(nonce, B.signing), signing_pubkey, enc_pubkey }
  A: verify sig, extract B's keys
  (B does the same simultaneously)

This proves key ownership without revealing the private key.
The node_id claimed by B must match the signing_pubkey in AUTH_RESPONSE.

TODO: replace with strict Schnorr ZKP (interactive, zero-knowledge in formal sense)
      once low-level Edwards25519 scalar ops are available.
"""

import os
from typing import Optional, Tuple

from .crypto import sign, verify, SigningKeypair, EncryptionKeypair
from .protocol import (
    Packet, T,
    make_auth_challenge, make_auth_response,
    encode_payload, decode_payload,
)


NONCE_SIZE = 32


def make_challenge(from_node: str, to_node: str) -> Tuple[Packet, bytes]:
    """Generate AUTH_CHALLENGE packet and the nonce to verify against."""
    nonce = os.urandom(NONCE_SIZE)
    pkt = make_auth_challenge(from_node, to_node, nonce)
    return pkt, nonce


def make_response(from_node: str, to_node: str, nonce: bytes,
                  signing: SigningKeypair, enc: EncryptionKeypair) -> Packet:
    """Sign the nonce and return AUTH_RESPONSE packet."""
    signature = sign(nonce, signing)
    return make_auth_response(
        from_node=from_node,
        to_node=to_node,
        nonce=nonce,
        signature=signature,
        signing_pubkey=signing.public,
        enc_pubkey=enc.public,
    )


class AuthResult:
    def __init__(self, node_id: str, signing_pubkey: bytes, enc_pubkey: bytes):
        self.node_id = node_id
        self.signing_pubkey = signing_pubkey
        self.enc_pubkey = enc_pubkey


def verify_response(response: Packet, expected_nonce: bytes,
                    expected_node_id: Optional[str] = None) -> Optional[AuthResult]:
    """
    Verify AUTH_RESPONSE.
    Returns AuthResult on success, None on failure.
    expected_node_id: if known, checks that claimed identity matches.
    """
    try:
        data = decode_payload(response.payload)
        nonce:          bytes = data["nonce"]
        sig:            bytes = data["sig"]
        signing_pubkey: bytes = data["signing_pubkey"]
        enc_pubkey:     bytes = data["enc_pubkey"]
    except (KeyError, Exception):
        return None

    if nonce != expected_nonce:
        return None

    node_id_claim = signing_pubkey.hex()
    if expected_node_id and node_id_claim != expected_node_id:
        return None

    if not verify(nonce, sig, signing_pubkey):
        return None

    return AuthResult(
        node_id=node_id_claim,
        signing_pubkey=signing_pubkey,
        enc_pubkey=enc_pubkey,
    )
