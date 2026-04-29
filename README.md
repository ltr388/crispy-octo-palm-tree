# crispy-octo-palm-tree — Windows 11 ISO Customiser

A Python tool that loads a **Windows 11 Insider** `.iso` file, applies
user-defined modules (features, registry tweaks, unattended setup files, …),
and repacks the result into a new bootable ISO.

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python ≥ 3.10 | Runtime |
| `7z` (`p7zip-full` on Debian/Ubuntu) | ISO extraction on Linux/macOS |
| `xorriso` | ISO repacking on Linux/macOS |
| `oscdimg` (Windows ADK) *or* `7z` | ISO repacking on Windows |
| `DISM.exe` | Applying optional-feature changes (Windows only) |

---

## Installation

```bash
pip install -e .
```

This installs the `win11-customizer` command-line tool.

---

## Quick start

### 1 – Using a JSON config file (recommended)

Create `my_config.json`:

```json
{
  "iso_path": "/path/to/Win11_InsiderPreview.iso",
  "work_dir": "/tmp/win11_work",
  "modules": [
    {
      "type": "unattend",
      "computer_name": "MY-PC",
      "time_zone": "UTC",
      "local_username": "Alice"
    },
    {
      "type": "registry",
      "presets": ["disable_telemetry", "show_file_extensions", "classic_context_menu"]
    },
    {
      "type": "features",
      "enable": ["TelnetClient", "Microsoft-Hyper-V"],
      "disable": ["WindowsMediaPlayer"]
    }
  ]
}
```

Then run:

```bash
win11-customizer build --config my_config.json --output Win11_Custom.iso
```

### 2 – Inline flags (no config file)

```bash
win11-customizer build \
  --iso Win11_InsiderPreview.iso \
  --output Win11_Custom.iso \
  --module registry:presets=disable_telemetry;show_file_extensions \
  --module unattend:computer_name=MY-PC,time_zone=UTC
```

### 3 – Validate an ISO without making changes

```bash
win11-customizer validate Win11_InsiderPreview.iso
```

---

## Available commands

| Command | Description |
|---|---|
| `build` | Extract, customise, and repack an ISO |
| `validate` | Check that a file is a valid ISO 9660 image |
| `list-modules` | Print all built-in modules |
| `list-presets` | Print all built-in registry presets |
| `apply-pending` | Apply pending DISM feature changes on Windows |

---

## Modules

### `unattend` – Automated Windows Setup

Injects an `autounattend.xml` answer file into the ISO root so that Windows
Setup runs without user interaction.

| Config key | Default | Description |
|---|---|---|
| `xml_path` | *(generate)* | Path to a custom answer file |
| `ui_language` | `en-US` | Setup UI language |
| `input_locale` | `en-US` | Keyboard locale |
| `user_locale` | `en-US` | User locale |
| `computer_name` | `WIN11PC` | Target machine name |
| `time_zone` | `UTC` | Windows time zone |
| `local_username` | `User` | Local admin account name |
| `local_password` | *(empty)* | Local admin password |

---

### `registry` – Registry Tweaks

Writes `.reg` files into the ISO `$OEM$\$$\Setup\Scripts` folder and
generates a `SetupComplete.cmd` that imports them on first boot.

| Config key | Default | Description |
|---|---|---|
| `presets` | `[]` | List of built-in preset names (see below) |
| `custom` | `[]` | Custom `.reg` entries (`name` + `content` or `path`) |
| `destination` | `$OEM$\$$\Setup\Scripts` | Target folder inside the ISO |

**Built-in presets**

| Preset | Effect |
|---|---|
| `disable_telemetry` | Turn off Windows telemetry / data collection |
| `disable_cortana` | Disable Cortana via group policy |
| `classic_context_menu` | Restore the Windows 10-style right-click menu |
| `show_file_extensions` | Show known file extensions in Explorer |
| `disable_action_center` | Hide the notification / Action Center |
| `enable_dark_mode` | Enable dark theme for apps and system UI |

---

### `features` – Optional Windows Features

Enables or disables Windows optional features via `DISM.exe` (Windows host)
or writes a `features_pending.json` sidecar on Linux/macOS.

| Config key | Default | Description |
|---|---|---|
| `enable` | `[]` | Feature names to enable |
| `disable` | `[]` | Feature names to disable |
| `wim_index` | `1` | WIM image index to modify |

---

### `bloatware` – Remove Pre-installed Apps

Removes provisioned UWP apps via DISM on Windows hosts.  On Linux/macOS
writes a `Remove-Bloatware.ps1` first-boot script.

| Config key | Default | Description |
|---|---|---|
| `packages` | *(35+ defaults)* | Package names to remove (Teams, Xbox, Clipchamp, …) |
| `extra_packages` | `[]` | Additional packages on top of defaults |
| `keep` | `[]` | Packages to skip even if listed in `packages` |
| `script_only` | `false` | Always write PS script, even on Windows |

---

### `onedrive` – OneDrive Control

| Config key | Default | Description |
|---|---|---|
| `action` | `"disable"` | `"disable"` / `"remove"` / `"remove_setup_binary"` |

---

### `edge` – Microsoft Edge Configuration

| Config key | Default | Description |
|---|---|---|
| `hide_first_run` | `true` | Suppress first-run nags and import prompts |
| `home_page` | *(none)* | Custom homepage URL |
| `new_tab_url` | *(none)* | Custom new-tab page URL |
| `prevent_default_browser_prompt` | `true` | Suppress "make Edge your default" prompt |

---

