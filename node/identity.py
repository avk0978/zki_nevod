"""
Node and Cell identity management.

NodeIdentity: Ed25519 signing keypair + X25519 encryption keypair + address
CellIdentity: same structure but for a user cell

Persisted as JSON with raw private keys encoded as hex.
In a future version, keys will be encrypted with a passphrase (AES-GCM or Argon2+ChaCha20).
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

from .crypto import (
    SigningKeypair, EncryptionKeypair,
    gen_signing, gen_encryption,
    signing_priv_to_bytes, signing_priv_from_bytes,
    enc_priv_to_bytes, enc_priv_from_bytes,
)
from cryptography.hazmat.primitives import serialization


@dataclass
class NodeIdentity:
    signing: SigningKeypair
    encryption: EncryptionKeypair
    address: str             # "host:port" where this node listens
    node_type: str = "permanent"   # permanent | temporary
    access: str    = "closed"      # open | closed

    @property
    def node_id(self) -> str:
        return self.signing.public.hex()

    @classmethod
    def generate(cls, address: str, node_type: str = "permanent",
                 access: str = "closed") -> "NodeIdentity":
        return cls(
            signing=gen_signing(),
            encryption=gen_encryption(),
            address=address,
            node_type=node_type,
            access=access,
        )

    def save(self, path: str):
        data = {
            "signing_priv": signing_priv_to_bytes(self.signing.private).hex(),
            "signing_pub":  self.signing.public.hex(),
            "enc_priv":     enc_priv_to_bytes(self.encryption.private).hex(),
            "enc_pub":      self.encryption.public.hex(),
            "address":      self.address,
            "node_type":    self.node_type,
            "access":       self.access,
        }
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "NodeIdentity":
        with open(path) as f:
            data = json.load(f)
        signing_priv = signing_priv_from_bytes(bytes.fromhex(data["signing_priv"]))
        signing = SigningKeypair(
            private=signing_priv,
            public=bytes.fromhex(data["signing_pub"]),
        )
        enc_priv = enc_priv_from_bytes(bytes.fromhex(data["enc_priv"]))
        encryption = EncryptionKeypair(
            private=enc_priv,
            public=bytes.fromhex(data["enc_pub"]),
        )
        return cls(
            signing=signing,
            encryption=encryption,
            address=data["address"],
            node_type=data.get("node_type", "permanent"),
            access=data.get("access", "closed"),
        )

    def as_node_entry_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "type":    self.node_type,
            "access":  self.access,
            "enc_pub": self.encryption.public.hex(),
        }


@dataclass
class CellIdentity:
    signing: SigningKeypair
    encryption: EncryptionKeypair
    name: str = ""

    @property
    def cell_id(self) -> str:
        return self.signing.public.hex()

    @classmethod
    def generate(cls, name: str = "") -> "CellIdentity":
        return cls(
            signing=gen_signing(),
            encryption=gen_encryption(),
            name=name,
        )

    def save(self, path: str):
        data = {
            "signing_priv": signing_priv_to_bytes(self.signing.private).hex(),
            "signing_pub":  self.signing.public.hex(),
            "enc_priv":     enc_priv_to_bytes(self.encryption.private).hex(),
            "enc_pub":      self.encryption.public.hex(),
            "name":         self.name,
        }
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "CellIdentity":
        with open(path) as f:
            data = json.load(f)
        signing_priv = signing_priv_from_bytes(bytes.fromhex(data["signing_priv"]))
        signing = SigningKeypair(
            private=signing_priv,
            public=bytes.fromhex(data["signing_pub"]),
        )
        enc_priv = enc_priv_from_bytes(bytes.fromhex(data["enc_priv"]))
        encryption = EncryptionKeypair(
            private=enc_priv,
            public=bytes.fromhex(data["enc_pub"]),
        )
        return cls(
            signing=signing,
            encryption=encryption,
            name=data.get("name", ""),
        )
