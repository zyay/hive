"""
QR Code Pairing — generate and display QR codes for P2P invite codes.
Uses ASCII QR codes for terminal display + PNG generation for UI.
"""

import json
import base64
import logging

logger = logging.getLogger(__name__)


def generate_invite_qr(invite_data: dict) -> str:
    """Generate an ASCII QR code for terminal display."""
    payload = base64.urlsafe_b64encode(json.dumps(invite_data).encode()).decode()

    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(payload)
        qr.make(fit=True)

        # Generate ASCII art
        lines = []
        matrix = qr.get_matrix()
        for row in matrix:
            line = ""
            for cell in row:
                line += "██" if cell else "  "
            lines.append(line)
        return "\n".join(lines)
    except ImportError:
        # Fallback: just show the payload as text
        return f"[QR Code requires 'qrcode' package]\nInvite code: {payload}"


def generate_invite_data(did: str, display_name: str, signing_key: str,
                          encryption_key: str, ip: str = "", port: int = 4242) -> dict:
    """Create invite data dict for QR encoding."""
    return {
        "v": 1,  # Version
        "did": did,
        "name": display_name,
        "signing_key": signing_key,
        "encryption_key": encryption_key,
        "ip": ip,
        "port": port,
    }


def parse_invite_qr(data: str) -> dict | None:
    """Parse invite data from QR code content."""
    try:
        return json.loads(base64.urlsafe_b64decode(data))
    except Exception as e:
        logger.error(f"Failed to parse invite QR: {e}")
        return None


def format_safety_number(fingerprint: str) -> str:
    """Format a fingerprint as a safety number for OOB verification."""
    # Remove spaces and format as groups
    fp = fingerprint.replace(" ", "")
    groups = [fp[i:i+5] for i in range(0, len(fp), 5)]
    return "\n".join(" ".join(groups[i:i+3]) for i in range(0, len(groups), 3))


def verify_safety_number(local_fingerprint: str, remote_fingerprint: str) -> bool:
    """Compare safety numbers for OOB verification."""
    local = local_fingerprint.replace(" ", "").lower()
    remote = remote_fingerprint.replace(" ", "").lower()
    return local == remote
