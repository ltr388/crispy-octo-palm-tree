"""ISO handler – extract, modify, and repack a Windows 11 ISO image.

External tools used (must be installed on the host):
  * 7z   (p7zip-full / 7-Zip)  – used on all platforms to extract ISO contents
  * xorriso                     – used on Linux/macOS to rebuild a bootable ISO
  * oscdimg                     – used on Windows to rebuild a bootable ISO
                                  (part of the Windows ADK)

On a plain Windows host you can also mount the ISO via PowerShell (Mount-DiskImage)
instead of using 7z; this class supports both paths.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class ISOHandlerError(Exception):
    """Raised when an ISO operation fails."""


class ISOHandler:
    """Manage loading, extraction, and repacking of a Windows 11 ISO.

    Parameters
    ----------
    iso_path:
        Absolute or relative path to the source ``.iso`` file.
    work_dir:
        Directory that will hold the extracted contents.  A temporary
        directory is created automatically when *work_dir* is ``None``.
    """

    # Minimum size heuristic for a Windows 11 ISO (~4 GB)
    MIN_ISO_SIZE_BYTES = 4 * 1024 * 1024 * 1024

    def __init__(self, iso_path: str | os.PathLike, work_dir: str | os.PathLike | None = None) -> None:
        self.iso_path = Path(iso_path).resolve()
        self._owns_work_dir = work_dir is None
        if work_dir is None:
            self._work_dir_obj: tempfile.TemporaryDirectory | None = tempfile.TemporaryDirectory(
                prefix="win11_customizer_"
            )
            self.work_dir = Path(self._work_dir_obj.name)
        else:
            self._work_dir_obj = None
            self.work_dir = Path(work_dir).resolve()
            self.work_dir.mkdir(parents=True, exist_ok=True)

        self._extracted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Verify that *iso_path* looks like a valid Windows 11 ISO.

        Raises
        ------
        ISOHandlerError
            If the file does not exist, is too small, or does not carry the
            expected ISO 9660 magic bytes.
        """
        if not self.iso_path.exists():
            raise ISOHandlerError(f"ISO file not found: {self.iso_path}")
        if not self.iso_path.is_file():
            raise ISOHandlerError(f"Path is not a regular file: {self.iso_path}")

        size = self.iso_path.stat().st_size
        if size < self.MIN_ISO_SIZE_BYTES:
            raise ISOHandlerError(
                f"ISO is too small ({size / 1e9:.1f} GB).  "
                "A Windows 11 image is typically > 4 GB."
            )

        # Check ISO 9660 magic at offset 32 768 (sector 16, byte 1)
        with self.iso_path.open("rb") as fh:
            fh.seek(32769)
            magic = fh.read(5)
        if magic != b"CD001":
            raise ISOHandlerError(
                "File does not appear to be a valid ISO 9660 image "
                f"(magic bytes missing at offset 32769): {self.iso_path}"
            )
        logger.info("ISO validation passed: %s  (%.1f GB)", self.iso_path, size / 1e9)

    def extract(self) -> Path:
        """Extract the ISO contents into :attr:`work_dir`.

        Returns
        -------
        Path
            The directory that now contains the extracted ISO tree.

        Raises
        ------
        ISOHandlerError
            If the extraction tool is unavailable or fails.
        """
        if self._extracted:
            logger.debug("ISO already extracted to %s – skipping.", self.work_dir)
            return self.work_dir

        logger.info("Extracting %s → %s", self.iso_path, self.work_dir)

        if platform.system() == "Windows":
            self._extract_windows()
        else:
            self._extract_unix()

        self._extracted = True
        logger.info("Extraction complete.")
        return self.work_dir

    def repack(self, output_iso: str | os.PathLike) -> Path:
        """Repack the (modified) working directory back into an ISO image.

        Parameters
        ----------
        output_iso:
            Destination path for the new ``.iso`` file.

        Returns
        -------
        Path
            Resolved path to the newly created ISO.

        Raises
        ------
        ISOHandlerError
            If the repacking tool is unavailable or fails.
        """
        if not self._extracted:
            raise ISOHandlerError("Cannot repack: ISO has not been extracted yet.")

        out = Path(output_iso).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Repacking %s → %s", self.work_dir, out)

        if platform.system() == "Windows":
            self._repack_windows(out)
        else:
            self._repack_unix(out)

        logger.info("Repacking complete: %s  (%.1f GB)", out, out.stat().st_size / 1e9)
        return out

    def checksum(self, algorithm: str = "sha256") -> str:
        """Return the hex-digest checksum of the *source* ISO file."""
        h = hashlib.new(algorithm)
        with self.iso_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def cleanup(self) -> None:
        """Remove the working directory (only if it was created automatically)."""
        if self._owns_work_dir and self._work_dir_obj is not None:
            self._work_dir_obj.cleanup()
            self._work_dir_obj = None
            logger.debug("Working directory cleaned up.")

    # Context-manager support -----------------------------------------

    def __enter__(self) -> "ISOHandler":
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        """Run *cmd* as a subprocess, streaming output to the logger."""
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.debug("[subprocess] %s", line)
        if check and result.returncode != 0:
            raise ISOHandlerError(
                f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n"
                f"{result.stdout}"
            )
        return result

    # --- Extraction ---

    def _extract_unix(self) -> None:
        """Extract using 7z (Linux / macOS)."""
        tool = shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
        if tool is None:
            raise ISOHandlerError(
                "7z is not installed.  Install p7zip-full (Debian/Ubuntu) or "
                "p7zip (Fedora/Arch) and try again."
            )
        self._run([tool, "x", str(self.iso_path), f"-o{self.work_dir}", "-y"])

    def _extract_windows(self) -> None:
        """Mount with PowerShell then robocopy the contents (Windows)."""
        # Try 7z first for simplicity and consistency
        tool = shutil.which("7z")
        if tool:
            self._run([tool, "x", str(self.iso_path), f"-o{self.work_dir}", "-y"])
            return

        # Fallback: mount via PowerShell
        ps_mount = (
            f"$m = Mount-DiskImage -ImagePath '{self.iso_path}' -PassThru; "
            "$d = ($m | Get-Volume).DriveLetter + ':\\'; "
            f"robocopy $d '{self.work_dir}' /E /NJH /NJS /NFL /NDL; "
            "Dismount-DiskImage -ImagePath $m.ImagePath"
        )
        self._run(["powershell", "-NonInteractive", "-Command", ps_mount], check=False)

    # --- Repacking ---

    def _repack_unix(self, out: Path) -> None:
        """Repack using xorriso (Linux / macOS)."""
        tool = shutil.which("xorriso")
        if tool is None:
            raise ISOHandlerError(
                "xorriso is not installed.  Install it with: "
                "apt install xorriso  or  brew install xorriso"
            )

        # Locate the boot catalogue / efi image if present
        efi_img = self.work_dir / "efi" / "microsoft" / "boot" / "efisys.bin"
        boot_img = self.work_dir / "boot" / "etfsboot.com"

        cmd = [
            tool,
            "-as", "mkisofs",
            "-iso-level", "3",
            "-full-iso9660-filenames",
            "-udf",
            "-allow-limited-size",
            "-volid", "WIN11_CUSTOM",
            "-o", str(out),
        ]

        if boot_img.exists():
            cmd += [
                "-b", "boot/etfsboot.com",
                "-no-emul-boot",
                "-boot-load-size", "8",
                "-boot-info-table",
            ]
        if efi_img.exists():
            cmd += [
                "-eltorito-alt-boot",
                "-e", "efi/microsoft/boot/efisys.bin",
                "-no-emul-boot",
            ]

        cmd.append(str(self.work_dir))
        self._run(cmd)

    def _repack_windows(self, out: Path) -> None:
        """Repack using oscdimg (Windows ADK) or 7z as fallback."""
        oscdimg = shutil.which("oscdimg")
        if oscdimg:
            boot_dat = self.work_dir / "boot" / "etfsboot.com"
            efi_dat = self.work_dir / "efi" / "microsoft" / "boot" / "efisys.bin"
            boot_flag = ""
            if boot_dat.exists() and efi_dat.exists():
                # Dual BIOS+UEFI boot: sector 0 = BIOS (etfsboot), partition EF = UEFI (efisys)
                boot_flag = (
                    f"2#p0,e,b{boot_dat}#pEF,e,b{efi_dat}"
                )
            elif boot_dat.exists():
                boot_flag = f"1#p0,e,b{boot_dat}"
            cmd = [oscdimg, "-m", "-o", "-u2", "-udfver102"]
            if boot_flag:
                cmd += [f"-bootdata:{boot_flag}"]
            cmd += [str(self.work_dir), str(out)]
            self._run(cmd)
            return

        # Fallback: 7z cannot create bootable ISOs but is better than nothing
        tool = shutil.which("7z")
        if tool is None:
            raise ISOHandlerError(
                "Neither oscdimg nor 7z found.  Install the Windows ADK or 7-Zip."
            )
        self._run([tool, "a", "-tiso", str(out), str(self.work_dir)])
