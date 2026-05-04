"""Workbook table generation for detail rows, summaries, and PWM-source tracing."""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd

from .config import (
    AXIS_SUMMARY_COLUMNS,
    DETAIL_COLUMNS,
    DIAGNOSTIC_COLUMNS,
    DIAGNOSTIC_SUMMARY_COLUMNS,
    DISTRIBUTION_CHART_METADATA_COLUMNS,
    DISTRIBUTION_ELIGIBILITY_SUMMARY_COLUMNS,
    DISTRIBUTION_EXCLUSION_SUMMARY_COLUMNS,
    DISTRIBUTION_RAW_DATA_COLUMNS,
    DISTRIBUTION_SUMMARY_COLUMNS,
    DURATION_STATUS_VALID,
    EVENT_SUMMARY_COLUMNS,
    HARDWARE_MOTION_SEGMENT_COLUMNS,
    LOG_COVERAGE_GAPS_COLUMNS,
    LOG_COVERAGE_SUMMARY_COLUMNS,
    PWM_SOURCE_COLUMNS,
    STATUS_CLOSED_BY_BOUNDARY,
    STATUS_CLOSED_BY_NEW_START,
    STATUS_DIAGNOSTIC,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_PARSE_WARNING,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
)
from .distribution import (
    DistributionAnalysisResult,
    DistributionExclusion,
    DistributionInputRow,
    DistributionStats,
    format_movement_distance_group_value,
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
        distribution_result: DistributionAnalysisResult | None = None,
        log_coverage_summary: list[dict[str, object]] | None = None,
        log_coverage_gaps: list[dict[str, object]] | None = None,
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
        hardware_motion_segments_frame = pd.DataFrame(
            self._build_hardware_motion_segment_rows(log_file_results),
            columns=HARDWARE_MOTION_SEGMENT_COLUMNS,
        )
        diagnostics_frame = pd.DataFrame(
            self._build_diagnostic_rows(diagnostics),
            columns=DIAGNOSTIC_COLUMNS,
        )
        diagnostics_summary_frame = pd.DataFrame(
            self._build_diagnostic_summary_rows(diagnostics),
            columns=DIAGNOSTIC_SUMMARY_COLUMNS,
        )
        distribution_summary_frame = None
        distribution_raw_data_frame = None
        distribution_chart_metadata_frame = None
        distribution_eligibility_summary_frame = None
        distribution_exclusion_summary_frame = None
        if distribution_result is not None:
            distribution_summary_frame = pd.DataFrame(
                self._build_distribution_summary_rows(distribution_result.stats),
                columns=DISTRIBUTION_SUMMARY_COLUMNS,
            )
            distribution_raw_data_frame = pd.DataFrame(
                self._build_distribution_raw_rows(distribution_result.input_rows),
                columns=DISTRIBUTION_RAW_DATA_COLUMNS,
            )
            distribution_chart_metadata_frame = pd.DataFrame(
                self._build_distribution_chart_metadata_rows(distribution_result.stats),
                columns=DISTRIBUTION_CHART_METADATA_COLUMNS,
            )
            distribution_eligibility_summary_frame = pd.DataFrame(
                self._build_distribution_exclusion_rows(distribution_result.eligibility_exclusions),
                columns=DISTRIBUTION_ELIGIBILITY_SUMMARY_COLUMNS,
            )
            distribution_exclusion_summary_frame = pd.DataFrame(
                self._build_distribution_exclusion_rows(distribution_result.exclusions),
                columns=DISTRIBUTION_EXCLUSION_SUMMARY_COLUMNS,
            )
        log_coverage_summary_frame = pd.DataFrame(
            log_coverage_summary or [],
            columns=LOG_COVERAGE_SUMMARY_COLUMNS,
        )
        log_coverage_gaps_frame = pd.DataFrame(
            log_coverage_gaps or [],
            columns=LOG_COVERAGE_GAPS_COLUMNS,
        )
        return ReportFrames(
            details=details_frame,
            event_summary=event_summary_frame,
            axis_summary=axis_summary_frame,
            pwm_sources=pwm_source_frame,
            hardware_motion_segments=hardware_motion_segments_frame,
            diagnostics=diagnostics_frame,
            diagnostics_summary=diagnostics_summary_frame,
            distribution_summary=distribution_summary_frame,
            distribution_raw_data=distribution_raw_data_frame,
            distribution_chart_metadata=distribution_chart_metadata_frame,
            distribution_eligibility_summary=distribution_eligibility_summary_frame,
            distribution_exclusion_summary=distribution_exclusion_summary_frame,
            log_coverage_summary=log_coverage_summary_frame,
            log_coverage_gaps=log_coverage_gaps_frame,
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
            "Hardware Motion Match Status": record.hardware_motion_match_status,
            "Hardware Motion Source File": record.hardware_motion_source_file,
            "Hardware Motion Time Delta (ms)": record.hardware_motion_time_delta_ms,
            "Hardware Raw Start Position": record.hardware_raw_start_position,
            "Hardware Raw End Position": record.hardware_raw_end_position,
            "Hardware Raw Target Position": record.hardware_raw_target_position,
            "Hardware Start Position": record.hardware_start_position,
            "Hardware End Position": record.hardware_end_position,
            "Hardware Target Position": record.hardware_target_position,
            "Hardware Actual Distance": record.hardware_actual_distance,
            "Candidate Hardware Actual Distance": record.hardware_actual_distance,
            "Hardware Commanded Distance": record.hardware_commanded_distance,
            "Hardware Distance Consistency Status": record.hardware_distance_consistency_status,
            "Hardware Distance Consistency Delta": record.hardware_distance_consistency_delta,
            "Hardware Start Line Number": record.hardware_start_line_number,
            "Hardware Start Line Text": record.hardware_start_line_text,
            "Hardware End Line Number": record.hardware_end_line_number,
            "Hardware End Line Text": record.hardware_end_line_text,
            "Hardware Target Line Number": record.hardware_target_line_number,
            "Hardware Target Line Text": record.hardware_target_line_text,
            "Selected Hardware Actual Distance": record.movement_distance,
            "Selected Movement Distance": record.movement_distance,
            "Selected Movement Distance Source": record.movement_distance_source,
            "Selected Movement Distance Method": record.movement_distance_method,
            "Selected Movement Distance Notes": record.movement_distance_notes,
            "Software TXT Start Position": record.movement_start_position,
            "Software TXT Target Position": record.movement_target_position,
            "Software TXT Reported End Position": record.movement_end_position,
            "Software TXT Commanded Distance": record.movement_commanded_distance,
            "Software TXT Reported Distance": record.movement_actual_distance,
            "Hardware Warning": record.hardware_warning,
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
            "PWM Missing Reason": record.pwm_missing_reason,
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
            "Closed By New Start Count": sum(record.match_status == STATUS_CLOSED_BY_NEW_START for record in group_records),
            "Initialization Failed Count": sum(record.match_status == STATUS_INITIALIZATION_FAILED for record in group_records),
            "Parse Warning Count": sum(record.match_status == STATUS_PARSE_WARNING for record in group_records),
            "Duration Warning Count": sum(record.duration_warning for record in group_records),
            "Hardware Warning Count": sum(record.hardware_warning for record in group_records),
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

    def _build_hardware_motion_segment_rows(
        self,
        log_file_results: list[DutyCycleLogFileResult],
    ) -> list[dict[str, object]]:
        """Convert parsed hardware TPOS Start/End segments into an audit worksheet."""

        self._logger.debug("Building hardware motion segment rows")
        rows: list[dict[str, object]] = []
        for file_result in sorted(log_file_results, key=lambda item: item.source_path.name):
            for segment in sorted(
                file_result.hardware_motion_segments,
                key=lambda item: (
                    item.start_time is None,
                    item.start_time or item.end_time or datetime.max,
                    item.axis,
                    item.start_line_number or item.end_line_number or 0,
                ),
            ):
                rows.append(
                    {
                        "Source Log File": segment.source_path.name,
                        "Axis": segment.axis,
                        "Match Status": segment.match_status,
                        "Start Time": format_log_timestamp(segment.start_time),
                        "End Time": format_log_timestamp(segment.end_time),
                        "Target Time": format_log_timestamp(segment.target_time),
                        "Raw Start Position": segment.raw_start_position,
                        "Raw End Position": segment.raw_end_position,
                        "Raw Target Position": segment.raw_target_position,
                        "Hardware Start Position": segment.hardware_start_position,
                        "Hardware End Position": segment.hardware_end_position,
                        "Hardware Target Position": segment.hardware_target_position,
                        "Hardware Actual Distance": segment.hardware_actual_distance,
                        "Hardware Commanded Distance": segment.hardware_commanded_distance,
                        "Start Line Number": segment.start_line_number,
                        "Start Line Text": segment.start_line_text,
                        "End Line Number": segment.end_line_number,
                        "End Line Text": segment.end_line_text,
                        "Target Line Number": segment.target_line_number,
                        "Target Line Text": segment.target_line_text,
                        "Duplicate Segment Key": segment.duplicate_segment_key,
                        "Duplicate Segment Count": segment.duplicate_segment_count,
                        "Possible Duplicate Source Files": segment.possible_duplicate_source_files,
                        "Notes": segment.notes,
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

    def _build_diagnostic_summary_rows(self, diagnostics: list[DiagnosticEvent]) -> list[dict[str, object]]:
        """Aggregate structured diagnostics by type, severity, axis, and node."""

        self._logger.debug("Building diagnostic summary rows")
        grouped: dict[tuple[str, str, str, int | None], list[DiagnosticEvent]] = defaultdict(list)
        for event in diagnostics:
            grouped[
                (
                    event.diagnostic_type,
                    event.severity,
                    event.axis or "",
                    event.node_id,
                )
            ].append(event)
        rows = []
        for (diagnostic_type, severity, axis, node_id), group_events in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], item[0][1], item[0][2], -1 if item[0][3] is None else item[0][3]),
        ):
            timestamps = [event.timestamp for event in group_events]
            rows.append(
                {
                    "Diagnostic Type": diagnostic_type,
                    "Severity": severity,
                    "Axis": axis,
                    "Node ID": node_id,
                    "Count": len(group_events),
                    "First Time": format_log_timestamp(min(timestamps)),
                    "Last Time": format_log_timestamp(max(timestamps)),
                }
            )
        return rows

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

    def _build_distribution_summary_rows(self, stats: list[DistributionStats]) -> list[dict[str, object]]:
        """Convert distribution group statistics into the workbook summary schema."""

        self._logger.debug("Building distribution summary rows")
        return [
            {
                "Group ID": item.group_id,
                "TXT Source File": item.txt_source_file,
                "PWM (%)": item.pwm_percent,
                "Axis": item.axis,
                "Example Hardware Start Position": item.example_movement_start_position,
                "Example Hardware Target Position": item.example_movement_target_position,
                "Example Hardware End Position": item.example_movement_end_position,
                "Example Hardware Commanded Distance": item.example_movement_commanded_distance,
                "Example Hardware Actual Distance": item.example_movement_actual_distance,
                "Example Selected Hardware Actual Distance": item.example_movement_distance,
                "Hardware Start Position Min": item.movement_start_position_min,
                "Hardware Start Position Max": item.movement_start_position_max,
                "Hardware Target Position Min": item.movement_target_position_min,
                "Hardware Target Position Max": item.movement_target_position_max,
                "Hardware End Position Min": item.movement_end_position_min,
                "Hardware End Position Max": item.movement_end_position_max,
                "Hardware Actual Distance Min": item.movement_distance_min,
                "Hardware Actual Distance Max": item.movement_distance_max,
                "Unique Position Combination Count": item.unique_position_combination_count,
                "Hardware Actual Distance Raw Example": item.movement_distance_raw_example,
                "Hardware Actual Distance Group Value": item.movement_distance_group_value,
                "Hardware Actual Distance Group Display": self._distance_display(item),
                "Movement Distance Grouping Mode": item.movement_distance_grouping_mode,
                "Movement Distance Bin Size": item.movement_distance_bin_size,
                "Selected Group Distance": item.movement_distance,
                "Hardware Actual Distance Rounded": item.movement_distance_rounded,
                "Hardware Distance Method": item.movement_distance_method,
                "Hardware Distance Source": item.movement_distance_source,
                "Hardware Distance Notes": item.movement_distance_notes,
                "Position Values Mixed": item.position_values_mixed,
                "Rule ID": item.rule_id,
                "Action Label": item.action_label,
                "Sample Count": item.sample_count,
                "Mean Duration (ms)": item.mean_ms,
                "Mean Duration (s)": item.mean_s,
                "Median Duration (ms)": item.median_ms,
                "Median Duration (s)": item.median_s,
                "Min Duration (ms)": item.min_ms,
                "Max Duration (ms)": item.max_ms,
                "Range Duration (ms)": item.range_ms,
                "Sample Std Dev Duration (ms)": item.sample_std_ms,
                "Sample Std Dev Duration (s)": item.sample_std_s,
                "Sample Variance Duration (ms^2)": item.sample_var_ms2,
                "Sample Variance Duration (s^2)": item.sample_var_s2,
                "Population Std Dev Duration (ms)": item.population_std_ms,
                "Population Variance Duration (ms^2)": item.population_var_ms2,
                "Coefficient of Variation (%)": item.cv_percent,
                "P05 Duration (ms)": item.p05_ms,
                "P25 Duration (ms)": item.p25_ms,
                "P75 Duration (ms)": item.p75_ms,
                "P95 Duration (ms)": item.p95_ms,
                "Normal Fit Mean (s)": item.normal_fit_mean_s,
                "Normal Fit Std Dev (s)": item.normal_fit_std_s,
                "Normal Fit Variance (s^2)": item.normal_fit_variance_s2,
                "Distribution Status": item.distribution_status,
                "Chart Status": item.chart_status,
                "Chart File": item.chart_file,
                "Chart Sheet Anchor / Image ID": item.chart_sheet_anchor,
                "Notes": item.notes,
            }
            for item in stats
        ]

    def _build_distribution_raw_rows(self, rows: list[DistributionInputRow]) -> list[dict[str, object]]:
        """Convert distribution input rows into the raw-data worksheet schema."""

        self._logger.debug("Building distribution raw-data rows")
        return [
            {
                "Group ID": row.group_id,
                "TXT Source File": row.txt_source_file,
                "Axis": row.axis,
                "PWM (%)": row.pwm_percent,
                "Selected Hardware Start Position": row.movement_start_position,
                "Selected Hardware Target Position": row.movement_target_position,
                "Selected Hardware End Position": row.movement_end_position,
                "Selected Hardware Commanded Distance": row.movement_commanded_distance,
                "Selected Hardware Actual Distance": row.movement_distance,
                "Hardware Motion Match Status": row.hardware_motion_match_status,
                "Hardware Motion Source File": row.hardware_motion_source_file,
                "Hardware Raw Start Position": row.hardware_raw_start_position,
                "Hardware Raw End Position": row.hardware_raw_end_position,
                "Hardware Raw Target Position": row.hardware_raw_target_position,
                "Hardware Start Position": row.hardware_start_position,
                "Hardware End Position": row.hardware_end_position,
                "Hardware Target Position": row.hardware_target_position,
                "Hardware Actual Distance": row.hardware_actual_distance,
                "Hardware Commanded Distance": row.hardware_commanded_distance,
                "Hardware Start Line Number": row.hardware_start_line_number,
                "Hardware Start Line Text": row.hardware_start_line_text,
                "Hardware End Line Number": row.hardware_end_line_number,
                "Hardware End Line Text": row.hardware_end_line_text,
                "Hardware Target Line Number": row.hardware_target_line_number,
                "Hardware Target Line Text": row.hardware_target_line_text,
                "Selected Movement Distance": row.movement_distance,
                "Selected Movement Distance Source": row.movement_distance_source,
                "Hardware Actual Distance Group Value": row.movement_distance_group_value,
                "Hardware Actual Distance Group Display": self._input_distance_display(row),
                "Movement Distance Grouping Mode": row.movement_distance_grouping_mode,
                "Movement Distance Bin Size": row.movement_distance_bin_size,
                "Hardware Actual Distance Rounded": row.movement_distance_rounded,
                "Selected Movement Distance Method": row.movement_distance_method,
                "Selected Movement Distance Notes": row.movement_distance_notes,
                "Rule ID": row.rule_id,
                "Action Label": row.action_label,
                "Start Time": format_log_timestamp(row.start_time),
                "End Time": format_log_timestamp(row.end_time),
                "Duration (ms)": row.duration_ms,
                "Duration (s)": row.duration_s,
                "Source TXT Start Line Number": row.source_txt_start_line_number,
                "Source TXT Start Line Text": row.source_txt_start_line_text,
                "Source TXT End Line Number": row.source_txt_end_line_number,
                "Source TXT End Line Text": row.source_txt_end_line_text,
                "PWM Source File": row.pwm_source_file,
                "PWM Raw Value": row.pwm_raw_value,
                "PWM Direction": row.pwm_direction,
                "PWM Direction Changed": row.pwm_direction_changed,
                "PWM Conflict": row.pwm_conflict,
                "PWM Conflict Reason": row.pwm_conflict_reason,
                "PWM Source Line Number": row.pwm_source_line_number,
                "PWM Source Line Text": row.pwm_source_line_text,
                "PWM Source Time": format_log_timestamp(row.pwm_source_time),
                "PWM Match Method": row.pwm_match_method,
                "PWM Match Status": row.pwm_match_status,
                "PWM Time Delta (ms)": row.pwm_time_delta_ms,
                "PWM Missing Reason": row.pwm_missing_reason,
                "Overall Status": row.overall_status,
                "Match Status": row.match_status,
                "Duration Status": row.duration_status,
                "Source Record ID": row.source_record_id,
            }
            for row in rows
        ]

    def _build_distribution_chart_metadata_rows(self, stats: list[DistributionStats]) -> list[dict[str, object]]:
        """Build metadata blocks for charts embedded in Excel."""

        self._logger.debug("Building distribution chart metadata rows")
        return [
            {
                "Group ID": item.group_id,
                "TXT Source File": item.txt_source_file,
                "PWM (%)": item.pwm_percent,
                "Axis": item.axis,
                "Hardware Actual Distance Group Value": item.movement_distance_group_value,
                "Hardware Actual Distance Display": self._distance_display(item),
                "Hardware Distance Source": item.movement_distance_source,
                "Hardware Distance Method": item.movement_distance_method,
                "Movement Distance Grouping Mode": item.movement_distance_grouping_mode,
                "Movement Distance Bin Size": item.movement_distance_bin_size,
                "Rule ID": item.rule_id,
                "Action Label": item.action_label,
                "Sample Count": item.sample_count,
                "Mean Duration (s)": item.mean_s,
                "Sample Std Dev Duration (s)": item.sample_std_s,
                "Variance": item.sample_var_s2,
                "Distribution Status": item.distribution_status,
                "Chart Status": item.chart_status,
                "Chart File": item.chart_file,
                "Notes": item.notes,
            }
            for item in stats
            if item.chart_file
        ]

    def _build_distribution_exclusion_rows(
        self,
        exclusions: list[DistributionExclusion],
    ) -> list[dict[str, object]]:
        """Aggregate excluded distribution rows by reason, rule, and axis."""

        self._logger.debug("Building distribution exclusion summary rows")
        grouped: dict[tuple[str, str, str, str, str, str], list[DistributionExclusion]] = defaultdict(list)
        for exclusion in exclusions:
            grouped[
                (
                    exclusion.reason,
                    exclusion.secondary_reasons,
                    exclusion.pwm_exclusion_reason,
                    exclusion.movement_distance_exclusion_reason,
                    exclusion.rule_id,
                    exclusion.axis,
                )
            ].append(exclusion)
        rows: list[dict[str, object]] = []
        for (reason, secondary, pwm_reason, movement_reason, rule_id, axis), group in sorted(grouped.items()):
            example = group[0]
            rows.append(
                {
                    "Exclusion Reason": reason,
                    "Secondary Exclusion Reasons": secondary,
                    "PWM Exclusion Reason": pwm_reason,
                    "Movement Distance Exclusion Reason": movement_reason,
                    "Rule ID": rule_id,
                    "Axis": axis,
                    "Count": len(group),
                    "PWM Match Status": example.pwm_match_status,
                    "PWM Missing Reason": example.pwm_missing_reason,
                    "PWM Time Delta (ms)": example.pwm_time_delta_ms,
                    "Example PWM Source File": example.example_pwm_source_file,
                    "Hardware Motion Match Status": example.hardware_motion_match_status,
                    "Example Start Line": example.start_line,
                    "Example Notes": example.notes,
                }
            )
        return rows

    def _distance_display(self, item: DistributionStats) -> str:
        """Return a text display for one grouped movement distance."""

        return format_movement_distance_group_value(
            item.movement_distance_group_value,
            item.movement_distance_grouping_mode,
            item.movement_distance_bin_size,
            item.movement_distance_round_digits,
        )

    def _input_distance_display(self, row: DistributionInputRow) -> str:
        """Return a text display for a raw row's grouped movement distance."""

        return format_movement_distance_group_value(
            row.movement_distance_group_value,
            row.movement_distance_grouping_mode,
            row.movement_distance_bin_size,
            row.movement_distance_round_digits,
        )
