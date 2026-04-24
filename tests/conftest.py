"""Shared fixtures for Nevod node tests."""

import asyncio
import os
import pytest

from node.identity import NodeIdentity, CellIdentity
from node.storage import Storage
from node.node import Node


# Ports used by integration tests — picked high to avoid conflicts
BASE_PORT = 19200


def node_port(offset: int) -> int:
    return BASE_PORT + offset


@pytest.fixture
def signing_keypair():
    from node.crypto import gen_signing
    return gen_signing()


@pytest.fixture
def enc_keypair():
    from node.crypto import gen_encryption
    return gen_encryption()


@pytest.fixture
def node_identity(tmp_path):
    return NodeIdentity.generate(f"127.0.0.1:{node_port(0)}")


@pytest.fixture
def cell_identity():
    return CellIdentity.generate("Alice")


@pytest.fixture
async def storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
async def genesis_node(tmp_path):
    addr = f"127.0.0.1:{node_port(1)}"
    node = await Node.create_genesis(
        addr,
        str(tmp_path / "n1.json"),
        str(tmp_path / "n1.db"),
        access="open",
    )
    await node.start()
    yield node
    await node.stop()


@pytest.fixture
async def second_node(tmp_path):
    addr = f"127.0.0.1:{node_port(2)}"
    idt = NodeIdentity.generate(addr)
    idt.save(str(tmp_path / "n2.json"))
    node = await Node.create(
        str(tmp_path / "n2.json"),
        str(tmp_path / "n2.db"),
    )
    await node.start()
    yield node
    await node.stop()
