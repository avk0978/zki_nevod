"""
SQLite storage for a Nevod node.

Tables:
  node_table      — all known nodes in the network
  cells           — cells registered on this node
  presence_table  — where each home-cell is currently located
  message_buffer  — buffered messages for offline recipients (TTL 72h)
"""

import time
import aiosqlite
from dataclasses import dataclass
from typing import Optional, List

TTL_NODE_OFFLINE_SECS = 72 * 3600    # 72h → remove from node_table
TTL_MESSAGE_SECS      = 72 * 3600    # 72h → drop undelivered message
MISSED_PINGS_OFFLINE  = 3


SCHEMA = """
CREATE TABLE IF NOT EXISTS node_table (
    node_id     TEXT PRIMARY KEY,
    address     TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'permanent',
    access      TEXT NOT NULL DEFAULT 'closed',
    cert        BLOB,
    parent_node TEXT,
    last_seen   INTEGER NOT NULL,
    missed_pings INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'online',
    added_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cells (
    cell_id         TEXT PRIMARY KEY,
    enc_pubkey      BLOB NOT NULL,
    registered_at   INTEGER NOT NULL,
    is_home         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS presence_table (
    cell_id             TEXT PRIMARY KEY,
    home_node_id        TEXT NOT NULL,
    visiting_node_id    TEXT,
    updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS message_buffer (
    message_id  TEXT PRIMARY KEY,
    to_cell     TEXT NOT NULL,
    to_node     TEXT NOT NULL,
    payload     BLOB NOT NULL,
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_buf_to_cell  ON message_buffer(to_cell);
CREATE INDEX IF NOT EXISTS idx_buf_expires  ON message_buffer(expires_at);
CREATE INDEX IF NOT EXISTS idx_node_status  ON node_table(status);
"""


@dataclass
class NodeEntry:
    node_id: str
    address: str
    type: str        = "permanent"
    access: str      = "closed"
    cert: bytes      = b""
    parent_node: str = ""
    last_seen: int   = 0
    missed_pings: int = 0
    status: str      = "online"
    added_at: int    = 0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "type": self.type,
            "access": self.access,
            "cert": self.cert.hex() if self.cert else "",
            "parent_node": self.parent_node,
            "last_seen": self.last_seen,
            "status": self.status,
        }


@dataclass
class CellEntry:
    cell_id: str
    enc_pubkey: bytes
    registered_at: int
    is_home: bool = True


@dataclass
class PresenceEntry:
    cell_id: str
    home_node_id: str
    visiting_node_id: Optional[str]
    updated_at: int


