"""Built-in module: remove pre-installed (bloatware) Windows 11 UWP apps.

Windows 11 ships with a large number of provisioned application packages that
are installed for every new user account.  This module removes them from the
offline install image via DISM ``/Remove-ProvisionedAppxPackage`` so they are
never present after a clean install.

On non-Windows hosts the module writes a ``Remove-Bloatware.ps1`` PowerShell
script into the ISO that the user can run after first boot, or via the
``$OEM$\\$$\\Setup\\Scripts\\SetupComplete.cmd`` mechanism.

Reference:
  https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/
  dism-app-package--appx-or-appxbundle--servicing-command-line-options
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default list of well-known bloatware package name prefixes shipped with
# Windows 11.  The list targets 23H2 / Insider builds.
# ---------------------------------------------------------------------------
DEFAULT_PACKAGES: list[str] = [
    # Communication / social
    "Microsoft.Teams",
    "MicrosoftTeams",
    "Microsoft.MicrosoftTeams",
    # Xbox / gaming
    "Microsoft.GamingApp",
    "Microsoft.XboxApp",
    "Microsoft.XboxGameOverlay",
    "Microsoft.XboxGamingOverlay",
    "Microsoft.XboxIdentityProvider",
    "Microsoft.XboxSpeechToTextOverlay",
    "Microsoft.Xbox.TCUI",
    # Clipchamp / media creation
    "Clipchamp.Clipchamp",
    "Microsoft.Clipchamp",
    # News / weather / widgets
    "Microsoft.BingNews",
    "Microsoft.BingWeather",
    "Microsoft.BingSearch",
    "MicrosoftWindows.Client.WebExperience",   # Widgets
    # Office / Outlook
    "Microsoft.MicrosoftOfficeHub",
    "Microsoft.OutlookForWindows",
    # Misc
    "Microsoft.Todos",
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.People",
    "Microsoft.WindowsFeedbackHub",
    "Microsoft.WindowsMaps",
    "Microsoft.ZuneMusic",       # Media Player (modern)
    "Microsoft.ZuneVideo",       # Movies & TV
    "Microsoft.YourPhone",       # Phone Link
    "Microsoft.549981C3F5F10",   # Cortana
    "Microsoft.MixedReality.Portal",
    "Microsoft.3DBuilder",
    "Microsoft.Print3D",
    "Microsoft.OneConnect",      # Paid Wi-Fi & Cellular
    "Microsoft.Wallet",
    "Microsoft.Advertising.Xaml",
    "Microsoft.MSPaint",         # Paint (legacy – Paint 3D)
    # Skype
    "Microsoft.SkypeApp",
]


class BloatwareModule(BaseModule):
    """Remove provisioned UWP app packages from the Windows image.

    Configuration keys
    ------------------
    ``packages`` (list[str], default: ``DEFAULT_PACKAGES``)
        Exact or partial package family names to remove.  Wildcards are not
        supported; partial names are matched with ``startswith``.
    ``extra_packages`` (list[str], default: ``[]``)
        Additional package names to remove on top of the defaults.
    ``keep`` (list[str], default: ``[]``)
        Package names to *skip* even if they appear in ``packages``.
    ``wim_index`` (int, default 1)
        WIM image index to modify (Windows-host DISM path only).
    ``script_only`` (bool, default ``False``)
        Always write the PowerShell script, even on Windows hosts.
    """

    metadata = ModuleMetadata(
        name="bloatware",
        description="Remove pre-installed Windows 11 UWP / provisioned app packages",
        category="cleanup",
    )

    def apply(self, work_dir: Path) -> None:
        packages: list[str] = list(self.config.get("packages", DEFAULT_PACKAGES))
        extra: list[str] = self.config.get("extra_packages", [])
        keep: list[str] = self.config.get("keep", [])
        script_only: bool = bool(self.config.get("script_only", False))

        packages = [p for p in packages + extra if p not in keep]
        if not packages:
            self._logger.warning("BloatwareModule: package list is empty.")
            return

        if platform.system() == "Windows" and not script_only:
            self._apply_dism(work_dir, packages)
        else:
            self._write_script(work_dir, packages)

    # ------------------------------------------------------------------

    def _apply_dism(self, work_dir: Path, packages: list[str]) -> None:
        dism = shutil.which("dism") or shutil.which("DISM")
        if dism is None:
            self._logger.warning("DISM not found – falling back to script.")
            self._write_script(work_dir, packages)
            return

        wim_path = self._find_wim(work_dir)
        index: int = self.config.get("wim_index", 1)
        mount_dir = work_dir / "__wim_mount_bloat__"
        mount_dir.mkdir(parents=True, exist_ok=True)

        try:
            _run([dism, "/Mount-Image", f"/ImageFile:{wim_path}",
                  f"/index:{index}", f"/MountDir:{mount_dir}"])

            # Query all provisioned packages then remove matching ones
            result = subprocess.run(
                [dism, f"/Image:{mount_dir}", "/Get-ProvisionedAppxPackages"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            installed = [
                line.split(":", 1)[1].strip()
                for line in result.stdout.splitlines()
                if line.strip().startswith("PackageName")
            ]
            to_remove = [
                pkg for pkg in installed
                if any(pkg.startswith(p) or p in pkg for p in packages)
            ]
            for pkg in to_remove:
                self._logger.info("Removing provisioned package: %s", pkg)
                _run([dism, f"/Image:{mount_dir}",
                      "/Remove-ProvisionedAppxPackage", f"/PackageName:{pkg}"],
                     check=False)

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

    def _write_script(self, work_dir: Path, packages: list[str]) -> None:
        scripts_dir = work_dir / "$OEM$" / "$$" / "Setup" / "Scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Remove-Bloatware.ps1 – generated by win11-customizer",
            "$packages = @(",
        ]
        for pkg in packages:
            lines.append(f"    '{pkg}',")
        lines += [
            ")",
            "foreach ($pkg in $packages) {",
            "    $provisioned = Get-AppxProvisionedPackage -Online | Where-Object { $_.PackageName -like \"$pkg*\" }",
            "    if ($provisioned) {",
            "        Remove-AppxProvisionedPackage -Online -PackageName $provisioned.PackageName -ErrorAction SilentlyContinue",
            "    }",
            "    Get-AppxPackage -AllUsers -Name \"$pkg*\" | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue",
            "}",
        ]
        script_path = scripts_dir / "Remove-Bloatware.ps1"
        script_path.write_text("\n".join(lines), encoding="utf-8")

        # Wire into SetupComplete.cmd
        cmd_path = scripts_dir / "SetupComplete.cmd"
        existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\n"
        if "Remove-Bloatware.ps1" not in existing:
            existing = existing.rstrip("\r\n")
            existing += '\r\nPowerShell -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Remove-Bloatware.ps1"\r\n'
            cmd_path.write_text(existing, encoding="utf-8")

        self._logger.info("Bloatware removal script written to %s", script_path)

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
