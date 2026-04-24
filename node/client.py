"""
Cell client — connects a cell (user or AI agent) to a Nevod node.

Flow:
  1. WebSocket connect to node
  2. Mutual challenge-response auth (same as node-to-node)
  3. Send CELL_REGISTER (cell_id + signing_pubkey + enc_pubkey)
  4. Ready: send E2E encrypted messages, receive and decrypt incoming

Usage:
    cell = CellClient(identity, on_message=handler)
    await cell.connect("127.0.0.1:8765")
    await cell.send(to_cell_id, to_node_id, recipient_enc_pubkey, b"hello")
    ...
    await cell.disconnect()
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

import websockets
from websockets.protocol import State as _WSState
from websockets.exceptions import ConnectionClosed

from .identity import CellIdentity
from .protocol import (
    Packet, T, pack, unpack,
    sign_packet, verify_packet,
    encode_payload, decode_payload,
)
from .auth import make_challenge, make_response, verify_response
from .crypto import encrypt, decrypt

log = logging.getLogger(__name__)

# on_message(from_addr: str, plaintext: bytes)
MessageCallback = Callable[[str, bytes], Awaitable[None]]


class CellClient:
    def __init__(self, identity: CellIdentity,
                 on_message: Optional[MessageCallback] = None):
        self.identity = identity
        self.on_message = on_message
        self._ws = None
        self._node_id: str = ""
        self._node_signing_pubkey: bytes = b""
        self._recv_task: Optional[asyncio.Task] = None

    @property
    def cell_id(self) -> str:
        return self.identity.cell_id

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.state == _WSState.OPEN

    async def connect(self, address: str,
                      expected_node_id: Optional[str] = None):
        """Connect to node, authenticate, register cell."""
        ws = await websockets.connect(f"ws://{address}")

        node_signing_pub, _node_enc_pub = await _do_auth(
            ws, self.identity, expected_node_id
        )
        self._node_id             = node_signing_pub.hex()
        self._node_signing_pubkey = node_signing_pub
        self._ws = ws

        # Register this cell on the node
        reg = Packet(
            type=T.CELL_REGISTER,
            payload=encode_payload({
                "cell_id":        self.cell_id,
                "signing_pubkey": self.identity.signing.public,
                "enc_pubkey":     self.identity.encryption.public,
                "is_home":        True,
            }),
            from_addr=self.cell_id,
            to_addr=self._node_id,
        )
        sign_packet(reg, self.identity.signing)
        await ws.send(pack(reg))

        self._recv_task = asyncio.create_task(
            self._recv_loop(), name=f"cell-recv-{self.cell_id[:8]}"
        )
        log.info("cell %s registered on node %s", self.cell_id[:8], self._node_id[:8])

    async def disconnect(self):
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, to_cell_id: str, to_node_id: str,
                   recipient_enc_pubkey: bytes, plaintext: bytes):
        """E2E encrypt plaintext and send to recipient cell."""
        if not self.connected:
            raise RuntimeError("CellClient: not connected")

        enc = encrypt(plaintext, recipient_enc_pubkey)
        pkt = Packet(
            type=T.MSG,
            payload=encode_payload({
                "ephemeral_pubkey": enc["ephemeral_pubkey"],
                "nonce":            enc["nonce"],
                "ciphertext":       enc["ciphertext"],
            }),
            from_addr=f"{self.cell_id}@{self._node_id}",
            to_addr=f"{to_cell_id}@{to_node_id}",
        )
        sign_packet(pkt, self.identity.signing)
        await self._ws.send(pack(pkt))

    # --- internal ---

    async def _recv_loop(self):
        try:
            async for raw in self._ws:
                pkt = unpack(raw)
                if not verify_packet(pkt, self._node_signing_pubkey):
                    log.warning("cell: dropped packet with invalid sig from node %s",
                                self._node_id[:8])
                    continue
                await self._dispatch(pkt)
        except ConnectionClosed:
            log.info("cell %s: connection to node closed", self.cell_id[:8])
        except Exception as e:
            log.error("cell %s recv loop error: %s", self.cell_id[:8], e)
        finally:
            self._ws = None

    async def _dispatch(self, pkt: Packet):
        if pkt.type == T.MSG:
            await self._handle_msg(pkt)
        else:
            log.debug("cell: unhandled packet type %s", pkt.type)

    async def _handle_msg(self, pkt: Packet):
        try:
            data = decode_payload(pkt.payload)
            plaintext = decrypt(
                bytes(data["ciphertext"]),
                bytes(data["nonce"]),
                bytes(data["ephemeral_pubkey"]),
                self.identity.encryption,
            )
        except Exception as e:
            log.warning("cell: failed to decrypt message from %s: %s",
                        pkt.from_addr[:16], e)
            return

        if self.on_message:
            await self.on_message(pkt.from_addr, plaintext)


# ─── shared auth helper ───────────────────────────────────────────────────────

async def _do_auth(ws, identity, expected_peer_id: Optional[str]):
    """
    Mutual challenge-response auth.
    Works for both NodeIdentity and CellIdentity — both have .signing and .encryption.
    Returns (peer_signing_pubkey, peer_enc_pubkey).
    """
    our_id = (
        identity.node_id if hasattr(identity, "node_id") else identity.cell_id
    )

    challenge, nonce = make_challenge(our_id, expected_peer_id or "")
    await ws.send(pack(challenge))

    their_challenge = unpack(await ws.recv())
    if their_challenge.type != T.AUTH_CHALLENGE:
        raise ValueError(f"expected AUTH_CHALLENGE, got {their_challenge.type}")
    their_nonce = decode_payload(their_challenge.payload)["nonce"]

    response = make_response(
        our_id, their_challenge.from_addr,
        their_nonce, identity.signing, identity.encryption,
    )
    await ws.send(pack(response))

    their_response = unpack(await ws.recv())
    if their_response.type != T.AUTH_RESPONSE:
        raise ValueError(f"expected AUTH_RESPONSE, got {their_response.type}")

    result = verify_response(their_response, nonce, expected_peer_id)
    if result is None:
        raise ValueError("peer auth verification failed")

    return result.signing_pubkey, result.enc_pubkey
