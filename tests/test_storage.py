"""Tests for node/storage.py"""

import time
import pytest

from node.storage import Storage, NodeEntry, TTL_MESSAGE_SECS, MISSED_PINGS_OFFLINE


def make_node(node_id="n1", address="1.2.3.4:8765", status="online") -> NodeEntry:
    now = int(time.time())
    return NodeEntry(
        node_id=node_id,
        address=address,
        type="permanent",
        access="open",
        last_seen=now,
        status=status,
        added_at=now,
    )


class TestNodeTable:
    async def test_upsert_and_get(self, storage):
        await storage.upsert_node(make_node("n1", "1.2.3.4:8765"))
        node = await storage.get_node("n1")
        assert node is not None
        assert node.node_id == "n1"
        assert node.address == "1.2.3.4:8765"
        assert node.status == "online"

    async def test_get_nonexistent(self, storage):
        assert await storage.get_node("missing") is None

    async def test_upsert_updates_existing(self, storage):
        await storage.upsert_node(make_node("n1", "1.1.1.1:8765"))
        updated = make_node("n1", "2.2.2.2:9000")
        await storage.upsert_node(updated)
        node = await storage.get_node("n1")
        assert node.address == "2.2.2.2:9000"

    async def test_get_all_nodes(self, storage):
        for i in range(5):
            await storage.upsert_node(make_node(f"n{i}", f"10.0.0.{i}:8765"))
        nodes = await storage.get_all_nodes()
        assert len(nodes) == 5

    async def test_get_online_nodes_excludes_offline(self, storage):
        await storage.upsert_node(make_node("online1", status="online"))
        await storage.upsert_node(make_node("offline1", status="offline"))
        online = await storage.get_online_nodes()
        ids = [n.node_id for n in online]
        assert "online1" in ids
        assert "offline1" not in ids

    async def test_remove_node(self, storage):
        await storage.upsert_node(make_node("n1"))
        await storage.remove_node("n1")
        assert await storage.get_node("n1") is None

    async def test_remove_nonexistent_is_noop(self, storage):
        await storage.remove_node("ghost")  # should not raise

    async def test_ping_success_resets_missed(self, storage):
        e = make_node("n1")
        e.missed_pings = 2
        e.status = "offline"
        await storage.upsert_node(e)
        await storage.update_node_ping("n1", success=True)
        node = await storage.get_node("n1")
        assert node.missed_pings == 0
        assert node.status == "online"

    async def test_ping_fail_increments_counter(self, storage):
        await storage.upsert_node(make_node("n1"))
        await storage.update_node_ping("n1", success=False)
        node = await storage.get_node("n1")
        assert node.missed_pings == 1
        assert node.status == "online"

    async def test_ping_fail_goes_offline_at_threshold(self, storage):
        await storage.upsert_node(make_node("n1"))
        for _ in range(MISSED_PINGS_OFFLINE):
            await storage.update_node_ping("n1", success=False)
        node = await storage.get_node("n1")
        assert node.status == "offline"

    async def test_cleanup_removes_long_offline(self, storage):
        old = make_node("old")
        old.status = "offline"
        old.last_seen = int(time.time()) - 73 * 3600  # 73h ago
        await storage.upsert_node(old)

        recent = make_node("recent")
        recent.status = "offline"
        recent.last_seen = int(time.time()) - 1 * 3600  # 1h ago
        await storage.upsert_node(recent)

        await storage.cleanup_expired_nodes()
        assert await storage.get_node("old") is None
        assert await storage.get_node("recent") is not None


