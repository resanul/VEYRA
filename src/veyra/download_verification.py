from __future__ import annotations

import hashlib
from pathlib import Path


class DownloadVerificationError(ValueError):
    """Raised when a downloaded file does not match its expected digest."""


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


__all__ = ["DownloadVerificationError", "normalize_sha256", "sha256_file", "verify_sha256"]
