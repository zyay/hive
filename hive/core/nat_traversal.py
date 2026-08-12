"""
NAT Traversal — STUN client + UDP hole punching.
Enables direct P2P connections between peers behind different NATs.
"""

import socket
import struct
import time
import random
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Public STUN servers for NAT discovery
STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun3.l.google.com", 19302),
]

# STUN message types
BINDING_REQUEST = 0x0001
BINDING_RESPONSE = 0x0101
MAPPED_ADDRESS = 0x0001
XOR_MAPPED_ADDRESS = 0x0020

# NAT types
NAT_OPEN = "open"            # No NAT, public IP
NAT_FULL_CONE = "full_cone"  # Any external host can send to mapped port
NAT_RESTRICTED = "restricted"  # Only hosts you've sent to can send back
NAT_SYMMETRIC = "symmetric"  # Different port for each destination
NAT_UNKNOWN = "unknown"


@dataclass
class NATInfo:
    """NAT discovery result."""
    nat_type: str
    internal_ip: str
    internal_port: int
    external_ip: str = ""
    external_port: int = 0
    stun_server: str = ""

    def to_dict(self) -> dict:
        return {
            "nat_type": self.nat_type,
            "internal_ip": self.internal_ip,
            "internal_port": self.internal_port,
            "external_ip": self.external_ip,
            "external_port": self.external_port,
            "stun_server": self.stun_server,
        }


def stun_binding_request(sock: socket.socket, server: tuple) -> dict | None:
    """Send STUN Binding Request and parse response."""
    # Build STUN Binding Request
    transaction_id = random.getrandbits(96).to_bytes(12, 'big')
    header = struct.pack("!HH", BINDING_REQUEST, 0)  # type, length
    header += transaction_id

    try:
        sock.settimeout(3.0)
        sock.sendto(header, server)
        data, addr = sock.recvfrom(1024)

        if len(data) < 20:
            return None

        msg_type, msg_len = struct.unpack("!HH", data[:4])
        if msg_type != BINDING_RESPONSE:
            return None

        # Parse attributes
        result = {"server": addr}
        offset = 20  # Skip header
        while offset < len(data):
            if offset + 4 > len(data):
                break
            attr_type, attr_len = struct.unpack("!HH", data[offset:offset+4])
            attr_data = data[offset+4:offset+4+attr_len]

            if attr_type == XOR_MAPPED_ADDRESS and len(attr_data) >= 8:
                # Parse XOR-MAPPED-ADDRESS
                family = attr_data[1]
                port = struct.unpack("!H", attr_data[2:4])[0]
                ip_bytes = attr_data[4:8]

                # XOR with magic cookie + transaction ID
                magic = struct.pack("!I", 0x2112A442)
                xor_port = port ^ (0x2112A442 >> 16)
                xor_ip = bytes(a ^ b for a, b in zip(ip_bytes, magic))

                result["external_ip"] = f"{xor_ip[0]}.{xor_ip[1]}.{xor_ip[2]}.{xor_ip[3]}"
                result["external_port"] = xor_port

            elif attr_type == MAPPED_ADDRESS and len(attr_data) >= 8:
                family = attr_data[1]
                port = struct.unpack("!H", attr_data[2:4])[0]
                ip = f"{attr_data[4]}.{attr_data[5]}.{attr_data[6]}.{attr_data[7]}"
                if "external_ip" not in result:
                    result["external_ip"] = ip
                    result["external_port"] = port

            offset += 4 + attr_len + (attr_len % 4)  # Pad to 4 bytes

        return result

    except socket.timeout:
        return None
    except Exception as e:
        logger.debug(f"STUN error with {server}: {e}")
        return None


def discover_nat(local_port: int = 0) -> NATInfo:
    """Discover NAT type and public IP using STUN."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if local_port:
        sock.bind(("0.0.0.0", local_port))
    else:
        sock.bind(("0.0.0.0", 0))

    internal_ip, internal_port = sock.getsockname()
    if internal_ip == "0.0.0.0":
        internal_ip = _get_local_ip()

    # Try multiple STUN servers
    results = []
    for server in STUN_SERVERS:
        result = stun_binding_request(sock, server)
        if result:
            results.append(result)

    sock.close()

    if not results:
        return NATInfo(
            nat_type=NAT_UNKNOWN,
            internal_ip=internal_ip,
            internal_port=internal_port,
        )

    # Analyze results
    first = results[0]
    ext_ip = first.get("external_ip", "")
    ext_port = first.get("external_port", 0)

    # Determine NAT type
    if ext_ip == internal_ip and ext_port == internal_port:
        nat_type = NAT_OPEN
    elif len(results) >= 2:
        # Check if different STUN servers give different ports
        ports = set(r.get("external_port", 0) for r in results)
        if len(ports) == 1:
            nat_type = NAT_FULL_CONE
        else:
            nat_type = NAT_SYMMETRIC
    else:
        nat_type = NAT_RESTRICTED

    return NATInfo(
        nat_type=nat_type,
        internal_ip=internal_ip,
        internal_port=internal_port,
        external_ip=ext_ip,
        external_port=ext_port,
        stun_server=first.get("server", ("",))[0],
    )


def _get_local_ip() -> str:
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def udp_hole_punch(sock: socket.socket, target_ip: str, target_port: int, packets: int = 10):
    """
    Send UDP packets to punch a hole in NAT.
    Both peers must call this simultaneously.
    """
    logger.info(f"Hole punching to {target_ip}:{target_port}")
    for i in range(packets):
        try:
            sock.sendto(b"PUNCH", (target_ip, target_port))
            time.sleep(0.1)
        except Exception as e:
            logger.debug(f"Hole punch error: {e}")


def wait_for_punch(sock: socket.socket, timeout: float = 5.0) -> tuple | None:
    """Wait for a hole punch packet from peer."""
    sock.settimeout(timeout)
    try:
        data, addr = sock.recvfrom(1024)
        if data == b"PUNCH":
            logger.info(f"Hole punch received from {addr}")
            return addr
    except socket.timeout:
        pass
    return None


def generate_connection_offer(nat_info: NATInfo, identity_did: str, display_name: str = "") -> dict:
    """Generate a connection offer for SDP-like exchange."""
    import json, base64
    offer = {
        "did": identity_did,
        "name": display_name,
        "internal_ip": nat_info.internal_ip,
        "internal_port": nat_info.internal_port,
        "external_ip": nat_info.external_ip,
        "external_port": nat_info.external_port,
        "nat_type": nat_info.nat_type,
        "timestamp": time.time(),
    }
    return offer


def encode_offer(offer: dict) -> str:
    """Encode offer as base64 string for sharing."""
    import json, base64
    return base64.urlsafe_b64encode(json.dumps(offer).encode()).decode()


def decode_offer(code: str) -> dict:
    """Decode offer from base64 string."""
    import json, base64
    return json.loads(base64.urlsafe_b64decode(code))
