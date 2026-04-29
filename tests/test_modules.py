"""Tests for the module framework and built-in modules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from win11_customizer.modules import BaseModule, ModuleMetadata
from win11_customizer.modules.registry import RegistryModule, PRESETS
from win11_customizer.modules.unattend import UnattendModule
from win11_customizer.modules.features import FeaturesModule


# ---------------------------------------------------------------------------
# BaseModule (abstract) – verify contract
# ---------------------------------------------------------------------------

class ConcreteModule(BaseModule):
    """Minimal concrete module used in tests."""

    metadata = ModuleMetadata(name="test_mod", description="A test module", category="test")

    def apply(self, work_dir: Path) -> None:
        (work_dir / "marker.txt").write_text("applied")


class TestBaseModule:
    def test_repr_contains_name(self) -> None:
        m = ConcreteModule()
        assert "test_mod" in repr(m)

    def test_config_defaults_to_empty_dict(self) -> None:
        m = ConcreteModule()
        assert m.config == {}

    def test_config_stored(self) -> None:
        m = ConcreteModule({"key": "value"})
        assert m.config["key"] == "value"

    def test_apply_creates_file(self, tmp_path: Path) -> None:
        m = ConcreteModule()
        m.apply(tmp_path)
        assert (tmp_path / "marker.txt").read_text() == "applied"


# ---------------------------------------------------------------------------
# RegistryModule
# ---------------------------------------------------------------------------

class TestRegistryModule:
    def test_known_preset_creates_reg_file(self, tmp_path: Path) -> None:
        mod = RegistryModule({"presets": ["disable_telemetry"]})
        mod.apply(tmp_path)
        dest = tmp_path / "$OEM$" / "$$" / "Setup" / "Scripts"
        assert (dest / "disable_telemetry.reg").exists()

    def test_multiple_presets(self, tmp_path: Path) -> None:
        presets = ["disable_telemetry", "show_file_extensions"]
        mod = RegistryModule({"presets": presets})
        mod.apply(tmp_path)
        dest = tmp_path / "$OEM$" / "$$" / "Setup" / "Scripts"
        for name in presets:
            assert (dest / f"{name}.reg").exists()

    def test_setup_script_written(self, tmp_path: Path) -> None:
        mod = RegistryModule({"presets": ["disable_telemetry"]})
        mod.apply(tmp_path)
        dest = tmp_path / "$OEM$" / "$$" / "Setup" / "Scripts"
        script = dest / "SetupComplete.cmd"
        assert script.exists()
        content = script.read_text(encoding="utf-8")
        assert "disable_telemetry.reg" in content

    def test_unknown_preset_raises(self, tmp_path: Path) -> None:
        mod = RegistryModule({"presets": ["nonexistent_preset"]})
        with pytest.raises(ValueError, match="Unknown registry preset"):
            mod.apply(tmp_path)

    def test_custom_content_entry(self, tmp_path: Path) -> None:
        custom_content = "Windows Registry Editor Version 5.00\n\n[HKEY_LOCAL_MACHINE\\TEST]\n"
        mod = RegistryModule({
            "custom": [{"name": "my_tweak", "content": custom_content}]
        })
        mod.apply(tmp_path)
        dest = tmp_path / "$OEM$" / "$$" / "Setup" / "Scripts"
        assert (dest / "my_tweak.reg").exists()

    def test_custom_path_not_found_raises(self, tmp_path: Path) -> None:
        mod = RegistryModule({
            "custom": [{"name": "x", "path": "/nonexistent/path/to.reg"}]
        })
        with pytest.raises(FileNotFoundError):
            mod.apply(tmp_path)

    def test_custom_entry_missing_content_and_path_raises(self, tmp_path: Path) -> None:
        mod = RegistryModule({"custom": [{"name": "bad_entry"}]})
        with pytest.raises(ValueError, match="must have either"):
            mod.apply(tmp_path)

    def test_custom_destination(self, tmp_path: Path) -> None:
        mod = RegistryModule({
            "presets": ["disable_telemetry"],
            "destination": "custom_dest",
        })
        mod.apply(tmp_path)
        assert (tmp_path / "custom_dest" / "disable_telemetry.reg").exists()

    def test_no_modules_does_nothing(self, tmp_path: Path) -> None:
        mod = RegistryModule({})
        mod.apply(tmp_path)  # Should not raise

    def test_all_builtin_presets_have_content(self) -> None:
        for name, content in PRESETS.items():
            assert "Windows Registry Editor Version 5.00" in content, (
                f"Preset '{name}' is missing the required header line"
            )


# ---------------------------------------------------------------------------
# UnattendModule
# ---------------------------------------------------------------------------

class TestUnattendModule:
    def test_generates_default_unattend(self, tmp_path: Path) -> None:
        mod = UnattendModule()
        mod.apply(tmp_path)
        out = tmp_path / "autounattend.xml"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<unattend" in content
        assert "WIN11PC" in content  # default computer name

    def test_custom_values(self, tmp_path: Path) -> None:
        mod = UnattendModule({
            "computer_name": "TESTBOX",
            "time_zone": "Pacific Standard Time",
            "ui_language": "en-GB",
        })
        mod.apply(tmp_path)
        content = (tmp_path / "autounattend.xml").read_text(encoding="utf-8")
        assert "TESTBOX" in content
        assert "Pacific Standard Time" in content
        assert "en-GB" in content

    def test_custom_xml_file(self, tmp_path: Path) -> None:
        custom_xml = tmp_path / "my_unattend.xml"
        custom_xml.write_text('<unattend/>', encoding="utf-8")
        mod = UnattendModule({"xml_path": str(custom_xml)})
        mod.apply(tmp_path)
        content = (tmp_path / "autounattend.xml").read_text(encoding="utf-8")
        assert "<unattend/>" in content

    def test_custom_xml_missing_raises(self, tmp_path: Path) -> None:
        mod = UnattendModule({"xml_path": "/nonexistent/path.xml"})
        with pytest.raises(FileNotFoundError):
            mod.apply(tmp_path)


# ---------------------------------------------------------------------------
# FeaturesModule  (non-Windows path only)
# ---------------------------------------------------------------------------

class TestFeaturesModule:
    def test_writes_pending_json_on_non_windows(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        mod = FeaturesModule({
            "enable": ["TelnetClient"],
            "disable": ["WindowsMediaPlayer"],
        })
        mod.apply(tmp_path)
        pending = tmp_path / "features_pending.json"
        assert pending.exists()
        data = json.loads(pending.read_text(encoding="utf-8"))
        assert "TelnetClient" in data["enable"]
        assert "WindowsMediaPlayer" in data["disable"]

    def test_pending_json_merges_entries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        # First application
        mod1 = FeaturesModule({"enable": ["TelnetClient"]})
        mod1.apply(tmp_path)
        # Second application adds more
        mod2 = FeaturesModule({"enable": ["HyperV"]})
        mod2.apply(tmp_path)
        data = json.loads((tmp_path / "features_pending.json").read_text(encoding="utf-8"))
        assert "TelnetClient" in data["enable"]
        assert "HyperV" in data["enable"]

    def test_no_features_does_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        mod = FeaturesModule({})
        mod.apply(tmp_path)
        assert not (tmp_path / "features_pending.json").exists()
