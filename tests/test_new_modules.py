"""Tests for new built-in modules (bloatware, onedrive, edge, privacy,
taskbar, power, wsl, drivers, fonts, wallpaper, office, scripts,
security, updates)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from win11_customizer.modules.bloatware import BloatwareModule, DEFAULT_PACKAGES
from win11_customizer.modules.onedrive import OneDriveModule
from win11_customizer.modules.edge import EdgeModule
from win11_customizer.modules.privacy import PrivacyModule, PRIVACY_PRESETS, ALL_PRESETS
from win11_customizer.modules.taskbar import TaskbarModule
from win11_customizer.modules.power import PowerModule, KNOWN_PLANS
from win11_customizer.modules.wsl import WSLModule
from win11_customizer.modules.drivers import DriversModule
from win11_customizer.modules.fonts import FontsModule
from win11_customizer.modules.wallpaper import WallpaperModule
from win11_customizer.modules.office import OfficeModule
from win11_customizer.modules.scripts import ScriptsModule
from win11_customizer.modules.security import SecurityModule, SECURITY_PRESETS
from win11_customizer.modules.updates import UpdatesModule, UPDATE_PRESETS


# ---------------------------------------------------------------------------
# Helper shortcuts
# ---------------------------------------------------------------------------

def _scripts_dir(work_dir: Path) -> Path:
    return work_dir / "$OEM$" / "$$" / "Setup" / "Scripts"


def _setup_cmd(work_dir: Path) -> str:
    p = _scripts_dir(work_dir) / "SetupComplete.cmd"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ---------------------------------------------------------------------------
# BloatwareModule
# ---------------------------------------------------------------------------

class TestBloatwareModule:
    def test_writes_removal_script_on_linux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        mod = BloatwareModule()
        mod.apply(tmp_path)
        ps = _scripts_dir(tmp_path) / "Remove-Bloatware.ps1"
        assert ps.exists()
        content = ps.read_text(encoding="utf-8")
        assert "Microsoft.Teams" in content

    def test_respects_keep_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        mod = BloatwareModule({
            "packages": ["Microsoft.Teams", "Microsoft.Xbox"],
            "keep": ["Microsoft.Teams"],
        })
        mod.apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Remove-Bloatware.ps1").read_text(encoding="utf-8")
        assert "Microsoft.Teams" not in content
        assert "Microsoft.Xbox" in content

    def test_extra_packages_added(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        mod = BloatwareModule({
            "packages": [],
            "extra_packages": ["Contoso.App"],
        })
        mod.apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Remove-Bloatware.ps1").read_text(encoding="utf-8")
        assert "Contoso.App" in content

    def test_wired_into_setup_cmd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        BloatwareModule().apply(tmp_path)
        assert "Remove-Bloatware.ps1" in _setup_cmd(tmp_path)

    def test_empty_package_list_does_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        BloatwareModule({"packages": [], "extra_packages": []}).apply(tmp_path)
        assert not (_scripts_dir(tmp_path) / "Remove-Bloatware.ps1").exists()

    def test_default_package_list_not_empty(self) -> None:
        assert len(DEFAULT_PACKAGES) > 10


# ---------------------------------------------------------------------------
# OneDriveModule
# ---------------------------------------------------------------------------

class TestOneDriveModule:
    def test_disable_writes_reg_file(self, tmp_path: Path) -> None:
        OneDriveModule({"action": "disable"}).apply(tmp_path)
        reg = _scripts_dir(tmp_path) / "disable_onedrive.reg"
        assert reg.exists()

    def test_remove_writes_ps_script(self, tmp_path: Path) -> None:
        OneDriveModule({"action": "remove"}).apply(tmp_path)
        ps = _scripts_dir(tmp_path) / "Remove-OneDrive.ps1"
        assert ps.exists()
        assert "OneDriveSetup.exe" in ps.read_text(encoding="utf-8")

    def test_remove_setup_binary_deletes_file(self, tmp_path: Path) -> None:
        # Create fake OneDriveSetup.exe in the expected location
        sys32 = tmp_path / "Windows" / "System32"
        sys32.mkdir(parents=True)
        fake_exe = sys32 / "OneDriveSetup.exe"
        fake_exe.write_bytes(b"\x00")
        OneDriveModule({"action": "remove_setup_binary"}).apply(tmp_path)
        assert not fake_exe.exists()

    def test_default_action_is_disable(self, tmp_path: Path) -> None:
        OneDriveModule().apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "disable_onedrive.reg").exists()
        assert not (_scripts_dir(tmp_path) / "Remove-OneDrive.ps1").exists()


# ---------------------------------------------------------------------------
# EdgeModule
# ---------------------------------------------------------------------------

class TestEdgeModule:
    def test_writes_reg_file(self, tmp_path: Path) -> None:
        EdgeModule().apply(tmp_path)
        reg = _scripts_dir(tmp_path) / "configure_edge.reg"
        assert reg.exists()

    def test_home_page_in_reg(self, tmp_path: Path) -> None:
        EdgeModule({"home_page": "https://example.com"}).apply(tmp_path)
        # reg is utf-16, read with that encoding
        content = (_scripts_dir(tmp_path) / "configure_edge.reg").read_text(encoding="utf-16")
        assert "https://example.com" in content

    def test_hide_first_run_keys_present(self, tmp_path: Path) -> None:
        EdgeModule({"hide_first_run": True}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "configure_edge.reg").read_text(encoding="utf-16")
        assert "HideFirstRunExperience" in content

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        EdgeModule().apply(tmp_path)
        assert "configure_edge.reg" in _setup_cmd(tmp_path)


# ---------------------------------------------------------------------------
# PrivacyModule
# ---------------------------------------------------------------------------

class TestPrivacyModule:
    def test_all_presets_applied_by_default(self, tmp_path: Path) -> None:
        PrivacyModule().apply(tmp_path)
        dest = _scripts_dir(tmp_path)
        for name in ALL_PRESETS:
            assert (dest / f"privacy_{name}.reg").exists(), f"Missing preset: {name}"

    def test_single_preset(self, tmp_path: Path) -> None:
        PrivacyModule({"presets": ["advertising_id"]}).apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "privacy_advertising_id.reg").exists()
        assert not (_scripts_dir(tmp_path) / "privacy_location.reg").exists()

    def test_unknown_preset_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown privacy preset"):
            PrivacyModule({"presets": ["does_not_exist"]}).apply(tmp_path)

    def test_all_presets_have_reg_header(self) -> None:
        for name, content in PRIVACY_PRESETS.items():
            assert "Windows Registry Editor Version 5.00" in content, name

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        PrivacyModule({"presets": ["advertising_id"]}).apply(tmp_path)
        assert "privacy_advertising_id.reg" in _setup_cmd(tmp_path)


# ---------------------------------------------------------------------------
# TaskbarModule
# ---------------------------------------------------------------------------

class TestTaskbarModule:
    def test_writes_taskbar_reg(self, tmp_path: Path) -> None:
        TaskbarModule().apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "configure_taskbar.reg").exists()

    def test_writes_startmenu_reg(self, tmp_path: Path) -> None:
        TaskbarModule().apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "configure_startmenu.reg").exists()

    def test_left_alignment_in_reg(self, tmp_path: Path) -> None:
        TaskbarModule({"alignment": "left"}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "configure_taskbar.reg").read_text(encoding="utf-16")
        assert '"TaskbarAl"=dword:00000000' in content

    def test_hide_widgets_key_present(self, tmp_path: Path) -> None:
        TaskbarModule({"hide_widgets": True}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "configure_taskbar.reg").read_text(encoding="utf-16")
        assert "TaskbarDa" in content

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        TaskbarModule().apply(tmp_path)
        cmd = _setup_cmd(tmp_path)
        assert "configure_taskbar.reg" in cmd
        assert "configure_startmenu.reg" in cmd


# ---------------------------------------------------------------------------
# PowerModule
# ---------------------------------------------------------------------------

class TestPowerModule:
    def test_writes_ps_script(self, tmp_path: Path) -> None:
        PowerModule({"plan": "high_performance"}).apply(tmp_path)
        ps = _scripts_dir(tmp_path) / "Configure-PowerPlan.ps1"
        assert ps.exists()
        content = ps.read_text(encoding="utf-8")
        assert KNOWN_PLANS["high_performance"] in content

    def test_default_plan_is_balanced(self, tmp_path: Path) -> None:
        PowerModule().apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Configure-PowerPlan.ps1").read_text(encoding="utf-8")
        assert KNOWN_PLANS["balanced"] in content

    def test_unknown_plan_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown power plan"):
            PowerModule({"plan": "nonexistent"}).apply(tmp_path)

    def test_custom_guid(self, tmp_path: Path) -> None:
        guid = "11111111-2222-3333-4444-555555555555"
        PowerModule({"custom_guid": guid}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Configure-PowerPlan.ps1").read_text(encoding="utf-8")
        assert guid in content

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        PowerModule().apply(tmp_path)
        assert "Configure-PowerPlan.ps1" in _setup_cmd(tmp_path)


# ---------------------------------------------------------------------------
# WSLModule
# ---------------------------------------------------------------------------

class TestWSLModule:
    def test_writes_enable_script(self, tmp_path: Path) -> None:
        WSLModule().apply(tmp_path)
        ps = _scripts_dir(tmp_path) / "Enable-WSL.ps1"
        assert ps.exists()
        content = ps.read_text(encoding="utf-8")
        assert "Microsoft-Windows-Subsystem-Linux" in content

    def test_distro_included_in_script(self, tmp_path: Path) -> None:
        WSLModule({"distro": "Ubuntu"}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Enable-WSL.ps1").read_text(encoding="utf-8")
        assert "Ubuntu" in content

    def test_no_distro_fallback_message(self, tmp_path: Path) -> None:
        WSLModule().apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Enable-WSL.ps1").read_text(encoding="utf-8")
        assert "wsl --install" in content

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        WSLModule().apply(tmp_path)
        assert "Enable-WSL.ps1" in _setup_cmd(tmp_path)


# ---------------------------------------------------------------------------
# DriversModule
# ---------------------------------------------------------------------------

class TestDriversModule:
    def test_no_drivers_does_nothing(self, tmp_path: Path) -> None:
        DriversModule({}).apply(tmp_path)
        assert not (tmp_path / "$OEM$").exists()

    def test_copies_drivers_on_linux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        # Create a fake driver package
        driver_dir = tmp_path / "fake_driver"
        driver_dir.mkdir()
        inf_file = driver_dir / "fake.inf"
        inf_file.write_text("[Version]\nSignature=$WINDOWS NT$\n")
        sys_file = driver_dir / "fake.sys"
        sys_file.write_bytes(b"\x00MZ")

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        DriversModule({"drivers": [str(inf_file)]}).apply(work_dir)

        dest = work_dir / "$OEM$" / "$1" / "Drivers"
        assert any(dest.rglob("*.inf"))

    def test_inf_file_from_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        driver_dir = tmp_path / "drv"
        driver_dir.mkdir()
        (driver_dir / "driver.inf").write_text("[Version]\n")

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        DriversModule({"drivers": [str(driver_dir)]}).apply(work_dir)
        assert any((work_dir / "$OEM$" / "$1" / "Drivers").rglob("*.inf"))


# ---------------------------------------------------------------------------
# FontsModule
# ---------------------------------------------------------------------------

class TestFontsModule:
    def test_no_fonts_does_nothing(self, tmp_path: Path) -> None:
        FontsModule({}).apply(tmp_path)
        assert not (tmp_path / "$OEM$").exists()

    def test_copies_font_files(self, tmp_path: Path) -> None:
        font_dir = tmp_path / "fonts_src"
        font_dir.mkdir()
        font_file = font_dir / "MyFont.ttf"
        font_file.write_bytes(b"\x00\x01\x00\x00")  # minimal TTF magic

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        FontsModule({"fonts": [str(font_file)]}).apply(work_dir)

        dest = work_dir / "$OEM$" / "$$" / "Fonts" / "MyFont.ttf"
        assert dest.exists()

    def test_writes_registration_script(self, tmp_path: Path) -> None:
        font_dir = tmp_path / "fonts_src"
        font_dir.mkdir()
        (font_dir / "A.ttf").write_bytes(b"\x00")

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        FontsModule({"fonts": [str(font_dir)]}).apply(work_dir)

        ps = _scripts_dir(work_dir) / "Register-Fonts.ps1"
        assert ps.exists()

    def test_unsupported_extension_ignored(self, tmp_path: Path) -> None:
        font_dir = tmp_path / "fonts_src"
        font_dir.mkdir()
        (font_dir / "readme.txt").write_text("not a font")

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        FontsModule({"fonts": [str(font_dir)]}).apply(work_dir)
        # No fonts dir should have been created
        assert not (work_dir / "$OEM$" / "$$" / "Fonts").exists()


# ---------------------------------------------------------------------------
# WallpaperModule
# ---------------------------------------------------------------------------

class TestWallpaperModule:
    def _make_image(self, path: Path) -> None:
        path.write_bytes(b"FAKEJPEG")  # content doesn't matter for file-copy tests

    def test_no_config_does_nothing(self, tmp_path: Path) -> None:
        WallpaperModule().apply(tmp_path)
        assert not (tmp_path / "$OEM$").exists()

    def test_copies_wallpaper(self, tmp_path: Path) -> None:
        img = tmp_path / "bg.jpg"
        self._make_image(img)
        work = tmp_path / "work"
        work.mkdir()
        WallpaperModule({"wallpaper": str(img)}).apply(work)
        assert (work / "Windows" / "Web" / "Wallpaper" / "Windows" / "bg.jpg").exists()

    def test_copies_lockscreen(self, tmp_path: Path) -> None:
        img = tmp_path / "lock.jpg"
        self._make_image(img)
        work = tmp_path / "work"
        work.mkdir()
        WallpaperModule({"lockscreen": str(img)}).apply(work)
        assert (work / "Windows" / "Web" / "Screen" / "lock.jpg").exists()

    def test_missing_wallpaper_raises(self, tmp_path: Path) -> None:
        work = tmp_path / "work"
        work.mkdir()
        with pytest.raises(FileNotFoundError):
            WallpaperModule({"wallpaper": "/nonexistent/bg.jpg"}).apply(work)

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bg.pdf"
        bad.write_bytes(b"%PDF")
        work = tmp_path / "work"
        work.mkdir()
        with pytest.raises(ValueError, match="Unsupported image format"):
            WallpaperModule({"wallpaper": str(bad)}).apply(work)

    def test_writes_reg_file(self, tmp_path: Path) -> None:
        img = tmp_path / "bg.png"
        self._make_image(img)
        work = tmp_path / "work"
        work.mkdir()
        WallpaperModule({"wallpaper": str(img)}).apply(work)
        assert (_scripts_dir(work) / "set_wallpaper.reg").exists()


# ---------------------------------------------------------------------------
# OfficeModule
# ---------------------------------------------------------------------------

class TestOfficeModule:
    def test_writes_odt_config(self, tmp_path: Path) -> None:
        OfficeModule().apply(tmp_path)
        config_xml = _scripts_dir(tmp_path) / "Office-Configuration.xml"
        assert config_xml.exists()
        content = config_xml.read_text(encoding="utf-8")
        assert "O365ProPlusRetail" in content

    def test_custom_product_id(self, tmp_path: Path) -> None:
        OfficeModule({"product_id": "ProPlus2021Volume"}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Office-Configuration.xml").read_text(encoding="utf-8")
        assert "ProPlus2021Volume" in content

    def test_exclude_apps_in_xml(self, tmp_path: Path) -> None:
        OfficeModule({"exclude_apps": ["Access", "Publisher"]}).apply(tmp_path)
        content = (_scripts_dir(tmp_path) / "Office-Configuration.xml").read_text(encoding="utf-8")
        assert 'ExcludeApp ID="Access"' in content
        assert 'ExcludeApp ID="Publisher"' in content

    def test_writes_install_script(self, tmp_path: Path) -> None:
        OfficeModule().apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "Install-Office.ps1").exists()

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        OfficeModule().apply(tmp_path)
        assert "Install-Office.ps1" in _setup_cmd(tmp_path)

    def test_missing_source_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            OfficeModule({"source_path": "/nonexistent/office_src"}).apply(tmp_path)


# ---------------------------------------------------------------------------
# ScriptsModule
# ---------------------------------------------------------------------------

class TestScriptsModule:
    def test_no_scripts_does_nothing(self, tmp_path: Path) -> None:
        ScriptsModule().apply(tmp_path)
        # Nothing should be created
        assert not (tmp_path / "$OEM$").exists()

    def test_copies_script_file(self, tmp_path: Path) -> None:
        script = tmp_path / "My-Script.ps1"
        script.write_text("Write-Host 'hello'")
        work = tmp_path / "work"
        work.mkdir()
        ScriptsModule({"scripts": [{"path": str(script)}]}).apply(work)
        dest = _scripts_dir(work) / "My-Script.ps1"
        assert dest.exists()

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        script = tmp_path / "Tweak.ps1"
        script.write_text("# tweak")
        work = tmp_path / "work"
        work.mkdir()
        ScriptsModule({"scripts": [{"path": str(script), "run_at_setup": True}]}).apply(work)
        assert "Tweak.ps1" in _setup_cmd(work)

    def test_run_at_setup_false_skips_cmd(self, tmp_path: Path) -> None:
        script = tmp_path / "Silent.ps1"
        script.write_text("# silent")
        work = tmp_path / "work"
        work.mkdir()
        ScriptsModule({"scripts": [{"path": str(script), "run_at_setup": False}]}).apply(work)
        assert "Silent.ps1" not in _setup_cmd(work)

    def test_cmd_script_uses_call(self, tmp_path: Path) -> None:
        script = tmp_path / "Patch.cmd"
        script.write_text("@echo Patching...")
        work = tmp_path / "work"
        work.mkdir()
        ScriptsModule({"scripts": [{"path": str(script), "run_as": "cmd"}]}).apply(work)
        cmd = _setup_cmd(work)
        assert "call" in cmd.lower() and "Patch.cmd" in cmd

    def test_missing_script_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ScriptsModule({"scripts": [{"path": "/no/such/file.ps1"}]}).apply(tmp_path)


# ---------------------------------------------------------------------------
# SecurityModule
# ---------------------------------------------------------------------------

class TestSecurityModule:
    def test_no_presets_does_nothing(self, tmp_path: Path) -> None:
        SecurityModule().apply(tmp_path)
        assert not (tmp_path / "$OEM$").exists()

    def test_known_preset_creates_reg(self, tmp_path: Path) -> None:
        SecurityModule({"presets": ["disable_smb1"]}).apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "security_disable_smb1.reg").exists()

    def test_unknown_preset_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown security preset"):
            SecurityModule({"presets": ["nonexistent"]}).apply(tmp_path)

    def test_all_presets_have_reg_header(self) -> None:
        for name, content in SECURITY_PRESETS.items():
            assert "Windows Registry Editor Version 5.00" in content, name

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        SecurityModule({"presets": ["uac_high"]}).apply(tmp_path)
        assert "security_uac_high.reg" in _setup_cmd(tmp_path)


# ---------------------------------------------------------------------------
# UpdatesModule
# ---------------------------------------------------------------------------

class TestUpdatesModule:
    def test_no_config_does_nothing(self, tmp_path: Path) -> None:
        UpdatesModule().apply(tmp_path)
        assert not (tmp_path / "$OEM$").exists()

    def test_known_preset_creates_reg(self, tmp_path: Path) -> None:
        UpdatesModule({"presets": ["defer_feature_updates"]}).apply(tmp_path)
        assert (_scripts_dir(tmp_path) / "update_defer_feature_updates.reg").exists()

    def test_unknown_preset_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown update preset"):
            UpdatesModule({"presets": ["nonexistent"]}).apply(tmp_path)

    def test_wsus_reg_written(self, tmp_path: Path) -> None:
        UpdatesModule({"wsus_server": "http://wsus.example.com:8530"}).apply(tmp_path)
        reg = _scripts_dir(tmp_path) / "update_wsus.reg"
        assert reg.exists()
        content = reg.read_text(encoding="utf-16")
        assert "wsus.example.com" in content

    def test_all_presets_have_reg_header(self) -> None:
        for name, content in UPDATE_PRESETS.items():
            assert "Windows Registry Editor Version 5.00" in content, name

    def test_wired_into_setup_cmd(self, tmp_path: Path) -> None:
        UpdatesModule({"presets": ["active_hours"]}).apply(tmp_path)
        assert "update_active_hours.reg" in _setup_cmd(tmp_path)


# ---------------------------------------------------------------------------
# customizer._build_module – all new types resolve
# ---------------------------------------------------------------------------

class TestBuildModuleAllNewTypes:
    @pytest.mark.parametrize("mod_type", [
        "bloatware", "onedrive", "edge", "privacy", "taskbar",
        "power", "wsl", "drivers", "fonts", "wallpaper",
        "office", "scripts", "security", "updates",
    ])
    def test_build_each_module(self, mod_type: str) -> None:
        from win11_customizer.customizer import _build_module
        m = _build_module(mod_type, {})
        assert m.metadata.name == mod_type
