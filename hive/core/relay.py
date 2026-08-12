"""
Offline messaging relay — store-and-forward for when peers are offline.
Encrypted messages are held until the recipient comes online.
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RELAY_DIR = Path("relay_mailbox")


@dataclass
class RelayMessage:
    """An encrypted message waiting for delivery."""
    id: str
    sender_did: str
    recipient_did: str
    ciphertext: str
    nonce: str
    timestamp: float
    delivered: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender_did": self.sender_did,
            "recipient_did": self.recipient_did,
            "ciphertext": self.ciphertext,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "delivered": self.delivered,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelayMessage":
        return cls(**data)


class RelayStore:
    """Store-and-forward relay for offline messages."""

    def __init__(self):
        RELAY_DIR.mkdir(exist_ok=True)
        self._mailbox: dict[str, list[RelayMessage]] = {}  # recipient_did -> messages
        self._load_all()

    def store(self, msg: RelayMessage):
        """Store a message for offline delivery."""
        did = msg.recipient_did
        if did not in self._mailbox:
            self._mailbox[did] = []
        self._mailbox[did].append(msg)
        self._save(did)
        logger.info(f"Relay: stored message for {did} (pending: {len(self._mailbox[did])})")

    def fetch(self, recipient_did: str) -> list[RelayMessage]:
        """Fetch all pending messages for a recipient."""
        messages = self._mailbox.get(recipient_did, [])
        undelivered = [m for m in messages if not m.delivered]
        return undelivered

    def mark_delivered(self, recipient_did: str, message_ids: list[str]):
        """Mark messages as delivered."""
        if recipient_did not in self._mailbox:
            return
        for msg in self._mailbox[recipient_did]:
            if msg.id in message_ids:
                msg.delivered = True
        self._save(recipient_did)
        # Clean up old delivered messages
        self._mailbox[recipient_did] = [
            m for m in self._mailbox[recipient_did]
            if not m.delivered or (time.time() - m.timestamp) < 86400  # keep 24h
        ]
        self._save(recipient_did)

    def pending_count(self, recipient_did: str) -> int:
        """Count pending messages for a recipient."""
        return len([m for m in self._mailbox.get(recipient_did, []) if not m.delivered])

    def all_pending(self) -> dict[str, int]:
        """Get pending counts for all recipients."""
        return {did: len([m for m in msgs if not m.delivered]) for did, msgs in self._mailbox.items()}

    def _save(self, did: str):
        """Save mailbox to disk."""
        path = RELAY_DIR / f"{did[:20]}.json"
        data = [m.to_dict() for m in self._mailbox.get(did, [])]
        path.write_text(json.dumps(data, indent=2))

    def _load_all(self):
        """Load all mailboxes from disk."""
        for path in RELAY_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                did = path.stem
                self._mailbox[did] = [RelayMessage.from_dict(d) for d in data]
            except Exception as e:
                logger.error(f"Failed to load relay mailbox {path}: {e}")


# Global relay instance
relay = RelayStore()
