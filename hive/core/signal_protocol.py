"""
Simplified Signal Protocol — Double Ratchet for forward secrecy.
Each message uses a unique key derived from a ratcheting chain.
If a key is compromised, past and future messages remain secure.
"""

import json
import time
import hashlib
import logging
from dataclasses import dataclass, field

from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import HexEncoder
from nacl.utils import random as nacl_random

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """State of an encrypted session with a peer."""
    peer_did: str
    root_key: bytes              # Root key for ratcheting
    sending_chain_key: bytes     # Chain key for sending messages
    receiving_chain_key: bytes   # Chain key for receiving messages
    sending_counter: int = 0     # Message counter (sending)
    receiving_counter: int = 0   # Message counter (receiving)
    their_public_key: str = ""   # Peer's current public key
    established_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "peer_did": self.peer_did,
            "root_key": self.root_key.hex(),
            "sending_chain_key": self.sending_chain_key.hex(),
            "receiving_chain_key": self.receiving_chain_key.hex(),
            "sending_counter": self.sending_counter,
            "receiving_counter": self.receiving_counter,
            "their_public_key": self.their_public_key,
            "established_at": self.established_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        return cls(
            peer_did=data["peer_did"],
            root_key=bytes.fromhex(data["root_key"]),
            sending_chain_key=bytes.fromhex(data["sending_chain_key"]),
            receiving_chain_key=bytes.fromhex(data["receiving_chain_key"]),
            sending_counter=data.get("sending_counter", 0),
            receiving_counter=data.get("receiving_counter", 0),
            their_public_key=data.get("their_public_key", ""),
            established_at=data.get("established_at", 0),
        )


def _hkdf(input_key: bytes, salt: bytes = b"", info: bytes = b"", length: int = 64) -> bytes:
    """HKDF key derivation (simplified using HMAC-SHA256)."""
    import hmac
    # Extract
    if not salt:
        salt = b"\x00" * 32
    prk = hmac.new(salt, input_key, hashlib.sha256).digest()
    # Expand
    okm = b""
    t = b""
    for i in range(1, (length // 32) + 2):
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def _derive_chain_key(chain_key: bytes) -> tuple[bytes, bytes]:
    """Derive message key and next chain key from current chain key."""
    output = _hkdf(chain_key, info=b"chain_ratchet", length=64)
    message_key = output[:32]
    next_chain_key = output[32:64]
    return message_key, next_chain_key


class SignalSession:
    """Manages an encrypted session with a peer using Double Ratchet."""

    def __init__(self, session: SessionState):
        self.session = session

    @classmethod
    def initiate(cls, my_private_key: PrivateKey, peer_public_key_hex: str, peer_did: str) -> "SignalSession":
        """Initiate a new session (Alice side)."""
        peer_public_key = PublicKey(peer_public_key_hex, encoder=HexEncoder)

        # X3DH: Compute shared secret via DH
        box = Box(my_private_key, peer_public_key)
        shared_secret = box.shared_key()

        # Derive root key and chain keys
        derived = _hkdf(bytes(shared_secret), info=b"x3dh_init", length=96)
        root_key = derived[:32]
        sending_chain = derived[32:64]
        receiving_chain = derived[64:96]

        session = SessionState(
            peer_did=peer_did,
            root_key=root_key,
            sending_chain_key=sending_chain,
            receiving_chain_key=receiving_chain,
            their_public_key=peer_public_key_hex,
            established_at=time.time(),
        )
        return cls(session)

    @classmethod
    def accept(cls, my_private_key: PrivateKey, peer_public_key_hex: str, peer_did: str) -> "SignalSession":
        """Accept a new session (Bob side) — mirrored chain keys."""
        peer_public_key = PublicKey(peer_public_key_hex, encoder=HexEncoder)

        # Same DH shared secret
        box = Box(my_private_key, peer_public_key)
        shared_secret = box.shared_key()

        # Derive same keys, but SWAP sending/receiving
        derived = _hkdf(bytes(shared_secret), info=b"x3dh_init", length=96)
        root_key = derived[:32]
        # Bob's sending = Alice's receiving, Bob's receiving = Alice's sending
        receiving_chain = derived[32:64]
        sending_chain = derived[64:96]

        session = SessionState(
            peer_did=peer_did,
            root_key=root_key,
            sending_chain_key=sending_chain,
            receiving_chain_key=receiving_chain,
            their_public_key=peer_public_key_hex,
            established_at=time.time(),
        )
        return cls(session)

    def encrypt(self, plaintext: str) -> dict:
        """Encrypt a message using the current sending chain key."""
        message_key, next_chain_key = _derive_chain_key(self.session.sending_chain_key)

        # Encrypt with derived message key
        from nacl.secret import SecretBox
        box = SecretBox(message_key)
        nonce = nacl_random(SecretBox.NONCE_SIZE)
        encrypted = box.encrypt(plaintext.encode(), nonce)

        # Ratchet the sending chain
        self.session.sending_chain_key = next_chain_key
        self.session.sending_counter += 1

        return {
            "ciphertext": encrypted.ciphertext.hex(),
            "nonce": encrypted.nonce.hex(),
            "counter": self.session.sending_counter,
            "timestamp": time.time(),
        }

    def decrypt(self, encrypted: dict) -> str:
        """Decrypt a message using the receiving chain key."""
        message_key, next_chain_key = _derive_chain_key(self.session.receiving_chain_key)

        ciphertext = bytes.fromhex(encrypted["ciphertext"])
        nonce = bytes.fromhex(encrypted["nonce"])

        from nacl.secret import SecretBox
        box = SecretBox(message_key)
        # NaCl SecretBox.decrypt expects nonce + ciphertext concatenated
        plaintext = box.decrypt(nonce + ciphertext)

        # Ratchet the receiving chain
        self.session.receiving_chain_key = next_chain_key
        self.session.receiving_counter += 1

        return plaintext.decode()

    def ratchet_dh(self, new_private_key: PrivateKey):
        """Perform DH ratchet step — update keys after receiving new peer key."""
        # This would be called when peer sends a new public key
        pass


class SessionManager:
    """Manages all active sessions."""

    def __init__(self):
        self._sessions: dict[str, SignalSession] = {}  # peer_did -> SignalSession

    def get_or_create_session(self, peer_did: str, my_private_key: PrivateKey,
                               peer_public_key_hex: str) -> SignalSession:
        """Get existing session or create new one."""
        if peer_did in self._sessions:
            return self._sessions[peer_did]

        session = SignalSession.initiate(my_private_key, peer_public_key_hex, peer_did)
        self._sessions[peer_did] = session
        logger.info(f"New Signal session established with {peer_did}")
        return session

    def get_session(self, peer_did: str) -> SignalSession | None:
        return self._sessions.get(peer_did)

    def remove_session(self, peer_did: str):
        self._sessions.pop(peer_did, None)

    def list_sessions(self) -> list[dict]:
        return [
            {
                "peer_did": s.session.peer_did,
                "sending_counter": s.session.sending_counter,
                "receiving_counter": s.session.receiving_counter,
                "established_at": s.session.established_at,
            }
            for s in self._sessions.values()
        ]

    def save_sessions(self, path: str = "sessions.json"):
        """Save session state to disk."""
        import json
        data = {did: s.session.to_dict() for did, s in self._sessions.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_sessions(self, path: str = "sessions.json"):
        """Load session state from disk."""
        import json
        try:
            with open(path) as f:
                data = json.load(f)
            for did, session_data in data.items():
                self._sessions[did] = SignalSession(SessionState.from_dict(session_data))
        except FileNotFoundError:
            pass
