"""Built-in module: inject an unattend.xml answer file.

An *unattend* file allows fully-automated, zero-touch Windows Setup.  This
module writes a user-supplied (or auto-generated) ``autounattend.xml`` into
the root of the extracted ISO so that Windows Setup picks it up automatically.

Reference:
  https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/automate-windows-setup
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any

from win11_customizer.modules import BaseModule, ModuleMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default minimal answer file – skips EULA, sets keyboard, locale, etc.
# Passwords / usernames are intentionally placeholder values so users
# must supply their own via the config dict.
# ---------------------------------------------------------------------------
_DEFAULT_UNATTEND = textwrap.dedent("""\
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">

  <!-- ====== Windows PE (pre-install) pass ====== -->
  <settings pass="windowsPE">
    <component name="Microsoft-Windows-International-Core-WinPE"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <SetupUILanguage>
        <UILanguage>{ui_language}</UILanguage>
      </SetupUILanguage>
      <InputLocale>{input_locale}</InputLocale>
      <UILanguage>{ui_language}</UILanguage>
      <UserLocale>{user_locale}</UserLocale>
    </component>

    <component name="Microsoft-Windows-Setup"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <UserData>
        <AcceptEula>true</AcceptEula>
      </UserData>
      <DiskConfiguration>
        <WillShowUI>OnError</WillShowUI>
      </DiskConfiguration>
    </component>
  </settings>

  <!-- ====== Specialize pass ====== -->
  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <ComputerName>{computer_name}</ComputerName>
      <TimeZone>{time_zone}</TimeZone>
    </component>
  </settings>

  <!-- ====== Out-of-box experience (OOBE) pass ====== -->
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-Shell-Setup"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <HideLocalAccountScreen>false</HideLocalAccountScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <NetworkLocation>Home</NetworkLocation>
        <ProtectYourPC>1</ProtectYourPC>
        <SkipMachineOOBE>false</SkipMachineOOBE>
        <SkipUserOOBE>false</SkipUserOOBE>
      </OOBE>
      <UserAccounts>
        <LocalAccounts>
          <LocalAccount wcm:action="add"
                        xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
            <Password>
              <Value>{local_password}</Value>
              <PlainText>true</PlainText>
            </Password>
            <DisplayName>{local_username}</DisplayName>
            <Group>Administrators</Group>
            <Name>{local_username}</Name>
          </LocalAccount>
        </LocalAccounts>
      </UserAccounts>
    </component>
  </settings>

</unattend>
""")


class UnattendModule(BaseModule):
    """Inject an ``autounattend.xml`` into the ISO root.

    Configuration keys
    ------------------
    ``xml_path``  (str, optional)
        Path to a custom ``autounattend.xml`` file.  When not supplied the
        module generates a minimal answer file from the template keys below.
    ``ui_language``   – default ``"en-US"``
    ``input_locale``  – default ``"en-US"``
    ``user_locale``   – default ``"en-US"``
    ``computer_name`` – default ``"WIN11PC"``
    ``time_zone``     – default ``"UTC"``
    ``local_username``– default ``"User"``
    ``local_password``– default ``""`` (empty – user should change this)
    """

    metadata = ModuleMetadata(
        name="unattend",
        description="Inject an autounattend.xml answer file to automate Windows Setup",
        category="setup",
    )

    def apply(self, work_dir: Path) -> None:
        dest = work_dir / "autounattend.xml"

        custom_path: str | None = self.config.get("xml_path")
        if custom_path:
            src = Path(custom_path).resolve()
            if not src.is_file():
                raise FileNotFoundError(f"Custom unattend file not found: {src}")
            xml_content = src.read_text(encoding="utf-8")
            self._logger.info("Using custom unattend file: %s", src)
        else:
            xml_content = _DEFAULT_UNATTEND.format(
                ui_language=self.config.get("ui_language", "en-US"),
                input_locale=self.config.get("input_locale", "en-US"),
                user_locale=self.config.get("user_locale", "en-US"),
                computer_name=self.config.get("computer_name", "WIN11PC"),
                time_zone=self.config.get("time_zone", "UTC"),
                local_username=self.config.get("local_username", "User"),
                local_password=self.config.get("local_password", ""),
            )
            self._logger.info("Generated default unattend.xml")

        dest.write_text(xml_content, encoding="utf-8")
        self._logger.info("Written %s", dest)
