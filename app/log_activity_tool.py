"""Command-line and file-picker entrypoint for the TXT-plus-log-folder analyzer."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

try:
    from backend.log_axis_activity_analyzer.service import LogAnalysisService
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without dependencies installed.
    LogAnalysisService = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def main(argv: list[str] | None = None) -> int:
    """Parse user input, run the analysis service, and return a process exit code."""

    args = _parse_arguments(argv)
    _configure_logging(args.verbose)
    if IMPORT_ERROR is not None or LogAnalysisService is None:
        logging.getLogger("log_activity_tool").error(
            "Missing dependency %s. Install packages with `pip install -r requirements.txt`.",
            getattr(IMPORT_ERROR, "name", "unknown"),
        )
        return 1
    try:
        resolved = _resolve_paths(args)
        service = LogAnalysisService(logging.getLogger("log_activity_tool.service"))
        result = service.run_analysis(
            txt_file_path=resolved["txt_file"],
            log_folder_path=resolved["log_folder"],
            output_path=resolved["output"],
            encoding_txt=args.encoding_txt,
            encoding_logs=args.encoding_logs,
            association_strategy=args.association_strategy,
            recursive=args.recursive,
        )
        _print_summary(result)
        return 0
    except Exception as exc:  # pragma: no cover - integration-oriented guard clause.
        logging.getLogger("log_activity_tool").exception("Analysis failed: %s", exc)
        return 1


def _parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Build the CLI parser and return parsed arguments."""

    parser = argparse.ArgumentParser(
        description="Analyze axis activity durations from one TXT file plus a folder of robot control logs.",
    )
    parser.add_argument(
        "--txt-file",
        "--log-a",
        dest="txt_file",
        help="Path to the main UroBiopsy TXT log file.",
    )
    parser.add_argument(
        "--log-folder",
        dest="log_folder",
        help="Path to the folder containing robot control .log files.",
    )
    parser.add_argument(
        "--log-b",
        dest="legacy_log_b",
        help="Backward-compatible legacy control-log input. If a file is provided, its parent folder is used and a warning is logged.",
    )
    parser.add_argument("--output", help="Destination .xlsx workbook path.")
    parser.add_argument(
        "--encoding-txt",
        "--encoding-a",
        dest="encoding_txt",
        help="Optional override encoding for the main TXT file.",
    )
    parser.add_argument(
        "--encoding-logs",
        "--log-folder-encoding",
        dest="encoding_logs",
        help="Optional override encoding for files in the log folder.",
    )
    parser.add_argument(
        "--association-strategy",
        choices=["same_file_then_nearest", "latest_before_start", "latest_known"],
        default="same_file_then_nearest",
        help="How PWM history should be matched to activities.",
    )
    parser.add_argument(
        "--recursive",
        "--recursive-log-folder",
        dest="recursive",
        action="store_true",
        help="Recursively scan subfolders under the selected log folder for .log files.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Disable file-picker dialogs and require all three paths on the command line.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def _configure_logging(verbose: bool) -> None:
    """Initialize application logging with a simple console format."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def _resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    """Resolve required paths from CLI arguments, legacy aliases, and optional dialogs."""

    legacy_folder = _resolve_legacy_log_folder(args.legacy_log_b)
    resolved = {
        "txt_file": Path(args.txt_file).expanduser() if args.txt_file else None,
        "log_folder": Path(args.log_folder).expanduser() if args.log_folder else legacy_folder,
        "output": Path(args.output).expanduser() if args.output else None,
    }
    missing_keys = [key for key, value in resolved.items() if value is None]
    if not missing_keys:
        return resolved
    if args.no_gui:
        missing_labels = ", ".join(missing_keys)
        raise ValueError(f"Missing required path arguments: {missing_labels}")
    dialog_paths = _prompt_for_missing_paths(missing_keys)
    for key, value in dialog_paths.items():
        resolved[key] = value
    if any(value is None for value in resolved.values()):
        raise ValueError("Analysis cancelled because not all required paths were selected.")
    return resolved


def _resolve_legacy_log_folder(legacy_value: str | None) -> Path | None:
    """Translate the old `--log-b` input into the new folder-based input model."""

    if not legacy_value:
        return None
    legacy_path = Path(legacy_value).expanduser()
    logger = logging.getLogger("log_activity_tool")
    if legacy_path.suffix.lower() == ".log":
        logger.warning(
            "Legacy --log-b file input was used. The parent folder %s will be scanned for .log files.",
            legacy_path.parent,
        )
        return legacy_path.parent
    logger.warning("Legacy --log-b input was used with folder %s.", legacy_path)
    return legacy_path


def _prompt_for_missing_paths(missing_keys: list[str]) -> dict[str, Path | None]:
    """Open file dialogs for any paths that were not provided on the command line."""

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        raise RuntimeError("Tkinter file dialogs are unavailable on this environment.") from exc
    root = tk.Tk()
    root.withdraw()
    selected: dict[str, Path | None] = {}
    try:
        if "txt_file" in missing_keys:
            selected_value = filedialog.askopenfilename(title="Select Main TXT File")
            selected["txt_file"] = Path(selected_value) if selected_value else None
        if "log_folder" in missing_keys:
            selected_value = filedialog.askdirectory(title="Select Log Folder")
            selected["log_folder"] = Path(selected_value) if selected_value else None
        if "output" in missing_keys:
            selected_value = filedialog.asksaveasfilename(
                title="Select Output Workbook",
                defaultextension=".xlsx",
                filetypes=[("Excel Workbook", "*.xlsx")],
            )
            selected["output"] = Path(selected_value) if selected_value else None
    finally:
        root.destroy()
    return selected


def _print_summary(result) -> None:
    """Print the finished run summary to stdout."""

    print(f"Workbook: {result.output_path}")
    print(f"TXT axis events parsed: {result.txt_axis_event_count}")
    print(f"TXT boundary events parsed: {result.boundary_event_count}")
    print(f"Log files scanned: {result.log_file_count}")
    print(f"PWM profiles found: {result.pwm_profile_count}")
    print(f"Details rows: {result.detail_count}")
    print(f"Matched rows: {result.matched_count}")
    print(f"Unmatched starts: {result.unmatched_start_count}")
    print(f"Unmatched ends: {result.unmatched_end_count}")
    print(f"Closed by boundary: {result.closed_by_boundary_count}")
    print(f"Initialization failed rows: {result.initialization_failed_count}")
    print(f"Diagnostics: {result.diagnostic_count}")
    print(f"Parse warnings: {result.parse_warning_count}")
    print(f"Duration warnings: {result.duration_warning_count}")
    print(f"PWM warnings: {result.pwm_warning_count}")
    print(f"TXT encoding: {result.txt_encoding}")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
