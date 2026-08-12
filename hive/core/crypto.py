"""
End-to-End Encryption using NaCl (libsodium).
Implements authenticated encryption with X25519 + XSalsa20-Poly1305.
Messages are signed with Ed25519 before encryption.
"""

import json
import time
import logging

from nacl.public import Box, PrivateKey, PublicKey
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
from nacl.utils import random as nacl_random

logger = logging.getLogger(__name__)


class EncryptedMessage:
    """An E2EE message with signature and metadata."""

    def __init__(self, ciphertext: bytes, nonce: bytes, signature: bytes,
                 sender_did: str, timestamp: float, message_type: str = "text"):
        self.ciphertext = ciphertext
        self.nonce = nonce
        self.signature = signature
        self.sender_did = sender_did
        self.timestamp = timestamp
        self.message_type = message_type

    def to_dict(self) -> dict:
        return {
            "ciphertext": self.ciphertext.hex(),
            "nonce": self.nonce.hex(),
            "signature": self.signature.hex(),
            "sender_did": self.sender_did,
            "timestamp": self.timestamp,
            "type": self.message_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncryptedMessage":
        return cls(
            ciphertext=bytes.fromhex(data["ciphertext"]),
            nonce=bytes.fromhex(data["nonce"]),
            signature=bytes.fromhex(data["signature"]),
            sender_did=data["sender_did"],
            timestamp=data["timestamp"],
            message_type=data.get("type", "text"),
        )

    def to_wire(self) -> str:
        """Serialize for network transmission."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_wire(cls, data: str) -> "EncryptedMessage":
        """Deserialize from network transmission."""
        return cls.from_dict(json.loads(data))


def encrypt_message(
    plaintext: str,
    sender_signing_key: SigningKey,
    sender_encryption_key: PrivateKey,
    recipient_encryption_key: PublicKey,
    message_type: str = "text",
) -> EncryptedMessage:
    """
    Encrypt and sign a message for a specific recipient.

    1. Create message payload with timestamp
    2. Sign the payload with Ed25519
    3. Encrypt signed payload with X25519 + XSalsa20-Poly1305
    """
    sender_did = f"hive:{sender_signing_key.verify_key.encode(encoder=HexEncoder).decode()[:32]}"
    timestamp = time.time()

    # Create message payload
    payload = json.dumps({
        "content": plaintext,
        "sender": sender_did,
        "timestamp": timestamp,
        "type": message_type,
    }).encode()

    # Sign the payload
    signed = sender_signing_key.sign(payload)
    signature = signed.signature

    # Encrypt with recipient's public key
    box = Box(sender_encryption_key, recipient_encryption_key)
    nonce = nacl_random(Box.NONCE_SIZE)
    ciphertext = box.encrypt(payload, nonce)

    return EncryptedMessage(
        ciphertext=ciphertext,
        nonce=nonce,
        signature=signature,
        sender_did=sender_did,
        timestamp=timestamp,
        message_type=message_type,
    )


def decrypt_message(
    encrypted: EncryptedMessage,
    recipient_encryption_key: PrivateKey,
    sender_encryption_key_hex: str,
    sender_signing_key_hex: str,
) -> dict:
    """
    Decrypt and verify a message from a specific sender.

    1. Decrypt with X25519 + XSalsa20-Poly1305
    2. Verify Ed25519 signature
    3. Return plaintext + metadata
    """
    # Decrypt
    sender_public_key = PublicKey(sender_encryption_key_hex, encoder=HexEncoder)
    box = Box(recipient_encryption_key, sender_public_key)
    payload = box.decrypt(encrypted.ciphertext)

    # Verify signature
    sender_verify_key = VerifyKey(sender_signing_key_hex, encoder=HexEncoder)
    try:
        sender_verify_key.verify(payload, encrypted.signature)
    except Exception as e:
        raise ValueError(f"Signature verification failed: {e}")

    # Parse payload
    data = json.loads(payload)

    return {
        "content": data["content"],
        "sender": data["sender"],
        "timestamp": data["timestamp"],
        "type": data.get("type", "text"),
        "verified": True,
    }


def sign_data(data: bytes, signing_key: SigningKey) -> bytes:
    """Sign arbitrary data with Ed25519."""
    signed = signing_key.sign(data)
    return signed.signature


def verify_signature(data: bytes, signature: bytes, verify_key_hex: str) -> bool:
    """Verify an Ed25519 signature."""
    try:
        verify_key = VerifyKey(verify_key_hex, encoder=HexEncoder)
        verify_key.verify(data, signature)
        return True
    except Exception:
        return False


def generate_shared_secret(private_key: PrivateKey, public_key: PublicKey) -> bytes:
    """Generate a shared secret using X25519 Diffie-Hellman."""
    box = Box(private_key, public_key)
    return box.shared_key()


def encrypt_symmetric(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    """Encrypt with symmetric key (NaCl SecretBox). Returns (ciphertext, nonce)."""
    from nacl.secret import SecretBox
    box = SecretBox(key)
    nonce = nacl_random(SecretBox.NONCE_SIZE)
    encrypted = box.encrypt(plaintext, nonce)
    # encrypted = nonce + ciphertext_with_mac (nacl prepends nonce)
    # We need to separate them for our format
    return encrypted.ciphertext, encrypted.nonce


def decrypt_symmetric(ciphertext: bytes, nonce: bytes, key: bytes) -> bytes:
    """Decrypt with symmetric key (NaCl SecretBox)."""
    from nacl.secret import SecretBox
    box = SecretBox(key)
    # Reconstruct the full encrypted message (nonce + ciphertext)
    return box.decrypt(nonce + ciphertext)