### `privacy` – Comprehensive Privacy Hardening

Applies 13 independent preset groups via group-policy registry keys.

| Config key | Default | Description |
|---|---|---|
| `presets` | *(all 13)* | List of preset names to apply |

**Available presets:** `advertising_id`, `activity_history`, `app_diagnostics`,
`find_my_device`, `handwriting`, `location`, `microphone_camera`,
`search_history`, `wifi_sense`, `error_reporting`, `insider_programme`,
`consumer_tips`, `feedback`

---

### `taskbar` – Taskbar & Start Menu

| Config key | Default | Description |
|---|---|---|
| `alignment` | `"center"` | `"left"` or `"center"` |
| `search_style` | `2` | `0`=hidden, `1`=icon, `2`=box, `3`=labelled box |
| `hide_widgets` | `false` | Hide Widgets / News-and-Interests button |
| `hide_chat` | `false` | Hide Teams Chat button |
| `hide_task_view` | `false` | Hide Task View button |
| `auto_hide` | `false` | Enable taskbar auto-hide |
| `show_seconds_in_clock` | `false` | Show seconds in system clock |
| `small_icons` | `false` | Use small taskbar icons |
| `start_layout` | `"default"` | `"default"`, `"more_pins"`, `"more_recommendations"` |

---

### `power` – Power Plan

| Config key | Default | Description |
|---|---|---|
| `plan` | `"balanced"` | `"balanced"`, `"high_performance"`, `"power_saver"`, `"ultimate_performance"` |
| `custom_guid` | *(none)* | Custom power-plan GUID |

---

### `wsl` – Windows Subsystem for Linux

| Config key | Default | Description |
|---|---|---|
| `distro` | *(none)* | Distribution to install (e.g. `"Ubuntu"`, `"Debian"`) |
| `version` | `2` | Default WSL version |

---

### `drivers` – Driver Injection

Injects `.inf` driver packages via DISM on Windows hosts, or copies them to
`$OEM$\$1\Drivers` for auto-detection by Setup.

| Config key | Default | Description |
|---|---|---|
| `drivers` | `[]` | Paths to `.inf` files or directories |
| `recurse` | `true` | Recursively scan directories |
| `unsigned` | `false` | Allow unsigned drivers |
| `wim_index` | `1` | WIM index (Windows/DISM path) |

---

### `fonts` – Custom Fonts

Copies font files to `C:\Windows\Fonts` and registers them on first boot.

| Config key | Default | Description |
|---|---|---|
| `fonts` | `[]` | Paths to `.ttf`/`.otf`/`.ttc` files or directories |
| `recurse` | `false` | Recursively scan font directories |

---

### `wallpaper` – Desktop & Lock Screen

| Config key | Default | Description |
|---|---|---|
| `wallpaper` | *(none)* | Path to desktop wallpaper image (JPG/PNG/BMP) |
| `lockscreen` | *(none)* | Path to lock-screen image |
| `style` | `"fill"` | `"fill"`, `"fit"`, `"stretch"`, `"tile"`, `"center"`, `"span"` |

---

### `office` – Microsoft Office / Microsoft 365

Embeds an ODT `Configuration.xml` and a silent-install PowerShell script.

| Config key | Default | Description |
|---|---|---|
| `product_id` | `"O365ProPlusRetail"` | ODT product ID |
| `arch` | `"64"` | `"64"` or `"32"` |
| `channel` | `"Current"` | Update channel |
| `language` | `"MatchOS"` | Language ID |
| `exclude_apps` | `[]` | Apps to exclude (e.g. `["Access","Publisher"]`) |
| `source_path` | *(CDN)* | Local pre-downloaded Office source tree |
| `odt_setup_exe` | *(auto-download)* | Path to ODT `setup.exe` |

---

### `scripts` – Custom Scripts

Generic escape hatch: injects any PowerShell / batch scripts into the ISO.

| Config key | Default | Description |
|---|---|---|
| `scripts` | `[]` | List of `{path, destination, run_at_setup, run_as}` entries |

---

### `security` – Security Hardening

| Config key | Default | Description |
|---|---|---|
| `presets` | `[]` | Preset names to apply |

**Available presets:** `uac_high`, `uac_low`, `disable_smb1`,
`disable_autorun`, `disable_remote_desktop`, `enable_remote_desktop`,
`firewall_on`, `defender_enhanced`, `credential_guard`,
`disable_llmnr`, `disable_netbios`

---

### `updates` – Windows Update Configuration

| Config key | Default | Description |
|---|---|---|
| `presets` | `[]` | Preset names to apply |
| `wsus_server` | *(none)* | WSUS server URL |

**Available presets:** `disable_auto_update`, `notify_only`,
`auto_download_notify_install`, `defer_feature_updates`,
`no_reboot_with_users`, `active_hours`, `disable_driver_updates`,
`disable_store_updates`

---

## Extending with custom modules

```python
from pathlib import Path
from win11_customizer.modules import BaseModule, ModuleMetadata

class MyModule(BaseModule):
    metadata = ModuleMetadata(
        name="my_module",
        description="Does something custom",
        category="custom",
    )

    def apply(self, work_dir: Path) -> None:
        (work_dir / "my_custom_file.txt").write_text("hello!")
```

Then register it programmatically:

```python
from win11_customizer.customizer import Customizer

c = Customizer("Win11.iso", work_dir="/tmp/win11")
c.add_module(MyModule({"key": "value"}))
c.run("Win11_Custom.iso")
```

---

## Running tests

```bash
pip install pytest
pytest
```

---

## License

MIT
