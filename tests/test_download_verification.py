import hashlib
from pathlib import Path

import pytest

from veyra.download_verification import (
    DownloadVerificationError,
    normalize_sha256,
    sha256_file,
    verify_sha256,
)


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    payload = b"VEYRA-download-verification"
    path = tmp_path / "sample.bin"
    path.write_bytes(payload)
    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_verify_sha256_accepts_case_insensitive_digest(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"verified")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert verify_sha256(path, digest.upper()) == digest


def test_verify_sha256_rejects_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"verified")
    expected = hashlib.sha256(b"different").hexdigest()
    with pytest.raises(DownloadVerificationError, match="verification failed"):
        verify_sha256(path, expected)


def test_normalize_sha256_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError):
        normalize_sha256("not-a-digest")
    with pytest.raises(ValueError):
        normalize_sha256("0" * 63)


def test_sha256_file_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sha256_file(tmp_path / "missing.bin")
