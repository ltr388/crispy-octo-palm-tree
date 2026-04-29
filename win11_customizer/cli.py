"""Command-line interface for win11-customizer.

Usage
-----
::

    # Show help
    win11-customizer --help

    # Customise an ISO using a JSON config file
    win11-customizer build --config my_config.json --output Win11_Custom.iso

    # Quick one-shot customisation without a config file
    win11-customizer build \\
        --iso Win11_Insider.iso \\
        --output Win11_Custom.iso \\
        --module registry:presets=disable_telemetry,show_file_extensions \\
        --module unattend:computer_name=MY-PC,time_zone=UTC

    # List available built-in modules
    win11-customizer list-modules

    # List available registry presets
    win11-customizer list-presets

    # Validate an ISO (no changes made)
    win11-customizer validate Win11_Insider.iso
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import textwrap
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="win11-customizer",
        description="Load a Windows 11 Insider ISO and apply modules / customisations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ------------------------------------------------------------------ build
    build_p = sub.add_parser(
        "build",
        help="Customise an ISO.",
        description="Extract, modify, and repack a Windows 11 ISO.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples
            --------
            Using a config file:
              win11-customizer build --config my_config.json --output Win11_Custom.iso

            Inline modules (key=value pairs, comma-separated per --module):
              win11-customizer build \\
                --iso Win11.iso \\
                --output Win11_Custom.iso \\
                --module registry:presets=disable_telemetry \\
                --module unattend:computer_name=MY-PC
        """),
    )
    build_p.add_argument(
        "--iso",
        metavar="ISO_PATH",
        help="Path to the source Windows 11 ISO (overrides config file).",
    )
    build_p.add_argument(
        "--output", "-o",
        metavar="OUTPUT_ISO",
        required=True,
        help="Destination path for the customised ISO.",
    )
    build_p.add_argument(
        "--config", "-c",
        metavar="CONFIG_FILE",
        help="JSON configuration file.",
    )
    build_p.add_argument(
        "--work-dir",
        metavar="DIR",
        help="Working directory for extraction.  A temp dir is used when omitted.",
    )
    build_p.add_argument(
        "--module", "-m",
        metavar="TYPE[:key=val,…]",
        action="append",
        dest="modules",
        help=(
            "Add a module inline.  Repeat for multiple modules.  "
            "Example: --module registry:presets=disable_telemetry"
        ),
    )
    build_p.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip ISO validation before extraction.",
    )

    # ---------------------------------------------------------------- validate
    val_p = sub.add_parser(
        "validate",
        help="Validate a Windows 11 ISO (no changes made).",
    )
    val_p.add_argument("iso", metavar="ISO_PATH")

    # ------------------------------------------------------------ list-modules
    sub.add_parser(
        "list-modules",
        help="List all available built-in modules.",
    )

    # ------------------------------------------------------------- list-presets
    sub.add_parser(
        "list-presets",
        help="List all built-in registry presets.",
    )

    # --------------------------------------------------------- apply-pending
    pend_p = sub.add_parser(
        "apply-pending",
        help="Apply pending DISM feature changes from features_pending.json (Windows only).",
    )
    pend_p.add_argument(
        "--work-dir",
        metavar="DIR",
        required=True,
        help="Working directory that contains features_pending.json.",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_build(args: argparse.Namespace) -> int:
    from win11_customizer.customizer import Customizer, _build_module

    # Build config dict
    config: dict[str, Any] = {}

    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: config file not found: {config_path}", file=sys.stderr)
            return 1
        with config_path.open(encoding="utf-8") as fh:
            config = json.load(fh)

    # CLI overrides
    if args.iso:
        config["iso_path"] = args.iso
    if args.work_dir:
        config["work_dir"] = args.work_dir

    if "iso_path" not in config:
        print("Error: --iso is required (or set 'iso_path' in --config).", file=sys.stderr)
        return 1

    # Inline modules
    inline_modules = []
    for mod_spec in args.modules or []:
        mod_type, _, kv_str = mod_spec.partition(":")
        mod_conf: dict[str, Any] = {}
        if kv_str:
            for pair in kv_str.split(","):
                k, _, v = pair.partition("=")
                # Detect list values (semicolon-separated)
                if ";" in v:
                    mod_conf[k.strip()] = [x.strip() for x in v.split(";")]
                else:
                    mod_conf[k.strip()] = v.strip()
        inline_modules.append(_build_module(mod_type.strip(), mod_conf))

    customizer = Customizer.from_config(config)
    customizer.add_modules(inline_modules)

    try:
        out = customizer.run(args.output, validate=not args.no_validate)
        print(f"✓ Customised ISO written to: {out}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    from win11_customizer.iso_handler import ISOHandler, ISOHandlerError

    handler = ISOHandler(args.iso)
    try:
        handler.validate()
        sha = handler.checksum()
        print(f"✓ ISO is valid: {handler.iso_path}")
        print(f"  SHA-256: {sha}")
        return 0
    except ISOHandlerError as exc:
        print(f"✗ Validation failed: {exc}", file=sys.stderr)
        return 1


def _cmd_list_modules(_args: argparse.Namespace) -> int:
    from win11_customizer.modules.unattend import UnattendModule
    from win11_customizer.modules.features import FeaturesModule
    from win11_customizer.modules.registry import RegistryModule
    from win11_customizer.modules.bloatware import BloatwareModule
    from win11_customizer.modules.onedrive import OneDriveModule
    from win11_customizer.modules.edge import EdgeModule
    from win11_customizer.modules.privacy import PrivacyModule
    from win11_customizer.modules.taskbar import TaskbarModule
    from win11_customizer.modules.power import PowerModule
    from win11_customizer.modules.wsl import WSLModule
    from win11_customizer.modules.drivers import DriversModule
    from win11_customizer.modules.fonts import FontsModule
    from win11_customizer.modules.wallpaper import WallpaperModule
    from win11_customizer.modules.office import OfficeModule
    from win11_customizer.modules.scripts import ScriptsModule
    from win11_customizer.modules.security import SecurityModule
    from win11_customizer.modules.updates import UpdatesModule

    all_modules = [
        UnattendModule, FeaturesModule, RegistryModule,
        BloatwareModule, OneDriveModule, EdgeModule,
        PrivacyModule, TaskbarModule, PowerModule,
        WSLModule, DriversModule, FontsModule,
        WallpaperModule, OfficeModule, ScriptsModule,
        SecurityModule, UpdatesModule,
    ]
    print(f"{'NAME':<20} {'CATEGORY':<16} DESCRIPTION")
    print("-" * 80)
    for klass in all_modules:
        m = klass.metadata
        desc = m.description[:42] + "…" if len(m.description) > 43 else m.description
        print(f"{m.name:<20} {m.category:<16} {desc}")
    return 0


def _cmd_list_presets(_args: argparse.Namespace) -> int:
    from win11_customizer.modules.registry import PRESETS

    print(f"{'PRESET NAME':<30}  FIRST LINE OF CONTENT")
    print("-" * 72)
    for name, content in sorted(PRESETS.items()):
        first = next((l for l in content.splitlines() if l.strip() and not l.startswith(";") and "Windows Registry" not in l), "")
        print(f"{name:<30}  {first[:40]}")
    return 0


def _cmd_apply_pending(args: argparse.Namespace) -> int:
    import platform
    import json as _json

    if platform.system() != "Windows":
        print("Error: apply-pending requires a Windows host (DISM).", file=sys.stderr)
        return 1

    work_dir = Path(args.work_dir)
    pending = work_dir / "features_pending.json"
    if not pending.exists():
        print(f"No pending features file found at {pending}", file=sys.stderr)
        return 1

    payload = _json.loads(pending.read_text(encoding="utf-8"))
    from win11_customizer.modules.features import FeaturesModule

    mod = FeaturesModule(payload)
    try:
        mod.apply(work_dir)
        pending.unlink()
        print("✓ Pending features applied and manifest removed.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    dispatch = {
        "build": _cmd_build,
        "validate": _cmd_validate,
        "list-modules": _cmd_list_modules,
        "list-presets": _cmd_list_presets,
        "apply-pending": _cmd_apply_pending,
    }
    handler = dispatch[args.command]
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
