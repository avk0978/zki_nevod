"""Tests for node/crypto.py"""

import pytest
from cryptography.exceptions import InvalidTag

from node.crypto import (
    gen_signing, gen_encryption,
    sign, verify,
    encrypt, decrypt,
    signing_priv_to_bytes, signing_priv_from_bytes,
    enc_priv_to_bytes, enc_priv_from_bytes,
)


class TestSignVerify:
    def test_sign_and_verify(self):
        kp = gen_signing()
        msg = b"hello nevod"
        sig = sign(msg, kp)
        assert verify(msg, sig, kp.public)

    def test_verify_wrong_key(self):
        kp1 = gen_signing()
        kp2 = gen_signing()
        sig = sign(b"test", kp1)
        assert not verify(b"test", sig, kp2.public)

    def test_verify_tampered_message(self):
        kp = gen_signing()
        sig = sign(b"original", kp)
        assert not verify(b"tampered", sig, kp.public)

    def test_verify_tampered_signature(self):
        kp = gen_signing()
        sig = bytearray(sign(b"test", kp))
        sig[0] ^= 0xFF
        assert not verify(b"test", bytes(sig), kp.public)

    def test_public_key_is_32_bytes(self):
        kp = gen_signing()
        assert len(kp.public) == 32

    def test_same_key_produces_same_node_id(self):
        kp = gen_signing()
        raw = signing_priv_to_bytes(kp.private)
        kp2_priv = signing_priv_from_bytes(raw)
        from node.crypto import SigningKeypair
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub2 = kp2_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        assert pub2 == kp.public

    def test_different_keys_produce_different_ids(self):
        assert gen_signing().public != gen_signing().public

    def test_sign_empty_message(self):
        kp = gen_signing()
        sig = sign(b"", kp)
        assert verify(b"", sig, kp.public)

    def test_sign_large_message(self):
        kp = gen_signing()
        msg = b"x" * 1_000_000
        sig = sign(msg, kp)
        assert verify(msg, sig, kp.public)


class TestEncryptDecrypt:
    def test_roundtrip(self):
        enc_kp = gen_encryption()
        plaintext = b"secret message"
        enc = encrypt(plaintext, enc_kp.public)
        result = decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"], enc_kp)
        assert result == plaintext

    def test_wrong_recipient_key(self):
        kp1 = gen_encryption()
        kp2 = gen_encryption()
        enc = encrypt(b"secret", kp1.public)
        with pytest.raises(InvalidTag):
            decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"], kp2)

    def test_tampered_ciphertext(self):
        kp = gen_encryption()
        enc = encrypt(b"secret", kp.public)
        corrupted = bytearray(enc["ciphertext"])
        corrupted[0] ^= 0xFF
        with pytest.raises(InvalidTag):
            decrypt(bytes(corrupted), enc["nonce"], enc["ephemeral_pubkey"], kp)

    def test_tampered_nonce(self):
        kp = gen_encryption()
        enc = encrypt(b"secret", kp.public)
        bad_nonce = bytes(b ^ 0xFF for b in enc["nonce"])
        with pytest.raises(InvalidTag):
            decrypt(enc["ciphertext"], bad_nonce, enc["ephemeral_pubkey"], kp)

    def test_ephemeral_key_is_unique_per_message(self):
        kp = gen_encryption()
        enc1 = encrypt(b"msg1", kp.public)
        enc2 = encrypt(b"msg2", kp.public)
        assert enc1["ephemeral_pubkey"] != enc2["ephemeral_pubkey"]
        assert enc1["nonce"] != enc2["nonce"]

    def test_encrypt_empty_message(self):
        kp = gen_encryption()
        enc = encrypt(b"", kp.public)
        result = decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"], kp)
        assert result == b""

    def test_encrypt_large_message(self):
        kp = gen_encryption()
        plaintext = b"Z" * 100_000
        enc = encrypt(plaintext, kp.public)
        result = decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"], kp)
        assert result == plaintext

    def test_enc_pubkey_is_32_bytes(self):
        kp = gen_encryption()
        assert len(kp.public) == 32


class TestKeySerialization:
    def test_signing_roundtrip(self):
        kp = gen_signing()
        raw = signing_priv_to_bytes(kp.private)
        assert len(raw) == 32
        restored = signing_priv_from_bytes(raw)
        from node.crypto import SigningKeypair
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub = restored.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        assert pub == kp.public

    def test_enc_roundtrip(self):
        kp = gen_encryption()
        raw = enc_priv_to_bytes(kp.private)
        assert len(raw) == 32
        restored = enc_priv_from_bytes(raw)
        msg = b"test"
        enc = encrypt(msg, kp.public)
        from node.crypto import EncryptionKeypair
        restored_kp = EncryptionKeypair(
            private=restored,
            public=kp.public,
        )
        result = decrypt(enc["ciphertext"], enc["nonce"], enc["ephemeral_pubkey"], restored_kp)
        assert result == msg
