"""
Security utilities — input validation, sanitization, rate limiting.
"""

import re
import time
import hashlib
import logging
from pathlib import Path
from collections import defaultdict
from functools import wraps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

MAX_STRING_LENGTH = 10000
MAX_TITLE_LENGTH = 200
MAX_PROMPT_LENGTH = 5000
MAX_FILENAME_LENGTH = 255
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

ALLOWED_FILE_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".csv", ".xml", ".html", ".css", ".sql", ".sh", ".bat", ".ps1",
    ".log", ".rst", ".toml", ".ini", ".cfg", ".conf",
}

DANGEROUS_PATH_PATTERNS = [
    r"\.\./", r"\.\.\\",  # Directory traversal
    r"^/etc/", r"^/proc/", r"^/sys/",  # Linux system dirs
    r"^C:\\Windows", r"^C:\\Program Files",  # Windows system dirs
]


def validate_string(value: str, max_length: int = MAX_STRING_LENGTH, name: str = "input") -> str:
    """Validate and truncate a string input."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if len(value) > max_length:
        raise ValueError(f"{name} exceeds maximum length of {max_length}")
    return value.strip()


def validate_filename(filename: str) -> str:
    """Validate a filename to prevent path traversal and dangerous names."""
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        raise ValueError("Invalid filename")
    # Remove path separators
    filename = Path(filename).name
    # Check for dangerous patterns
    for pattern in DANGEROUS_PATH_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            raise ValueError(f"Dangerous filename pattern detected")
    return filename


def validate_file_extension(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_FILE_EXTENSIONS


def validate_path(path: str) -> Path:
    """Validate and sanitize a file path."""
    path = path.strip()
    for pattern in DANGEROUS_PATH_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            raise ValueError(f"Dangerous path pattern detected")
    return Path(path).resolve()


def sanitize_sql_string(value: str) -> str:
    """Sanitize a string for safe use in SQL (though parameterized queries should be used)."""
    # Remove null bytes
    value = value.replace("\x00", "")
    return value


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed for the given key."""
        now = time.time()
        window_start = now - self.window_seconds

        # Remove old requests outside the window
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for the given key."""
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        return max(0, self.max_requests - len(self._requests[key]))


# Global rate limiters
auth_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 auth attempts per minute
api_limiter = RateLimiter(max_requests=120, window_seconds=60)  # 120 API calls per minute
chat_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 messages per minute


def rate_limit(limiter: RateLimiter):
    """Decorator for rate limiting endpoints."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Use a simple key based on function name
            key = fn.__name__
            if not limiter.is_allowed(key):
                from fastapi import HTTPException
                raise HTTPException(429, "Rate limit exceeded. Please try again later.")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# API Key Hashing
# ---------------------------------------------------------------------------

def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256 with a fixed salt."""
    salt = "hive_api_key_salt_v1"
    return hashlib.sha256(f"{salt}:{key}".encode()).hexdigest()


def verify_api_key(key: str, hashed: str) -> bool:
    """Verify an API key against its hash."""
    return hash_api_key(key) == hashed
