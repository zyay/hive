"""
File sharing in chat — upload, store, and share files between users in rooms.
Files are stored locally and accessible via unique URLs.
Includes file type validation, size limits, and path traversal prevention.
"""

import os
import re
import uuid
import time
import shutil
import mimetypes
import logging
from pathlib import Path

from hive.core.db import get_connection
from hive.core.security import validate_filename, validate_file_extension, MAX_FILE_SIZE

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path("uploads")

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".csv", ".xml", ".html", ".css", ".sql", ".sh", ".bat", ".ps1",
    ".log", ".rst", ".toml", ".ini", ".cfg", ".conf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".tar", ".gz", ".7z", ".rar",
}

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def init_uploads():
    """Create uploads directory."""
    UPLOADS_DIR.mkdir(exist_ok=True)
    (UPLOADS_DIR / "rooms").mkdir(exist_ok=True)


def _sanitize_room_id(room_id: str) -> str:
    """Sanitize room_id to prevent path traversal."""
    safe = re.sub(r"[^\w\-]", "", room_id)
    if not safe:
        raise ValueError("Invalid room ID")
    if len(safe) > 64:
        raise ValueError("Room ID too long")
    return safe


async def upload_file(room_id: str, uploader_id: str, filename: str, content: bytes) -> dict:
    """Upload a file to a room. Returns file metadata."""
    # Validate filename
    safe_filename = validate_filename(filename)

    # Validate file extension
    ext = Path(safe_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{ext}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Validate file size
    size = len(content)
    if size > MAX_UPLOAD_SIZE:
        raise ValueError(f"File too large ({size} bytes). Maximum: {MAX_UPLOAD_SIZE // (1024*1024)}MB")
    if size == 0:
        raise ValueError("Cannot upload empty file")

    # Sanitize room_id to prevent path traversal
    safe_room_id = _sanitize_room_id(room_id)

    file_id = str(uuid.uuid4())[:12]
    now = time.time()
    mime_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"

    # Save file
    room_dir = UPLOADS_DIR / "rooms" / safe_room_id
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / f"{file_id}{ext}"
    file_path.write_bytes(content)

    # Store metadata in DB
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO shared_files (id, room_id, uploader_id, filename, file_path, mime_type, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, safe_room_id, uploader_id, safe_filename, str(file_path), mime_type, size, now)
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"File uploaded: {safe_filename} ({size} bytes) to room {safe_room_id}")
    return {
        "id": file_id,
        "room_id": safe_room_id,
        "uploader_id": uploader_id,
        "filename": safe_filename,
        "mime_type": mime_type,
        "size": size,
        "created_at": now,
        "url": f"/api/files/{file_id}/download",
    }


async def get_file(file_id: str) -> dict | None:
    """Get file metadata."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM shared_files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def get_room_files(room_id: str, limit: int = 50) -> list[dict]:
    """List files shared in a room."""
    safe_room_id = _sanitize_room_id(room_id)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, uploader_id, filename, mime_type, size, created_at FROM shared_files WHERE room_id = ? ORDER BY created_at DESC LIMIT ?",
            (safe_room_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def delete_file(file_id: str) -> bool:
    """Delete a shared file."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT file_path FROM shared_files WHERE id = ?", (file_id,)).fetchone()
        if row:
            try:
                Path(row["file_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        cursor = conn.execute("DELETE FROM shared_files WHERE id = ?", (file_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_file_path(file_id: str) -> Path | None:
    """Get the actual file path for download."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT file_path FROM shared_files WHERE id = ?", (file_id,)).fetchone()
        if row:
            path = Path(row["file_path"])
            # Verify the resolved path is still under UPLOADS_DIR
            try:
                path.resolve().relative_to(UPLOADS_DIR.resolve())
            except ValueError:
                logger.warning(f"Path traversal attempt detected for file_id={file_id}: {path}")
                return None
            if path.exists():
                return path
        return None
    finally:
        conn.close()
