"""Workbook table generation for detail rows, summaries, and PWM-source tracing."""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict

import pandas as pd

from .config import (
    AXIS_SUMMARY_COLUMNS,
    DETAIL_COLUMNS,
    DIAGNOSTIC_COLUMNS,
    DURATION_STATUS_VALID,
    EVENT_SUMMARY_COLUMNS,
    PWM_SOURCE_COLUMNS,
    STATUS_CLOSED_BY_BOUNDARY,
    STATUS_DIAGNOSTIC,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_PARSE_WARNING,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
)
from .models import ActivityRecord, DiagnosticEvent, DutyCycleLogFileResult, ReportFrames
from .time_utils import format_log_timestamp


class SummaryGenerator:
    """Builds detail and summary data frames from activity and PWM records."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the summary generator with an optional logger."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def build_report_frames(
        self,
        records: list[ActivityRecord],
        log_file_results: list[DutyCycleLogFileResult],
        diagnostics: list[DiagnosticEvent] | None = None,
    ) -> ReportFrames:
        """Convert activity records into workbook-ready data frames."""

        self._logger.info("Generating report frames from %s detail records", len(records))
        diagnostics = diagnostics or []
        sorted_records = sorted(records, key=lambda item: item.sort_key())
        details_frame = pd.DataFrame(
            [self._build_detail_row(record) for record in sorted_records],
            columns=DETAIL_COLUMNS,
        )
        event_summary_frame = pd.DataFrame(
            self._build_event_summary_rows(sorted_records),
            columns=EVENT_SUMMARY_COLUMNS,
        )
        axis_summary_frame = pd.DataFrame(
            self._build_axis_summary_rows(sorted_records),
            columns=AXIS_SUMMARY_COLUMNS,
        )
        pwm_source_frame = pd.DataFrame(
            self._build_pwm_source_rows(log_file_results),
            columns=PWM_SOURCE_COLUMNS,
        )
        diagnostics_frame = pd.DataFrame(
            self._build_diagnostic_rows(diagnostics),
            columns=DIAGNOSTIC_COLUMNS,
        )
        return ReportFrames(
            details=details_frame,
            event_summary=event_summary_frame,
            axis_summary=axis_summary_frame,
            pwm_sources=pwm_source_frame,
            diagnostics=diagnostics_frame,
        )

    def _build_detail_row(self, record: ActivityRecord) -> dict[str, object]:
        """Convert one activity record into the Details sheet schema."""

        self._logger.debug("Shaping detail row for axis %s status %s", record.axis, record.status)
        return {
            "Axis": record.axis,
            "Rule ID": record.rule_id,
            "Start Event": record.start_event,
            "End Event": record.end_event,
            "Start Time": format_log_timestamp(record.start_time),
            "End Time": format_log_timestamp(record.end_time),
            "Duration (ms)": record.duration_ms,
            "Duration (s)": record.duration_s,
            "Start Value": record.start_value,
            "End Value": record.end_value,
            "PWM (%)": record.pwm_percent,
            "PWM Raw Value": record.pwm_raw_value,
            "PWM Direction": record.pwm_direction,
            "PWM Direction Changed": record.pwm_direction_changed,
            "PWM Conflict": record.pwm_conflict,
            "PWM Conflict Reason": record.pwm_conflict_reason,
            "PWM Source File": record.pwm_source_file,
            "PWM Source Line Number": record.pwm_line_number or None,
            "PWM Source Line Text": record.pwm_source_line,
            "PWM Source Time": format_log_timestamp(record.pwm_source_time),
            "PWM Match Method": record.pwm_match_method,
            "PWM Time Delta (ms)": record.pwm_time_delta_ms,
            "PWM Match Status": record.pwm_match_status,
            "Source TXT Start Line Number": record.start_line_number or None,
            "Source TXT Start Line Text": record.source_txt_start_line,
            "Source TXT End Line Number": record.end_line_number or None,
            "Source TXT End Line Text": record.source_txt_end_line,
            "Match Status": record.match_status,
            "Duration Status": record.duration_status,
            "Boundary Close Reason": record.boundary_close_reason,
            "Closed By Boundary Type": record.closed_by_boundary_type,
            "Closed By Boundary Time": format_log_timestamp(record.closed_by_boundary_time),
            "Boundary Line Number": record.closed_by_boundary_line or None,
            "Boundary Line Text": record.closed_by_boundary_line_text,
            "Candidate Duration (ms)": record.candidate_duration_ms,
            "Candidate Duration (s)": record.candidate_duration_s,
            "Max Duration (ms)": record.max_duration_ms,
            "Exceeded Max Duration": record.exceeded_max_duration,
            "Notes": record.notes,
            "Overall Status": record.status,
        }

    def _build_event_summary_rows(self, records: list[ActivityRecord]) -> list[dict[str, object]]:
        """Aggregate records by axis and normalized event type."""

        self._logger.debug("Building event summary rows")
        grouped: dict[tuple[str, str], list[ActivityRecord]] = defaultdict(list)
        for record in records:
            if record.match_status in {STATUS_PARSE_WARNING, STATUS_DIAGNOSTIC} or not record.axis:
                continue
            grouped[(record.axis, record.event_type or record.start_event)].append(record)
        rows = []
        for (axis, event_type), group_records in sorted(grouped.items()):
            row = self._build_summary_metrics(group_records)
            row["Axis"] = axis
            row["Event Type / Start Event"] = event_type
            rows.append(row)
        return rows

    def _build_axis_summary_rows(self, records: list[ActivityRecord]) -> list[dict[str, object]]:
        """Aggregate records by axis only."""

        self._logger.debug("Building axis summary rows")
        grouped: dict[str, list[ActivityRecord]] = defaultdict(list)
        for record in records:
            if record.match_status in {STATUS_PARSE_WARNING, STATUS_DIAGNOSTIC} or not record.axis:
                continue
            grouped[record.axis].append(record)
        rows = []
        for axis, group_records in sorted(grouped.items()):
            row = self._build_summary_metrics(group_records)
            row["Axis"] = axis
            rows.append(row)
        return rows

    def _build_summary_metrics(self, group_records: list[ActivityRecord]) -> dict[str, object]:
        """Compute summary metrics for one group of activity records."""

        self._logger.debug("Computing summary metrics for %s records", len(group_records))
        durations = [
            record.duration_ms
            for record in group_records
            if record.match_status == STATUS_MATCHED
            and record.duration_status == DURATION_STATUS_VALID
            and record.duration_ms is not None
        ]
        pwm_values = [
            record.pwm_percent
            for record in group_records
            if record.match_status == STATUS_MATCHED
            and record.duration_status == DURATION_STATUS_VALID
            and record.pwm_percent is not None
        ]
        avg_ms = round(sum(durations) / len(durations), 3) if durations else None
        median_ms = round(statistics.median(durations), 3) if durations else None
        return {
            "Count": len(group_records),
            "Avg Duration (ms)": avg_ms,
            "Avg Duration (s)": round(avg_ms / 1000.0, 3) if avg_ms is not None else None,
            "Min Duration (ms)": min(durations) if durations else None,
            "Max Duration (ms)": max(durations) if durations else None,
            "Median Duration (ms)": median_ms,
            "Most Common PWM (%)": self._resolve_most_common_pwm(pwm_values),
            "Matched Count": sum(
                record.match_status == STATUS_MATCHED and record.duration_status == DURATION_STATUS_VALID
                for record in group_records
            ),
            "Unmatched Start Count": sum(record.match_status == STATUS_UNMATCHED_START for record in group_records),
            "Unmatched End Count": sum(record.match_status == STATUS_UNMATCHED_END for record in group_records),
            "Closed By Boundary Count": sum(record.match_status == STATUS_CLOSED_BY_BOUNDARY for record in group_records),
            "Initialization Failed Count": sum(record.match_status == STATUS_INITIALIZATION_FAILED for record in group_records),
            "Diagnostic Count": sum(record.match_status == STATUS_DIAGNOSTIC for record in group_records),
            "Parse Warning Count": sum(record.match_status == STATUS_PARSE_WARNING for record in group_records),
            "Duration Warning Count": sum(record.duration_warning for record in group_records),
            "PWM Warning Count": sum(record.pwm_warning for record in group_records),
        }

    def _build_pwm_source_rows(self, log_file_results: list[DutyCycleLogFileResult]) -> list[dict[str, object]]:
        """Convert parsed PWM events into rows for the optional PWM Sources sheet."""

        self._logger.debug("Building PWM source rows")
        rows = []
        for file_result in sorted(log_file_results, key=lambda item: item.source_path.name):
            for event in file_result.pwm_events:
                profile = file_result.axis_profiles.get(event.axis)
                rows.append(
                    {
                        "Log File": file_result.source_path.name,
                        "Log File Start Time": format_log_timestamp(file_result.file_start_time),
                        "Log File End Time": format_log_timestamp(file_result.file_end_time),
                        "Axis": event.axis,
                        "PWM (%)": event.pwm_percent,
                        "PWM Raw Value": event.pwm_raw_value,
                        "Direction": event.direction,
                        "Direction Changed": profile.direction_changed if profile is not None else False,
                        "Command Type": event.command_type,
                        "PWM Source Time": format_log_timestamp(event.timestamp),
                        "PWM Source Line Number": event.line_number,
                        "PWM Source Line Text": event.raw_line,
                        "Is Status Confirmation": event.is_status_confirmation,
                        "PWM Conflict": profile.conflict if profile is not None else False,
                        "PWM Conflict Reason": profile.conflict_reason if profile is not None else "",
                        "Notes": event.notes or (profile.notes if profile is not None else ""),
                    }
                )
        return rows

    def _build_diagnostic_rows(self, diagnostics: list[DiagnosticEvent]) -> list[dict[str, object]]:
        """Convert structured main-log diagnostics into a workbook table."""

        self._logger.debug("Building diagnostic rows")
        return [
            {
                "Time": format_log_timestamp(event.timestamp),
                "Severity": event.severity,
                "Diagnostic Type": event.diagnostic_type,
                "Axis": event.axis or "",
                "Node ID": event.node_id,
                "Source TXT Line Number": event.line_number,
                "Source TXT Line Text": event.raw_line,
                "Notes": self._diagnostic_note(event),
            }
            for event in sorted(diagnostics, key=lambda item: (item.timestamp, item.line_number))
        ]

    def _diagnostic_note(self, event: DiagnosticEvent) -> str:
        """Return a concise diagnostic note for the Diagnostics sheet."""

        if event.flush_pending:
            return f"Flushes pending activity records with scope {event.flush_scope}."
        return ""

    def _resolve_most_common_pwm(self, pwm_values: list[float]) -> float | None:
        """Return the most common PWM percent for one summary group."""

        self._logger.debug("Resolving PWM mode for %s values", len(pwm_values))
        if not pwm_values:
            return None
        return Counter(pwm_values).most_common(1)[0][0]
