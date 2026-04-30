"""End-to-end orchestration service for TXT parsing, PWM folder scanning, and workbook export."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import (
    ALLOW_PWM_CARRY_FORWARD_ACROSS_SESSION,
    ALLOW_TARGET_ABSOLUTE_DISTANCE_FALLBACK,
    CLEAN_DISTRIBUTION_OUTPUT_DIR_BEFORE_RUN,
    DEFAULT_EVENT_RULES,
    DISTRIBUTION_ALLOW_LATEST_BEFORE_PWM,
    DISTRIBUTION_ALLOW_NEAREST_PWM,
    DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES,
    DISTRIBUTION_CHART_FOLDER_MODE,
    DISTRIBUTION_ALLOW_PWM_CARRY_FORWARD,
    DISTRIBUTION_DISTANCE_GROUPING_MODE,
    DISTRIBUTION_DISTANCE_SOURCE,
    DISTRIBUTION_OUTPUT_SUBDIR,
    DURATION_STATUS_VALID,
    EMBED_DISTRIBUTION_CHARTS_IN_EXCEL,
    ENABLE_DISTRIBUTION_ANALYSIS,
    MOVEMENT_DISTANCE_BIN_SIZE,
    MOVEMENT_DISTANCE_GROUPING_MODES,
    MOVEMENT_DISTANCE_ROUND_DIGITS,
    MOVEMENT_DISTANCE_SOURCE_OPTIONS,
    NORMAL_CHART_BINS,
    NORMAL_DISTRIBUTION_CHART_DPI,
    NORMAL_DISTRIBUTION_CHART_FORMAT,
    NORMAL_DISTRIBUTION_MAX_CHARTS,
    STATUS_CLOSED_BY_BOUNDARY,
    STATUS_CLOSED_BY_NEW_START,
    STATUS_DURATION_TOO_LONG_CANDIDATE,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_PARSE_WARNING,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
    PWM_STATUS_MATCHED_CARRY_FORWARD,
    PWM_STATUS_MATCHED_CONTAINING,
    PWM_STATUS_MATCHED_LATEST_BEFORE,
    PWM_STATUS_MATCHED_NEAREST,
)
from .chart_generator import NormalDistributionChartGenerator
from .distribution import DistributionAnalysisResult, DistributionAnalyzer
from .duty_cycle_associator import DutyCycleAssociator
from .excel_exporter import ExcelExporter
from .file_loader import TextFileLoader
from .log_a_parser import MainLogParser
from .log_b_parser import DutyCycleLogParser
from .log_folder_scanner import LogFolderScanner
from .matcher import EventMatcher
from .models import ActivityRecord, AnalysisRunResult, DiagnosticEvent, DutyCycleFolderParseResult, ParseWarning
from .summary import SummaryGenerator
from .time_utils import format_log_timestamp
from .validation import ActivityValidator


class LogAnalysisService:
    """Coordinates one full analysis run from input paths to workbook output."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the full analysis pipeline and its collaborators."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)
        loader = TextFileLoader(self._logger.getChild("loader"))
        self._main_log_parser = MainLogParser(loader, self._logger.getChild("main_log_parser"))
        pwm_parser = DutyCycleLogParser(loader, self._logger.getChild("pwm_log_parser"))
        self._log_folder_scanner = LogFolderScanner(pwm_parser, self._logger.getChild("log_folder_scanner"))
        self._matcher = EventMatcher(DEFAULT_EVENT_RULES, logger=self._logger.getChild("matcher"))
        self._associator = DutyCycleAssociator(self._logger.getChild("pwm_associator"))
        self._validator = ActivityValidator(self._logger.getChild("validator"))
        self._summary_generator = SummaryGenerator(self._logger.getChild("summary"))
        self._exporter = ExcelExporter(self._logger.getChild("excel_exporter"))

    def run_analysis(
        self,
        txt_file_path: Path | str,
        log_folder_path: Path | str,
        output_path: Path | str,
        encoding_txt: str | None = None,
        encoding_logs: str | None = None,
        association_strategy: str = "same_file_then_nearest",
        recursive: bool = False,
        enable_distribution_analysis: bool = ENABLE_DISTRIBUTION_ANALYSIS,
        distribution_output_dir: Path | str | None = None,
        max_distribution_charts: int = NORMAL_DISTRIBUTION_MAX_CHARTS,
        embed_distribution_charts: bool = EMBED_DISTRIBUTION_CHARTS_IN_EXCEL,
        movement_distance_round_digits: int = MOVEMENT_DISTANCE_ROUND_DIGITS,
        distribution_distance_source: str = DISTRIBUTION_DISTANCE_SOURCE,
        distribution_distance_grouping_mode: str = DISTRIBUTION_DISTANCE_GROUPING_MODE,
        movement_distance_bin_size: float = MOVEMENT_DISTANCE_BIN_SIZE,
        distribution_allow_nearest_pwm: bool = DISTRIBUTION_ALLOW_NEAREST_PWM,
        distribution_allow_latest_before_pwm: bool = DISTRIBUTION_ALLOW_LATEST_BEFORE_PWM,
        distribution_allow_carry_forward_pwm: bool = DISTRIBUTION_ALLOW_PWM_CARRY_FORWARD,
        allow_pwm_carry_forward: bool = ALLOW_PWM_CARRY_FORWARD_ACROSS_SESSION,
        **legacy_kwargs,
    ) -> AnalysisRunResult:
        """Run the full analysis workflow and return a concise execution summary."""

        if "encoding_a" in legacy_kwargs and encoding_txt is None:
            encoding_txt = legacy_kwargs["encoding_a"]
        if "log_folder_encoding" in legacy_kwargs and encoding_logs is None:
            encoding_logs = legacy_kwargs["log_folder_encoding"]
        if "recursive_log_folder" in legacy_kwargs and not recursive:
            recursive = bool(legacy_kwargs["recursive_log_folder"])

        normalized_paths = self._validate_paths(txt_file_path, log_folder_path, output_path)
        main_result = self._main_log_parser.parse(normalized_paths["txt_file"], encoding_txt)
        folder_result = self._log_folder_scanner.scan(
            normalized_paths["log_folder"],
            preferred_encoding=encoding_logs,
            recursive=recursive,
        )
        activity_records = self._matcher.build_activity_records(main_result.timeline)
        enriched_records = self._associator.attach(
            activity_records,
            folder_result.files,
            association_strategy,
            allow_carry_forward=allow_pwm_carry_forward,
        )
        all_records = self._append_parse_warnings(enriched_records, main_result.warnings, folder_result)
        validated_records = self._validator.validate(all_records)
        distribution_result = None
        distribution_allowed_pwm_statuses = self._build_distribution_allowed_pwm_statuses(
            allow_nearest_pwm=distribution_allow_nearest_pwm,
            allow_latest_before_pwm=distribution_allow_latest_before_pwm,
            allow_carry_forward_pwm=distribution_allow_carry_forward_pwm,
        )
        if enable_distribution_analysis:
            distribution_result = self._run_distribution_analysis(
                records=validated_records,
                txt_file=normalized_paths["txt_file"],
                output_path=normalized_paths["output"],
                distribution_output_dir=distribution_output_dir,
                max_distribution_charts=max_distribution_charts,
                embed_distribution_charts=embed_distribution_charts,
                movement_distance_round_digits=movement_distance_round_digits,
                distribution_distance_source=distribution_distance_source,
                distribution_distance_grouping_mode=distribution_distance_grouping_mode,
                movement_distance_bin_size=movement_distance_bin_size,
                allowed_pwm_match_statuses=distribution_allowed_pwm_statuses,
                distribution_allow_carry_forward_pwm=distribution_allow_carry_forward_pwm,
            )
        log_coverage_summary = self._build_log_coverage_summary(
            normalized_paths=normalized_paths,
            main_result=main_result,
            folder_result=folder_result,
            records=validated_records,
            distribution_result=distribution_result,
            distribution_allowed_pwm_match_statuses=distribution_allowed_pwm_statuses,
        )
        report_frames = self._summary_generator.build_report_frames(
            validated_records,
            folder_result.files,
            diagnostics=main_result.diagnostics,
            distribution_result=distribution_result,
            log_coverage_summary=log_coverage_summary,
        )
        run_result = self._build_run_result(
            output_path=normalized_paths["output"],
            records=validated_records,
            diagnostics=main_result.diagnostics,
            txt_encoding=main_result.encoding_used,
            txt_axis_event_count=len(main_result.events),
            boundary_event_count=len(main_result.boundary_events),
            log_file_count=len(folder_result.files),
            pwm_profile_count=sum(len(file_result.axis_profiles) for file_result in folder_result.files),
            distribution_enabled=enable_distribution_analysis,
            distribution_result=distribution_result,
        )
        self._exporter.export(
            normalized_paths["output"],
            report_frames,
            metadata={
                "txt_file_path": str(normalized_paths["txt_file"]),
                "log_folder_path": str(normalized_paths["log_folder"]),
                "output_path": str(normalized_paths["output"]),
                "association_strategy": association_strategy,
                "txt_axis_event_count": run_result.txt_axis_event_count,
                "boundary_event_count": run_result.boundary_event_count,
                "log_file_count": run_result.log_file_count,
                "pwm_profile_count": run_result.pwm_profile_count,
                "matched_count": run_result.matched_count,
                "unmatched_start_count": run_result.unmatched_start_count,
                "unmatched_end_count": run_result.unmatched_end_count,
                "parse_warning_count": run_result.parse_warning_count,
                "closed_by_boundary_count": run_result.closed_by_boundary_count,
                "closed_by_new_start_count": run_result.closed_by_new_start_count,
                "initialization_failed_count": run_result.initialization_failed_count,
                "diagnostic_count": run_result.diagnostic_count,
                "duration_warning_count": run_result.duration_warning_count,
                "pwm_warning_count": run_result.pwm_warning_count,
                "distribution_enabled": run_result.distribution_enabled,
                "distribution_group_count": run_result.distribution_group_count,
                "distribution_raw_row_count": run_result.distribution_raw_row_count,
                "distribution_chart_count": run_result.distribution_chart_count,
                "distribution_output_dir": str(run_result.distribution_output_dir or ""),
                "distribution_excluded_missing_pwm_count": run_result.distribution_excluded_missing_pwm_count,
                "distribution_excluded_missing_distance_count": run_result.distribution_excluded_missing_distance_count,
                "distribution_excluded_missing_true_distance_count": (
                    run_result.distribution_excluded_missing_true_distance_count
                ),
                "distribution_excluded_unreliable_pwm_count": run_result.distribution_excluded_unreliable_pwm_count,
                "embed_distribution_charts": embed_distribution_charts,
                "log_coverage_warning": self._coverage_warning_from_rows(log_coverage_summary),
            },
        )
        return run_result

    def _validate_paths(
        self,
        txt_file_path: Path | str,
        log_folder_path: Path | str,
        output_path: Path | str,
    ) -> dict[str, Path]:
        """Validate the input TXT file, log folder, and output path."""

        self._logger.info("Validating TXT file, log folder, and output path")
        txt_file = Path(txt_file_path).expanduser().resolve()
        log_folder = Path(log_folder_path).expanduser().resolve()
        output = Path(output_path).expanduser().resolve()
        if not txt_file.is_file():
            raise FileNotFoundError(f"TXT file does not exist: {txt_file}")
        if not log_folder.is_dir():
            raise FileNotFoundError(f"Log folder does not exist: {log_folder}")
        output.parent.mkdir(parents=True, exist_ok=True)
        return {"txt_file": txt_file, "log_folder": log_folder, "output": output}

    def _append_parse_warnings(
        self,
        records: list[ActivityRecord],
        txt_warnings: list[ParseWarning],
        folder_result: DutyCycleFolderParseResult,
    ) -> list[ActivityRecord]:
        """Append parse-warning rows so the workbook captures recoverable issues."""

        pwm_warnings = list(folder_result.warnings)
        for file_result in folder_result.files:
            pwm_warnings.extend(file_result.warnings)
        all_warnings = txt_warnings + pwm_warnings
        self._logger.info("Appending %s parse warnings to detail records", len(all_warnings))
        for warning in all_warnings:
            records.append(self._build_warning_record(warning))
        return records

    def _build_warning_record(self, warning: ParseWarning) -> ActivityRecord:
        """Convert one parse warning into the Details worksheet schema."""

        self._logger.debug("Building parse-warning record for %s:%s", warning.source_path, warning.line_number)
        record = ActivityRecord(
            axis=warning.axis,
            match_status=STATUS_PARSE_WARNING,
            activity_status=STATUS_PARSE_WARNING,
            status=STATUS_PARSE_WARNING,
            notes=warning.message,
            sort_time=warning.timestamp,
            sort_index=warning.line_number,
        )
        if warning.source_name == "TXT":
            record.source_txt_start_line = warning.raw_line
            record.start_line_number = warning.line_number
        else:
            record.pwm_source_file = warning.source_path.name
            record.pwm_source_line = warning.raw_line
            record.pwm_line_number = warning.line_number
            record.pwm_match_status = warning.source_name
        return record

    def _run_distribution_analysis(
        self,
        records: list[ActivityRecord],
        txt_file: Path,
        output_path: Path,
        distribution_output_dir: Path | str | None,
        max_distribution_charts: int,
        embed_distribution_charts: bool,
        movement_distance_round_digits: int,
        distribution_distance_source: str,
        distribution_distance_grouping_mode: str,
        movement_distance_bin_size: float,
        allowed_pwm_match_statuses: set[str],
        distribution_allow_carry_forward_pwm: bool,
    ) -> DistributionAnalysisResult:
        """Run distribution grouping, statistics, and chart generation."""

        self._logger.info("Running normal distribution analysis")
        analyzer = DistributionAnalyzer(
            movement_distance_round_digits=movement_distance_round_digits,
            allow_target_absolute_distance_fallback=ALLOW_TARGET_ABSOLUTE_DISTANCE_FALLBACK,
            allowed_pwm_match_statuses=allowed_pwm_match_statuses,
            distance_source=distribution_distance_source,
            distance_grouping_mode=distribution_distance_grouping_mode,
            movement_distance_bin_size=movement_distance_bin_size,
            distribution_allow_pwm_carry_forward=distribution_allow_carry_forward_pwm,
            logger=self._logger.getChild("distribution"),
        )
        result = analyzer.analyze(records, txt_file.name)
        chart_output_dir = self._resolve_distribution_chart_output_dir(output_path, distribution_output_dir)
        self._prepare_distribution_chart_output_dir(chart_output_dir)
        generator = NormalDistributionChartGenerator(
            bins=NORMAL_CHART_BINS,
            dpi=NORMAL_DISTRIBUTION_CHART_DPI,
            chart_format=NORMAL_DISTRIBUTION_CHART_FORMAT,
            max_charts=max_distribution_charts,
            logger=self._logger.getChild("distribution_charts"),
        )
        stats_by_group = {item.group_id: item for item in result.stats}
        generator.generate_charts(result.grouped_rows, stats_by_group, chart_output_dir)
        result.chart_output_dir = chart_output_dir
        self._assign_distribution_chart_anchors(result, embed_distribution_charts)
        return result

    def _resolve_distribution_chart_output_dir(
        self,
        output_path: Path,
        distribution_output_dir: Path | str | None,
    ) -> Path:
        """Resolve the chart output folder for this workbook run."""

        if distribution_output_dir is not None:
            return Path(distribution_output_dir).expanduser().resolve()
        if DISTRIBUTION_CHART_FOLDER_MODE == "per_workbook":
            return (output_path.parent / f"{output_path.stem}_distribution_charts").resolve()
        return (output_path.parent / DISTRIBUTION_OUTPUT_SUBDIR).resolve()

    def _prepare_distribution_chart_output_dir(self, chart_output_dir: Path) -> None:
        """Create and optionally clear the current run's distribution chart folder."""

        chart_output_dir.mkdir(parents=True, exist_ok=True)
        if not CLEAN_DISTRIBUTION_OUTPUT_DIR_BEFORE_RUN:
            return
        for chart_file in chart_output_dir.glob("*.png"):
            chart_file.unlink()

    def _assign_distribution_chart_anchors(
        self,
        distribution_result: DistributionAnalysisResult,
        embed_distribution_charts: bool,
    ) -> None:
        """Set human-readable chart anchors before workbook frames are built."""

        current_row = 1
        for stats in distribution_result.stats:
            if not stats.chart_file:
                continue
            if embed_distribution_charts:
                stats.chart_sheet_anchor = f"Distribution Charts!A{current_row}"
                current_row += 43
            else:
                stats.chart_sheet_anchor = "External chart file"

    def _build_distribution_allowed_pwm_statuses(
        self,
        allow_nearest_pwm: bool,
        allow_latest_before_pwm: bool,
        allow_carry_forward_pwm: bool,
    ) -> set[str]:
        """Resolve PWM statuses accepted for distribution grouping."""

        statuses = set(DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES)
        if allow_nearest_pwm:
            statuses.add(PWM_STATUS_MATCHED_NEAREST)
        if allow_latest_before_pwm:
            statuses.add(PWM_STATUS_MATCHED_LATEST_BEFORE)
        if allow_carry_forward_pwm:
            statuses.add(PWM_STATUS_MATCHED_CARRY_FORWARD)
        return statuses

    def _build_log_coverage_summary(
        self,
        normalized_paths: dict[str, Path],
        main_result,
        folder_result: DutyCycleFolderParseResult,
        records: list[ActivityRecord],
        distribution_result: DistributionAnalysisResult | None,
        distribution_allowed_pwm_match_statuses: set[str],
    ) -> list[dict[str, object]]:
        """Build a one-row summary showing control-log coverage for the TXT timeline."""

        txt_times = [
            item.timestamp
            for item in main_result.timeline
            if getattr(item, "timestamp", None) is not None
        ]
        txt_start = min(txt_times) if txt_times else None
        txt_end = max(txt_times) if txt_times else None
        control_intervals = [
            (item.file_start_time, item.file_end_time)
            for item in folder_result.files
            if item.file_start_time is not None and item.file_end_time is not None
        ]
        log_starts = [start for start, _ in control_intervals]
        log_ends = [end for _, end in control_intervals]
        control_start = min(log_starts) if log_starts else None
        control_end = max(log_ends) if log_ends else None
        txt_duration_s = self._duration_seconds(txt_start, txt_end)
        merged_intervals = self._merge_time_intervals(control_intervals)
        covered_duration_s = self._covered_seconds(txt_start, txt_end, merged_intervals)
        uncovered_spans = self._uncovered_spans(txt_start, txt_end, merged_intervals)
        uncovered_duration_s = sum(
            self._duration_seconds(start, end) or 0.0
            for start, end in uncovered_spans
        )
        coverage_ratio = (
            covered_duration_s / txt_duration_s * 100.0
            if txt_duration_s and txt_duration_s > 0 and covered_duration_s is not None
            else None
        )
        uncovered_start, uncovered_end = uncovered_spans[0] if uncovered_spans else (None, None)
        valid_duration_records = [
            record
            for record in records
            if record.match_status == STATUS_MATCHED
            and record.duration_status == DURATION_STATUS_VALID
            and not record.duration_warning
        ]
        distribution_accepted_pwm_count = sum(
            self._record_has_distribution_accepted_pwm(record, distribution_allowed_pwm_match_statuses)
            for record in valid_duration_records
        )
        containing_pwm_count = self._count_pwm_status(valid_duration_records, PWM_STATUS_MATCHED_CONTAINING)
        nearest_pwm_count = self._count_pwm_status(valid_duration_records, PWM_STATUS_MATCHED_NEAREST)
        latest_before_pwm_count = self._count_pwm_status(valid_duration_records, PWM_STATUS_MATCHED_LATEST_BEFORE)
        carry_forward_pwm_count = self._count_pwm_status(valid_duration_records, PWM_STATUS_MATCHED_CARRY_FORWARD)
        without_pwm_count = sum(record.pwm_percent is None for record in valid_duration_records)
        exclusions = distribution_result.exclusion_counts if distribution_result is not None else {}
        excluded_due_to_pwm_reliability = exclusions.get("missing_pwm", 0) + exclusions.get("unreliable_pwm", 0)
        notes = self._build_coverage_notes(coverage_ratio, len(uncovered_spans), excluded_due_to_pwm_reliability)
        return [
            {
                "TXT Source File": normalized_paths["txt_file"].name,
                "TXT Start Time": format_log_timestamp(txt_start),
                "TXT End Time": format_log_timestamp(txt_end),
                "Control Log Folder": str(normalized_paths["log_folder"]),
                "Control Log File Count": len(folder_result.files),
                "Control Log Earliest Time": format_log_timestamp(control_start),
                "Control Log Latest Time": format_log_timestamp(control_end),
                "Merged Control Log Interval Count": len(merged_intervals),
                "Covered Duration (s)": round(covered_duration_s, 3) if covered_duration_s is not None else None,
                "Uncovered Duration (s)": round(uncovered_duration_s, 3),
                "Coverage Gap Count": len(uncovered_spans),
                "TXT Duration (s)": round(txt_duration_s, 3) if txt_duration_s is not None else None,
                "Coverage Ratio (%)": round(coverage_ratio, 3) if coverage_ratio is not None else None,
                "Representative Uncovered TXT Start Time": format_log_timestamp(uncovered_start),
                "Representative Uncovered TXT End Time": format_log_timestamp(uncovered_end),
                "Rows With Distribution-Accepted PWM": distribution_accepted_pwm_count,
                "Rows With Containing-File PWM": containing_pwm_count,
                "Rows With Nearest-File PWM": nearest_pwm_count,
                "Rows With Latest-Before PWM": latest_before_pwm_count,
                "Rows With Carry-Forward PWM": carry_forward_pwm_count,
                "Rows Without PWM": without_pwm_count,
                "Rows Excluded From Distribution Due To PWM Reliability": excluded_due_to_pwm_reliability,
                "Notes": notes,
            }
        ]

    def _record_has_distribution_accepted_pwm(
        self,
        record: ActivityRecord,
        allowed_pwm_match_statuses: set[str],
    ) -> bool:
        """Return whether a valid activity row has PWM acceptable for distribution grouping."""

        if record.pwm_percent is None or record.pwm_conflict:
            return False
        return record.pwm_match_status in allowed_pwm_match_statuses

    def _count_pwm_status(self, records: list[ActivityRecord], status: str) -> int:
        """Count valid activity records with a specific PWM match status."""

        return sum(record.pwm_match_status == status for record in records)

    def _duration_seconds(self, start, end) -> float | None:
        """Return positive duration in seconds for optional datetimes."""

        if start is None or end is None:
            return None
        return max((end - start).total_seconds(), 0.0)

    def _merge_time_intervals(self, intervals: list[tuple[object, object]]) -> list[tuple[object, object]]:
        """Merge overlapping control-log intervals without filling real gaps."""

        sorted_intervals = sorted(intervals, key=lambda item: (item[0], item[1]))
        merged: list[tuple[object, object]] = []
        for start, end in sorted_intervals:
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
                continue
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        return merged

    def _covered_seconds(self, txt_start, txt_end, intervals: list[tuple[object, object]]) -> float | None:
        """Return total TXT duration covered by the union of control-log intervals."""

        if txt_start is None or txt_end is None:
            return None
        covered = 0.0
        for start, end in intervals:
            overlap_start = max(txt_start, start)
            overlap_end = min(txt_end, end)
            covered += max((overlap_end - overlap_start).total_seconds(), 0.0)
        return covered

    def _uncovered_spans(self, txt_start, txt_end, intervals: list[tuple[object, object]]) -> list[tuple[object, object]]:
        """Return uncovered TXT intervals after subtracting merged control-log intervals."""

        if txt_start is None or txt_end is None:
            return []
        spans: list[tuple[object, object]] = []
        cursor = txt_start
        for start, end in intervals:
            if end <= txt_start or start >= txt_end:
                continue
            clipped_start = max(start, txt_start)
            clipped_end = min(end, txt_end)
            if clipped_start > cursor:
                spans.append((cursor, clipped_start))
            if clipped_end > cursor:
                cursor = clipped_end
        if cursor < txt_end:
            spans.append((cursor, txt_end))
        return spans

    def _build_coverage_notes(
        self,
        coverage_ratio: float | None,
        coverage_gap_count: int,
        excluded_due_to_pwm_reliability: int,
    ) -> str:
        """Build a concise coverage warning for workbook readers."""

        notes: list[str] = []
        if coverage_ratio is None:
            notes.append("Coverage ratio could not be computed.")
        elif coverage_ratio < 80.0:
            notes.append(
                "Control log coverage appears incomplete. Many TXT activities may be excluded from PWM-based distribution analysis."
            )
        if coverage_gap_count:
            notes.append(f"{coverage_gap_count} uncovered TXT interval(s) remain after merging control-log intervals.")
        if excluded_due_to_pwm_reliability:
            notes.append(
                f"{excluded_due_to_pwm_reliability} valid duration row(s) were excluded from distribution due to PWM reliability."
            )
        return " | ".join(notes)

    def _coverage_warning_from_rows(self, rows: list[dict[str, object]]) -> str:
        """Return the coverage notes string for workbook metadata."""

        if not rows:
            return ""
        return str(rows[0].get("Notes") or "")

    def _build_run_result(
        self,
        output_path: Path,
        records: list[ActivityRecord],
        diagnostics: list[DiagnosticEvent],
        txt_encoding: str,
        txt_axis_event_count: int,
        boundary_event_count: int,
        log_file_count: int,
        pwm_profile_count: int,
        distribution_enabled: bool = False,
        distribution_result: DistributionAnalysisResult | None = None,
    ) -> AnalysisRunResult:
        """Summarize the finished run for CLI output."""

        self._logger.info("Building run summary")
        distribution_exclusions = distribution_result.exclusion_counts if distribution_result is not None else {}
        return AnalysisRunResult(
            output_path=output_path,
            txt_axis_event_count=txt_axis_event_count,
            boundary_event_count=boundary_event_count,
            log_file_count=log_file_count,
            pwm_profile_count=pwm_profile_count,
            detail_count=len(records),
            matched_count=sum(record.match_status == STATUS_MATCHED and not record.duration_warning for record in records),
            unmatched_start_count=sum(record.match_status == STATUS_UNMATCHED_START for record in records),
            unmatched_end_count=sum(record.match_status == STATUS_UNMATCHED_END for record in records),
            closed_by_boundary_count=sum(record.match_status == STATUS_CLOSED_BY_BOUNDARY for record in records),
            closed_by_new_start_count=sum(record.match_status == STATUS_CLOSED_BY_NEW_START for record in records),
            initialization_failed_count=sum(record.match_status == STATUS_INITIALIZATION_FAILED for record in records),
            diagnostic_count=len(diagnostics),
            parse_warning_count=sum(record.match_status == STATUS_PARSE_WARNING for record in records),
            duration_warning_count=sum(
                record.duration_warning or record.match_status == STATUS_DURATION_TOO_LONG_CANDIDATE
                for record in records
            ),
            pwm_warning_count=sum(record.pwm_warning for record in records),
            txt_encoding=txt_encoding,
            distribution_enabled=distribution_enabled,
            distribution_group_count=len(distribution_result.stats) if distribution_result is not None else 0,
            distribution_raw_row_count=len(distribution_result.input_rows) if distribution_result is not None else 0,
            distribution_chart_count=sum(
                bool(item.chart_file) for item in distribution_result.stats
            )
            if distribution_result is not None
            else 0,
            distribution_output_dir=distribution_result.chart_output_dir if distribution_result is not None else None,
            distribution_excluded_missing_pwm_count=distribution_exclusions.get("missing_pwm", 0),
            distribution_excluded_missing_distance_count=distribution_exclusions.get("missing_movement_distance", 0),
            distribution_excluded_missing_true_distance_count=distribution_exclusions.get(
                "missing_true_movement_distance",
                0,
            ),
            distribution_excluded_unreliable_pwm_count=distribution_exclusions.get("unreliable_pwm", 0),
        )
