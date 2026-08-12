"""Tests for P2P modules: identity, crypto, signal protocol, agent peer."""

import pytest
import json
import time


class TestIdentity:
    def test_generate_identity(self):
        from hive.core.identity import generate_identity
        identity = generate_identity("TestUser")
        assert identity.did.startswith("hive:")
        assert len(identity.peer_id) == 16
        assert identity.display_name == "TestUser"
        assert identity.public_signing_key_hex
        assert identity.public_encryption_key_hex

    def test_identity_sign_verify(self):
        from hive.core.identity import generate_identity
        identity = generate_identity()
        message = b"Hello P2P"
        signature = identity.sign(message)
        assert len(signature) == 64  # Ed25519 signature

    def test_identity_fingerprint(self):
        from hive.core.identity import generate_identity
        identity = generate_identity()
        fp = identity.fingerprint()
        assert len(fp) > 20  # groups of 5 chars with spaces

    def test_identity_to_dict(self):
        from hive.core.identity import generate_identity
        identity = generate_identity("Test")
        d = identity.to_dict()
        assert "did" in d
        assert "peer_id" in d
        assert "public_signing_key" in d

    def test_save_load_identity(self, tmp_path, monkeypatch):
        from hive.core.identity import generate_identity, save_identity, load_identity, identity_exists
        monkeypatch.setattr("hive.core.identity.KEYSTORE_DIR", tmp_path / "keystore")
        identity = generate_identity("SaveTest")
        save_identity(identity)
        assert identity_exists()
        loaded = load_identity()
        assert loaded is not None
        assert loaded.did == identity.did

    def test_import_peer(self):
        from hive.core.identity import generate_identity, import_peer
        peer = generate_identity("Peer")
        imported = import_peer(peer.public_signing_key_hex, peer.public_encryption_key_hex, "Peer")
        assert imported["did"] == peer.did
        assert imported["display_name"] == "Peer"


class TestCrypto:
    def test_encrypt_decrypt(self):
        from hive.core.identity import generate_identity
        from hive.core.crypto import encrypt_message, decrypt_message
        from nacl.public import PublicKey
        from nacl.encoding import HexEncoder

        sender = generate_identity("Sender")
        recipient = generate_identity("Recipient")

        encrypted = encrypt_message(
            "Hello E2EE!",
            sender.signing_key,
            sender.encryption_key,
            recipient.public_key,
        )
        assert encrypted.ciphertext
        assert encrypted.sender_did == sender.did

        decrypted = decrypt_message(
            encrypted,
            recipient.encryption_key,
            sender.public_encryption_key_hex,
            sender.public_signing_key_hex,
        )
        assert decrypted["content"] == "Hello E2EE!"
        assert decrypted["verified"] is True

    def test_message_serialization(self):
        from hive.core.identity import generate_identity
        from hive.core.crypto import encrypt_message, EncryptedMessage

        sender = generate_identity()
        recipient = generate_identity()
        encrypted = encrypt_message("test", sender.signing_key, sender.encryption_key, recipient.public_key)

        wire = encrypted.to_wire()
        restored = EncryptedMessage.from_wire(wire)
        assert restored.sender_did == encrypted.sender_did
        assert restored.ciphertext == encrypted.ciphertext

    def test_symmetric_encrypt_decrypt(self):
        from hive.core.crypto import encrypt_symmetric, decrypt_symmetric
        from nacl.utils import random as nacl_random
        from nacl.secret import SecretBox

        key = nacl_random(SecretBox.KEY_SIZE)
        plaintext = b"Secret data"
        ciphertext, nonce = encrypt_symmetric(plaintext, key)
        # ciphertext includes the MAC, need to pass full ciphertext to decrypt
        decrypted = decrypt_symmetric(ciphertext, nonce, key)
        assert decrypted == plaintext


