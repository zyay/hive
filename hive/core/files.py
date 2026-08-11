"""
File sharing in chat — upload, store, and share files between users in rooms.
Files are stored locally and accessible via unique URLs.
Compatible with Tailscale for secure peer-to-peer access.
"""

import os
import uuid
import time
import shutil
import mimetypes
import logging
from pathlib import Path

from hive.core.db import get_connection

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path("uploads")


def init_uploads():
    """Create uploads directory."""
    UPLOADS_DIR.mkdir(exist_ok=True)
    (UPLOADS_DIR / "rooms").mkdir(exist_ok=True)


async def upload_file(room_id: str, uploader_id: str, filename: str, content: bytes) -> dict:
    """Upload a file to a room. Returns file metadata."""
    file_id = str(uuid.uuid4())[:12]
    now = time.time()

    # Determine file extension and MIME type
    ext = Path(filename).suffix.lower()
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    size = len(content)

    # Save file
    room_dir = UPLOADS_DIR / "rooms" / room_id
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / f"{file_id}{ext}"
    file_path.write_bytes(content)

    # Store metadata in DB
    conn = get_connection()
    conn.execute(
        "INSERT INTO shared_files (id, room_id, uploader_id, filename, file_path, mime_type, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (file_id, room_id, uploader_id, filename, str(file_path), mime_type, size, now)
    )
    conn.commit()
    conn.close()

    logger.info(f"File uploaded: {filename} ({size} bytes) to room {room_id}")
    return {
        "id": file_id,
        "room_id": room_id,
        "uploader_id": uploader_id,
        "filename": filename,
        "mime_type": mime_type,
        "size": size,
        "created_at": now,
        "url": f"/api/files/{file_id}/download",
    }


async def get_file(file_id: str) -> dict | None:
    """Get file metadata."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM shared_files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


async def get_room_files(room_id: str, limit: int = 50) -> list[dict]:
    """List files shared in a room."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, uploader_id, filename, mime_type, size, created_at FROM shared_files WHERE room_id = ? ORDER BY created_at DESC LIMIT ?",
        (room_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def delete_file(file_id: str) -> bool:
    """Delete a shared file."""
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM shared_files WHERE id = ?", (file_id,)).fetchone()
    if row:
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    cursor = conn.execute("DELETE FROM shared_files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_file_path(file_id: str) -> Path | None:
    """Get the actual file path for download."""
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM shared_files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    if row and Path(row["file_path"]).exists():
        return Path(row["file_path"])
    return None
