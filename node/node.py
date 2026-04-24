"""
Nevod Node — main orchestrator.

Lifecycle:
  node = await Node.create(identity_path, db_path)
  await node.start()
  ...
  await node.stop()

Genesis mode (first node in the network):
  node = await Node.create_genesis(address, identity_path, db_path)
"""

import asyncio
import logging
import time
from typing import Optional, Callable, Awaitable

from .identity import NodeIdentity
from .storage import Storage, NodeEntry
from .transport import Transport, PeerConnection
from .gossip import GossipEngine
from .router import Router
from .protocol import Packet, T, pack, unpack, encode_payload, decode_payload

log = logging.getLogger(__name__)

MessageCallback = Callable[[Packet], Awaitable[None]]


class Node:
    def __init__(
        self,
        identity: NodeIdentity,
        storage: Storage,
        on_message: Optional[MessageCallback] = None,
    ):
        self.identity = identity
        self.storage = storage
        self.on_message = on_message

        self.transport = Transport(identity, on_packet=self._dispatch)
        self.gossip = GossipEngine(self)
        self.router = Router(self)

    @classmethod
    async def create(cls, identity_path: str, db_path: str,
                     on_message: Optional[MessageCallback] = None) -> "Node":
        identity = NodeIdentity.load(identity_path)
        storage = Storage(db_path)
        await storage.open()
        return cls(identity, storage, on_message)

    @classmethod
    async def create_genesis(cls, address: str, identity_path: str, db_path: str,
                              access: str = "open",
                              on_message: Optional[MessageCallback] = None) -> "Node":
        """Create and persist the first node in the network."""
        identity = NodeIdentity.generate(address, node_type="permanent", access=access)
        identity.save(identity_path)

        storage = Storage(db_path)
        await storage.open()

        node = cls(identity, storage, on_message)

        # register self in node_table
        await storage.upsert_node(NodeEntry(
            node_id=identity.node_id,
            address=address,
            type="permanent",
            access=access,
            last_seen=int(time.time()),
            status="online",
            added_at=int(time.time()),
        ))

        log.info("genesis node created: %s at %s", identity.node_id[:16], address)
        return node

    async def start(self):
        host, port = _split_address(self.identity.address)
        await self.transport.start(host, port)
        self.gossip.start()
        log.info("node %s started", self.identity.node_id[:16])

    async def stop(self):
        self.gossip.stop()
        await self.transport.stop()
        await self.storage.close()
        log.info("node %s stopped", self.identity.node_id[:16])

    async def join(self, bootstrap_address: str):
        """
        Connect to an existing node and pull the full node_table.
        The bootstrap node acts as recommender (simplified: no consensus in v1).
        """
        conn = await self.transport.connect(bootstrap_address)
        log.info("joined via %s (peer: %s)", bootstrap_address, conn.peer_node_id[:8])

        # register bootstrap peer in our node_table
        await self.storage.upsert_node(NodeEntry(
            node_id=conn.peer_node_id,
            address=bootstrap_address,
            type="permanent",
            access="open",
            last_seen=int(time.time()),
            status="online",
            added_at=int(time.time()),
        ))

    async def send_message(self, to_cell_at_node: str, plaintext: bytes,
                           from_cell_id: Optional[str] = None):
        """
        Send an E2E encrypted message.
        to_cell_at_node: "cell_id@node_id"
        plaintext: raw message bytes
        """
        from .crypto import encrypt
        from .protocol import Packet

        cell_id, _ = to_cell_at_node.split("@", 1)
        cell = await self.storage.get_cell(cell_id)
        if cell is None:
            raise ValueError(f"unknown cell {cell_id[:8]} — no enc_pubkey")

        encrypted = encrypt(plaintext, cell.enc_pubkey)
        payload = encode_payload({
            "ephemeral_pubkey": encrypted["ephemeral_pubkey"],
            "nonce":            encrypted["nonce"],
            "ciphertext":       encrypted["ciphertext"],
        })

        from_addr = (
            f"{from_cell_id}@{self.identity.node_id}"
            if from_cell_id
            else self.identity.node_id
        )
        pkt = Packet(
            type=T.MSG,
            payload=payload,
            from_addr=from_addr,
            to_addr=to_cell_at_node,
        )
        await self.router.route(pkt)

    # --- packet dispatcher ---

    async def _dispatch(self, pkt: Packet, conn: PeerConnection):
        t = pkt.type

        if t == T.PING:
            await self.gossip.handle_ping(pkt, conn)

        elif t == T.PONG:
            await self.gossip.handle_pong(pkt)

        elif t == T.GOSSIP:
            await self.gossip.handle_gossip(pkt)

        elif t == T.MSG:
            await self.router.route(pkt)

        elif t == T.NODE_REMOVE:
            await self._handle_node_remove(pkt)

        elif t == T.NODE_LEAVING:
            await self._handle_node_leaving(pkt)

        elif t == T.PRESENCE_QUERY:
            await self._handle_presence_query(pkt, conn)

        elif t == T.PRESENCE_RESPONSE:
            pass  # handled by callers that await specific replies

        elif t == T.CELL_REGISTER:
            await self._handle_cell_register(pkt, conn)

        else:
            log.debug("unhandled packet type: %s from %s", t, pkt.from_addr[:16])

    async def _handle_node_remove(self, pkt: Packet):
        try:
            data = decode_payload(pkt.payload)
            node_id = data["node_id"]
        except Exception:
            return
        await self.storage.remove_node(node_id)
        log.info("removed node %s (network broadcast)", node_id[:8])

    async def _handle_node_leaving(self, pkt: Packet):
        node_id = pkt.from_addr
        await self.storage.remove_node(node_id)
        await self.transport.connections.remove(node_id)
        log.info("node %s left gracefully", node_id[:8])

    async def _handle_presence_query(self, pkt: Packet, conn: PeerConnection):
        try:
            data = decode_payload(pkt.payload)
            cell_id = data["cell_id"]
        except Exception:
            return
        presence = await self.storage.get_presence(cell_id)
        response_payload = encode_payload({
            "cell_id": cell_id,
            "home_node_id": presence.home_node_id if presence else None,
            "visiting_node_id": presence.visiting_node_id if presence else None,
        })
        response = Packet(
            type=T.PRESENCE_RESPONSE,
            payload=response_payload,
            from_addr=self.identity.node_id,
            to_addr=pkt.from_addr,
        )
        await self.transport.send_via(conn, response)

    async def _handle_cell_register(self, pkt: Packet, conn: PeerConnection):
        try:
            data = decode_payload(pkt.payload)
            cell_id      = data["cell_id"]
            signing_pub  = bytes(data["signing_pubkey"])
            enc_pub      = bytes(data["enc_pubkey"])
            is_home      = bool(data.get("is_home", True))
        except Exception:
            return
        await self.storage.register_cell(cell_id, signing_pub, enc_pub, is_home)
        await self.storage.update_presence(
            cell_id,
            home_node_id=self.identity.node_id,
            visiting_node_id=None,
        )
        log.info("cell registered: %s (home=%s)", cell_id[:8], is_home)

    # --- convenience ---

    async def register_cell_locally(self, cell_id: str,
                                     signing_pubkey: bytes, enc_pubkey: bytes):
        """Register a local cell on this node."""
        await self.storage.register_cell(cell_id, signing_pubkey, enc_pubkey, is_home=True)
        await self.storage.update_presence(
            cell_id,
            home_node_id=self.identity.node_id,
        )


def _split_address(address: str):
    host, port = address.rsplit(":", 1)
    return host, int(port)
