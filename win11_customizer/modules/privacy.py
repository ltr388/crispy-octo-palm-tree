"""Built-in module: comprehensive privacy hardening.

Windows 11 collects various forms of diagnostic, advertising, and usage data
by default.  This module applies a broad set of group-policy and user-profile
registry keys that minimise data collection while keeping the system
functional.

Covers:
* Advertising ID / targeted ads
* Activity History / Timeline
* App diagnostics / background app access
* Cortana
* Find My Device
* Handwriting personalisation
* Ink / typing personalisation
* Location services
* Microphone / camera access policy
* Search history
* Telemetry (beyond the basic registry preset)
* Wi-Fi Sense
* Windows Error Reporting
* Windows Insider programme
* Microsoft consumer experience / tips
* Feedback frequency

Reference:
  https://learn.microsoft.com/en-us/windows/privacy/
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

# Key: preset group name → .reg content
PRIVACY_PRESETS: dict[str, str] = {

    "advertising_id": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable advertising ID for all users
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\AdvertisingInfo]
        "DisabledByGroupPolicy"=dword:00000001
    """),

    "activity_history": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable Activity History / Timeline upload
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\System]
        "EnableActivityFeed"=dword:00000000
        "PublishUserActivities"=dword:00000000
        "UploadUserActivities"=dword:00000000
    """),

    "app_diagnostics": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Restrict app access to diagnostics information
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppPrivacy]
        "LetAppsGetDiagnosticInfo"=dword:00000002
        "LetAppsRunInBackground"=dword:00000002
        "LetAppsAccessNotifications"=dword:00000002
    """),

    "find_my_device": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\FindMyDevice]
        "AllowFindMyDevice"=dword:00000000
    """),

    "handwriting": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable handwriting & inking personalisation
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\InputPersonalization]
        "AllowInputPersonalization"=dword:00000000
        "RestrictImplicitInkCollection"=dword:00000001
        "RestrictImplicitTextCollection"=dword:00000001
    """),

    "location": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable location services system-wide via policy
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\LocationAndSensors]
        "DisableLocation"=dword:00000001
        "DisableWindowsLocationProvider"=dword:00000001
    """),

    "microphone_camera": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Block app access to microphone and camera by default
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppPrivacy]
        "LetAppsAccessMicrophone"=dword:00000002
        "LetAppsAccessCamera"=dword:00000002
    """),

    "search_history": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable cloud search and search history
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search]
        "AllowCloudSearch"=dword:00000000
        "AllowSearchHighlights"=dword:00000000
        "DisableWebSearch"=dword:00000001
        "ConnectedSearchUseWeb"=dword:00000000
        "ConnectedSearchPrivacy"=dword:00000003
    """),

    "wifi_sense": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable Wi-Fi Sense (auto-connect / password sharing)
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\WcmSvc\\wifinetworkmanager\\config]
        "AutoConnectAllowedOEM"=dword:00000000
        "WiFiSenseCredShared"=dword:00000000
        "WiFiSenseOpen"=dword:00000000
    """),

    "error_reporting": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable Windows Error Reporting
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Error Reporting]
        "Disabled"=dword:00000001
        "DontSendAdditionalData"=dword:00000001

        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\WerSvc]
        "Start"=dword:00000004
    """),

    "insider_programme": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable Windows Insider Programme enrolment
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\PreviewBuilds]
        "AllowBuildPreview"=dword:00000000
        "EnableConfigFlighting"=dword:00000000
    """),

    "consumer_tips": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable tips, tricks, suggestions & consumer features
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent]
        "DisableWindowsConsumerFeatures"=dword:00000001
        "DisableSoftLanding"=dword:00000001
        "DisableCloudOptimizedContent"=dword:00000001
        "DisableTailoredExperiencesWithDiagnosticData"=dword:00000001

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection]
        "DoNotShowFeedbackNotifications"=dword:00000001
    """),

    "feedback": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Set feedback frequency to never
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection]
        "DoNotShowFeedbackNotifications"=dword:00000001

        [HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Siuf\\Rules]
        "NumberOfSIUFInPeriod"=dword:00000000
        "PeriodInNanoSeconds"=-
    """),
}

# Convenient bundle: all presets
ALL_PRESETS = list(PRIVACY_PRESETS.keys())


class PrivacyModule(BaseModule):
    """Apply comprehensive privacy hardening via registry group-policy keys.

    Configuration keys
    ------------------
    ``presets`` (list[str], default: all)
        Privacy preset groups to apply.  Available groups:
        ``advertising_id``, ``activity_history``, ``app_diagnostics``,
        ``find_my_device``, ``handwriting``, ``location``,
        ``microphone_camera``, ``search_history``, ``wifi_sense``,
        ``error_reporting``, ``insider_programme``, ``consumer_tips``,
        ``feedback``.
    ``destination`` (str)
        Target folder inside the ISO.  Defaults to
        ``$OEM$\\$$\\Setup\\Scripts``.
    """

    metadata = ModuleMetadata(
        name="privacy",
        description="Comprehensive privacy hardening: telemetry, location, advertising ID, and more",
        category="privacy",
    )

    _DEFAULT_DEST = r"$OEM$\$$\Setup\Scripts"

    def apply(self, work_dir: Path) -> None:
        presets: list[str] = self.config.get("presets", ALL_PRESETS)
        destination: str = self.config.get("destination", self._DEFAULT_DEST)

        dest_dir = work_dir / Path(destination.replace("\\", "/"))
        dest_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        for preset_name in presets:
            content = PRIVACY_PRESETS.get(preset_name)
            if content is None:
                available = ", ".join(sorted(PRIVACY_PRESETS))
                raise ValueError(
                    f"Unknown privacy preset '{preset_name}'.  Available: {available}"
                )
            file_path = dest_dir / f"privacy_{preset_name}.reg"
            file_path.write_text(content, encoding="utf-16")
            self._logger.info("Written privacy preset '%s' → %s", preset_name, file_path)
            written.append(preset_name)

        if written:
            self._write_setup_script(dest_dir, written)

    @staticmethod
    def _write_setup_script(dest_dir: Path, names: list[str]) -> None:
        script_path = dest_dir / "SetupComplete.cmd"
        existing = script_path.read_text(encoding="utf-8") if script_path.exists() else "@echo off\r\n"
        for name in names:
            reg_file = f"privacy_{name}.reg"
            if reg_file not in existing:
                existing = existing.rstrip("\r\n")
                existing += f'\r\nreg import "%~dp0{reg_file}" /reg:64\r\n'
        script_path.write_text(existing, encoding="utf-8")
