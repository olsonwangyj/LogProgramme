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
    _configure_logging(args.verbose, args.trace_lines)
    if args.distribution_distance_source != "hardware_actual":
        logging.getLogger("log_activity_tool").error(
            "Software distance sources are no longer supported. Hardware actual distance is the only supported distance source."
        )
        return 1
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
            enable_distribution_analysis=not args.no_distribution,
            distribution_output_dir=args.distribution_output_dir,
            max_distribution_charts=args.max_distribution_charts,
            embed_distribution_charts=not args.no_embed_distribution_charts,
            movement_distance_round_digits=args.movement_distance_round_digits,
            distribution_distance_source=args.distribution_distance_source,
            distribution_distance_grouping_mode=args.distribution_distance_grouping_mode,
            movement_distance_bin_size=args.movement_distance_bin_size,
            distribution_allow_nearest_pwm=args.distribution_allow_nearest_pwm,
            distribution_allow_latest_before_pwm=args.distribution_allow_latest_before_pwm,
            distribution_allow_carry_forward_pwm=args.distribution_allow_carry_forward_pwm,
            distribution_allow_nearest_hardware_segment=args.distribution_allow_nearest_hardware_segment,
            distribution_allow_ambiguous_hardware_segment=args.distribution_allow_ambiguous_hardware_segment,
            allow_pwm_carry_forward=args.pwm_carry_forward,
            export_distribution_image_gallery=args.distribution_image_gallery,
            distribution_image_gallery_output=args.distribution_image_gallery_output,
            distribution_image_gallery_layout=args.distribution_image_gallery_layout,
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
        help=(
            "Backward-compatible legacy control-log input. If a .log file is provided, "
            "its parent folder is scanned for all .log files and a warning is logged."
        ),
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
        "--no-distribution",
        action="store_true",
        help="Disable normal distribution analysis and chart generation.",
    )
    parser.add_argument(
        "--distribution-output-dir",
        help="Optional folder where normal distribution chart PNG files are saved.",
    )
    parser.add_argument(
        "--max-distribution-charts",
        type=int,
        default=200,
        help="Maximum number of distribution charts to generate. Largest groups are charted first.",
    )
    parser.add_argument(
        "--no-embed-distribution-charts",
        action="store_true",
        help="Save chart PNG files externally but do not embed them in the Excel workbook.",
    )
    parser.add_argument(
        "--movement-distance-round-digits",
        type=int,
        default=2,
        help="Decimal places used when grouping movement distances.",
    )
    parser.add_argument(
        "--distribution-distance-source",
        "--distance-source",
        default="hardware_actual",
        help="Movement distance source used for distribution grouping. Only hardware_actual is supported.",
    )
    parser.add_argument(
        "--distribution-distance-grouping-mode",
        choices=["exact", "round_digits", "bin"],
        default="bin",
        help="How selected movement distances are grouped for distribution analysis.",
    )
    parser.add_argument(
        "--movement-distance-bin-size",
        type=float,
        default=0.1,
        help="Distance bin size used when --distribution-distance-grouping-mode bin is active.",
    )
    parser.add_argument(
        "--distribution-allow-nearest-pwm",
        action="store_true",
        help="Allow nearest-file PWM matches in distribution groups.",
    )
    parser.add_argument(
        "--distribution-allow-latest-before-pwm",
        action="store_true",
        help="Allow latest-before-start PWM matches in distribution groups.",
    )
    parser.add_argument(
        "--distribution-allow-carry-forward-pwm",
        action="store_true",
        help="Allow carry-forward PWM matches in distribution groups.",
    )
    parser.add_argument(
        "--distribution-allow-nearest-hardware-segment",
        action="store_true",
        help="Allow nearest previous/future hardware TPOS segment fallback matches in distribution groups.",
    )
    parser.add_argument(
        "--distribution-allow-ambiguous-hardware-segment",
        action="store_true",
        help="Allow overlapping hardware matches with multiple same-axis candidates in distribution groups.",
    )
    parser.add_argument(
        "--pwm-carry-forward",
        action="store_true",
        help="Allow same-axis PWM values to carry forward when strict time matching cannot find reliable evidence.",
    )
    gallery_group = parser.add_mutually_exclusive_group()
    gallery_group.add_argument(
        "--distribution-image-gallery",
        dest="distribution_image_gallery",
        action="store_true",
        help="Export a separate workbook containing distribution chart images and image statistics.",
    )
    gallery_group.add_argument(
        "--no-distribution-image-gallery",
        dest="distribution_image_gallery",
        action="store_false",
        help="Do not export the separate distribution image gallery workbook.",
    )
    parser.add_argument(
        "--distribution-image-gallery-output",
        help="Optional path for the separate distribution image gallery workbook.",
    )
    parser.add_argument(
        "--distribution-image-gallery-layout",
        choices=["vertical", "compact_grid"],
        default="vertical",
        help="Layout for the separate distribution image gallery workbook.",
    )
    parser.set_defaults(distribution_image_gallery=None)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--trace-lines",
        action="store_true",
        help="Include per-line parser debug logging when --verbose is enabled.",
    )
    return parser.parse_args(argv)


