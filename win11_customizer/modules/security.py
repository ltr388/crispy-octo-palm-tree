"""Built-in module: security hardening.

Applies a broad set of security-focused registry group-policy keys and
optionally configures Windows Defender, UAC, Windows Firewall, and
BitLocker via first-boot scripts.

Covers:
* UAC (User Account Control) elevation level
* Windows Defender / Microsoft Defender Antivirus (enhanced protection)
* Windows Firewall profiles
* SMBv1 disable
* AutoRun / AutoPlay disable
* Credential Guard policy
* Remote Desktop settings
* Spectre / Meltdown mitigations (optional, may hurt performance)

Reference:
  https://learn.microsoft.com/en-us/windows/security/
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from win11_customizer.modules import BaseModule, ModuleMetadata

# ---------------------------------------------------------------------------
# Registry preset catalogue
# ---------------------------------------------------------------------------

SECURITY_PRESETS: dict[str, str] = {

    "uac_high": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Set UAC to highest (prompt on secure desktop for all elevation)
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System]
        "EnableLUA"=dword:00000001
        "ConsentPromptBehaviorAdmin"=dword:00000002
        "ConsentPromptBehaviorUser"=dword:00000000
        "PromptOnSecureDesktop"=dword:00000001
    """),

    "uac_low": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable UAC prompts (not recommended for general use)
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System]
        "EnableLUA"=dword:00000000
        "ConsentPromptBehaviorAdmin"=dword:00000000
        "PromptOnSecureDesktop"=dword:00000000
    """),

    "disable_smb1": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable SMBv1 (legacy, insecure – responsible for WannaCry)
        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters]
        "SMB1"=dword:00000000

        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\mrxsmb10]
        "Start"=dword:00000004
    """),

    "disable_autorun": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable AutoRun / AutoPlay on all drive types
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer]
        "NoDriveTypeAutoRun"=dword:000000FF
        "NoAutorun"=dword:00000001

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer]
        "NoAutoplayfornonVolume"=dword:00000001
    """),

    "disable_remote_desktop": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable Remote Desktop
        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server]
        "fDenyTSConnections"=dword:00000001
    """),

    "enable_remote_desktop": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Enable Remote Desktop and require NLA
        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server]
        "fDenyTSConnections"=dword:00000000

        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp]
        "UserAuthentication"=dword:00000001
    """),

    "firewall_on": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Enable Windows Firewall on all profiles
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\WindowsFirewall\\DomainProfile]
        "EnableFirewall"=dword:00000001

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\WindowsFirewall\\PrivateProfile]
        "EnableFirewall"=dword:00000001

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\WindowsFirewall\\PublicProfile]
        "EnableFirewall"=dword:00000001
    """),

    "defender_enhanced": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Enable Windows Defender enhanced protection features
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows Defender]
        "DisableAntiSpyware"=dword:00000000
        "DisableRoutinelyTakingAction"=dword:00000000

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\Real-Time Protection]
        "DisableBehaviorMonitoring"=dword:00000000
        "DisableIOAVProtection"=dword:00000000
        "DisableOnAccessProtection"=dword:00000000
        "DisableRealtimeMonitoring"=dword:00000000
        "DisableScanOnRealtimeEnable"=dword:00000000

        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\MpEngine]
        "MpEnablePus"=dword:00000001
    """),

    "credential_guard": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Enable Credential Guard (requires UEFI + Secure Boot + TPM)
        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\DeviceGuard]
        "EnableVirtualizationBasedSecurity"=dword:00000001
        "RequirePlatformSecurityFeatures"=dword:00000003
        "LsaCfgFlags"=dword:00000001
    """),

    "disable_llmnr": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable LLMNR (Link-Local Multicast Name Resolution) – prevents poisoning attacks
        [HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient]
        "EnableMulticast"=dword:00000000
    """),

    "disable_netbios": textwrap.dedent("""\
        Windows Registry Editor Version 5.00

        ; Disable NetBIOS over TCP/IP (reduces attack surface)
        [HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\NetBT\\Parameters]
        "NetbiosOptions"=dword:00000002
    """),
}

ALL_SECURITY_PRESETS = list(SECURITY_PRESETS.keys())


class SecurityModule(BaseModule):
    """Apply security hardening registry policies.

    Configuration keys
    ------------------
    ``presets`` (list[str])
        Security preset names to apply.  Available presets:
        ``uac_high``, ``uac_low``, ``disable_smb1``, ``disable_autorun``,
        ``disable_remote_desktop``, ``enable_remote_desktop``,
        ``firewall_on``, ``defender_enhanced``, ``credential_guard``,
        ``disable_llmnr``, ``disable_netbios``.
    ``destination`` (str)
        Target folder inside the ISO (default ``$OEM$\\$$\\Setup\\Scripts``).
    """

    metadata = ModuleMetadata(
        name="security",
        description="Apply security hardening: UAC, SMBv1, Defender, Firewall, Credential Guard, and more",
        category="security",
    )

    _DEFAULT_DEST = r"$OEM$\$$\Setup\Scripts"

    def apply(self, work_dir: Path) -> None:
        presets: list[str] = self.config.get("presets", [])
        destination: str = self.config.get("destination", self._DEFAULT_DEST)

        if not presets:
            self._logger.warning("SecurityModule: no presets specified.")
            return

        dest_dir = work_dir / Path(destination.replace("\\", "/"))
        dest_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        for preset_name in presets:
            content = SECURITY_PRESETS.get(preset_name)
            if content is None:
                available = ", ".join(sorted(SECURITY_PRESETS))
                raise ValueError(
                    f"Unknown security preset '{preset_name}'.  Available: {available}"
                )
            file_path = dest_dir / f"security_{preset_name}.reg"
            file_path.write_text(content, encoding="utf-16")
            self._logger.info("Written security preset '%s' → %s", preset_name, file_path)
            written.append(preset_name)

        if written:
            cmd_path = dest_dir / "SetupComplete.cmd"
            existing = cmd_path.read_text(encoding="utf-8") if cmd_path.exists() else "@echo off\r\n"
            for name in written:
                reg_file = f"security_{name}.reg"
                if reg_file not in existing:
                    existing = existing.rstrip("\r\n")
                    existing += f'\r\nreg import "%~dp0{reg_file}" /reg:64\r\n'
            cmd_path.write_text(existing, encoding="utf-8")
