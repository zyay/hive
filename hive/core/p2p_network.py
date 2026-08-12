"""
P2P Network Transport — UDP-based peer-to-peer communication.
Features: mDNS local discovery, UDP hole punching, invite codes.
"""

import json
import socket
import struct
import time
import asyncio
import logging
import threading
from typing import Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Protocol constants
MAGIC = b"HIVE"
VERSION = 1
HEADER_SIZE = 32  # magic(4) + version(1) + msg_type(1) + payload_len(4) + timestamp(8) + reserved(14)

# Message types
MSG_PING = 0x01
MSG_PONG = 0x02
MSG_HANDSHAKE = 0x03
MSG_ENCRYPTED = 0x10
MSG_PEER_DISCOVER = 0x20
MSG_PEER_ANNOUNCE = 0x21
MSG_RELAY = 0x30

DEFAULT_PORT = 4242
MDNS_SERVICE_TYPE = "_hive-p2p._udp.local."


@dataclass
class PeerInfo:
    """Information about a connected peer."""
    did: str
    peer_id: str
    display_name: str
    address: tuple  # (ip, port)
    public_signing_key: str
    public_encryption_key: str
    last_seen: float = 0.0
    is_online: bool = False
    nat_type: str = "unknown"  # "open", "symmetric", "unknown"

    def to_dict(self) -> dict:
        return {
            "did": self.did,
            "peer_id": self.peer_id,
            "display_name": self.display_name,
            "address": f"{self.address[0]}:{self.address[1]}",
            "last_seen": self.last_seen,
            "is_online": self.is_online,
        }


@dataclass
class P2PMessage:
    """A message in the P2P protocol."""
    msg_type: int
    payload: bytes
    sender_did: str = ""
    timestamp: float = 0.0

    def serialize(self) -> bytes:
        """Serialize to wire format."""
        header = MAGIC
        header += struct.pack("!B", VERSION)
        header += struct.pack("!B", self.msg_type)
        header += struct.pack("!I", len(self.payload))
        header += struct.pack("!d", self.timestamp or time.time())
        header += b"\x00" * 14  # reserved
        return header + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> "P2PMessage":
        """Deserialize from wire format."""
        if len(data) < HEADER_SIZE:
            raise ValueError("Message too short")
        if data[:4] != MAGIC:
            raise ValueError("Invalid magic bytes")
        version = struct.unpack("!B", data[4:5])[0]
        msg_type = struct.unpack("!B", data[5:6])[0]
        payload_len = struct.unpack("!I", data[6:10])[0]
        timestamp = struct.unpack("!d", data[10:18])[0]
        payload = data[HEADER_SIZE:HEADER_SIZE + payload_len]
        return cls(msg_type=msg_type, payload=payload, timestamp=timestamp)