@dataclass
class BufferedMessage:
    message_id: str
    to_cell: str
    to_node: str
    payload: bytes
    created_at: int
    expires_at: int


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def open(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    # --- node_table ---

    async def upsert_node(self, entry: NodeEntry):
        now = entry.added_at or int(time.time())
        await self._db.execute(
            """
            INSERT INTO node_table
                (node_id, address, type, access, cert, parent_node,
                 last_seen, missed_pings, status, added_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
                address      = excluded.address,
                last_seen    = excluded.last_seen,
                missed_pings = excluded.missed_pings,
                status       = excluded.status,
                cert         = excluded.cert
            """,
            (
                entry.node_id, entry.address, entry.type, entry.access,
                entry.cert, entry.parent_node,
                entry.last_seen, entry.missed_pings, entry.status, now,
            ),
        )
        await self._db.commit()

    async def get_node(self, node_id: str) -> Optional[NodeEntry]:
        async with self._db.execute(
            "SELECT * FROM node_table WHERE node_id = ?", (node_id,)
        ) as cur:
            row = await cur.fetchone()
            return _row_to_node(row) if row else None

    async def get_all_nodes(self) -> List[NodeEntry]:
        async with self._db.execute("SELECT * FROM node_table") as cur:
            return [_row_to_node(r) for r in await cur.fetchall()]

    async def get_online_nodes(self) -> List[NodeEntry]:
        async with self._db.execute(
            "SELECT * FROM node_table WHERE status = 'online'"
        ) as cur:
            return [_row_to_node(r) for r in await cur.fetchall()]

    async def update_node_ping(self, node_id: str, success: bool):
        now = int(time.time())
        if success:
            await self._db.execute(
                "UPDATE node_table SET last_seen=?, missed_pings=0, status='online' WHERE node_id=?",
                (now, node_id),
            )
        else:
            await self._db.execute(
                """
                UPDATE node_table
                SET missed_pings = missed_pings + 1,
                    status = CASE WHEN missed_pings + 1 >= ? THEN 'offline' ELSE status END
                WHERE node_id = ?
                """,
                (MISSED_PINGS_OFFLINE, node_id),
            )
        await self._db.commit()

    async def remove_node(self, node_id: str):
        await self._db.execute("DELETE FROM node_table WHERE node_id = ?", (node_id,))
        await self._db.commit()

    async def cleanup_expired_nodes(self):
        cutoff = int(time.time()) - TTL_NODE_OFFLINE_SECS
        await self._db.execute(
            "DELETE FROM node_table WHERE status='offline' AND last_seen < ?",
            (cutoff,),
        )
        await self._db.commit()

    # --- cells ---

    async def register_cell(self, cell_id: str, enc_pubkey: bytes, is_home: bool = True):
        now = int(time.time())
        await self._db.execute(
            """
            INSERT INTO cells (cell_id, enc_pubkey, registered_at, is_home)
            VALUES (?,?,?,?)
            ON CONFLICT(cell_id) DO UPDATE SET enc_pubkey = excluded.enc_pubkey
            """,
            (cell_id, enc_pubkey, now, int(is_home)),
        )
        await self._db.commit()

    async def get_cell(self, cell_id: str) -> Optional[CellEntry]:
        async with self._db.execute(
            "SELECT * FROM cells WHERE cell_id = ?", (cell_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return CellEntry(
                cell_id=row["cell_id"],
                enc_pubkey=bytes(row["enc_pubkey"]),
                registered_at=row["registered_at"],
                is_home=bool(row["is_home"]),
            )

    async def list_cells(self, home_only: bool = False) -> List[CellEntry]:
        q = "SELECT * FROM cells"
        if home_only:
            q += " WHERE is_home = 1"
        async with self._db.execute(q) as cur:
            rows = await cur.fetchall()
        return [
            CellEntry(
                cell_id=r["cell_id"],
                enc_pubkey=bytes(r["enc_pubkey"]),
                registered_at=r["registered_at"],
                is_home=bool(r["is_home"]),
            )
            for r in rows
        ]

    # --- presence ---

    async def update_presence(self, cell_id: str, home_node_id: str,
                               visiting_node_id: Optional[str] = None):
        now = int(time.time())
        await self._db.execute(
            """
            INSERT INTO presence_table (cell_id, home_node_id, visiting_node_id, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(cell_id) DO UPDATE SET
                home_node_id     = excluded.home_node_id,
                visiting_node_id = excluded.visiting_node_id,
                updated_at       = excluded.updated_at
            """,
            (cell_id, home_node_id, visiting_node_id, now),
        )
        await self._db.commit()

    async def get_presence(self, cell_id: str) -> Optional[PresenceEntry]:
        async with self._db.execute(
            "SELECT * FROM presence_table WHERE cell_id = ?", (cell_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return PresenceEntry(
                cell_id=row["cell_id"],
                home_node_id=row["home_node_id"],
                visiting_node_id=row["visiting_node_id"],
                updated_at=row["updated_at"],
            )

    # --- message_buffer ---

    async def buffer_message(self, message_id: str, to_cell: str,
                              to_node: str, payload: bytes):
        now = int(time.time())
        await self._db.execute(
            """
            INSERT OR IGNORE INTO message_buffer
                (message_id, to_cell, to_node, payload, created_at, expires_at)
            VALUES (?,?,?,?,?,?)
            """,
            (message_id, to_cell, to_node, payload, now, now + TTL_MESSAGE_SECS),
        )
        await self._db.commit()

    async def get_buffered(self, to_cell: str) -> List[BufferedMessage]:
        now = int(time.time())
        async with self._db.execute(
            "SELECT * FROM message_buffer WHERE to_cell=? AND expires_at > ?",
            (to_cell, now),
        ) as cur:
            rows = await cur.fetchall()
        return [
            BufferedMessage(
                message_id=r["message_id"],
                to_cell=r["to_cell"],
                to_node=r["to_node"],
                payload=bytes(r["payload"]),
                created_at=r["created_at"],
                expires_at=r["expires_at"],
            )
            for r in rows
        ]

    async def delete_buffered(self, message_id: str):
        await self._db.execute(
            "DELETE FROM message_buffer WHERE message_id = ?", (message_id,)
        )
        await self._db.commit()

    async def cleanup_expired_messages(self):
        now = int(time.time())
        await self._db.execute(
            "DELETE FROM message_buffer WHERE expires_at <= ?", (now,)
        )
        await self._db.commit()


def _row_to_node(row) -> NodeEntry:
    return NodeEntry(
        node_id=row["node_id"],
        address=row["address"],
        type=row["type"],
        access=row["access"],
        cert=bytes(row["cert"]) if row["cert"] else b"",
        parent_node=row["parent_node"] or "",
        last_seen=row["last_seen"],
        missed_pings=row["missed_pings"],
        status=row["status"],
        added_at=row["added_at"],
    )
