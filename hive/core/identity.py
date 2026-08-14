"""
P2P Identity — Ed25519 signing keys + X25519 encryption keys.
Each user/agent has a cryptographic identity (DID-like).
No central server — your key IS your identity.
"""

import json
import os
import time
import logging
from pathlib import Path

from nacl.signing import SigningKey, VerifyKey
from nacl.public import PrivateKey, PublicKey
from nacl.encoding import HexEncoder

logger = logging.getLogger(__name__)

KEYSTORE_DIR = Path("keystore")


class Identity:
    """Cryptographic identity — Ed25519 signing + X25519 encryption."""

    def __init__(self, signing_key: SigningKey, encryption_key: PrivateKey, display_name: str = ""):
        self.signing_key = signing_key
        self.verify_key = signing_key.verify_key
        self.encryption_key = encryption_key
        self.public_key = encryption_key.public_key
        self.display_name = display_name
        self.created_at = time.time()

    @property
    def did(self) -> str:
        """Decentralized Identifier — derived from public signing key."""
        pub_hex = self.verify_key.encode(encoder=HexEncoder).decode()
        return f"hive:{pub_hex[:32]}"

    @property
    def peer_id(self) -> str:
        """Short peer ID for display (first 16 chars of DID)."""
        return self.did[5:21]

    @property
    def public_signing_key_hex(self) -> str:
        return self.verify_key.encode(encoder=HexEncoder).decode()

    @property
    def public_encryption_key_hex(self) -> str:
        return self.public_key.encode(encoder=HexEncoder).decode()

    def sign(self, message: bytes) -> bytes:
        """Sign a message with Ed25519."""
        signed = self.signing_key.sign(message)
        return signed.signature

    def fingerprint(self) -> str:
        """Safety number fingerprint for OOB verification (QR code)."""
        combined = self.public_signing_key_hex + self.public_encryption_key_hex
        # Take first 30 chars, format as groups of 5
        fp = combined[:30]
        return " ".join(fp[i:i+5] for i in range(0, 30, 5))

    def to_dict(self) -> dict:
        return {
            "did": self.did,
            "peer_id": self.peer_id,
            "display_name": self.display_name,
            "public_signing_key": self.public_signing_key_hex,
            "public_encryption_key": self.public_encryption_key_hex,
            "fingerprint": self.fingerprint(),
            "created_at": self.created_at,
        }


def generate_identity(display_name: str = "") -> Identity:
    """Generate a new cryptographic identity."""
    signing_key = SigningKey.generate()
    encryption_key = PrivateKey.generate()
    identity = Identity(signing_key, encryption_key, display_name)
    logger.info(f"Generated new identity: {identity.did} ({identity.peer_id})")
    return identity


def save_identity(identity: Identity, password: str = ""):
    """Save identity to encrypted keystore."""
    KEYSTORE_DIR.mkdir(exist_ok=True)
    keystore_path = KEYSTORE_DIR / "identity.json"

    data = {
        "signing_key": identity.signing_key.encode(encoder=HexEncoder).decode(),
        "encryption_key": identity.encryption_key.encode(encoder=HexEncoder).decode(),
        "display_name": identity.display_name,
        "created_at": identity.created_at,
    }

    # If password provided, encrypt with NaCl SecretBox
    if password:
        from nacl.secret import SecretBox
        from nacl.pwhash import argon2id
        salt = os.urandom(argon2id.SALT_SIZE)
        key = argon2id.kdf(
            SecretBox.KEY_SIZE,
            password.encode(),
            salt,
            opslimit=argon2id.OPSLIMIT_INTERACTIVE,
            memlimit=argon2id.MEMLIMIT_INTERACTIVE,
        )
        box = SecretBox(key)
        plaintext = json.dumps(data).encode()
        encrypted = box.encrypt(plaintext)
        # Store salt + encrypted data
        keystore_path.write_bytes(salt + encrypted)
    else:
        keystore_path.write_text(json.dumps(data, indent=2))

    logger.info(f"Identity saved to {keystore_path}")


def load_identity(password: str = "") -> Identity | None:
    """Load identity from keystore."""
    keystore_path = KEYSTORE_DIR / "identity.json"
    if not keystore_path.exists():
        return None

    try:
        if password:
            from nacl.secret import SecretBox
            from nacl.pwhash import argon2id
            raw = keystore_path.read_bytes()
            # Salt is stored at the beginning (SALT_SIZE bytes)
            salt_size = argon2id.SALT_SIZE
            salt = raw[:salt_size]
            encrypted = raw[salt_size:]
            key = argon2id.kdf(
                SecretBox.KEY_SIZE,
                password.encode(),
                salt,
                opslimit=argon2id.OPSLIMIT_INTERACTIVE,
                memlimit=argon2id.MEMLIMIT_INTERACTIVE,
            )
            box = SecretBox(key)
            plaintext = box.decrypt(encrypted)
            data = json.loads(plaintext)
        else:
            data = json.loads(keystore_path.read_text())

        signing_key = SigningKey(data["signing_key"], encoder=HexEncoder)
        encryption_key = PrivateKey(data["encryption_key"], encoder=HexEncoder)
        identity = Identity(signing_key, encryption_key, data.get("display_name", ""))
        identity.created_at = data.get("created_at", time.time())
        logger.info(f"Loaded identity: {identity.did}")
        return identity

    except Exception as e:
        logger.error(f"Failed to load identity: {e}")
        return None


def identity_exists() -> bool:
    """Check if an identity exists in the keystore."""
    return (KEYSTORE_DIR / "identity.json").exists()


def import_peer(public_signing_hex: str, public_encryption_hex: str, display_name: str = "") -> dict:
    """Import a peer's public keys for communication."""
    from nacl.signing import VerifyKey
    from nacl.public import PublicKey

    verify_key = VerifyKey(public_signing_hex, encoder=HexEncoder)
    enc_key = PublicKey(public_encryption_hex, encoder=HexEncoder)

    peer_did = f"hive:{public_signing_hex[:32]}"
    peer = {
        "did": peer_did,
        "peer_id": peer_did[5:21],
        "display_name": display_name,
        "public_signing_key": public_signing_hex,
        "public_encryption_key": public_encryption_hex,
        "verify_key": verify_key,
        "public_key": enc_key,
        "added_at": time.time(),
    }
    logger.info(f"Imported peer: {peer_did} ({display_name})")
    return peer