class P2PNetwork:
    """P2P network transport layer."""

    def __init__(self, identity, port: int = DEFAULT_PORT):
        self.identity = identity
        self.port = port
        self.peers: dict[str, PeerInfo] = {}  # did -> PeerInfo
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._message_handlers: list[Callable] = []
        self._mdns_browser = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self):
        """Start the P2P network listener."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.bind(("0.0.0.0", self.port))
        self._socket.settimeout(1.0)
        self._running = True

        # Start listener thread
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        # Start mDNS discovery
        self._start_mdns()

        # Announce ourselves
        self._broadcast_announce()

        logger.info(f"P2P network started on port {self.port}, DID: {self.identity.did}")

    def stop(self):
        """Stop the P2P network."""
        self._running = False
        if self._socket:
            self._socket.close()
        if self._mdns_browser:
            try:
                self._mdns_browser.cancel()
            except Exception:
                pass
        logger.info("P2P network stopped")

    def _listen_loop(self):
        """Main UDP listener loop."""
        while self._running:
            try:
                data, addr = self._socket.recvfrom(65535)
                self._handle_incoming(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Listener error: {e}")

    def _handle_incoming(self, data: bytes, addr: tuple):
        """Handle incoming UDP packet."""
        try:
            msg = P2PMessage.deserialize(data)
        except ValueError as e:
            logger.debug(f"Invalid message from {addr}: {e}")
            return

        if msg.msg_type == MSG_PING:
            self._send_pong(addr)
        elif msg.msg_type == MSG_PONG:
            self._handle_pong(addr, msg)
        elif msg.msg_type == MSG_HANDSHAKE:
            self._handle_handshake(addr, msg)
        elif msg.msg_type == MSG_ENCRYPTED:
            self._handle_encrypted(addr, msg)
        elif msg.msg_type == MSG_PEER_ANNOUNCE:
            self._handle_announce(addr, msg)
        elif msg.msg_type == MSG_RELAY:
            self._handle_relay(addr, msg)

        # Notify handlers
        for handler in self._message_handlers:
            try:
                handler(msg, addr)
            except Exception as e:
                logger.error(f"Handler error: {e}")

    def _send_pong(self, addr: tuple):
        """Respond to ping with pong."""
        pong = P2PMessage(msg_type=MSG_PONG, payload=self.identity.did.encode())
        self._send_raw(pong.serialize(), addr)

    def _handle_pong(self, addr: tuple, msg: P2PMessage):
        """Handle pong response — peer is alive."""
        did = msg.payload.decode()
        if did in self.peers:
            self.peers[did].last_seen = time.time()
            self.peers[did].is_online = True

    def _handle_handshake(self, addr: tuple, msg: P2PMessage):
        """Handle handshake — peer wants to establish connection."""
        try:
            data = json.loads(msg.payload)
            did = data.get("did", "")
            peer = PeerInfo(
                did=did,
                peer_id=did[5:21] if len(did) > 21 else did,
                display_name=data.get("display_name", ""),
                address=addr,
                public_signing_key=data.get("public_signing_key", ""),
                public_encryption_key=data.get("public_encryption_key", ""),
                last_seen=time.time(),
                is_online=True,
            )
            self.peers[did] = peer
            logger.info(f"Handshake from peer: {did} ({peer.display_name})")

            # Send handshake response
            response = json.dumps({
                "did": self.identity.did,
                "display_name": self.identity.display_name,
                "public_signing_key": self.identity.public_signing_key_hex,
                "public_encryption_key": self.identity.public_encryption_key_hex,
            }).encode()
            self._send_raw(P2PMessage(MSG_HANDSHAKE, response).serialize(), addr)

        except Exception as e:
            logger.error(f"Handshake error: {e}")

    def _handle_encrypted(self, addr: tuple, msg: P2PMessage):
        """Handle encrypted message — pass to crypto layer."""
        # This will be handled by the signal protocol layer
        pass

    def _handle_announce(self, addr: tuple, msg: P2PMessage):
        """Handle peer announcement — new peer on the network."""
        try:
            data = json.loads(msg.payload)
            did = data.get("did", "")
            if did != self.identity.did and did not in self.peers:
                peer = PeerInfo(
                    did=did,
                    peer_id=did[5:21] if len(did) > 21 else did,
                    display_name=data.get("display_name", ""),
                    address=addr,
                    public_signing_key=data.get("public_signing_key", ""),
                    public_encryption_key=data.get("public_encryption_key", ""),
                    last_seen=time.time(),
                    is_online=True,
                )
                self.peers[did] = peer
                logger.info(f"Discovered peer: {did} ({peer.display_name}) at {addr}")
        except Exception as e:
            logger.error(f"Announce error: {e}")

    def _handle_relay(self, addr: tuple, msg: P2PMessage):
        """Handle relay message — forward to target peer."""
        pass

    def _broadcast_announce(self):
        """Announce ourselves to the local network."""
        payload = json.dumps({
            "did": self.identity.did,
            "display_name": self.identity.display_name,
            "public_signing_key": self.identity.public_signing_key_hex,
            "public_encryption_key": self.identity.public_encryption_key_hex,
        }).encode()
        msg = P2PMessage(MSG_PEER_ANNOUNCE, payload).serialize()

        # Broadcast to local network
        try:
            self._socket.sendto(msg, ("<broadcast>", self.port))
        except Exception as e:
            logger.debug(f"Broadcast error: {e}")

    def _start_mdns(self):
        """Start mDNS service discovery."""
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo
            import socket as sock

            self._zeroconf = Zeroconf()

            # Register our service
            info = ServiceInfo(
                MDNS_SERVICE_TYPE,
                f"hive-{self.identity.peer_id}.{MDNS_SERVICE_TYPE}",
                addresses=[sock.inet_aton(self._get_local_ip())],
                port=self.port,
                properties={
                    "did": self.identity.did,
                    "name": self.identity.display_name,
                },
            )
            self._zeroconf.register_service(info)

            # Browse for other services
            self._mdns_browser = ServiceBrowser(
                self._zeroconf, MDNS_SERVICE_TYPE,
                handlers=[self._on_mdns_service],
            )
            logger.info("mDNS discovery started")
        except Exception as e:
            logger.warning(f"mDNS failed: {e}")

    def _on_mdns_service(self, zeroconf, service_type, name, state_change):
        """Handle mDNS service discovery event."""
        from zeroconf import ServiceStateChange
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                did = info.properties.get(b"did", b"").decode()
                display_name = info.properties.get(b"name", b"").decode()
                if did and did != self.identity.did:
                    import socket as sock
                    addr = (sock.inet_ntoa(info.addresses[0]), info.port)
                    peer = PeerInfo(
                        did=did,
                        peer_id=did[5:21] if len(did) > 21 else did,
                        display_name=display_name,
                        address=addr,
                        public_signing_key="",
                        public_encryption_key="",
                        last_seen=time.time(),
                        is_online=True,
                    )
                    self.peers[did] = peer
                    logger.info(f"mDNS discovered peer: {did} ({display_name}) at {addr}")

                    # Initiate handshake
                    self.send_handshake(addr)

    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def send_handshake(self, addr: tuple):
        """Send handshake to a peer."""
        payload = json.dumps({
            "did": self.identity.did,
            "display_name": self.identity.display_name,
            "public_signing_key": self.identity.public_signing_key_hex,
            "public_encryption_key": self.identity.public_encryption_key_hex,
        }).encode()
        msg = P2PMessage(MSG_HANDSHAKE, payload)
        self._send_raw(msg.serialize(), addr)

    def send_encrypted(self, peer_did: str, encrypted_data: bytes):
        """Send encrypted message to a peer."""
        peer = self.peers.get(peer_did)
        if not peer:
            logger.error(f"Peer not found: {peer_did}")
            return
        msg = P2PMessage(MSG_ENCRYPTED, encrypted_data)
        self._send_raw(msg.serialize(), peer.address)

    def _send_raw(self, data: bytes, addr: tuple):
        """Send raw bytes to an address."""
        if self._socket:
            try:
                self._socket.sendto(data, addr)
            except Exception as e:
                logger.error(f"Send error to {addr}: {e}")

    def on_message(self, handler: Callable):
        """Register a message handler."""
        self._message_handlers.append(handler)

    def ping_all(self):
        """Ping all known peers."""
        ping = P2PMessage(MSG_PING, self.identity.did.encode())
        for peer in self.peers.values():
            self._send_raw(ping.serialize(), peer.address)

    def get_online_peers(self) -> list[PeerInfo]:
        """Get list of online peers."""
        cutoff = time.time() - 30  # 30 second timeout
        return [p for p in self.peers.values() if p.last_seen > cutoff]

    def generate_invite_code(self) -> str:
        """Generate an invite code for direct connection."""
        import base64
        data = json.dumps({
            "did": self.identity.did,
            "name": self.identity.display_name,
            "ip": self._get_local_ip(),
            "port": self.port,
            "signing_key": self.identity.public_signing_key_hex,
            "encryption_key": self.identity.public_encryption_key_hex,
        })
        return base64.urlsafe_b64encode(data.encode()).decode()

    def connect_from_invite(self, code: str):
        """Connect to a peer using an invite code."""
        import base64
        try:
            data = json.loads(base64.urlsafe_b64decode(code))
            addr = (data["ip"], data["port"])
            peer = PeerInfo(
                did=data["did"],
                peer_id=data["did"][5:21] if len(data["did"]) > 21 else data["did"],
                display_name=data.get("name", ""),
                address=addr,
                public_signing_key=data.get("signing_key", ""),
                public_encryption_key=data.get("encryption_key", ""),
                last_seen=time.time(),
                is_online=True,
            )
            self.peers[peer.did] = peer
            self.send_handshake(addr)
            logger.info(f"Connected via invite: {peer.did} ({peer.display_name})")
            return peer
        except Exception as e:
            logger.error(f"Invite connection failed: {e}")
            return None