class TestSignalProtocol:
    def test_session_initiation(self):
        from hive.core.identity import generate_identity
        from hive.core.signal_protocol import SignalSession

        alice = generate_identity("Alice")
        bob = generate_identity("Bob")

        session = SignalSession.initiate(
            alice.encryption_key,
            bob.public_encryption_key_hex,
            bob.did,
        )
        assert session.session.peer_did == bob.did
        assert session.session.sending_counter == 0

    def test_encrypt_decrypt_roundtrip(self):
        from hive.core.identity import generate_identity
        from hive.core.signal_protocol import SignalSession

        alice = generate_identity("Alice")
        bob = generate_identity("Bob")

        alice_session = SignalSession.initiate(alice.encryption_key, bob.public_encryption_key_hex, bob.did)
        bob_session = SignalSession.accept(bob.encryption_key, alice.public_encryption_key_hex, alice.did)

        # Alice encrypts
        encrypted = alice_session.encrypt("Hello Bob!")
        assert encrypted["counter"] == 1

        # Bob decrypts
        decrypted = bob_session.decrypt(encrypted)
        assert decrypted == "Hello Bob!"

    def test_multiple_messages(self):
        from hive.core.identity import generate_identity
        from hive.core.signal_protocol import SignalSession

        alice = generate_identity()
        bob = generate_identity()

        alice_session = SignalSession.initiate(alice.encryption_key, bob.public_encryption_key_hex, bob.did)
        bob_session = SignalSession.accept(bob.encryption_key, alice.public_encryption_key_hex, alice.did)

        for i in range(5):
            encrypted = alice_session.encrypt(f"Message {i}")
            decrypted = bob_session.decrypt(encrypted)
            assert decrypted == f"Message {i}"

        assert alice_session.session.sending_counter == 5
        assert bob_session.session.receiving_counter == 5

    def test_session_manager(self):
        from hive.core.identity import generate_identity
        from hive.core.signal_protocol import SessionManager

        alice = generate_identity()
        bob = generate_identity()

        manager = SessionManager()
        session = manager.get_or_create_session(bob.did, alice.encryption_key, bob.public_encryption_key_hex)
        assert session is not None
        assert manager.get_session(bob.did) is session
        assert len(manager.list_sessions()) == 1


class TestP2PNetwork:
    def test_message_serialization(self):
        from hive.core.p2p_network import P2PMessage, MSG_PING

        msg = P2PMessage(msg_type=MSG_PING, payload=b"test")
        data = msg.serialize()
        restored = P2PMessage.deserialize(data)
        assert restored.msg_type == MSG_PING
        assert restored.payload == b"test"

    def test_peer_info(self):
        from hive.core.p2p_network import PeerInfo

        peer = PeerInfo(
            did="hive:abc123",
            peer_id="abc123",
            display_name="Test",
            address=("127.0.0.1", 4242),
            public_signing_key="key1",
            public_encryption_key="key2",
        )
        d = peer.to_dict()
        assert d["did"] == "hive:abc123"
        assert d["address"] == "127.0.0.1:4242"

    def test_invite_code(self):
        from hive.core.identity import generate_identity
        from hive.core.p2p_network import P2PNetwork

        identity = generate_identity("Test")
        network = P2PNetwork(identity, port=14242)
        code = network.generate_invite_code()
        assert len(code) > 20  # base64 encoded


class TestAgentPeer:
    def test_create_agent_peer(self):
        from hive.core.agent_peer import create_agent_peer

        agent = create_agent_peer(
            name="TestBot",
            system_prompt="You are a test bot.",
            provider="ollama",
            model="llama3.2",
        )
        assert agent.did.startswith("hive:")
        assert agent.name == "TestBot"
        assert agent.provider == "ollama"

    def test_agent_registry(self):
        from hive.core.agent_peer import create_agent_peer, AgentRegistry

        registry = AgentRegistry()
        agent = create_agent_peer("Bot1", "You are helpful.")
        registry.register(agent)

        assert registry.get(agent.did) is agent
        assert registry.get_by_name("Bot1") is agent
        assert len(registry.list_agents()) == 1

    def test_agent_to_dict(self):
        from hive.core.agent_peer import create_agent_peer

        agent = create_agent_peer("DictBot", "Test", "openai", "gpt-4.1-mini", use_local=False)
        d = agent.to_dict()
        assert d["name"] == "DictBot"
        assert d["provider"] == "openai"
        assert d["use_local"] is False
