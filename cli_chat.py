"""
CLI Chat — Terminal-based P2P encrypted chat client.
Use for testing P2P connections without the web UI.
"""

import sys
import os
import time
import json
import threading
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hive.core.identity import generate_identity, load_identity, save_identity, identity_exists
from hive.core.p2p_network import P2PNetwork, PeerInfo
from hive.core.signal_protocol import SessionManager
from hive.core.crypto import encrypt_message, decrypt_message

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class CLIChat:
    """Terminal-based P2P chat."""

    def __init__(self):
        self.identity = None
        self.network = None
        self.session_mgr = SessionManager()
        self._running = False

    def setup(self):
        """Initialize or load identity."""
        if identity_exists():
            self.identity = load_identity()
            if self.identity:
                print(f"Loaded identity: {self.identity.did}")
                print(f"Peer ID: {self.identity.peer_id}")
                print(f"Name: {self.identity.display_name}")
                return

        print("No identity found. Creating new one...")
        name = input("Your display name: ").strip() or "Anonymous"
        self.identity = generate_identity(name)
        save_identity(self.identity)
        print(f"Created identity: {self.identity.did}")
        print(f"Peer ID: {self.identity.peer_id}")
        print(f"Fingerprint: {self.identity.fingerprint()}")

    def start_network(self, port: int = 4242):
        """Start P2P network."""
        self.network = P2PNetwork(self.identity, port=port)
        self.network.on_message(self._on_message)
        self.network.start()
        print(f"\nP2P network started on port {port}")
        print(f"Invite code: {self.network.generate_invite_code()}")

    def connect_peer(self, invite_code: str = None):
        """Connect to a peer."""
        if not invite_code:
            invite_code = input("\nEnter peer's invite code: ").strip()
        if not invite_code:
            return

        peer = self.network.connect_from_invite(invite_code)
        if peer:
            print(f"Connected to: {peer.display_name} ({peer.did})")
        else:
            print("Failed to connect. Check the invite code.")

    def list_peers(self):
        """List known peers."""
        if not self.network:
            print("Network not started.")
            return
        peers = self.network.get_online_peers()
        if not peers:
            print("No peers connected. Use 'connect' to add peers.")
            return
        print(f"\nOnline peers ({len(peers)}):")
        for i, peer in enumerate(peers):
            print(f"  [{i}] {peer.display_name} ({peer.peer_id}) - {peer.address}")

    def send_message(self, peer_did: str, text: str):
        """Send an encrypted message to a peer."""
        peer = self.network.peers.get(peer_did)
        if not peer:
            print(f"Peer not found: {peer_did}")
            return

        # Get or create session
        session = self.session_mgr.get_or_create_session(
            peer_did, self.identity.encryption_key, peer.public_encryption_key
        )

        # Encrypt and send
        encrypted = session.encrypt(text)
        msg_data = json.dumps({
            "content": text,
            "sender": self.identity.did,
            "timestamp": time.time(),
            "encrypted": encrypted,
        })

        # Send via network
        from hive.core.p2p_network import P2PMessage, MSG_ENCRYPTED
        msg = P2PMessage(MSG_ENCRYPTED, msg_data.encode())
        self.network._send_raw(msg.serialize(), peer.address)
        print(f"  → [{peer.display_name}]: {text}")

    def _on_message(self, msg, addr):
        """Handle incoming P2P message."""
        from hive.core.p2p_network import MSG_ENCRYPTED
        if msg.msg_type != MSG_ENCRYPTED:
            return

        try:
            data = json.loads(msg.payload)
            sender_did = data.get("sender", "")
            content = data.get("content", "")
            encrypted = data.get("encrypted", {})

            peer = self.network.peers.get(sender_did)
            name = peer.display_name if peer else sender_did[:16]

            # Decrypt if we have a session
            session = self.session_mgr.get_session(sender_did)
            if session and encrypted:
                try:
                    content = session.decrypt(encrypted)
                except Exception:
                    pass  # Use plaintext content as fallback

            print(f"\n  ← [{name}]: {content}")
        except Exception as e:
            logger.debug(f"Message parse error: {e}")

    def chat_loop(self, peer_did: str = None):
        """Interactive chat loop."""
        if peer_did:
            peer = self.network.peers.get(peer_did)
            if not peer:
                print(f"Peer not found: {peer_did}")
                return
            print(f"\nChatting with: {peer.display_name}")
            print("Type 'quit' to exit, 'switch' to change peer\n")

        self._running = True
        while self._running:
            try:
                line = input("> ").strip()
                if not line:
                    continue
                if line == "quit":
                    break
                if line == "switch":
                    self.list_peers()
                    idx = input("Peer number: ").strip()
                    try:
                        peers = self.network.get_online_peers()
                        peer_did = peers[int(idx)].did
                        peer = self.network.peers[peer_did]
                        print(f"Switched to: {peer.display_name}")
                    except (ValueError, IndexError):
                        print("Invalid selection")
                    continue
                if line == "peers":
                    self.list_peers()
                    continue
                if line == "invite":
                    print(f"\nYour invite code:\n{self.network.generate_invite_code()}")
                    continue

                if peer_did:
                    self.send_message(peer_did, line)
                else:
                    print("No peer selected. Use 'switch' to select a peer.")

            except KeyboardInterrupt:
                break
            except EOFError:
                break

        self._running = False

    def run(self):
        """Main entry point."""
        print("=" * 50)
        print("  Hive P2P Chat — Terminal Client")
        print("=" * 50)

        self.setup()
        self.start_network()

        print("\nCommands:")
        print("  connect  — Connect to peer via invite code")
        print("  peers    — List online peers")
        print("  switch   — Select peer to chat with")
        print("  invite   — Show your invite code")
        print("  quit     — Exit chat")
        print()

        self.chat_loop()

        if self.network:
            self.network.stop()
        print("\nGoodbye!")


if __name__ == "__main__":
    chat = CLIChat()
    chat.run()
