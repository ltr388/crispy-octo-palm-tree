"""Module framework for win11_customizer.

Every customisation is a *Module* subclass.  Modules are self-describing
(name, description, category) and implement a single ``apply(work_dir)``
method that mutates the extracted ISO tree.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModuleMetadata:
    """Descriptive metadata attached to every module."""

    name: str
    description: str
    category: str = "general"
    author: str = "community"
    version: str = "1.0.0"
    #: Names of other modules that must be applied before this one.
    requires: list[str] = field(default_factory=list)


class BaseModule(abc.ABC):
    """Abstract base class for all customisation modules.

    Subclasses must:
      1. Set the class-level ``metadata`` attribute.
      2. Implement :meth:`apply`.

    Parameters
    ----------
    config:
        Optional module-specific configuration dictionary.
    """

    metadata: ModuleMetadata

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    @abc.abstractmethod
    def apply(self, work_dir: Path) -> None:
        """Apply this module's changes to the extracted ISO tree.

        Parameters
        ----------
        work_dir:
            Root of the extracted ISO contents (writable).
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.metadata.name!r}>"
