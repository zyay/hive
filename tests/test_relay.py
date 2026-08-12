"""Tests for relay (offline messaging) and P2P API endpoints."""

import pytest
import time
import json


class TestRelay:
    def setup_method(self):
        from hive.core.relay import RelayStore, RELAY_DIR
        import shutil
        if RELAY_DIR.exists():
            shutil.rmtree(RELAY_DIR)
        RELAY_DIR.mkdir(exist_ok=True)

    def test_store_and_fetch(self):
        from hive.core.relay import RelayStore, RelayMessage
        store = RelayStore()
        msg = RelayMessage(
            id="msg1", sender_did="hive:sender", recipient_did="hive:recipient",
            ciphertext="abc", nonce="def", timestamp=time.time(),
        )
        store.store(msg)
        fetched = store.fetch("hive:recipient")
        assert len(fetched) == 1
        assert fetched[0].id == "msg1"

    def test_mark_delivered(self):
        from hive.core.relay import RelayStore, RelayMessage
        store = RelayStore()
        msg = RelayMessage(
            id="msg2", sender_did="hive:a", recipient_did="hive:b",
            ciphertext="x", nonce="y", timestamp=time.time(),
        )
        store.store(msg)
        store.mark_delivered("hive:b", ["msg2"])
        fetched = store.fetch("hive:b")
        assert len(fetched) == 0

    def test_pending_count(self):
        from hive.core.relay import RelayStore, RelayMessage
        store = RelayStore()
        for i in range(3):
            store.store(RelayMessage(
                id=f"m{i}", sender_did="hive:a", recipient_did="hive:b",
                ciphertext="x", nonce="y", timestamp=time.time(),
            ))
        assert store.pending_count("hive:b") == 3

    def test_all_pending(self):
        from hive.core.relay import RelayStore, RelayMessage
        store = RelayStore()
        store.store(RelayMessage(id="m1", sender_did="a", recipient_did="x", ciphertext="c", nonce="n", timestamp=time.time()))
        store.store(RelayMessage(id="m2", sender_did="a", recipient_did="y", ciphertext="c", nonce="n", timestamp=time.time()))
        pending = store.all_pending()
        assert "x" in pending
        assert "y" in pending


class TestP2PAPI:
    def test_identity_creation(self):
        from hive.core.identity import generate_identity, identity_exists, load_identity
        from hive.core.identity import KEYSTORE_DIR
        import shutil
        if KEYSTORE_DIR.exists():
            shutil.rmtree(KEYSTORE_DIR)
        identity = generate_identity("TestUser")
        from hive.core.identity import save_identity
        save_identity(identity)
        assert identity_exists()
        loaded = load_identity()
        assert loaded.did == identity.did

    def test_invite_code_generation(self):
        from hive.core.identity import generate_identity
        import base64
        identity = generate_identity("InviteTest")
        data = json.dumps({
            "did": identity.did,
            "name": identity.display_name,
            "signing_key": identity.public_signing_key_hex,
            "encryption_key": identity.public_encryption_key_hex,
        })
        code = base64.urlsafe_b64encode(data.encode()).decode()
        decoded = json.loads(base64.urlsafe_b64decode(code))
        assert decoded["did"] == identity.did
