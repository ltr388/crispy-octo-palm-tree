"""Built-in module: Microsoft Edge configuration.

Microsoft Edge is the default browser in Windows 11 and cannot easily be
uninstalled without breaking OS features.  This module:

* Applies group-policy registry keys to suppress Edge's first-run experience,
  privacy nags, sync prompts, and desktop shortcut creation.
* Optionally prevents Edge from being the default PDF / protocol handler.
* Optionally sets a custom home page / new-tab URL.

Reference:
  https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata


def _build_reg(home_page: str | None, new_tab_url: str | None,
               prevent_default: bool, hide_first_run: bool) -> str:
    lines = ["Windows Registry Editor Version 5.00", ""]

    # Edge policy root
    root = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Edge"
    lines.append(f"[{root}]")

    if hide_first_run:
        lines += [
            '"HideFirstRunExperience"=dword:00000001',
            '"ShowRecommendationsEnabled"=dword:00000000',
            '"EdgeShoppingAssistantEnabled"=dword:00000000',
            '"ImportAutofillFormData"=dword:00000000',
            '"ImportBrowserSettings"=dword:00000000',
            '"ImportCookies"=dword:00000000',
            '"ImportExtensions"=dword:00000000',
            '"ImportFavorites"=dword:00000000',
            '"ImportHistory"=dword:00000000',
            '"ImportHomepage"=dword:00000000',
            '"ImportOpenTabs"=dword:00000000',
            '"ImportPaymentInfo"=dword:00000000',
            '"ImportSavedPasswords"=dword:00000000',
            '"ImportSearchEngine"=dword:00000000',
            '"PromotionalTabsEnabled"=dword:00000000',
            '"ShowCastIconInToolbar"=dword:00000000',
            '"EdgeCollectionsEnabled"=dword:00000000',
            '"HubsSidebarEnabled"=dword:00000000',
            '"EdgeFollowEnabled"=dword:00000000',
            '"CopilotPageContext"=dword:00000000',
            '"DiscoverPageContextEnabled"=dword:00000000',
        ]

    if home_page:
        lines.append(f'"HomepageLocation"="{home_page}"')
        lines.append('"HomepageIsNewTabPage"=dword:00000000')

    if new_tab_url:
        lines.append(f'"NewTabPageLocation"="{new_tab_url}"')

    if prevent_default:
        # Suppress the "Make Edge your default browser" nag
        lines += [
            '"DefaultBrowserSettingEnabled"=dword:00000000',
        ]

    # Disable Edge desktop shortcut creation after updates
    lines += [
        "",
        "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\EdgeUpdate]",
        '"CreateDesktopShortcutDefault"=dword:00000000',
        '"RemoveDesktopShortcutDefault"=dword:00000001',
        "",
        "; Disable Edge auto-start delay on login",
        "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\MicrosoftEdge\\Main]",
        '"AllowPrelaunch"=dword:00000000',
    ]
    return "\n".join(lines) + "\n"


class EdgeModule(BaseModule):
    """Configure Microsoft Edge via group-policy registry keys.

    Configuration keys
    ------------------
    ``hide_first_run`` (bool, default ``True``)
        Suppress the first-run experience, import prompts, and promotional tabs.
    ``home_page`` (str, optional)
        Set a custom homepage URL (e.g. ``"https://example.com"``).
    ``new_tab_url`` (str, optional)
        Set a custom new-tab page URL.
    ``prevent_default_browser_prompt`` (bool, default ``True``)
        Disable the "Make Edge your default browser" nag.
    """

    metadata = ModuleMetadata(
        name="edge",
        description="Configure Microsoft Edge first-run, home page, and default-browser prompt",
        category="browser",
    )

    def apply(self, work_dir: Path) -> None:
        hide_first_run: bool = bool(self.config.get("hide_first_run", True))
        home_page: str | None = self.config.get("home_page")
        new_tab_url: str | None = self.config.get("new_tab_url")
        prevent_default: bool = bool(self.config.get("prevent_default_browser_prompt", True))

        scripts_dir = work_dir / "$OEM$" / "$$" / "Setup" / "Scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        reg_content = _build_reg(home_page, new_tab_url, prevent_default, hide_first_run)
        reg_path = scripts_dir / "configure_edge.reg"
        reg_path.write_text(reg_content, encoding="utf-16")
        self._logger.info("Written Edge configuration registry file: %s", reg_path)

        # Wire into SetupComplete.cmd
        cmd_path = scripts_dir / "SetupComplete.cmd"
        existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\r\n"
        if "configure_edge.reg" not in existing:
            existing = existing.rstrip("\r\n")
            existing += '\r\nreg import "%~dp0configure_edge.reg" /reg:64\r\n'
            cmd_path.write_text(existing, encoding="utf-8")
