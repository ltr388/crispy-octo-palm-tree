"""Built-in module: Windows Update configuration.

Controls how and when Windows Update downloads and installs updates by
applying group-policy registry keys.  This is useful for:

* Deferring feature updates in enterprise deployments.
* Disabling automatic restarts during active hours.
* Routing updates through a WSUS server.
* Completely pausing updates while testing an insider build.

Reference:
  https://learn.microsoft.com/en-us/windows/deployment/update/
  waas-configure-wufb
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

# ---------------------------------------------------------------------------
# Registry preset catalogue
# ---------------------------------------------------------------------------

UPDATE_PRESETS: dict[str, str] = {

    "disable_auto_update": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable automatic Windows Update downloads and installations
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU]
        "NoAutoUpdate"=dword:00000001
        "AUOptions"=dword:00000001
    """),

    "notify_only": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Notify but don't auto-download or install
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU]
        "NoAutoUpdate"=dword:00000000
        "AUOptions"=dword:00000002
    """),

    "auto_download_notify_install": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Auto-download but prompt before installing
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU]
        "NoAutoUpdate"=dword:00000000
        "AUOptions"=dword:00000003
    """),

    "defer_feature_updates": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Defer feature updates by 365 days, quality updates by 30 days
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate]
        "DeferFeatureUpdates"=dword:00000001
        "DeferFeatureUpdatesPeriodInDays"=dword:0000016D
        "DeferQualityUpdates"=dword:00000001
        "DeferQualityUpdatesPeriodInDays"=dword:0000001E
    """),

    "no_reboot_with_users": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Prevent automatic restarts when users are logged on
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU]
        "NoAutoRebootWithLoggedOnUsers"=dword:00000001
    """),

    "active_hours": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Set active hours 8 AM – 10 PM (no restarts during this window)
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings]
        "ActiveHoursStart"=dword:00000008     ; 8  = 08:00 (8 AM)
        "ActiveHoursEnd"=dword:00000016       ; 22 = 22:00 (10 PM)
    """),

    "disable_driver_updates": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Prevent Windows Update from installing driver updates automatically
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate]
        "ExcludeWUDriversInQualityUpdate"=dword:00000001
    """),

    "disable_store_updates": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable automatic updates from the Microsoft Store
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\WindowsStore]
        "AutoDownload"=dword:00000002
        "DisableOSUpgrade"=dword:00000001
    """),
}

ALL_UPDATE_PRESETS = list(UPDATE_PRESETS.keys())


class UpdatesModule(BaseModule):
    """Configure Windows Update behaviour via group-policy registry keys.

    Configuration keys
    ------------------
    ``presets`` (list[str])
        Update preset names to apply.  Available presets:
        ``disable_auto_update``, ``notify_only``,
        ``auto_download_notify_install``, ``defer_feature_updates``,
        ``no_reboot_with_users``, ``active_hours``,
        ``disable_driver_updates``, ``disable_store_updates``.
    ``wsus_server`` (str, optional)
        URL of a WSUS server to route updates through
        (e.g. ``"http://wsus.corp.example.com:8530"``).
    ``destination`` (str)
        Target folder inside the ISO (default ``$OEM$\\$$\\Setup\\Scripts``).
    """

    metadata = ModuleMetadata(
        name="updates",
        description="Configure Windows Update: deferral, active hours, WSUS, driver updates, and more",
        category="updates",
    )

    _DEFAULT_DEST = r"$OEM$\$$\Setup\Scripts"

    def apply(self, work_dir: Path) -> None:
        presets: list[str] = self.config.get("presets", [])
        wsus_server: str | None = self.config.get("wsus_server")
        destination: str = self.config.get("destination", self._DEFAULT_DEST)

        if not presets and not wsus_server:
            self._logger.warning("UpdatesModule: no presets or wsus_server specified.")
            return

        dest_dir = work_dir / Path(destination.replace("\\", "/"))
        dest_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []

        for preset_name in presets:
            content = UPDATE_PRESETS.get(preset_name)
            if content is None:
                available = ", ".join(sorted(UPDATE_PRESETS))
                raise ValueError(
                    f"Unknown update preset '{preset_name}'.  Available: {available}"
                )
            file_path = dest_dir / f"update_{preset_name}.reg"
            file_path.write_text(content, encoding="utf-16")
            self._logger.info("Written update preset '%s' → %s", preset_name, file_path)
            written.append(preset_name)

        if wsus_server:
            wsus_reg = self._build_wsus_reg(wsus_server)
            file_path = dest_dir / "update_wsus.reg"
            file_path.write_text(wsus_reg, encoding="utf-16")
            self._logger.info("Written WSUS configuration: %s", file_path)
            written.append("wsus")

        if written:
            cmd_path = dest_dir / "SetupComplete.cmd"
            existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\r\n"
            for name in written:
                reg_file = f"update_{name}.reg"
                if reg_file not in existing:
                    existing = existing.rstrip("\r\n")
                    existing += f'\r\nreg import "%~dp0{reg_file}" /reg:64\r\n'
            cmd_path.write_text(existing, encoding="utf-8")

    @staticmethod
    def _build_wsus_reg(server: str) -> str:
        return textwrap.dedent(f"""\
            Windows Registry Editor Version 5.00

            ; Route Windows Update traffic through WSUS server: {server}
            [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate]
            "WUServer"="{server}"
            "WUStatusServer"="{server}"
            "UpdateServiceUrlAlternate"="{server}"

            [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU]
            "UseWUServer"=dword:00000001
        """)
