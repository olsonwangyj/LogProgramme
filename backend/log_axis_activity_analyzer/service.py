"""End-to-end orchestration service for TXT parsing, PWM folder scanning, and workbook export."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import (
    DEFAULT_EVENT_RULES,
    STATUS_CLOSED_BY_BOUNDARY,
    STATUS_DURATION_TOO_LONG_CANDIDATE,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_PARSE_WARNING,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
)
from .duty_cycle_associator import DutyCycleAssociator
from .excel_exporter import ExcelExporter
from .file_loader import TextFileLoader
from .log_a_parser import MainLogParser
from .log_b_parser import DutyCycleLogParser
from .log_folder_scanner import LogFolderScanner
from .matcher import EventMatcher
from .models import ActivityRecord, AnalysisRunResult, DiagnosticEvent, DutyCycleFolderParseResult, ParseWarning
from .summary import SummaryGenerator
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
        enriched_records = self._associator.attach(activity_records, folder_result.files, association_strategy)
        all_records = self._append_parse_warnings(enriched_records, main_result.warnings, folder_result)
        validated_records = self._validator.validate(all_records)
        report_frames = self._summary_generator.build_report_frames(
            validated_records,
            folder_result.files,
            diagnostics=main_result.diagnostics,
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
                "initialization_failed_count": run_result.initialization_failed_count,
                "diagnostic_count": run_result.diagnostic_count,
                "duration_warning_count": run_result.duration_warning_count,
                "pwm_warning_count": run_result.pwm_warning_count,
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
    ) -> AnalysisRunResult:
        """Summarize the finished run for CLI output."""

        self._logger.info("Building run summary")
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
            initialization_failed_count=sum(record.match_status == STATUS_INITIALIZATION_FAILED for record in records),
            diagnostic_count=len(diagnostics),
            parse_warning_count=sum(record.match_status == STATUS_PARSE_WARNING for record in records),
            duration_warning_count=sum(
                record.duration_warning or record.match_status == STATUS_DURATION_TOO_LONG_CANDIDATE
                for record in records
            ),
            pwm_warning_count=sum(record.pwm_warning for record in records),
            txt_encoding=txt_encoding,
        )