def _configure_logging(verbose: bool, trace_lines: bool = False) -> None:
    """Initialize application logging with a simple console format."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    if verbose and not trace_lines:
        for logger_name in (
            "log_activity_tool.service.loader",
            "log_activity_tool.service.main_log_parser",
            "log_activity_tool.service.pwm_log_parser",
            "log_activity_tool.service.matcher",
            "log_activity_tool.service.pwm_associator",
            "log_activity_tool.service.hardware_motion",
            "log_activity_tool.service.distribution",
            "log_activity_tool.service.validator",
            "log_activity_tool.service.summary",
            "log_activity_tool.service.excel_exporter",
            "log_activity_tool.service.distribution_charts",
            "log_activity_tool.service.distribution_image_gallery",
        ):
            logging.getLogger(logger_name).setLevel(logging.INFO)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("PIL.PngImagePlugin").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


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
    print(f"Closed by new start: {result.closed_by_new_start_count}")
    print(f"Initialization failed rows: {result.initialization_failed_count}")
    print(f"Diagnostics: {result.diagnostic_count}")
    print(f"Parse warnings: {result.parse_warning_count}")
    print(f"Duration warnings: {result.duration_warning_count}")
    print(f"Hardware matched by overlap: {result.hardware_matched_by_overlap_count}")
    print(f"Hardware nearest previous: {result.hardware_nearest_previous_count}")
    print(f"Hardware nearest future: {result.hardware_nearest_future_count}")
    print(f"Hardware nearest generic: {result.hardware_nearest_count}")
    print(f"Hardware multiple candidates: {result.hardware_multiple_candidates_count}")
    print(f"Hardware no segment found: {result.hardware_no_segment_found_count}")
    print(f"Hardware segment incomplete: {result.hardware_segment_incomplete_count}")
    print(f"Hardware warnings: {result.hardware_warning_count}")
    print(f"Hardware duplicate segment groups: {result.hardware_duplicate_segment_group_count}")
    print(f"Hardware duplicate segment rows: {result.hardware_duplicate_segment_row_count}")
    print(f"PWM warnings: {result.pwm_warning_count}")
    if getattr(result, "distribution_enabled", False):
        print(f"Distribution groups: {result.distribution_group_count}")
        print(f"Distribution raw rows: {result.distribution_raw_row_count}")
        print(f"Distribution charts: {result.distribution_chart_count}")
        print(f"Distribution chart folder: {result.distribution_output_dir}")
        print(f"Distribution image gallery: {result.distribution_image_gallery_path}")
        print(
            "Distribution groups with chart file path: "
            f"{result.distribution_gallery_groups_with_chart_file_path_count}"
        )
        print(f"Distribution existing chart files: {result.distribution_gallery_existing_chart_file_count}")
        print(f"Distribution images inserted into gallery: {result.distribution_image_count}")
        print(f"Distribution image statistics rows: {result.distribution_image_statistics_count}")
        print(f"Distribution groups without charts: {result.distribution_gallery_groups_without_charts_count}")
        print(f"Distribution images skipped due to image limit: {result.distribution_gallery_image_limit_skipped_count}")
        print(f"Distribution gallery missing chart files: {result.distribution_gallery_missing_chart_file_count}")
        print(
            "Distribution gallery image embedding unavailable: "
            f"{result.distribution_gallery_image_embedding_unavailable_count}"
        )
        print(f"Distribution gallery image insert failures: {result.distribution_gallery_image_insert_failed_count}")
        print(
            "Distribution rows excluded unreliable hardware match: "
            f"{result.distribution_excluded_unreliable_hardware_count}"
        )
        if getattr(result, "distribution_image_gallery_error", ""):
            print(f"Distribution image gallery error: {result.distribution_image_gallery_error}")
        if getattr(result, "distribution_exclusion_reason_counts", None):
            print("Distribution exclusion reasons:")
            for reason, count in sorted(result.distribution_exclusion_reason_counts.items()):
                print(f"  {reason}: {count}")
        else:
            print(f"Distribution rows excluded missing PWM: {result.distribution_excluded_missing_pwm_count}")
            print(f"Distribution rows excluded missing movement distance: {result.distribution_excluded_missing_distance_count}")
            print(
                "Distribution rows excluded missing true movement distance: "
                f"{result.distribution_excluded_missing_true_distance_count}"
            )
            print(f"Distribution rows excluded unreliable PWM: {result.distribution_excluded_unreliable_pwm_count}")
    print(f"TXT encoding: {result.txt_encoding}")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
