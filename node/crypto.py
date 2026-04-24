"""
Cryptographic primitives for Nevod.

Signing:    Ed25519  (identity, authentication)
Encryption: X25519 + ChaCha20-Poly1305  (E2E, ephemeral key per message)
KDF:        HKDF-SHA256
"""

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


RAW = serialization.Encoding.Raw
RAW_PUB = serialization.PublicFormat.Raw
RAW_PRIV = serialization.PrivateFormat.Raw
NO_ENC = serialization.NoEncryption()

KDF_INFO = b"nevod-e2e-v1"
NONCE_SIZE = 12


@dataclass
class SigningKeypair:
    private: Ed25519PrivateKey
    public: bytes   # 32 raw bytes = node_id / cell_id


@dataclass
class EncryptionKeypair:
    private: X25519PrivateKey
    public: bytes   # 32 raw bytes = published enc pubkey


def gen_signing() -> SigningKeypair:
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(RAW, RAW_PUB)
    return SigningKeypair(private=priv, public=pub)


def gen_encryption() -> EncryptionKeypair:
    priv = X25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(RAW, RAW_PUB)
    return EncryptionKeypair(private=priv, public=pub)


def sign(message: bytes, signing_key: SigningKeypair) -> bytes:
    return signing_key.private.sign(message)


def verify(message: bytes, signature: bytes, pubkey_bytes: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature, message)
        return True
    except InvalidSignature:
        return False


def encrypt(plaintext: bytes, recipient_enc_pubkey: bytes) -> dict:
    """
    Encrypt plaintext for recipient.
    Returns dict with ephemeral_pubkey, nonce, ciphertext.
    recipient_enc_pubkey: X25519 public key (32 bytes).
    """
    ephemeral = X25519PrivateKey.generate()
    recipient = X25519PublicKey.from_public_bytes(recipient_enc_pubkey)
    shared = ephemeral.exchange(recipient)
    key = _kdf(shared, ephemeral.public_key().public_bytes(RAW, RAW_PUB))

    nonce = os.urandom(NONCE_SIZE)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)

    return {
        "ephemeral_pubkey": ephemeral.public_key().public_bytes(RAW, RAW_PUB),
        "nonce": nonce,
        "ciphertext": ciphertext,
    }


def decrypt(ciphertext: bytes, nonce: bytes, ephemeral_pubkey: bytes,
            enc_keypair: EncryptionKeypair) -> bytes:
    """
    Decrypt E2E message.
    Raises cryptography.exceptions.InvalidTag on auth failure.
    """
    ephemeral_pub = X25519PublicKey.from_public_bytes(ephemeral_pubkey)
    shared = enc_keypair.private.exchange(ephemeral_pub)
    key = _kdf(shared, ephemeral_pubkey)
    return ChaCha20Poly1305(key).decrypt(nonce, ciphertext, None)


def _kdf(shared_secret: bytes, ephemeral_pubkey: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=ephemeral_pubkey,
        info=KDF_INFO,
    ).derive(shared_secret)


def signing_priv_to_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(RAW, RAW_PRIV, NO_ENC)


def signing_priv_from_bytes(b: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b)


def enc_priv_to_bytes(key: X25519PrivateKey) -> bytes:
    return key.private_bytes(RAW, RAW_PRIV, NO_ENC)


def enc_priv_from_bytes(b: bytes) -> X25519PrivateKey:
    return X25519PrivateKey.from_private_bytes(b)
