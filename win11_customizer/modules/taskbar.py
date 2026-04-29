"""Built-in module: Taskbar and Start Menu customisation.

Windows 11 changed the taskbar significantly: the Start button and icons are
centred by default and many classic options (combining, small icons, always-
visible system-tray icons) were removed.  This module applies registry keys
that restore common preferences and control taskbar behaviour.

Covers:
* Taskbar alignment (left / center)
* Widget / News and Interests button visibility
* Chat (Teams) button visibility
* Search box style (hidden, icon, bar)
* Task View button visibility
* Cortana button visibility
* Clock / calendar flyout seconds
* Auto-hide taskbar
* System tray icon visibility
* Peek-at-desktop button
* Start menu layout (default / more pins / more recommendations)
* Start menu – show recently added apps / most used apps

Reference:
  https://learn.microsoft.com/en-us/windows-hardware/customize/desktop/unattend/
  microsoft-windows-shell-setup-taskbar
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Start menu layout registry values
START_LAYOUT_VALUES: dict[str, int] = {
    "default": 0,
    "more_pins": 1,
    "more_recommendations": 2,
}

# ---------------------------------------------------------------------------
# Registry key builders
# ---------------------------------------------------------------------------

def _build_taskbar_reg(
    alignment: str,
    search_style: int,
    hide_widgets: bool,
    hide_chat: bool,
    hide_task_view: bool,
    auto_hide: bool,
    show_seconds: bool,
    small_icons: bool,
) -> str:
    lines = ["Windows Registry Editor Version 5.00", ""]

    # TaskbarAl: 0 = left, 1 = center (default)
    al_val = 0 if alignment.lower() == "left" else 1

    lines += [
        "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced]",
        f'"TaskbarAl"=dword:{al_val:08x}',
    ]
    if hide_task_view:
        lines.append('"ShowTaskViewButton"=dword:00000000')
    if small_icons:
        lines.append('"TaskbarSmallIcons"=dword:00000001')
    if auto_hide:
        lines.append('"AutoHideTaskbar"=dword:00000001')

    # Search box: 0=hidden, 1=icon only, 2=search box (default), 3=search box + label
    lines += [
        "",
        "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Search]",
        f'"SearchboxTaskbarMode"=dword:{search_style:08x}',
    ]

    # Widgets (News and Interests / Web Experience)
    if hide_widgets:
        lines += [
            "",
            "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Dsh]",
            '"AllowNewsAndInterests"=dword:00000000',
            "",
            "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced]",
            '"TaskbarDa"=dword:00000000',
        ]

    # Chat / Teams in taskbar
    if hide_chat:
        lines += [
            "",
            "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced]",
            '"TaskbarMn"=dword:00000000',
        ]

    # Show seconds in clock
    if show_seconds:
        lines += [
            "",
            "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced]",
            '"ShowSecondsInSystemClock"=dword:00000001',
        ]

    return "\n".join(lines) + "\n"


def _build_startmenu_reg(
    alignment: str,
    show_recently_added: bool,
    show_most_used: bool,
    layout: str,
) -> str:
    # layout: "default", "more_pins", "more_recommendations"
    layout_val = START_LAYOUT_VALUES.get(layout, 0)
    lines = [
        "Windows Registry Editor Version 5.00",
        "",
        "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced]",
        f'"Start_Layout"=dword:{layout_val:08x}',
    ]
    if not show_recently_added:
        lines.append('"Start_TrackProgs"=dword:00000000')
    if not show_most_used:
        lines.append('"Start_TrackDocs"=dword:00000000')
    return "\n".join(lines) + "\n"


class TaskbarModule(BaseModule):
    """Customise the Windows 11 taskbar and Start menu via registry keys.

    Configuration keys
    ------------------
    ``alignment`` (str)
        ``"left"`` or ``"center"`` *(default)*.
    ``search_style`` (int)
        ``0`` = hidden, ``1`` = icon, ``2`` = search box *(default)*, ``3`` = labelled box.
    ``hide_widgets`` (bool, default ``False``)
        Hide the Widgets / News-and-Interests button.
    ``hide_chat`` (bool, default ``False``)
        Hide the Microsoft Teams Chat button.
    ``hide_task_view`` (bool, default ``False``)
        Hide the Task View button.
    ``auto_hide`` (bool, default ``False``)
        Enable auto-hide for the taskbar.
    ``show_seconds_in_clock`` (bool, default ``False``)
        Show seconds in the system clock.
    ``small_icons`` (bool, default ``False``)
        Use small taskbar icons (requires restart).
    ``start_layout`` (str)
        ``"default"``, ``"more_pins"`` *(default Windows 11)*, or
        ``"more_recommendations"``.
    ``show_recently_added_apps`` (bool, default ``True``)
        Show recently added apps in Start.
    ``show_most_used_apps`` (bool, default ``True``)
        Show most-used apps in Start.
    """

    metadata = ModuleMetadata(
        name="taskbar",
        description="Customise Windows 11 taskbar alignment, buttons, search box, and Start menu",
        category="ui",
    )

    def apply(self, work_dir: Path) -> None:
        alignment: str = self.config.get("alignment", "center")
        search_style: int = int(self.config.get("search_style", 2))
        hide_widgets: bool = bool(self.config.get("hide_widgets", False))
        hide_chat: bool = bool(self.config.get("hide_chat", False))
        hide_task_view: bool = bool(self.config.get("hide_task_view", False))
        auto_hide: bool = bool(self.config.get("auto_hide", False))
        show_seconds: bool = bool(self.config.get("show_seconds_in_clock", False))
        small_icons: bool = bool(self.config.get("small_icons", False))
        start_layout: str = self.config.get("start_layout", "default")
        show_recently_added: bool = bool(self.config.get("show_recently_added_apps", True))
        show_most_used: bool = bool(self.config.get("show_most_used_apps", True))

        dest_dir = work_dir / "$OEM$" / "$$" / "Setup" / "Scripts"
        dest_dir.mkdir(parents=True, exist_ok=True)

        tb_reg = _build_taskbar_reg(
            alignment, search_style, hide_widgets, hide_chat,
            hide_task_view, auto_hide, show_seconds, small_icons,
        )
        tb_path = dest_dir / "configure_taskbar.reg"
        tb_path.write_text(tb_reg, encoding="utf-16")
        self._logger.info("Written taskbar registry file: %s", tb_path)

        sm_reg = _build_startmenu_reg(alignment, show_recently_added, show_most_used, start_layout)
        sm_path = dest_dir / "configure_startmenu.reg"
        sm_path.write_text(sm_reg, encoding="utf-16")
        self._logger.info("Written Start menu registry file: %s", sm_path)

        cmd_path = dest_dir / "SetupComplete.cmd"
        existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\r\n"
        for reg_file in ("configure_taskbar.reg", "configure_startmenu.reg"):
            if reg_file not in existing:
                existing = existing.rstrip("\r\n")
                existing += f'\r\nreg import "%~dp0{reg_file}" /reg:64\r\n'
        cmd_path.write_text(existing, encoding="utf-8")
