"""Built-in module: inject arbitrary PowerShell or batch scripts.

This is a generic escape-hatch module that copies user-supplied scripts
into ``$OEM$\\$$\\Setup\\Scripts`` and (optionally) wires them into
``SetupComplete.cmd`` so they run at first boot.

Scripts can also be placed in any other location inside the ISO tree.

Reference:
  https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/
  add-a-custom-script-to-windows-setup
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from win11_customizer.modules import BaseModule, ModuleMetadata


class ScriptsModule(BaseModule):
    """Inject custom PowerShell or batch scripts into the ISO.

    Configuration keys
    ------------------
    ``scripts`` (list[dict])
        Each entry describes one script to inject:

        ``path`` (str, required)
            Path to the script file on the host machine.
        ``destination`` (str, default ``"$OEM$\\$$\\Setup\\Scripts"``)
            Destination folder inside the ISO (relative to the ISO root).
        ``run_at_setup`` (bool, default ``True``)
            Wire the script into ``SetupComplete.cmd`` so it runs on first boot.
            Only applicable when ``destination`` is the default Scripts folder.
        ``run_as`` (str, default ``"powershell"``)
            How to invoke the script in ``SetupComplete.cmd``:
            ``"powershell"`` or ``"cmd"``.
    """

    metadata = ModuleMetadata(
        name="scripts",
        description="Inject custom PowerShell / batch scripts into the ISO (runs at first boot)",
        category="scripting",
    )

    _DEFAULT_DEST = r"$OEM$\$$\Setup\Scripts"

    def apply(self, work_dir: Path) -> None:
        scripts: list[dict[str, Any]] = self.config.get("scripts", [])
        if not scripts:
            self._logger.warning("ScriptsModule: no scripts specified.")
            return

        for entry in scripts:
            src_str: str = entry.get("path", "")
            if not src_str:
                self._logger.warning("ScriptsModule: skipping entry with no 'path': %s", entry)
                continue

            src = Path(src_str).resolve()
            if not src.is_file():
                raise FileNotFoundError(f"Script file not found: {src}")

            destination: str = entry.get("destination", self._DEFAULT_DEST)
            dest_dir = work_dir / Path(destination.replace("\\", "/"))
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_file = dest_dir / src.name
            shutil.copy2(src, dest_file)
            self._logger.info("Copied script: %s → %s", src, dest_file)

            run_at_setup: bool = bool(entry.get("run_at_setup", True))
            run_as: str = entry.get("run_as", "powershell").lower()

            if run_at_setup:
                self._wire_setup_cmd(dest_dir, src.name, run_as)

    @staticmethod
    def _wire_setup_cmd(scripts_dir: Path, filename: str, run_as: str) -> None:
        cmd_path = scripts_dir / "SetupComplete.cmd"
        existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\r\n"
        if filename not in existing:
            existing = existing.rstrip("\r\n")
            if run_as == "powershell" or filename.lower().endswith(".ps1"):
                line = f'\r\nPowerShell -NonInteractive -ExecutionPolicy Bypass -File "%~dp0{filename}"\r\n'
            else:
                line = f'\r\ncall "%~dp0{filename}"\r\n'
            existing += line
            cmd_path.write_text(existing, encoding="utf-8")
