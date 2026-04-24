"""Tests for node/identity.py"""

import json
import pytest

from node.identity import NodeIdentity, CellIdentity
from node.crypto import sign, verify, encrypt, decrypt


class TestNodeIdentity:
    def test_generate(self):
        idt = NodeIdentity.generate("127.0.0.1:8765")
        assert len(idt.node_id) == 64        # 32 bytes hex
        assert idt.address == "127.0.0.1:8765"
        assert idt.node_type == "permanent"
        assert idt.access == "closed"

    def test_node_id_is_signing_pubkey_hex(self):
        idt = NodeIdentity.generate("localhost:9000")
        assert idt.node_id == idt.signing.public.hex()

    def test_different_instances_have_different_ids(self):
        a = NodeIdentity.generate("localhost:8765")
        b = NodeIdentity.generate("localhost:8765")
        assert a.node_id != b.node_id

    def test_save_and_load_roundtrip(self, tmp_path):
        idt = NodeIdentity.generate("10.0.0.1:9000", node_type="temporary", access="open")
        path = str(tmp_path / "node.json")
        idt.save(path)

        loaded = NodeIdentity.load(path)
        assert loaded.node_id == idt.node_id
        assert loaded.address == idt.address
        assert loaded.node_type == idt.node_type
        assert loaded.access == idt.access
        assert loaded.encryption.public == idt.encryption.public

    def test_saved_file_is_valid_json(self, tmp_path):
        path = str(tmp_path / "node.json")
        NodeIdentity.generate("localhost:8765").save(path)
        with open(path) as f:
            data = json.load(f)
        assert "signing_priv" in data
        assert "enc_priv" in data
        assert "address" in data

    def test_signing_key_works_after_load(self, tmp_path):
        idt = NodeIdentity.generate("localhost:8765")
        path = str(tmp_path / "node.json")
        idt.save(path)
        loaded = NodeIdentity.load(path)

        msg = b"authenticate me"
        sig = sign(msg, loaded.signing)
        assert verify(msg, sig, loaded.signing.public)

    def test_enc_key_works_after_load(self, tmp_path):
        idt = NodeIdentity.generate("localhost:8765")
        path = str(tmp_path / "node.json")
        idt.save(path)
        loaded = NodeIdentity.load(path)

        plaintext = b"secret"
        enc = encrypt(plaintext, loaded.encryption.public)
        result = decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"],
                         loaded.encryption)
        assert result == plaintext

    def test_as_node_entry_dict(self):
        idt = NodeIdentity.generate("1.2.3.4:8765", access="open")
        d = idt.as_node_entry_dict()
        assert d["node_id"] == idt.node_id
        assert d["address"] == "1.2.3.4:8765"
        assert d["access"] == "open"
        assert d["enc_pub"] == idt.encryption.public.hex()

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            NodeIdentity.load(str(tmp_path / "ghost.json"))


class TestCellIdentity:
    def test_generate(self):
        cell = CellIdentity.generate("Alice")
        assert len(cell.cell_id) == 64
        assert cell.name == "Alice"

    def test_cell_id_is_signing_pubkey(self):
        cell = CellIdentity.generate()
        assert cell.cell_id == cell.signing.public.hex()

    def test_generate_without_name(self):
        cell = CellIdentity.generate()
        assert cell.name == ""

    def test_different_cells_have_different_ids(self):
        a = CellIdentity.generate("A")
        b = CellIdentity.generate("B")
        assert a.cell_id != b.cell_id

    def test_save_and_load_roundtrip(self, tmp_path):
        cell = CellIdentity.generate("Bob")
        path = str(tmp_path / "cell.json")
        cell.save(path)

        loaded = CellIdentity.load(path)
        assert loaded.cell_id == cell.cell_id
        assert loaded.name == cell.name
        assert loaded.encryption.public == cell.encryption.public

    def test_signing_works_after_load(self, tmp_path):
        cell = CellIdentity.generate("Charlie")
        path = str(tmp_path / "cell.json")
        cell.save(path)
        loaded = CellIdentity.load(path)

        msg = b"I am Charlie"
        sig = sign(msg, loaded.signing)
        assert verify(msg, sig, loaded.signing.public)

    def test_enc_works_after_load(self, tmp_path):
        cell = CellIdentity.generate()
        path = str(tmp_path / "cell.json")
        cell.save(path)
        loaded = CellIdentity.load(path)

        plaintext = b"dm content"
        enc = encrypt(plaintext, loaded.encryption.public)
        result = decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"],
                         loaded.encryption)
        assert result == plaintext