class TestCells:
    async def test_register_and_get(self, storage):
        sign_pub = b"\xaa" * 32
        enc_pub  = b"\xab" * 32
        await storage.register_cell("cell1", sign_pub, enc_pub)
        cell = await storage.get_cell("cell1")
        assert cell.cell_id == "cell1"
        assert cell.signing_pubkey == sign_pub
        assert cell.enc_pubkey == enc_pub
        assert cell.is_home is True

    async def test_register_visiting_cell(self, storage):
        await storage.register_cell("cell1", b"s" * 32, b"x" * 32, is_home=False)
        cell = await storage.get_cell("cell1")
        assert cell.is_home is False

    async def test_get_nonexistent_cell(self, storage):
        assert await storage.get_cell("ghost") is None

    async def test_list_cells(self, storage):
        await storage.register_cell("c1", b"s1" * 16, b"a" * 32, is_home=True)
        await storage.register_cell("c2", b"s2" * 16, b"b" * 32, is_home=False)
        all_cells = await storage.list_cells()
        assert len(all_cells) == 2

    async def test_list_home_only(self, storage):
        await storage.register_cell("c1", b"s1" * 16, b"a" * 32, is_home=True)
        await storage.register_cell("c2", b"s2" * 16, b"b" * 32, is_home=False)
        home = await storage.list_cells(home_only=True)
        assert len(home) == 1
        assert home[0].cell_id == "c1"

    async def test_upsert_updates_pubkeys(self, storage):
        await storage.register_cell("c1", b"s1" * 16, b"a" * 32)
        await storage.register_cell("c1", b"s2" * 16, b"b" * 32)  # update
        cell = await storage.get_cell("c1")
        assert cell.signing_pubkey == b"s2" * 16
        assert cell.enc_pubkey == b"b" * 32


class TestPresence:
    async def test_update_and_get(self, storage):
        await storage.update_presence("cell1", "home_node", "visit_node")
        p = await storage.get_presence("cell1")
        assert p.cell_id == "cell1"
        assert p.home_node_id == "home_node"
        assert p.visiting_node_id == "visit_node"

    async def test_presence_without_visiting(self, storage):
        await storage.update_presence("cell1", "home_node")
        p = await storage.get_presence("cell1")
        assert p.visiting_node_id is None

    async def test_get_nonexistent_presence(self, storage):
        assert await storage.get_presence("ghost") is None

    async def test_update_overwrites(self, storage):
        await storage.update_presence("cell1", "home1", "visit1")
        await storage.update_presence("cell1", "home1", "visit2")
        p = await storage.get_presence("cell1")
        assert p.visiting_node_id == "visit2"


class TestMessageBuffer:
    async def test_buffer_and_get(self, storage):
        await storage.buffer_message("msg1", "cell1", "node1", b"payload")
        msgs = await storage.get_buffered("cell1")
        assert len(msgs) == 1
        assert msgs[0].payload == b"payload"
        assert msgs[0].to_node == "node1"

    async def test_get_empty(self, storage):
        assert await storage.get_buffered("nobody") == []

    async def test_multiple_messages(self, storage):
        for i in range(5):
            await storage.buffer_message(f"msg{i}", "cell1", "node1", f"p{i}".encode())
        msgs = await storage.get_buffered("cell1")
        assert len(msgs) == 5

    async def test_delete_message(self, storage):
        await storage.buffer_message("msg1", "cell1", "node1", b"data")
        await storage.delete_buffered("msg1")
        assert await storage.get_buffered("cell1") == []

    async def test_cleanup_expired(self, storage):
        # Manually insert an expired message
        expired_at = int(time.time()) - 1
        await storage._db.execute(
            "INSERT INTO message_buffer (message_id, to_cell, to_node, payload, created_at, expires_at) "
            "VALUES ('expired', 'cell1', 'n1', X'00', ?, ?)",
            (int(time.time()) - 10, expired_at),
        )
        await storage._db.commit()

        await storage.buffer_message("fresh", "cell1", "node1", b"ok")
        await storage.cleanup_expired_messages()

        msgs = await storage.get_buffered("cell1")
        ids = [m.message_id for m in msgs]
        assert "expired" not in ids
        assert "fresh" in ids

    async def test_duplicate_message_ignored(self, storage):
        await storage.buffer_message("msg1", "cell1", "node1", b"first")
        await storage.buffer_message("msg1", "cell1", "node1", b"second")
        msgs = await storage.get_buffered("cell1")
        assert len(msgs) == 1
        assert msgs[0].payload == b"first"
