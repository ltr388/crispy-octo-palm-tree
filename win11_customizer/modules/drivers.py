"""Built-in module: offline driver injection.

Injects device driver packages (.inf + associated files) into the offline
Windows image using DISM ``/Add-Driver``.  On non-Windows hosts the module
copies the driver files to ``$OEM$\\$1\\Drivers`` so that Windows Setup
detects and installs them automatically during the setup phase.

Common use-cases:
* Pre-injecting Wi-Fi / Ethernet / chipset drivers so the device is usable
  immediately after installation (no internet required).
* Mass-deployment scenarios where the driver repository is packaged with the
  customised ISO.

Reference:
  https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/
  add-and-remove-drivers-to-an-offline-windows-image
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import logging
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

logger = logging.getLogger(__name__)


class DriversModule(BaseModule):
    """Inject driver packages into the offline Windows image.

    Configuration keys
    ------------------
    ``drivers`` (list[str])
        List of paths to driver ``.inf`` files **or** to directories
        containing driver packages.  Directories are searched recursively
        for ``.inf`` files.
    ``recurse`` (bool, default ``True``)
        When a directory path is given, scan it recursively.
    ``unsigned`` (bool, default ``False``)
        Allow unsigned drivers (passes ``/ForceUnsigned`` to DISM on
        Windows or copies them without signature verification on other
        platforms).
    ``wim_index`` (int, default 1)
        WIM image index to modify (Windows DISM path only).
    """

    metadata = ModuleMetadata(
        name="drivers",
        description="Inject .inf driver packages into the offline Windows image via DISM",
        category="drivers",
    )

    def apply(self, work_dir: Path) -> None:
        driver_sources: list[str] = self.config.get("drivers", [])
        if not driver_sources:
            self._logger.warning("DriversModule: no driver paths specified.")
            return

        recurse: bool = bool(self.config.get("recurse", True))
        unsigned: bool = bool(self.config.get("unsigned", False))

        # Resolve all .inf files from the provided paths
        inf_files: list[Path] = []
        for src_str in driver_sources:
            src = Path(src_str).resolve()
            if src.is_file() and src.suffix.lower() == ".inf":
                inf_files.append(src)
            elif src.is_dir():
                pattern = "**/*.inf" if recurse else "*.inf"
                inf_files.extend(src.glob(pattern))
            else:
                self._logger.warning("Driver path not found or not an .inf file: %s", src)

        if not inf_files:
            self._logger.warning("DriversModule: no .inf files found.")
            return

        self._logger.info("Found %d driver .inf file(s).", len(inf_files))

        if platform.system() == "Windows":
            self._inject_dism(work_dir, inf_files, unsigned)
        else:
            self._copy_drivers(work_dir, inf_files)

    # ------------------------------------------------------------------

    def _inject_dism(self, work_dir: Path, inf_files: list[Path], unsigned: bool) -> None:
        dism = shutil.which("dism") or shutil.which("DISM")
        if dism is None:
            self._logger.warning("DISM not found – falling back to file copy.")
            self._copy_drivers(work_dir, inf_files)
            return

        wim_path = self._find_wim(work_dir)
        index: int = self.config.get("wim_index", 1)
        mount_dir = work_dir / "__wim_mount_drivers__"
        mount_dir.mkdir(parents=True, exist_ok=True)

        try:
            _run([dism, "/Mount-Image", f"/ImageFile:{wim_path}",
                  f"/index:{index}", f"/MountDir:{mount_dir}"])

            for inf in inf_files:
                cmd = [dism, f"/Image:{mount_dir}", "/Add-Driver", f"/Driver:{inf}"]
                if unsigned:
                    cmd.append("/ForceUnsigned")
                self._logger.info("Injecting driver: %s", inf)
                _run(cmd, check=False)

            _run([dism, "/Unmount-Image", f"/MountDir:{mount_dir}", "/Commit"])
        except Exception:
            try:
                _run([dism, "/Unmount-Image", f"/MountDir:{mount_dir}", "/Discard"],
                     check=False)
            except Exception:
                pass
            raise
        finally:
            try:
                mount_dir.rmdir()
            except OSError:
                pass

    def _copy_drivers(self, work_dir: Path, inf_files: list[Path]) -> None:
        """Copy driver packages into $OEM$\\$1\\Drivers so Setup picks them up."""
        dest_base = work_dir / "$OEM$" / "$1" / "Drivers"
        for inf in inf_files:
            # Keep the immediate parent folder name for organisation
            pkg_dir = dest_base / inf.parent.name
            pkg_dir.mkdir(parents=True, exist_ok=True)
            # Copy every file in the same directory as the .inf
            for f in inf.parent.iterdir():
                if f.is_file():
                    shutil.copy2(f, pkg_dir / f.name)
        self._logger.info(
            "Copied %d driver package(s) to %s", len(inf_files), dest_base
        )

    @staticmethod
    def _find_wim(work_dir: Path) -> Path:
        for candidate in ("sources/install.wim", "sources/install.esd"):
            p = work_dir / candidate
            if p.exists():
                return p
        raise FileNotFoundError(
            f"Could not find install.wim or install.esd under {work_dir / 'sources'}"
        )


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        for line in result.stdout.splitlines():
            logger.debug("[dism] %s", line)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n{result.stdout}"
        )
    return result
