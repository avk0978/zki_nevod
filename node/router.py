"""
Message routing.

Algorithm:
  1. Look up to_cell in presence_table → get visiting_node and home_node
  2. Try visiting_node first (where cell is currently online)
  3. Fallback to home_node
  4. If both unreachable → buffer the message (72h TTL)

Addressing: "cell_id@node_id" or just "node_id" for node-to-node messages.
"""

import logging
from typing import TYPE_CHECKING, Optional

from .protocol import Packet, T, encode_payload, decode_payload, make_ping

if TYPE_CHECKING:
    from .node import Node

log = logging.getLogger(__name__)


def parse_addr(addr: str):
    """Split "cell_id@node_id" → (cell_id, node_id). Or (None, addr) for node-only."""
    if "@" in addr:
        cell_id, node_id = addr.split("@", 1)
        return cell_id, node_id
    return None, addr


class Router:
    def __init__(self, node: "Node"):
        self.node = node

    async def route(self, pkt: Packet):
        """Route a MSG packet to its destination."""
        cell_id, to_node_id = parse_addr(pkt.to_addr)

        if cell_id is None:
            # node-to-node message: deliver to connected peer directly
            await self._send_to_node(to_node_id, pkt)
            return

        # cell message: resolve presence
        presence = await self.node.storage.get_presence(cell_id)

        if presence is None:
            # check if cell is registered here
            cell = await self.node.storage.get_cell(cell_id)
            if cell:
                # cell is registered locally but no presence record → deliver locally
                await self._deliver_local(pkt)
            else:
                log.debug("router: unknown cell %s, dropping", cell_id[:8])
            return

        # try visiting node first
        if presence.visiting_node_id:
            sent = await self._send_to_node(presence.visiting_node_id, pkt)
            if sent:
                return

        # try home node
        sent = await self._send_to_node(presence.home_node_id, pkt)
        if sent:
            return

        # buffer
        log.debug("router: buffering message %s for %s", pkt.id[:8], cell_id[:8])
        await self.node.storage.buffer_message(
            pkt.id, cell_id, presence.home_node_id, _serialize_packet(pkt)
        )

    async def _send_to_node(self, node_id: str, pkt: Packet) -> bool:
        my_id = self.node.identity.node_id
        if node_id == my_id:
            await self._deliver_local(pkt)
            return True

        # check existing connection
        sent = await self.node.transport.send_to(node_id, pkt)
        if sent:
            return True

        # try to connect
        entry = await self.node.storage.get_node(node_id)
        if not entry or entry.status != "online":
            return False

        try:
            conn = await self.node.transport.connect_to_node(node_id, entry.address)
            await self.node.transport.send_via(conn, pkt)
            return True
        except Exception as e:
            log.debug("router: failed to connect to %s: %s", node_id[:8], e)
            return False

    async def _deliver_local(self, pkt: Packet):
        """Deliver to a cell connected on this node."""
        cell_id, _ = parse_addr(pkt.to_addr)
        if cell_id:
            # Cell connection is registered in transport by cell_id after auth+CELL_REGISTER
            sent = await self.node.transport.send_to(cell_id, pkt)
            if sent:
                return
        # Fallback: on_message callback (used in tests and embedding scenarios)
        if self.node.on_message:
            await self.node.on_message(pkt)
        else:
            log.debug("router: cell %s not connected, no handler", pkt.to_addr[:16])

    async def flush_buffer(self, cell_id: str):
        """Attempt to deliver all buffered messages for a cell that came online."""
        messages = await self.node.storage.get_buffered(cell_id)
        for msg in messages:
            pkt = _deserialize_packet(msg.payload)
            if pkt:
                await self.route(pkt)
                await self.node.storage.delete_buffered(msg.message_id)


def _serialize_packet(pkt: Packet) -> bytes:
    import msgpack
    return msgpack.packb({
        "type": pkt.type, "id": pkt.id,
        "from": pkt.from_addr, "to": pkt.to_addr,
        "payload": pkt.payload, "sig": pkt.sig, "ts": pkt.ts,
    }, use_bin_type=True)


def _deserialize_packet(data: bytes) -> Optional[Packet]:
    try:
        from .protocol import unpack
        return unpack(data)
    except Exception:
        return None
