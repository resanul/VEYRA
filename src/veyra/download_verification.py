from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .download_manager import DownloadTask


class DownloadVerificationError(ValueError):
    """Raised when a downloaded file fails an integrity check."""


def normalize_sha256(value: str) -> str:
    """Return a canonical lowercase SHA-256 hex digest."""
    digest = value.strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("SHA-256 digest must be exactly 64 hexadecimal characters")
    return digest


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Calculate the SHA-256 digest of a file without loading it all into memory."""
    if not path.is_file():
        raise FileNotFoundError(path)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected_sha256: str) -> str:
    """Verify a file and return its actual digest, raising on mismatch."""
    expected = normalize_sha256(expected_sha256)
    actual = sha256_file(path)
    if actual != expected:
        raise DownloadVerificationError(
            f"SHA-256 verification failed: expected {expected}, got {actual}"
        )
    return actual


def verify_download(task: DownloadTask, *, expected_sha256: str | None = None) -> str:
    """Verify a completed DownloadTask by size and SHA-256."""
    if task.status.value != "completed":
        raise DownloadVerificationError("only completed downloads can be verified")
    path = Path(task.destination) / task.filename
    if not path.is_file():
        raise DownloadVerificationError(f"downloaded file is missing: {path}")
    if task.total_bytes > 0 and path.stat().st_size != task.total_bytes:
        raise DownloadVerificationError(
            f"file size verification failed: expected {task.total_bytes}, got {path.stat().st_size}"
        )
    expected = expected_sha256 or task.sha256
    if not expected:
        raise DownloadVerificationError("no SHA-256 digest is available for verification")
    return verify_sha256(path, expected)


__all__ = [
    "DownloadVerificationError",
    "normalize_sha256",
    "sha256_file",
    "verify_sha256",
    "verify_download",
]
