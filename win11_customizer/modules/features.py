"""Built-in module: Windows feature toggle via DISM.

This module calls ``DISM.exe`` (Deployment Image Servicing and Management)
to enable or disable Windows optional features inside the WIM image that is
embedded in the ISO.

DISM is only available on Windows hosts.  On other platforms the module
records the requested changes in a ``features_pending.json`` sidecar file so
that they can be applied later (e.g., by the end-user or a CI runner that has
access to a Windows environment).

Reference:
  https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/dism-overview
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from win11_customizer.modules import BaseModule, ModuleMetadata

logger = logging.getLogger(__name__)


class FeaturesModule(BaseModule):
    """Enable or disable Windows optional features in the install.wim.

    Configuration keys
    ------------------
    ``enable``  (list[str])
        Feature names to enable, e.g. ``["Microsoft-Hyper-V", "TelnetClient"]``.
    ``disable`` (list[str])
        Feature names to disable, e.g. ``["WindowsMediaPlayer"]``.
    ``wim_index`` (int, default 1)
        Index inside ``install.wim`` / ``install.esd`` to modify.
    """

    metadata = ModuleMetadata(
        name="features",
        description=(
            "Enable or disable Windows optional features via DISM "
            "(Windows host required; records a pending manifest on other platforms)"
        ),
        category="features",
    )

    def apply(self, work_dir: Path) -> None:
        enable: list[str] = self.config.get("enable", [])
        disable: list[str] = self.config.get("disable", [])

        if not enable and not disable:
            self._logger.warning("FeaturesModule: no features specified – nothing to do.")
            return

        if platform.system() == "Windows":
            self._apply_dism(work_dir, enable, disable)
        else:
            self._write_pending(work_dir, enable, disable)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_dism(self, work_dir: Path, enable: list[str], disable: list[str]) -> None:
        dism = shutil.which("dism") or shutil.which("DISM")
        if dism is None:
            raise RuntimeError("DISM.exe not found on PATH.")

        wim_path = self._find_wim(work_dir)
        index: int = self.config.get("wim_index", 1)

        mount_dir = work_dir / "__wim_mount__"
        mount_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Mount the WIM
            self._run(
                [dism, "/Mount-Image", f"/ImageFile:{wim_path}", f"/index:{index}", f"/MountDir:{mount_dir}"]
            )

            for feature in enable:
                self._logger.info("Enabling feature: %s", feature)
                self._run(
                    [dism, f"/Image:{mount_dir}", "/Enable-Feature", f"/FeatureName:{feature}", "/All"]
                )

            for feature in disable:
                self._logger.info("Disabling feature: %s", feature)
                self._run(
                    [dism, f"/Image:{mount_dir}", "/Disable-Feature", f"/FeatureName:{feature}"]
                )

            # Commit & unmount
            self._run(
                [dism, "/Unmount-Image", f"/MountDir:{mount_dir}", "/Commit"]
            )
        except Exception:
            # Best-effort discard on failure
            try:
                self._run(
                    [dism, "/Unmount-Image", f"/MountDir:{mount_dir}", "/Discard"],
                    check=False,
                )
            except Exception:
                pass
            raise
        finally:
            if mount_dir.exists():
                try:
                    mount_dir.rmdir()
                except OSError:
                    pass

    def _write_pending(self, work_dir: Path, enable: list[str], disable: list[str]) -> None:
        """Write a sidecar JSON so the user can apply the changes on Windows."""
        pending_file = work_dir / "features_pending.json"
        payload: dict[str, Any] = {}
        if pending_file.exists():
            try:
                payload = json.loads(pending_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        existing_enable: list[str] = payload.get("enable", [])
        existing_disable: list[str] = payload.get("disable", [])

        for f in enable:
            if f not in existing_enable:
                existing_enable.append(f)
        for f in disable:
            if f not in existing_disable:
                existing_disable.append(f)

        payload["enable"] = existing_enable
        payload["disable"] = existing_disable
        payload["wim_index"] = self.config.get("wim_index", 1)

        pending_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._logger.warning(
            "DISM is not available on this platform.  "
            "Feature changes written to: %s  "
            "Apply them on a Windows host using: "
            "win11-customizer apply-pending --work-dir %s",
            pending_file,
            work_dir,
        )

    @staticmethod
    def _find_wim(work_dir: Path) -> Path:
        for candidate in ("sources/install.wim", "sources/install.esd"):
            p = work_dir / candidate
            if p.exists():
                return p
        raise FileNotFoundError(
            "Could not locate install.wim or install.esd under "
            f"{work_dir / 'sources'}"
        )

    @staticmethod
    def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.debug("[dism] %s", line)
        if check and result.returncode != 0:
            raise RuntimeError(
                f"DISM command failed (exit {result.returncode}): {' '.join(cmd)}\n"
                f"{result.stdout}"
            )
        return result
