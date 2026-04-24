"""
WebSocket transport layer.

- Server: accepts incoming connections from other nodes / cells
- Client: initiates outgoing connections to other nodes
- Each connection: mutual auth (auth.py) → then message exchange
- After auth: connection registered in ConnectionRegistry
"""

import asyncio
import logging
import os
from typing import Optional, Callable, Dict, Awaitable

import websockets
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed

from .protocol import Packet, pack, unpack, T
from .auth import make_challenge, make_response, verify_response, AuthResult

log = logging.getLogger(__name__)

# Type alias: handler called after auth succeeds
PacketHandler = Callable[[Packet, "PeerConnection"], Awaitable[None]]


class PeerConnection:
    """Authenticated connection to a remote node."""

    def __init__(self, ws, peer_node_id: str, peer_enc_pubkey: bytes,
                 local_node_id: str):
        self.ws = ws
        self.peer_node_id = peer_node_id
        self.peer_enc_pubkey = peer_enc_pubkey
        self.local_node_id = local_node_id

    async def send(self, packet: Packet):
        try:
            await self.ws.send(pack(packet))
        except ConnectionClosed:
            log.debug("send failed: connection to %s closed", self.peer_node_id[:8])
            raise

    async def recv(self) -> Packet:
        data = await self.ws.recv()
        return unpack(data)

    async def close(self):
        await self.ws.close()


class ConnectionRegistry:
    """Thread-safe registry of authenticated peer connections."""

    def __init__(self):
        self._conns: Dict[str, PeerConnection] = {}
        self._lock = asyncio.Lock()

    async def add(self, conn: PeerConnection):
        async with self._lock:
            self._conns[conn.peer_node_id] = conn

    async def remove(self, node_id: str):
        async with self._lock:
            self._conns.pop(node_id, None)

    async def get(self, node_id: str) -> Optional[PeerConnection]:
        async with self._lock:
            return self._conns.get(node_id)

    async def all(self) -> list:
        async with self._lock:
            return list(self._conns.values())


class Transport:
    """
    WebSocket transport for a Nevod node.

    Usage:
        t = Transport(identity, on_packet=handler)
        await t.start("0.0.0.0", 8765)
        conn = await t.connect("192.168.1.1:8765")
        await t.stop()
    """

    def __init__(self, identity, on_packet: PacketHandler):
        self.identity = identity
        self.on_packet = on_packet
        self.connections = ConnectionRegistry()
        self._server = None

    @property
    def node_id(self) -> str:
        return self.identity.node_id

    async def start(self, host: str = "0.0.0.0", port: int = 8765):
        self._server = await websockets.serve(
            self._handle_incoming,
            host,
            port,
        )
        log.info("node %s listening on %s:%d", self.node_id[:8], host, port)

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for conn in await self.connections.all():
            await conn.close()

    async def connect(self, address: str) -> PeerConnection:
        """Open outgoing connection to address "host:port", perform mutual auth."""
        if ":" not in address:
            raise ValueError(f"invalid address: {address}")
        uri = f"ws://{address}"
        ws = await websockets.connect(uri)
        conn = await self._do_auth(ws, expected_node_id=None, initiator=True)
        await self.connections.add(conn)
        asyncio.create_task(self._recv_loop(conn))
        return conn

    async def connect_to_node(self, node_id: str, address: str) -> PeerConnection:
        """Connect and verify the remote node is who we expect."""
        uri = f"ws://{address}"
        ws = await websockets.connect(uri)
        conn = await self._do_auth(ws, expected_node_id=node_id, initiator=True)
        await self.connections.add(conn)
        asyncio.create_task(self._recv_loop(conn))
        return conn

    async def send_to(self, node_id: str, packet: Packet) -> bool:
        """Send packet to a connected peer. Returns False if not connected."""
        conn = await self.connections.get(node_id)
        if not conn:
            return False
        try:
            await conn.send(packet)
            return True
        except ConnectionClosed:
            await self.connections.remove(node_id)
            return False

    # --- internal ---

    async def _handle_incoming(self, ws: WebSocketServerProtocol, path: str = "/"):
        try:
            conn = await self._do_auth(ws, expected_node_id=None, initiator=False)
        except Exception as e:
            log.warning("auth failed from %s: %s", ws.remote_address, e)
            await ws.close()
            return

        await self.connections.add(conn)
        log.info("peer connected: %s", conn.peer_node_id[:8])
        try:
            await self._recv_loop(conn)
        finally:
            await self.connections.remove(conn.peer_node_id)
            log.info("peer disconnected: %s", conn.peer_node_id[:8])

    async def _do_auth(self, ws, expected_node_id: Optional[str],
                       initiator: bool) -> PeerConnection:
        """
        Mutual challenge-response auth.
        Both sides send a challenge and respond to the other's challenge concurrently.
        """
        node_id = self.node_id

        # send our challenge
        our_challenge_pkt, our_nonce = make_challenge(node_id, expected_node_id or "")
        await ws.send(pack(our_challenge_pkt))

        # receive peer's challenge
        their_challenge_pkt = unpack(await ws.recv())
        if their_challenge_pkt.type != T.AUTH_CHALLENGE:
            raise ValueError(f"expected AUTH_CHALLENGE, got {their_challenge_pkt.type}")
        from .protocol import decode_payload
        their_nonce = decode_payload(their_challenge_pkt.payload)["nonce"]

        # send our response
        response_pkt = make_response(
            node_id, their_challenge_pkt.from_addr,
            their_nonce, self.identity.signing, self.identity.encryption,
        )
        await ws.send(pack(response_pkt))

        # receive peer's response
        their_response_pkt = unpack(await ws.recv())
        if their_response_pkt.type != T.AUTH_RESPONSE:
            raise ValueError(f"expected AUTH_RESPONSE, got {their_response_pkt.type}")

        result: Optional[AuthResult] = verify_response(
            their_response_pkt, our_nonce, expected_node_id
        )
        if result is None:
            raise ValueError("auth verification failed")

        return PeerConnection(
            ws=ws,
            peer_node_id=result.node_id,
            peer_enc_pubkey=result.enc_pubkey,
            local_node_id=node_id,
        )

    async def _recv_loop(self, conn: PeerConnection):
        try:
            async for raw in conn.ws:
                pkt = unpack(raw)
                try:
                    await self.on_packet(pkt, conn)
                except Exception as e:
                    log.error("packet handler error from %s: %s", conn.peer_node_id[:8], e)
        except ConnectionClosed:
            pass
        finally:
            await self.connections.remove(conn.peer_node_id)
