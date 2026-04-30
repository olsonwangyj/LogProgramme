"""Typed models for timeline events, PWM sources, workbook rows, and run summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class EventRule:
    """Describes one configurable start/end event-pair rule."""

    rule_id: str
    start_label: str
    end_label: str
    start_pattern: str
    end_pattern: str


@dataclass(frozen=True)
class BoundaryRule:
    """Describes one configurable workflow-boundary pattern in the main TXT log."""

    boundary_type: str
    pattern: str
    flush_pending: bool = True
    flush_scope: str = "all"
    close_pending_when_seen: bool = False


@dataclass(frozen=True)
class AxisLogEvent:
    """Represents one parsed axis activity line from the main TXT log."""

    source_path: Path
    line_number: int
    ordinal: int
    timestamp: datetime
    axis: str
    message: str
    raw_line: str
    inline_value: Optional[float] = None
    event_kind: str = "AxisEvent"
    boundary_type: str | None = None
    is_boundary: bool = False
    failure_axis: str | None = None


@dataclass(frozen=True)
class BoundaryEvent:
    """Represents a workflow boundary or failure event from the main TXT log."""

    source_path: Path
    line_number: int
    ordinal: int
    timestamp: datetime
    boundary_type: str
    raw_line: str
    axis: str | None = None
    message: str = ""
    flush_pending: bool = True
    flush_scope: str = "all"
    close_pending_when_seen: bool = False
    event_kind: str = "BoundaryEvent"
    is_boundary: bool = True


@dataclass(frozen=True)
class DiagnosticEvent:
    """Represents a structured diagnostic line from the main TXT log."""

    source_path: Path
    line_number: int
    ordinal: int
    timestamp: datetime
    severity: str
    diagnostic_type: str
    axis: str | None
    node_id: int | None
    message: str
    raw_line: str
    flush_pending: bool = False
    flush_scope: str = "all"
    event_kind: str = "DiagnosticEvent"
    is_boundary: bool = False


MainTimelineEvent = AxisLogEvent | BoundaryEvent | DiagnosticEvent


@dataclass
class PWMEvent:
    """Represents one parsed PWM-related record from a control log file."""

    source_path: Path
    line_number: int
    timestamp: Optional[datetime]
    node_id: str
    axis: str
    pwm_raw_value: float
    pwm_percent: float
    direction: str
    raw_line: str
    command_type: str
    is_status_confirmation: bool
    is_confirmed_by_status_line: bool = False
    source_file_start_time: Optional[datetime] = None
    source_file_end_time: Optional[datetime] = None
    notes: str = ""


@dataclass
class AxisPWMProfile:
    """Aggregates PWM history for one axis within one control-log file."""

    source_path: Path
    axis: str
    pwm_percent: Optional[float] = None
    pwm_percent_values: list[float] = field(default_factory=list)
    pwm_raw_values: list[float] = field(default_factory=list)
    direction_values: list[str] = field(default_factory=list)
    first_seen_time: Optional[datetime] = None
    last_seen_time: Optional[datetime] = None
    source_lines: list[int] = field(default_factory=list)
    source_line_texts: list[str] = field(default_factory=list)
    conflict: bool = False
    direction_changed: bool = False
    conflict_reason: str = ""
    notes: str = ""
    events: list[PWMEvent] = field(default_factory=list)


@dataclass(frozen=True)
class ParseWarning:
    """Captures a malformed but relevant line that should appear in the report."""

    source_name: str
    source_path: Path
    line_number: int
    raw_line: str
    message: str
    axis: str = ""
    timestamp: Optional[datetime] = None


@dataclass
class MainLogParseResult:
    """Holds parsed axis events, boundary events, a merged timeline, and warnings."""

    events: list[AxisLogEvent] = field(default_factory=list)
    boundary_events: list[BoundaryEvent] = field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = field(default_factory=list)
    timeline: list[MainTimelineEvent] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    encoding_used: str = ""


@dataclass
class DutyCycleLogFileResult:
    """Holds parsed PWM events, profiles, and warnings for one control-log file."""

    source_path: Path
    encoding_used: str = ""
    file_start_time: Optional[datetime] = None
    file_end_time: Optional[datetime] = None
    pwm_events: list[PWMEvent] = field(default_factory=list)
    axis_profiles: dict[str, AxisPWMProfile] = field(default_factory=dict)
    warnings: list[ParseWarning] = field(default_factory=list)


@dataclass
class DutyCycleFolderParseResult:
    """Aggregates PWM parse results for every scanned `.log` file in a folder."""

    root_path: Path
    recursive: bool
    files: list[DutyCycleLogFileResult] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)


@dataclass
class PWMMatchSelection:
    """Describes how one PWM source was selected for an activity row."""

    event: Optional[PWMEvent] = None
    profile: Optional[AxisPWMProfile] = None
    match_method: str = ""
    match_status: str = ""
    time_delta_ms: Optional[int] = None
    missing_reason: str = ""
    notes: str = ""


@dataclass
class ActivityRecord:
    """Represents one row for the Details worksheet."""

    axis: str = ""
    rule_id: str = ""
    event_type: str = ""
    start_event: str = ""
    end_event: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    duration_s: Optional[float] = None
    start_value: Optional[float] = None
    end_value: Optional[float] = None
    movement_start_position: Optional[float] = None
    movement_target_position: Optional[float] = None
    movement_end_position: Optional[float] = None
    movement_commanded_distance: Optional[float] = None
    movement_actual_distance: Optional[float] = None
    movement_distance: Optional[float] = None
    movement_distance_source: str = ""
    movement_distance_method: str = ""
    movement_distance_notes: str = ""
    pwm_percent: Optional[float] = None
    pwm_raw_value: Optional[float] = None
    pwm_direction: str = ""
    pwm_direction_changed: bool = False
    pwm_conflict: bool = False
    pwm_conflict_reason: str = ""
    pwm_source_file: str = ""
    pwm_source_line: str = ""
    pwm_source_time: Optional[datetime] = None
    pwm_match_method: str = ""
    pwm_time_delta_ms: Optional[int] = None
    pwm_match_status: str = ""
    pwm_missing_reason: str = ""
    source_txt_start_line: str = ""
    source_txt_end_line: str = ""
    match_status: str = ""
    duration_status: str = ""
    boundary_close_reason: str = ""
    closed_by_boundary_type: str = ""
    closed_by_boundary_time: Optional[datetime] = None
    closed_by_boundary_line: int = 0
    closed_by_boundary_line_text: str = ""
    candidate_duration_ms: Optional[int] = None
    candidate_duration_s: Optional[float] = None
    max_duration_ms: Optional[int] = None
    exceeded_max_duration: bool = False
    status: str = ""
    notes: str = ""
    activity_status: str = ""
    duration_warning: bool = False
    pwm_warning: bool = False
    start_line_number: int = 0
    end_line_number: int = 0
    pwm_line_number: int = 0
    sort_time: Optional[datetime] = None
    sort_index: int = 0

    def sort_key(self) -> tuple[int, datetime, int]:
        """Return a stable chronological sort key for workbook rows."""

        if self.sort_time is not None:
            return (0, self.sort_time, self.sort_index)
        return (1, datetime.max, self.sort_index)


@dataclass
class ReportFrames:
    """Collects the data frames needed by the workbook exporter."""

    details: object
    event_summary: object
    axis_summary: object
    pwm_sources: object | None = None
    diagnostics: object | None = None
    diagnostics_summary: object | None = None
    distribution_summary: object | None = None
    distribution_raw_data: object | None = None
    distribution_chart_metadata: object | None = None
    distribution_exclusion_summary: object | None = None
    log_coverage_summary: object | None = None


@dataclass
class AnalysisRunResult:
    """Summarizes one completed analysis run for CLI output."""

    output_path: Path
    txt_axis_event_count: int
    boundary_event_count: int
    log_file_count: int
    pwm_profile_count: int
    detail_count: int
    matched_count: int
    unmatched_start_count: int
    unmatched_end_count: int
    closed_by_boundary_count: int
    closed_by_new_start_count: int
    initialization_failed_count: int
    diagnostic_count: int
    parse_warning_count: int
    duration_warning_count: int
    pwm_warning_count: int
    txt_encoding: str
    distribution_enabled: bool = False
    distribution_group_count: int = 0
    distribution_raw_row_count: int = 0
    distribution_chart_count: int = 0
    distribution_output_dir: Path | None = None
    distribution_excluded_missing_pwm_count: int = 0
    distribution_excluded_missing_distance_count: int = 0
    distribution_excluded_missing_true_distance_count: int = 0
    distribution_excluded_unreliable_pwm_count: int = 0
