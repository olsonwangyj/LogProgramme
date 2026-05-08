"""Workbook table generation for detail rows, summaries, and PWM-source tracing."""

from __future__ import annotations

import logging
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd

from .config import (
    AXIS_SUMMARY_COLUMNS,
    AXIS_ACTION_SUMMARY_COLUMNS,
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
    HARDWARE_REFERENCE_EVENT_COLUMNS,
    HARDWARE_STATUS_MATCHED_OVERLAP,
    HARDWARE_MOTION_SEGMENT_COLUMNS,
    LOG_COVERAGE_GAPS_COLUMNS,
    LOG_COVERAGE_SUMMARY_COLUMNS,
    PWM_SOURCE_COLUMNS,
    REFERENCE_EXCLUSION_SUMMARY_COLUMNS,
    REFERENCE_DURATION_CHART_METADATA_COLUMNS,
    REFERENCE_DURATION_RAW_DATA_COLUMNS,
    REFERENCE_DURATION_SUMMARY_COLUMNS,
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
    ReferenceDurationAnalysisResult,
    ReferenceDurationInputRow,
    ReferenceDurationStats,
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
        reference_duration_result: ReferenceDurationAnalysisResult | None = None,
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
        hardware_reference_events_frame = pd.DataFrame(
            self._build_hardware_reference_event_rows(log_file_results),
            columns=HARDWARE_REFERENCE_EVENT_COLUMNS,
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
        reference_duration_summary_frame = None
        reference_duration_raw_data_frame = None
        reference_exclusion_summary_frame = None
        reference_duration_chart_metadata_frame = None
        axis_action_summary_frame = None
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
        if reference_duration_result is not None:
            reference_duration_summary_frame = pd.DataFrame(
                self._build_reference_duration_summary_rows(reference_duration_result.stats),
                columns=REFERENCE_DURATION_SUMMARY_COLUMNS,
            )
            reference_duration_raw_data_frame = pd.DataFrame(
                self._build_reference_duration_raw_rows(reference_duration_result.input_rows),
                columns=REFERENCE_DURATION_RAW_DATA_COLUMNS,
            )
            reference_exclusion_summary_frame = pd.DataFrame(
                self._build_reference_exclusion_summary_rows(reference_duration_result.input_rows),
                columns=REFERENCE_EXCLUSION_SUMMARY_COLUMNS,
            )
            reference_duration_chart_metadata_frame = pd.DataFrame(
                self._build_reference_duration_chart_metadata_rows(reference_duration_result.stats),
                columns=REFERENCE_DURATION_CHART_METADATA_COLUMNS,
            )
        if distribution_result is not None or reference_duration_result is not None:
            axis_action_summary_frame = pd.DataFrame(
                self._build_axis_action_summary_rows(
                    distribution_result.input_rows if distribution_result is not None else [],
                    [
                        row
                        for row in reference_duration_result.input_rows
                        if row.included_in_reference_distribution
                    ]
                    if reference_duration_result is not None
                    else [],
                ),
                columns=AXIS_ACTION_SUMMARY_COLUMNS,
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
            hardware_reference_events=hardware_reference_events_frame,
            diagnostics=diagnostics_frame,
            diagnostics_summary=diagnostics_summary_frame,
            distribution_summary=distribution_summary_frame,
            distribution_raw_data=distribution_raw_data_frame,
            distribution_chart_metadata=distribution_chart_metadata_frame,
            reference_duration_summary=reference_duration_summary_frame,
            reference_duration_raw_data=reference_duration_raw_data_frame,
            reference_exclusion_summary=reference_exclusion_summary_frame,
            reference_duration_chart_metadata=reference_duration_chart_metadata_frame,
            axis_action_summary=axis_action_summary_frame,
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
            "Candidate Hardware Actual Distance": (
                None
                if record.hardware_motion_match_status == HARDWARE_STATUS_MATCHED_OVERLAP
                else record.hardware_actual_distance
            ),
            "Hardware Commanded Distance": record.hardware_commanded_distance,
            "Hardware Distance Consistency Status": record.hardware_distance_consistency_status,
            "Hardware Distance Consistency Delta": record.hardware_distance_consistency_delta,
            "Hardware Reference Match Status": record.hardware_reference_match_status,
            "Hardware Reference Source File": record.hardware_reference_source_file,
            "Hardware Reference Time Delta (ms)": record.hardware_reference_time_delta_ms,
            "Hardware Reference Zero Sensor Time": format_log_timestamp(record.hardware_reference_zero_sensor_time),
            "Hardware Reference Reset Time": format_log_timestamp(record.hardware_reference_reset_time),
            "Hardware Reference Zero Sensor Raw Value": record.hardware_reference_zero_sensor_raw_value,
            "Hardware Reference Line Number": record.hardware_reference_line_number,
            "Hardware Reference Line Text": record.hardware_reference_line_text,
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
                        "Duplicate Segment Count": (
                            segment.duplicate_segment_count
                            if segment.possible_duplicate_hardware_segment
                            else None
                        ),
                        "Possible Duplicate Hardware Segment": segment.possible_duplicate_hardware_segment,
                        "Possible Duplicate Source Files": segment.possible_duplicate_source_files,
                        "Effective Segment Used For Matching": segment.effective_segment_used_for_matching,
                        "Matched TXT Activity Count": segment.matched_txt_activity_count or None,
                        "Matched TXT Rule ID": segment.matched_txt_rule_id,
                        "Matched TXT Start Time": format_log_timestamp(segment.matched_txt_start_time),
                        "Notes": segment.notes,
                    }
                )
        return rows

    def _build_hardware_reference_event_rows(
        self,
        log_file_results: list[DutyCycleLogFileResult],
    ) -> list[dict[str, object]]:
        """Convert parsed TPOS Z/I reference evidence into an audit worksheet."""

        self._logger.debug("Building hardware reference event rows")
        rows: list[dict[str, object]] = []
        for file_result in sorted(log_file_results, key=lambda item: item.source_path.name):
            for event in sorted(
                file_result.hardware_reference_events,
                key=lambda item: (
                    item.timestamp is None,
                    item.timestamp or datetime.max,
                    item.axis,
                    item.line_number or 0,
                ),
            ):
                rows.append(
                    {
                        "Source Log File": event.source_path.name,
                        "Axis": event.axis,
                        "Evidence Type": event.evidence_type,
                        "Timestamp": format_log_timestamp(event.timestamp),
                        "Raw / Status Value": event.raw_value,
                        "Line Number": event.line_number,
                        "Line Text": event.line_text,
                        "Matched TXT Rule ID": event.matched_txt_rule_id,
                        "Matched TXT Start Time": format_log_timestamp(event.matched_txt_start_time),
                        "Matched TXT End Time": format_log_timestamp(event.matched_txt_end_time),
                        "Match Status": event.match_status,
                        "Notes": event.notes,
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
                "Outlier Count": item.outlier_count,
                "Outlier Values": item.outlier_values,
                "Chart Uses Outlier-Trimmed Axis": item.chart_uses_outlier_trimmed_axis,
                "Distribution Status": item.distribution_status,
                "Chart Status": item.chart_status,
                "Chart File": self._chart_file_display(item.chart_file),
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
                "Chart Type": "Motion Duration Distribution",
                "TXT Source File": item.txt_source_file,
                "PWM (%)": item.pwm_percent,
                "Axis": item.axis,
                "Action": self._human_action(item.rule_id, item.action_label),
                "Hardware Actual Distance Group Value": item.movement_distance_group_value,
                "Hardware Actual Distance Display": self._distance_display(item),
                "Distance": self._distance_display(item),
                "Reference Evidence Status": "",
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
                "Outlier Count": item.outlier_count,
                "Outlier Values": item.outlier_values,
                "Chart Uses Outlier-Trimmed Axis": item.chart_uses_outlier_trimmed_axis,
                "Distribution Status": item.distribution_status,
                "Chart Status": item.chart_status,
                "Chart File": self._chart_file_display(item.chart_file),
                "Notes": item.notes,
            }
            for item in stats
            if item.chart_file
        ]

    def _build_reference_duration_summary_rows(
        self,
        stats: list[ReferenceDurationStats],
    ) -> list[dict[str, object]]:
        """Convert reference-duration statistics into workbook rows."""

        return [
            {
                "Group ID": item.group_id,
                "TXT Source File": item.txt_source_file,
                "Axis": item.axis,
                "Action": self._human_action(item.rule_id, item.action_label),
                "Rule ID": item.rule_id,
                "Sample Count": item.sample_count,
                "Mean Duration (ms)": item.mean_ms,
                "Mean Duration (s)": item.mean_s,
                "Median Duration (s)": item.median_s,
                "Sample SD Duration (s)": item.sample_std_s,
                "Sample Variance Duration (s^2)": item.sample_var_s2,
                "Population SD Duration (s)": item.population_std_s,
                "Population Variance Duration (s^2)": item.population_var_s2,
                "Min Duration (s)": item.min_s,
                "Max Duration (s)": item.max_s,
                "Min-Max Display": self._min_max_display(item.min_s, item.max_s),
                "CV (%)": item.cv_percent,
                "Outlier Count": item.outlier_count,
                "Outlier Values": item.outlier_values,
                "Chart Uses Outlier-Trimmed Axis": item.chart_uses_outlier_trimmed_axis,
                "Hardware Reference Evidence Found Count": item.hardware_reference_evidence_found_count,
                "Hardware Reference Evidence Missing Count": item.hardware_reference_evidence_missing_count,
                "Distribution Status": item.distribution_status,
                "Chart Status": item.chart_status,
                "Chart File": self._chart_file_display(item.chart_file),
                "Chart Sheet Anchor / Image ID": item.chart_sheet_anchor,
                "Notes": item.notes,
            }
            for item in stats
        ]

    def _build_reference_duration_raw_rows(
        self,
        rows: list[ReferenceDurationInputRow],
    ) -> list[dict[str, object]]:
        """Convert reference-duration input rows into auditable raw-data rows."""

        return [
            {
                "Group ID": row.group_id,
                "TXT Source File": row.txt_source_file,
                "Axis": row.axis,
                "Action": self._human_action(row.rule_id, row.action_label),
                "Rule ID": row.rule_id,
                "Start Time": format_log_timestamp(row.start_time),
                "End Time": format_log_timestamp(row.end_time),
                "Duration (ms)": row.duration_ms,
                "Duration (s)": row.duration_s,
                "Hardware Reference Match Status": row.hardware_reference_match_status,
                "Hardware Reference Source File": row.hardware_reference_source_file,
                "Hardware Reference Zero Sensor Raw Value": row.hardware_reference_zero_sensor_raw_value,
                "Hardware Reference Line Text": row.hardware_reference_line_text,
                "Included In Reference Distribution": row.included_in_reference_distribution,
                "Reference Exclusion Reason": row.reference_exclusion_reason,
                "Hardware Motion Match Status": row.hardware_motion_match_status,
                "Selected Movement Distance Method": row.movement_distance_method,
                "Overall Status": row.overall_status,
                "Match Status": row.match_status,
                "Duration Status": row.duration_status,
                "Source TXT Start Line Number": row.source_txt_start_line_number,
                "Source TXT Start Line Text": row.source_txt_start_line_text,
                "Source TXT End Line Number": row.source_txt_end_line_number,
                "Source TXT End Line Text": row.source_txt_end_line_text,
                "Notes": row.notes,
            }
            for row in rows
        ]

    def _build_reference_duration_chart_metadata_rows(
        self,
        stats: list[ReferenceDurationStats],
    ) -> list[dict[str, object]]:
        """Build metadata blocks for reference charts embedded in Excel."""

        return [
            {
                "Group ID": item.group_id,
                "Chart Type": item.chart_type,
                "TXT Source File": item.txt_source_file,
                "Axis": item.axis,
                "Action": self._human_action(item.rule_id, item.action_label),
                "Rule ID": item.rule_id,
                "Distance": "Not Applicable",
                "Sample Count": item.sample_count,
                "Mean Duration (s)": item.mean_s,
                "Sample Std Dev Duration (s)": item.sample_std_s,
                "Variance": item.sample_var_s2,
                "Min-Max Display": self._min_max_display(item.min_s, item.max_s),
                "CV (%)": item.cv_percent,
                "Outlier Count": item.outlier_count,
                "Outlier Values": item.outlier_values,
                "Chart Uses Outlier-Trimmed Axis": item.chart_uses_outlier_trimmed_axis,
                "Reference Evidence Status": self._reference_evidence_status(item),
                "Hardware Reference Evidence Found Count": item.hardware_reference_evidence_found_count,
                "Hardware Reference Evidence Missing Count": item.hardware_reference_evidence_missing_count,
                "Distribution Status": item.distribution_status,
                "Chart Status": item.chart_status,
                "Chart File": self._chart_file_display(item.chart_file),
                "Notes": item.notes,
            }
            for item in stats
            if item.chart_file
        ]

    def _build_reference_exclusion_summary_rows(
        self,
        rows: list[ReferenceDurationInputRow],
    ) -> list[dict[str, object]]:
        """Aggregate reference-duration rows excluded from reference statistics."""

        grouped: dict[tuple[str, str, str], list[ReferenceDurationInputRow]] = defaultdict(list)
        for row in rows:
            if row.included_in_reference_distribution:
                continue
            reason = row.reference_exclusion_reason or "ReferenceDurationExcluded"
            action = self._human_action(row.rule_id, row.action_label)
            grouped[(reason, row.axis, action)].append(row)
        output_rows: list[dict[str, object]] = []
        for (reason, axis, action), group in sorted(grouped.items()):
            example = group[0]
            output_rows.append(
                {
                    "Reference Exclusion Reason": reason,
                    "Axis": axis,
                    "Action": action,
                    "Count": len(group),
                    "Example Duration (s)": example.duration_s,
                    "Example Start Time": format_log_timestamp(example.start_time),
                    "Example Notes": example.notes,
                }
            )
        return output_rows

    def _build_axis_action_summary_rows(
        self,
        motion_rows: list[DistributionInputRow],
        reference_rows: list[ReferenceDurationInputRow],
    ) -> list[dict[str, object]]:
        """Build the clean axis/action duration summary requested by users."""

        grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in motion_rows:
            grouped[(row.axis, self._human_action(row.rule_id, row.action_label))].append(row.duration_s)
        for row in reference_rows:
            grouped[(row.axis, self._human_action(row.rule_id, row.action_label))].append(row.duration_s)

        rows: list[dict[str, object]] = []
        for (axis, action), durations_s in sorted(grouped.items(), key=lambda item: self._axis_action_sort_key(item[0])):
            stats = self._duration_stats_seconds(durations_s)
            rows.append(
                {
                    "Axis": axis,
                    "Action": action,
                    "n": stats["n"],
                    "Mean (s)": stats["mean"],
                    "SD (s)": stats["sd"],
                    "Var (s^2)": stats["var"],
                    "Median (s)": stats["median"],
                    "IQR (s)": stats["iqr"],
                    "Min-Max (s)": self._min_max_display(stats["min"], stats["max"]),
                    "CV (%)": stats["cv"],
                }
            )
        return rows

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

    def _chart_file_display(self, chart_file: str | None) -> str:
        """Return a user-facing chart file name without local folder paths."""

        return "" if not chart_file else str(chart_file).replace("\\", "/").split("/")[-1]

    def _human_action(self, rule_id: str, fallback: str = "") -> str:
        """Return the compact action labels used in final summary sheets."""

        labels = {
            "search_reference": "Search Reference",
            "clear_motor": "Clear Motor",
            "move_to_home": "Move to Home",
            "move_to_max": "Move to Max",
        }
        return labels.get(rule_id, fallback or rule_id)

    def _axis_action_sort_key(self, key: tuple[str, str]) -> tuple[str, int, str]:
        """Sort axis/action summary rows in the requested action order."""

        axis, action = key
        action_order = {
            "Search Reference": 0,
            "Clear Motor": 1,
            "Move to Home": 2,
            "Move to Max": 3,
        }
        return (axis, action_order.get(action, 99), action)

    def _duration_stats_seconds(self, values: list[float]) -> dict[str, float | int | None]:
        """Compute common stats for already-second duration values.

        A single valid sample has IQR 0.0 because Q1 and Q3 are both that value.
        """

        numeric: list[float] = []
        for value in values:
            if value is None:
                continue
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric_value):
                numeric.append(numeric_value)
        if not numeric:
            return {
                "n": 0,
                "mean": None,
                "sd": None,
                "var": None,
                "median": None,
                "q1": None,
                "q3": None,
                "iqr": None,
                "min": None,
                "max": None,
                "cv": None,
            }
        count = len(numeric)
        mean = statistics.mean(numeric)
        sd = statistics.stdev(numeric) if count > 1 else None
        var = statistics.variance(numeric) if count > 1 else None
        series = pd.Series(numeric, dtype="float64")
        q1 = float(series.quantile(0.25, interpolation="linear"))
        q3 = float(series.quantile(0.75, interpolation="linear"))
        return {
            "n": count,
            "mean": mean,
            "sd": sd,
            "var": var,
            "median": statistics.median(numeric),
            "q1": q1,
            "q3": q3,
            "iqr": q3 - q1,
            "min": min(numeric),
            "max": max(numeric),
            "cv": sd / mean * 100.0 if sd is not None and mean else None,
        }

    def _min_max_display(self, minimum: float | None, maximum: float | None) -> str:
        """Format a compact min-max seconds display."""

        if minimum is None or maximum is None:
            return ""
        return f"{minimum:.3f}-{maximum:.3f}"

    def _reference_evidence_status(self, item: ReferenceDurationStats) -> str:
        """Return a compact reference-evidence status for gallery/index sheets."""

        if item.hardware_reference_evidence_found_count and not item.hardware_reference_evidence_missing_count:
            return "Found"
        if item.hardware_reference_evidence_found_count and item.hardware_reference_evidence_missing_count:
            return "Mixed"
        return "Missing"
