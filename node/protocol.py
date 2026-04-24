"""
Nevod wire protocol.

Transport: WebSocket over TLS
Serialization: MessagePack

Packet format:
  v       — protocol version (int)
  id      — UUID v4 (str)
  type    — message type (str)
  from    — "cell_id@node_id" or "node_id" (str)
  to      — "cell_id@node_id" or "node_id" (str)
  payload — content (bytes, encrypted or plaintext depending on type)
  sig     — Ed25519 signature over (id+type+from+to+payload+ts) (bytes)
  ts      — unix timestamp (int)
"""

import uuid
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional

import msgpack


PROTO_VERSION = 1


class T:
    """Message types."""
    MSG              = "msg"
    ACK              = "ack"
    PING             = "ping"
    PONG             = "pong"
    GOSSIP           = "gossip"
    NODE_REGISTER    = "node_register"
    NODE_VOTE        = "node_vote"
    NODE_CERT        = "node_cert"
    NODE_REMOVE      = "node_remove"
    NODE_LEAVING     = "node_leaving"
    PRESENCE_QUERY   = "presence_query"
    PRESENCE_RESPONSE = "presence_response"
    CELL_REGISTER    = "cell_register"
    CELL_INVITE      = "cell_invite"
    AUTH_CHALLENGE   = "auth_challenge"
    AUTH_RESPONSE    = "auth_response"


@dataclass
class Packet:
    type: str
    payload: bytes
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_addr: str = ""
    to_addr: str = ""
    sig: bytes = b""
    ts: int = field(default_factory=lambda: int(time.time()))
    v: int = PROTO_VERSION

    def sign_data(self) -> bytes:
        """Canonical bytes to sign: id + type + from + to + payload + ts."""
        return (
            self.id.encode()
            + self.type.encode()
            + self.from_addr.encode()
            + self.to_addr.encode()
            + self.payload
            + str(self.ts).encode()
        )


def pack(packet: Packet) -> bytes:
    return msgpack.packb(
        {
            "v": packet.v,
            "id": packet.id,
            "type": packet.type,
            "from": packet.from_addr,
            "to": packet.to_addr,
            "payload": packet.payload,
            "sig": packet.sig,
            "ts": packet.ts,
        },
        use_bin_type=True,
    )


def unpack(data: bytes) -> Packet:
    d = msgpack.unpackb(data, raw=False)
    return Packet(
        v=d.get("v", PROTO_VERSION),
        id=d.get("id", ""),
        type=d.get("type", ""),
        from_addr=d.get("from", ""),
        to_addr=d.get("to", ""),
        payload=d.get("payload", b"") or b"",
        sig=d.get("sig", b"") or b"",
        ts=d.get("ts", 0),
    )


# --- Payload helpers (msgpack encode/decode dicts into payload bytes) ---

def encode_payload(data: dict) -> bytes:
    return msgpack.packb(data, use_bin_type=True)


def decode_payload(payload: bytes) -> dict:
    return msgpack.unpackb(payload, raw=False)


# --- Specific packet constructors ---

def make_ping(from_node: str, to_node: str) -> Packet:
    return Packet(type=T.PING, payload=b"", from_addr=from_node, to_addr=to_node)


def make_pong(from_node: str, to_node: str, ping_id: str) -> Packet:
    return Packet(
        type=T.PONG,
        payload=encode_payload({"ping_id": ping_id}),
        from_addr=from_node,
        to_addr=to_node,
    )


def make_gossip(from_node: str, node_table_entries: list) -> Packet:
    return Packet(
        type=T.GOSSIP,
        payload=encode_payload({"nodes": node_table_entries}),
        from_addr=from_node,
    )


def make_auth_challenge(from_node: str, to_node: str, nonce: bytes) -> Packet:
    return Packet(
        type=T.AUTH_CHALLENGE,
        payload=encode_payload({"nonce": nonce}),
        from_addr=from_node,
        to_addr=to_node,
    )


def make_auth_response(from_node: str, to_node: str,
                       nonce: bytes, signature: bytes,
                       signing_pubkey: bytes, enc_pubkey: bytes) -> Packet:
    return Packet(
        type=T.AUTH_RESPONSE,
        payload=encode_payload({
            "nonce": nonce,
            "sig": signature,
            "signing_pubkey": signing_pubkey,
            "enc_pubkey": enc_pubkey,
        }),
        from_addr=from_node,
        to_addr=to_node,
    )
