"""
E2EE File Transfer — encrypted chunked file sending over P2P.
Files are split into chunks, each encrypted independently, then reassembled.
"""

import os
import json
import time
import uuid
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass

from nacl.secret import SecretBox
from nacl.utils import random as nacl_random

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64KB chunks
UPLOADS_DIR = Path("uploads/e2ee")


@dataclass
class FileMetadata:
    """Metadata for an encrypted file transfer."""
    id: str
    filename: str
    original_size: int
    chunk_count: int
    chunk_size: int
    sha256: str
    mime_type: str
    encryption_key: bytes  # Symmetric key for file chunks
    sender_did: str
    created_at: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "original_size": self.original_size,
            "chunk_count": self.chunk_count,
            "chunk_size": self.chunk_size,
            "sha256": self.sha256,
            "mime_type": self.mime_type,
            "encryption_key": self.encryption_key.hex(),
            "sender_did": self.sender_did,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileMetadata":
        data["encryption_key"] = bytes.fromhex(data["encryption_key"])
        return cls(**data)


def encrypt_file(file_path: str, sender_did: str) -> tuple[FileMetadata, list[bytes]]:
    """
    Encrypt a file for P2P transfer.
    Returns metadata and list of encrypted chunks.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_id = str(uuid.uuid4())[:12]
    file_data = path.read_bytes()
    file_size = len(file_data)
    file_hash = hashlib.sha256(file_data).hexdigest()

    # Generate symmetric encryption key for this file
    encryption_key = nacl_random(SecretBox.KEY_SIZE)

    # Determine MIME type
    import mimetypes
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    # Split into chunks and encrypt each
    chunks = []
    chunk_count = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

    for i in range(chunk_count):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, file_size)
        chunk_data = file_data[start:end]

        # Encrypt chunk
        box = SecretBox(encryption_key)
        nonce = nacl_random(SecretBox.NONCE_SIZE)
        encrypted = box.encrypt(chunk_data, nonce)
        # Store as nonce + ciphertext
        chunks.append(encrypted.nonce + encrypted.ciphertext)

    metadata = FileMetadata(
        id=file_id,
        filename=path.name,
        original_size=file_size,
        chunk_count=chunk_count,
        chunk_size=CHUNK_SIZE,
        sha256=file_hash,
        mime_type=mime_type,
        encryption_key=encryption_key,
        sender_did=sender_did,
        created_at=time.time(),
    )

    logger.info(f"Encrypted file: {path.name} ({file_size} bytes, {chunk_count} chunks)")
    return metadata, chunks


def decrypt_file(metadata: FileMetadata, chunks: list[bytes], output_dir: str = None) -> Path:
    """
    Decrypt and reassemble a file from encrypted chunks.
    Returns path to decrypted file.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    output_dir = Path(output_dir) if output_dir else UPLOADS_DIR

    box = SecretBox(metadata.encryption_key)
    decrypted_chunks = []

    for i, encrypted_chunk in enumerate(chunks):
        # Split nonce and ciphertext
        nonce = encrypted_chunk[:SecretBox.NONCE_SIZE]
        ciphertext = encrypted_chunk[SecretBox.NONCE_SIZE:]
        chunk_data = box.decrypt(ciphertext, nonce)
        decrypted_chunks.append(chunk_data)

    # Reassemble file
    file_data = b"".join(decrypted_chunks)

    # Verify hash
    file_hash = hashlib.sha256(file_data).hexdigest()
    if file_hash != metadata.sha256:
        raise ValueError(f"File hash mismatch! Expected {metadata.sha256}, got {file_hash}")

    # Save file
    output_path = output_dir / f"{metadata.id}_{metadata.filename}"
    output_path.write_bytes(file_data)

    logger.info(f"Decrypted file: {metadata.filename} ({len(file_data)} bytes)")
    return output_path


def prepare_file_for_transfer(metadata: FileMetadata, chunks: list[bytes]) -> list[dict]:
    """Prepare encrypted chunks for network transfer (base64 encoded)."""
    import base64
    transfer_chunks = []
    for i, chunk in enumerate(chunks):
        transfer_chunks.append({
            "file_id": metadata.id,
            "chunk_index": i,
            "data": base64.b64encode(chunk).decode(),
            "size": len(chunk),
        })
    return transfer_chunks


def receive_file_chunk(chunk_data: dict) -> tuple[str, int, bytes]:
    """Receive a file chunk from network transfer."""
    import base64
    file_id = chunk_data["file_id"]
    chunk_index = chunk_data["chunk_index"]
    data = base64.b64decode(chunk_data["data"])
    return file_id, chunk_index, data


class FileTransferManager:
    """Manages ongoing file transfers (send and receive)."""

    def __init__(self):
        self._sending: dict[str, dict] = {}  # file_id -> {metadata, chunks, progress}
        self._receiving: dict[str, dict] = {}  # file_id -> {metadata, chunks_received, total_chunks}

    def start_send(self, file_path: str, sender_did: str) -> tuple[FileMetadata, list[dict]]:
        """Start sending a file. Returns metadata and transfer chunks."""
        metadata, chunks = encrypt_file(file_path, sender_did)
        transfer_chunks = prepare_file_for_transfer(metadata, chunks)
        self._sending[metadata.id] = {
            "metadata": metadata,
            "chunks": transfer_chunks,
            "sent": 0,
            "total": len(transfer_chunks),
        }
        return metadata, transfer_chunks

    def start_receive(self, metadata: FileMetadata):
        """Prepare to receive a file."""
        self._receiving[metadata.id] = {
            "metadata": metadata,
            "chunks": [None] * metadata.chunk_count,
            "received": 0,
        }

    def add_chunk(self, file_id: str, chunk_index: int, data: bytes) -> bool:
        """Add a received chunk. Returns True if file is complete."""
        if file_id not in self._receiving:
            return False
        transfer = self._receiving[file_id]
        transfer["chunks"][chunk_index] = data
        transfer["received"] += 1
        return transfer["received"] == transfer["metadata"].chunk_count

    def complete_receive(self, file_id: str) -> Path | None:
        """Complete file reception and decrypt."""
        if file_id not in self._receiving:
            return None
        transfer = self._receiving[file_id]
        if transfer["received"] < transfer["metadata"].chunk_count:
            return None
        return decrypt_file(transfer["metadata"], transfer["chunks"])

    def get_progress(self, file_id: str) -> dict | None:
        """Get transfer progress."""
        if file_id in self._sending:
            s = self._sending[file_id]
            return {"direction": "send", "sent": s["sent"], "total": s["total"]}
        if file_id in self._receiving:
            r = self._receiving[file_id]
            return {"direction": "receive", "received": r["received"], "total": r["metadata"].chunk_count}
        return None
