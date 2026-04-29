"""Main orchestrator – ties ISOHandler and modules together.

Usage example
-------------
::

    from pathlib import Path
    from win11_customizer.customizer import Customizer
    from win11_customizer.modules.registry import RegistryModule
    from win11_customizer.modules.unattend import UnattendModule

    c = Customizer(iso_path="Win11_Insider.iso", work_dir="/tmp/win11_work")
    c.add_module(UnattendModule({"computer_name": "MY-PC", "time_zone": "Pacific Standard Time"}))
    c.add_module(RegistryModule({"presets": ["disable_telemetry", "show_file_extensions"]}))
    c.run(output_iso="Win11_Custom.iso")
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from win11_customizer.iso_handler import ISOHandler
from win11_customizer.modules import BaseModule

logger = logging.getLogger(__name__)


class Customizer:
    """High-level orchestrator for loading, modifying, and repacking a Windows 11 ISO.

    Parameters
    ----------
    iso_path:
        Path to the source Windows 11 Insider ISO.
    work_dir:
        Working directory for the extracted ISO tree.  ``None`` creates a
        temporary directory that is removed after :meth:`run` completes.
    """

    def __init__(
        self,
        iso_path: str | os.PathLike,
        work_dir: str | os.PathLike | None = None,
    ) -> None:
        self._handler = ISOHandler(iso_path, work_dir)
        self._modules: list[BaseModule] = []

    # ------------------------------------------------------------------
    # Module management
    # ------------------------------------------------------------------

    def add_module(self, module: BaseModule) -> "Customizer":
        """Register *module* to be applied during :meth:`run`.

        Returns *self* to allow chaining::

            c.add_module(mod_a).add_module(mod_b)
        """
        self._modules.append(module)
        logger.debug("Module registered: %s", module)
        return self

    def add_modules(self, modules: list[BaseModule]) -> "Customizer":
        """Register multiple modules at once."""
        for m in modules:
            self.add_module(m)
        return self

    # ------------------------------------------------------------------
    # Configuration-driven loading
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Customizer":
        """Build a :class:`Customizer` from a configuration dictionary.

        Expected shape::

            {
              "iso_path": "/path/to/Win11.iso",
              "work_dir": "/tmp/win11_work",   # optional
              "modules": [
                {"type": "unattend", "computer_name": "MY-PC"},
                {"type": "registry", "presets": ["disable_telemetry"]},
                {"type": "features", "enable": ["TelnetClient"]}
              ]
            }

        Parameters
        ----------
        config:
            Parsed configuration mapping.

        Raises
        ------
        KeyError
            If ``iso_path`` is missing from the config.
        ValueError
            If an unknown module type is specified.
        """
        iso_path = config["iso_path"]
        work_dir = config.get("work_dir")
        instance = cls(iso_path=iso_path, work_dir=work_dir)

        for mod_conf in config.get("modules", []):
            mod_conf = dict(mod_conf)  # copy so we don't mutate the caller's dict
            mod_type = mod_conf.pop("type", None)
            if mod_type is None:
                raise ValueError("Each module entry must have a 'type' key.")
            module = _build_module(mod_type, mod_conf)
            instance.add_module(module)

        return instance

    @classmethod
    def from_config_file(cls, path: str | os.PathLike) -> "Customizer":
        """Build a :class:`Customizer` from a JSON configuration file.

        Parameters
        ----------
        path:
            Path to a JSON file following the schema described in
            :meth:`from_config`.
        """
        config_path = Path(path).resolve()
        with config_path.open(encoding="utf-8") as fh:
            config = json.load(fh)
        logger.info("Loaded configuration from %s", config_path)
        return cls.from_config(config)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self, output_iso: str | os.PathLike, *, validate: bool = True) -> Path:
        """Execute the full pipeline:

        1. Optionally validate the source ISO.
        2. Extract the ISO to the working directory.
        3. Apply all registered modules in order.
        4. Repack the modified tree into *output_iso*.
        5. Clean up the working directory (if it was auto-created).

        Parameters
        ----------
        output_iso:
            Destination path for the customised ISO.
        validate:
            Whether to run :meth:`ISOHandler.validate` before extraction.

        Returns
        -------
        Path
            Resolved path to the finished ISO.
        """
        with self._handler as h:
            if validate:
                h.validate()
            h.extract()
            self._apply_modules(h.work_dir)
            return h.repack(output_iso)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_modules(self, work_dir: Path) -> None:
        if not self._modules:
            logger.warning("No modules registered – the ISO will be repacked unchanged.")
            return

        # Build a simple dependency order (topological sort by 'requires')
        ordered = _topological_sort(self._modules)

        for module in ordered:
            logger.info("Applying module: %s", module.metadata.name)
            try:
                module.apply(work_dir)
            except Exception as exc:
                logger.error("Module '%s' failed: %s", module.metadata.name, exc)
                raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_module(mod_type: str, config: dict[str, Any]) -> BaseModule:
    """Instantiate a module by its type name."""
    # Lazy imports to avoid circular dependencies
    _registry: dict[str, type[BaseModule]] = {}

    from win11_customizer.modules.unattend import UnattendModule
    from win11_customizer.modules.features import FeaturesModule
    from win11_customizer.modules.registry import RegistryModule

    _registry = {
        "unattend": UnattendModule,
        "features": FeaturesModule,
        "registry": RegistryModule,
    }

    klass = _registry.get(mod_type)
    if klass is None:
        available = ", ".join(sorted(_registry))
        raise ValueError(
            f"Unknown module type '{mod_type}'.  Available types: {available}"
        )
    return klass(config)


def _topological_sort(modules: list[BaseModule]) -> list[BaseModule]:
    """Return *modules* in an order that respects ``metadata.requires``."""
    name_to_module: dict[str, BaseModule] = {m.metadata.name: m for m in modules}
    visited: set[str] = set()
    result: list[BaseModule] = []

    def visit(module: BaseModule) -> None:
        name = module.metadata.name
        if name in visited:
            return
        for dep_name in module.metadata.requires:
            dep = name_to_module.get(dep_name)
            if dep is None:
                logger.warning(
                    "Module '%s' requires '%s' which is not registered – skipping dependency.",
                    name,
                    dep_name,
                )
                continue
            visit(dep)
        visited.add(name)
        result.append(module)

    for m in modules:
        visit(m)

    return result
