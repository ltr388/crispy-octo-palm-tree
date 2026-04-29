"""Tests for ISOHandler."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from win11_customizer.iso_handler import ISOHandler, ISOHandlerError


# ---------------------------------------------------------------------------
# Helpers to create minimal fake ISOs for unit testing
# ---------------------------------------------------------------------------

def _make_fake_iso(path: Path, *, large: bool = True, valid_magic: bool = True) -> None:
    """Write a bare-minimum file that looks (or doesn't look) like an ISO."""
    # ISO 9660 magic "CD001" lives at byte offset 32769
    required_size = ISOHandler.MIN_ISO_SIZE_BYTES if large else 1024

    data = bytearray(required_size)
    if valid_magic and required_size > 32773:
        # Primary Volume Descriptor type byte (0x01) at sector 16 (offset 32768)
        # followed by "CD001"
        offset = 32768
        data[offset] = 0x01
        data[offset + 1 : offset + 6] = b"CD001"

    path.write_bytes(bytes(data))


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

class TestValidate:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        h = ISOHandler(tmp_path / "nonexistent.iso", work_dir=tmp_path)
        with pytest.raises(ISOHandlerError, match="not found"):
            h.validate()

    def test_too_small_raises(self, tmp_path: Path) -> None:
        iso = tmp_path / "small.iso"
        _make_fake_iso(iso, large=False, valid_magic=True)
        h = ISOHandler(iso, work_dir=tmp_path)
        with pytest.raises(ISOHandlerError, match="too small"):
            h.validate()

    def test_bad_magic_raises(self, tmp_path: Path) -> None:
        iso = tmp_path / "bad_magic.iso"
        _make_fake_iso(iso, large=True, valid_magic=False)
        h = ISOHandler(iso, work_dir=tmp_path)
        with pytest.raises(ISOHandlerError, match="ISO 9660"):
            h.validate()

    def test_valid_iso_passes(self, tmp_path: Path) -> None:
        iso = tmp_path / "valid.iso"
        _make_fake_iso(iso, large=True, valid_magic=True)
        h = ISOHandler(iso, work_dir=tmp_path)
        # Should not raise
        h.validate()


# ---------------------------------------------------------------------------
# checksum()
# ---------------------------------------------------------------------------

class TestChecksum:
    def test_sha256_returns_hex_string(self, tmp_path: Path) -> None:
        iso = tmp_path / "small.iso"
        iso.write_bytes(b"hello world")
        h = ISOHandler(iso, work_dir=tmp_path)
        digest = h.checksum()
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_md5_algorithm(self, tmp_path: Path) -> None:
        iso = tmp_path / "small.iso"
        iso.write_bytes(b"hello world")
        h = ISOHandler(iso, work_dir=tmp_path)
        digest = h.checksum("md5")
        assert len(digest) == 32


# ---------------------------------------------------------------------------
# repack() without extraction raises
# ---------------------------------------------------------------------------

class TestRepackGuard:
    def test_repack_before_extract_raises(self, tmp_path: Path) -> None:
        iso = tmp_path / "fake.iso"
        iso.write_bytes(b"\x00" * 100)
        h = ISOHandler(iso, work_dir=tmp_path)
        with pytest.raises(ISOHandlerError, match="not been extracted"):
            h.repack(tmp_path / "out.iso")


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_cleans_up_temp_dir(self, tmp_path: Path) -> None:
        iso = tmp_path / "fake.iso"
        iso.write_bytes(b"\x00" * 100)
        with ISOHandler(iso) as h:
            work = h.work_dir
            assert work.exists()
        # After exiting the work dir should be gone (it was auto-created)
        assert not work.exists()

    def test_provided_work_dir_not_removed(self, tmp_path: Path) -> None:
        iso = tmp_path / "fake.iso"
        iso.write_bytes(b"\x00" * 100)
        explicit = tmp_path / "explicit_work"
        explicit.mkdir()
        with ISOHandler(iso, work_dir=explicit) as h:
            pass
        assert explicit.exists()
