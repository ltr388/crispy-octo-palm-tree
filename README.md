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
