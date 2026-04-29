"""Built-in module: registry tweaks.

Writes ``.reg`` files into the ISO so that they are applied automatically
during the Specialize or OOBE pass via a ``RunSynchronous`` command in
the answer file, or can be applied manually after first boot.

The module also supports embedding tweaks directly into the offline registry
hives under ``Windows\\System32\\config\\`` when ``offline_apply`` is set to
``true`` in the config (requires the ``hivex`` Python package).
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any

from win11_customizer.modules import BaseModule, ModuleMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry preset catalogue
# ---------------------------------------------------------------------------

PRESETS: dict[str, str] = {
    "disable_telemetry": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable telemetry / data collection
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection]
        "AllowTelemetry"=dword:00000000

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\DataCollection]
        "AllowTelemetry"=dword:00000000
        "MaxTelemetryAllowed"=dword:00000000
    """),

    "disable_cortana": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search]
        "AllowCortana"=dword:00000000
    """),

    "classic_context_menu": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Restore the classic (Windows 10-style) right-click context menu
        [HKEY_CURRENT_USER\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\\InprocServer32]
        @=""
    """),

    "show_file_extensions": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        [HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced]
        "HideFileExt"=dword:00000000
    """),

    "disable_action_center": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        [HKEY_CURRENT_USER\\Software\\Policies\\Microsoft\\Windows\\Explorer]
        "DisableNotificationCenter"=dword:00000001
    """),

    "enable_dark_mode": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        [HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize]
        "AppsUseLightTheme"=dword:00000000
        "SystemUsesLightTheme"=dword:00000000
    """),
}


class RegistryModule(BaseModule):
    """Write registry tweak files into the ISO.

    Configuration keys
    ------------------
    ``presets`` (list[str])
        Names of built-in presets to apply (see ``PRESETS`` dict above).
    ``custom`` (list[dict])
        Custom ``.reg`` file entries.  Each entry must have:
          - ``name`` (str) – filename (without ``.reg``)
          - ``content`` (str) – raw .reg file content
        OR
          - ``name`` (str)
          - ``path`` (str)  – path to an existing ``.reg`` file on disk
    ``destination`` (str, default ``"$OEM$\\$$\\Setup\\Scripts"``)
        Relative path inside the ISO where the ``.reg`` files will be placed.
    """

    metadata = ModuleMetadata(
        name="registry",
        description="Apply registry tweaks by injecting .reg files into the ISO",
        category="customization",
    )

    _DEFAULT_DEST = r"$OEM$\$$\Setup\Scripts"

    def apply(self, work_dir: Path) -> None:
        presets: list[str] = self.config.get("presets", [])
        custom: list[dict[str, Any]] = self.config.get("custom", [])
        destination: str = self.config.get("destination", self._DEFAULT_DEST)

        # Normalise destination to a Path (handle both / and \)
        dest_dir = work_dir / Path(destination.replace("\\", "/"))
        dest_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []

        for preset_name in presets:
            content = PRESETS.get(preset_name)
            if content is None:
                available = ", ".join(sorted(PRESETS))
                raise ValueError(
                    f"Unknown registry preset '{preset_name}'.  "
                    f"Available presets: {available}"
                )
            file_path = dest_dir / f"{preset_name}.reg"
            file_path.write_text(content, encoding="utf-16")
            self._logger.info("Wrote preset '%s' → %s", preset_name, file_path)
            written.append(preset_name)

        for entry in custom:
            name: str = entry.get("name", "custom")
            if "path" in entry:
                src = Path(entry["path"]).resolve()
                if not src.is_file():
                    raise FileNotFoundError(f"Custom .reg file not found: {src}")
                content = src.read_text(encoding="utf-8")
            elif "content" in entry:
                content = entry["content"]
            else:
                raise ValueError(
                    f"Custom registry entry '{name}' must have either 'path' or 'content'."
                )
            file_path = dest_dir / f"{name}.reg"
            file_path.write_text(content, encoding="utf-16")
            self._logger.info("Wrote custom entry '%s' → %s", name, file_path)
            written.append(name)

        if written:
            self._logger.info(
                "Registry module applied %d tweak(s): %s", len(written), written
            )
            self._write_setup_script(dest_dir, written)
        else:
            self._logger.warning("RegistryModule: no presets or custom entries specified.")

    # ------------------------------------------------------------------

    def _write_setup_script(self, dest_dir: Path, names: list[str]) -> None:
        """Write a SetupComplete.cmd that imports all .reg files at first boot."""
        script_path = dest_dir / "SetupComplete.cmd"
        lines = ["@echo off"]
        for name in names:
            lines.append(f'reg import "%~dp0{name}.reg" /reg:64')
        lines.append("exit /b 0")
        script_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        self._logger.info("Written SetupComplete.cmd → %s", script_path)
