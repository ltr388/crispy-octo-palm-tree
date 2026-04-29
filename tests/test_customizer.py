"""Tests for the Customizer orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from win11_customizer.customizer import Customizer, _build_module, _topological_sort
from win11_customizer.modules import BaseModule, ModuleMetadata
from win11_customizer.modules.registry import RegistryModule
from win11_customizer.modules.unattend import UnattendModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TrackingModule(BaseModule):
    """Module that records whether apply() was called."""

    metadata = ModuleMetadata(name="tracking", description="Tracking module")
    applied: list[Path] = []

    def __init__(self, config=None):
        super().__init__(config)
        TrackingModule.applied = []

    def apply(self, work_dir: Path) -> None:
        TrackingModule.applied.append(work_dir)


class DepModule(BaseModule):
    metadata = ModuleMetadata(
        name="dep_module",
        description="Depends on tracking",
        requires=["tracking"],
    )
    order: list[str] = []

    def apply(self, work_dir: Path) -> None:
        DepModule.order.append("dep_module")


class TrackingModuleForOrder(BaseModule):
    metadata = ModuleMetadata(name="tracking", description="Tracking for order")
    order: list[str] = []

    def apply(self, work_dir: Path) -> None:
        TrackingModuleForOrder.order.append("tracking")


# ---------------------------------------------------------------------------
# _build_module
# ---------------------------------------------------------------------------

class TestBuildModule:
    def test_builds_registry_module(self) -> None:
        m = _build_module("registry", {})
        assert isinstance(m, RegistryModule)

    def test_builds_unattend_module(self) -> None:
        m = _build_module("unattend", {})
        assert isinstance(m, UnattendModule)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown module type"):
            _build_module("nonexistent", {})


# ---------------------------------------------------------------------------
# _topological_sort
# ---------------------------------------------------------------------------

class TestTopologicalSort:
    def test_no_deps_order_preserved(self) -> None:
        mods = [RegistryModule(), UnattendModule()]
        result = _topological_sort(mods)
        assert [m.metadata.name for m in result] == ["registry", "unattend"]

    def test_dep_comes_first(self) -> None:
        DepModule.order = []
        TrackingModuleForOrder.order = []
        dep = DepModule()
        tracking = TrackingModuleForOrder()
        # dep requires tracking – tracking must come first
        result = _topological_sort([dep, tracking])
        names = [m.metadata.name for m in result]
        assert names.index("tracking") < names.index("dep_module")


# ---------------------------------------------------------------------------
# Customizer.from_config
# ---------------------------------------------------------------------------

class TestFromConfig:
    def test_missing_iso_path_raises(self) -> None:
        with pytest.raises(KeyError):
            Customizer.from_config({})

    def test_valid_config(self, tmp_path: Path) -> None:
        fake_iso = tmp_path / "fake.iso"
        fake_iso.write_bytes(b"\x00" * 10)
        config = {
            "iso_path": str(fake_iso),
            "work_dir": str(tmp_path),
            "modules": [
                {"type": "unattend", "computer_name": "PC1"},
                {"type": "registry", "presets": ["disable_telemetry"]},
            ],
        }
        c = Customizer.from_config(config)
        assert len(c._modules) == 2

    def test_module_missing_type_raises(self, tmp_path: Path) -> None:
        fake_iso = tmp_path / "fake.iso"
        fake_iso.write_bytes(b"\x00" * 10)
        with pytest.raises(ValueError, match="'type' key"):
            Customizer.from_config({
                "iso_path": str(fake_iso),
                "modules": [{"presets": ["disable_telemetry"]}],
            })


class TestFromConfigFile:
    def test_loads_json_config(self, tmp_path: Path) -> None:
        fake_iso = tmp_path / "fake.iso"
        fake_iso.write_bytes(b"\x00" * 10)
        config = {
            "iso_path": str(fake_iso),
            "work_dir": str(tmp_path),
            "modules": [],
        }
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps(config), encoding="utf-8")
        c = Customizer.from_config_file(cfg_file)
        assert isinstance(c, Customizer)


# ---------------------------------------------------------------------------
# add_module / add_modules chaining
# ---------------------------------------------------------------------------

class TestModuleRegistration:
    def test_chaining(self, tmp_path: Path) -> None:
        fake_iso = tmp_path / "fake.iso"
        fake_iso.write_bytes(b"\x00" * 10)
        c = Customizer(fake_iso, work_dir=tmp_path)
        result = c.add_module(RegistryModule()).add_module(UnattendModule())
        assert result is c
        assert len(c._modules) == 2

    def test_add_modules_list(self, tmp_path: Path) -> None:
        fake_iso = tmp_path / "fake.iso"
        fake_iso.write_bytes(b"\x00" * 10)
        c = Customizer(fake_iso, work_dir=tmp_path)
        c.add_modules([RegistryModule(), UnattendModule()])
        assert len(c._modules) == 2
