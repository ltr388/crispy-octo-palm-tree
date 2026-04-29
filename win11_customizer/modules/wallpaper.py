"""Built-in module: custom desktop wallpaper and lock-screen image.

Copies user-supplied image files into the offline Windows image and optionally
writes registry keys / policy keys so they become the default wallpaper or
lock-screen background for all new user accounts.

Windows stores its default wallpaper images under:
  ``C:\\Windows\\Web\\Wallpaper\\Windows``          (desktop)
  ``C:\\Windows\\Web\\Screen``                      (lock screen)

Reference:
  https://learn.microsoft.com/en-us/windows/configuration/
  lock-screen/windows-spotlight
  https://learn.microsoft.com/en-us/windows/win32/shell/
  changing-the-default-desktop-wallpaper-and-screensaver
"""

from __future__ import annotations

import shutil
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

_SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".bmp"}


def _build_wallpaper_reg(wallpaper_path_on_target: str, style: int, tile: int) -> str:
    return "\n".join([
        "Windows Registry Editor Version 5.00",
        "",
        "[HKEY_CURRENT_USER\\Control Panel\\Desktop]",
        f'"Wallpaper"="{wallpaper_path_on_target}"',
        f'"WallpaperStyle"="{style}"',
        f'"TileWallpaper"="{tile}"',
        "",
        "; Apply to Default user hive too (affects new accounts)",
        "[HKEY_USERS\\.DEFAULT\\Control Panel\\Desktop]",
        f'"Wallpaper"="{wallpaper_path_on_target}"',
        f'"WallpaperStyle"="{style}"',
        f'"TileWallpaper"="{tile}"',
    ]) + "\n"


def _build_lockscreen_reg(image_path_on_target: str) -> str:
    return "\n".join([
        "Windows Registry Editor Version 5.00",
        "",
        "; Disable Spotlight and set a custom lock-screen image",
        "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\Personalization]",
        '"LockScreenImage"="{img}"'.format(img=image_path_on_target.replace("\\", "\\\\")),
        '"NoChangingLockScreen"=dword:00000001',
        '"NoLockScreenSlideshow"=dword:00000001',
        '"NoWindowsSpotlight"=dword:00000001',
    ]) + "\n"


class WallpaperModule(BaseModule):
    """Set the default desktop wallpaper and / or lock-screen background.

    Configuration keys
    ------------------
    ``wallpaper`` (str, optional)
        Path to the image file to use as the default desktop wallpaper.
    ``lockscreen`` (str, optional)
        Path to the image file to use as the lock-screen background.
    ``style`` (str, default ``"fill"``)
        Wallpaper display style: ``"fill"``, ``"fit"``, ``"stretch"``,
        ``"tile"``, ``"center"``, ``"span"``.
    """

    metadata = ModuleMetadata(
        name="wallpaper",
        description="Set default desktop wallpaper and / or lock-screen background image",
        category="ui",
    )

    # WallpaperStyle values
    _STYLES: dict[str, tuple[int, int]] = {
        #                       WallpaperStyle  TileWallpaper
        "tile":    (0, 1),
        "center":  (0, 0),
        "stretch": (2, 0),
        "fit":     (6, 0),
        "fill":    (10, 0),
        "span":    (22, 0),
    }

    # Destination paths inside the ISO (map to C:\Windows\...)
    _WALLPAPER_DEST_REL = "Windows/Web/Wallpaper/Windows"
    _LOCKSCREEN_DEST_REL = "Windows/Web/Screen"

    # Corresponding Windows paths (used in .reg values)
    _WALLPAPER_WIN_PATH = "%SystemRoot%\\Web\\Wallpaper\\Windows\\{filename}"
    _LOCKSCREEN_WIN_PATH = "%SystemRoot%\\Web\\Screen\\{filename}"

    def apply(self, work_dir: Path) -> None:
        wallpaper_src: str | None = self.config.get("wallpaper")
        lockscreen_src: str | None = self.config.get("lockscreen")
        style_name: str = self.config.get("style", "fill").lower()

        if not wallpaper_src and not lockscreen_src:
            self._logger.warning("WallpaperModule: neither 'wallpaper' nor 'lockscreen' specified.")
            return

        style_val, tile_val = self._STYLES.get(style_name, (10, 0))

        scripts_dir = work_dir / "$OEM$" / "$$" / "Setup" / "Scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        reg_files: list[str] = []

        if wallpaper_src:
            src = Path(wallpaper_src).resolve()
            self._check_image(src)
            dest_dir = work_dir / self._WALLPAPER_DEST_REL
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / src.name
            shutil.copy2(src, dest_file)
            self._logger.info("Copied wallpaper: %s → %s", src, dest_file)

            win_path = self._WALLPAPER_WIN_PATH.format(filename=src.name)
            reg_path = scripts_dir / "set_wallpaper.reg"
            reg_path.write_text(
                _build_wallpaper_reg(win_path, style_val, tile_val), encoding="utf-16"
            )
            reg_files.append("set_wallpaper.reg")

        if lockscreen_src:
            src = Path(lockscreen_src).resolve()
            self._check_image(src)
            dest_dir = work_dir / self._LOCKSCREEN_DEST_REL
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / src.name
            shutil.copy2(src, dest_file)
            self._logger.info("Copied lock screen image: %s → %s", src, dest_file)

            win_path = self._LOCKSCREEN_WIN_PATH.format(filename=src.name)
            reg_path = scripts_dir / "set_lockscreen.reg"
            reg_path.write_text(_build_lockscreen_reg(win_path), encoding="utf-16")
            reg_files.append("set_lockscreen.reg")

        # Wire into SetupComplete.cmd
        cmd_path = scripts_dir / "SetupComplete.cmd"
        existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\r\n"
        for reg_file in reg_files:
            if reg_file not in existing:
                existing = existing.rstrip("\r\n")
                existing += f'\r\nreg import "%~dp0{reg_file}" /reg:64\r\n'
        cmd_path.write_text(existing, encoding="utf-8")

    def _check_image(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        if path.suffix.lower() not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported image format '{path.suffix}'.  "
                f"Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}"
            )
