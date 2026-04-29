"""Boundary-aware, axis-local event matching for main TXT activities."""

from __future__ import annotations

import logging
import re
from typing import Iterable

from .config import (
    COMPANION_VALUE_PREFIXES,
    DEFAULT_MAX_EVENT_DURATION_MS,
    DURATION_STATUS_END_BEFORE_START,
    DURATION_STATUS_NOT_APPLICABLE,
    DURATION_STATUS_TOO_LONG,
    DURATION_STATUS_VALID,
    MAX_EVENT_DURATION_MS,
    STATUS_CLOSED_BY_BOUNDARY,
    STATUS_CLOSED_BY_NEW_START,
    STATUS_DURATION_TOO_LONG_CANDIDATE,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
)
from .models import ActivityRecord, AxisLogEvent, BoundaryEvent, DiagnosticEvent, EventRule, MainTimelineEvent
from .time_utils import calculate_duration_values, format_log_timestamp


class EventMatcher:
    """Matches configured start and end activity events within each axis and workflow boundary."""

    def __init__(
        self,
        event_rules: Iterable[EventRule],
        max_event_duration_ms: dict[str, int] | None = None,
        default_max_event_duration_ms: int = DEFAULT_MAX_EVENT_DURATION_MS,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the matcher with the configured rule set and per-rule max durations."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._compiled_rules = [
            (
                rule,
                re.compile(rule.start_pattern, re.IGNORECASE),
                re.compile(rule.end_pattern, re.IGNORECASE),
            )
            for rule in event_rules
        ]
        self._max_event_duration_ms = dict(MAX_EVENT_DURATION_MS)
        if max_event_duration_ms is not None:
            self._max_event_duration_ms.update(max_event_duration_ms)
        self._default_max_event_duration_ms = default_max_event_duration_ms

    def build_activity_records(self, timeline: list[MainTimelineEvent]) -> list[ActivityRecord]:
        """Match start and end events on the mixed axis-plus-boundary timeline."""

        self._logger.info("Matching %s parsed TXT timeline events", len(timeline))
        pending: dict[tuple[str, str], tuple[AxisLogEvent, EventRule]] = {}
        records: list[ActivityRecord] = []
        for index, item in enumerate(timeline):
            if isinstance(item, BoundaryEvent) or isinstance(item, DiagnosticEvent):
                records.extend(self._flush_pending_for_boundary(pending, item))
                continue
            classification = self._classify_event(item.message)
            if classification is None:
                continue
            kind, rule = classification
            if kind == "start":
                records.extend(self._register_start_event(pending, item, rule))
                continue
            records.extend(self._resolve_end_event(pending, timeline, index, item, rule))
        records.extend(self._close_remaining_pending(pending))
        self._logger.info("Built %s activity records", len(records))
        return records

    def _classify_event(self, message: str) -> tuple[str, EventRule] | None:
        """Return whether a message is a configured start or end event."""

        self._logger.debug("Classifying activity message %s", message)
        for rule, start_pattern, end_pattern in self._compiled_rules:
            if start_pattern.search(message):
                return "start", rule
            if end_pattern.search(message):
                return "end", rule
        return None

    def _register_start_event(
        self,
        pending: dict[tuple[str, str], tuple[AxisLogEvent, EventRule]],
        event: AxisLogEvent,
        rule: EventRule,
    ) -> list[ActivityRecord]:
        """Register one start event, replacing an older stale start for the same axis/rule."""

        self._logger.debug("Registering start event %s on axis %s", rule.start_label, event.axis)
        key = (event.axis, rule.rule_id)
        records: list[ActivityRecord] = []
        previous_pending = pending.get(key)
        if previous_pending is not None:
            previous_event, previous_rule = previous_pending
            records.append(
                self._build_unmatched_start_record(
                    start_event=previous_event,
                    rule=previous_rule,
                    reason="Closed because a new start for the same axis/rule appeared before an end event.",
                    match_status=STATUS_CLOSED_BY_NEW_START,
                    closing_time=event.timestamp,
                    closing_line=event.line_number,
                    closing_raw_line=event.raw_line,
                )
            )
        pending[key] = (event, rule)
        return records

    def _resolve_end_event(
        self,
        pending: dict[tuple[str, str], tuple[AxisLogEvent, EventRule]],
        timeline: list[MainTimelineEvent],
        end_index: int,
        end_event: AxisLogEvent,
        rule: EventRule,
    ) -> list[ActivityRecord]:
        """Resolve one end event against a pending same-axis same-rule start."""

        self._logger.debug("Resolving end event %s on axis %s", rule.end_label, end_event.axis)
        key = (end_event.axis, rule.rule_id)
        if key not in pending:
            return [self._build_unmatched_end_record(end_event, rule)]
        start_event, pending_rule = pending.pop(key)
        max_duration_ms = self._resolve_max_duration_ms(rule.rule_id)
        duration_ms, _ = calculate_duration_values(start_event.timestamp, end_event.timestamp)
        if duration_ms < 0:
            return [
                self._build_rejected_duration_record(
                    start_event=start_event,
                    rule=pending_rule,
                    end_event=end_event,
                    duration_status=DURATION_STATUS_END_BEFORE_START,
                    max_duration_ms=max_duration_ms,
                    reason=f"Candidate pair ended before it started: {duration_ms} ms.",
                ),
                self._build_unmatched_end_record(
                    end_event,
                    rule,
                    reason="End event appeared without a valid pending start because the candidate start/end ordering was invalid.",
                ),
            ]
        if duration_ms > max_duration_ms:
            return [
                self._build_rejected_duration_record(
                    start_event=start_event,
                    rule=pending_rule,
                    end_event=end_event,
                    duration_status=DURATION_STATUS_TOO_LONG,
                    max_duration_ms=max_duration_ms,
                    reason=f"Candidate pair exceeded max duration: {duration_ms} ms > {max_duration_ms} ms.",
                ),
                self._build_unmatched_end_record(
                    end_event,
                    rule,
                    reason=f"End event was not matched because the pending start exceeded the configured max duration of {max_duration_ms} ms.",
                ),
            ]
        return [self._build_matched_record(timeline, end_index, start_event, end_event, pending_rule, max_duration_ms)]

    def _flush_pending_for_boundary(
        self,
        pending: dict[tuple[str, str], tuple[AxisLogEvent, EventRule]],
        boundary: BoundaryEvent | DiagnosticEvent,
    ) -> list[ActivityRecord]:
        """Flush pending starts when a boundary indicates the workflow moved on or failed."""

        boundary_type = self._boundary_type(boundary)
        self._logger.debug("Handling boundary %s on line %s", boundary_type, boundary.line_number)
        close_pending_when_seen = getattr(boundary, "close_pending_when_seen", False)
        if not boundary.flush_pending and not close_pending_when_seen:
            return []
        records: list[ActivityRecord] = []
        keys_to_close = [
            key
            for key in pending
            if boundary.flush_scope != "axis" or not boundary.axis or key[0] == boundary.axis
        ]
        for key in keys_to_close:
            start_event, rule = pending.pop(key)
            records.append(self._build_boundary_closed_record(start_event, rule, boundary))
        return records

    def _close_remaining_pending(
        self,
        pending: dict[tuple[str, str], tuple[AxisLogEvent, EventRule]],
    ) -> list[ActivityRecord]:
        """Close any starts that survived to the end of the TXT file."""

        self._logger.debug("Closing %s pending starts at end of TXT file", len(pending))
        return [
            self._build_unmatched_start_record(
                start_event=start_event,
                rule=rule,
                reason="Still pending at end of TXT file.",
            )
            for start_event, rule in pending.values()
        ]

    def _build_matched_record(
        self,
        timeline: list[MainTimelineEvent],
        end_index: int,
        start_event: AxisLogEvent,
        end_event: AxisLogEvent,
        rule: EventRule,
        max_duration_ms: int,
    ) -> ActivityRecord:
        """Create one matched detail row from a start/end pair."""

        self._logger.debug("Building matched record for axis %s rule %s", start_event.axis, rule.rule_id)
        end_value, note = self._find_end_value(timeline, end_index, end_event)
        return ActivityRecord(
            axis=start_event.axis,
            rule_id=rule.rule_id,
            event_type=rule.start_label,
            start_event=rule.start_label,
            end_event=rule.end_label,
            start_time=start_event.timestamp,
            end_time=end_event.timestamp,
            start_value=start_event.inline_value,
            end_value=end_value,
            source_txt_start_line=start_event.raw_line,
            source_txt_end_line=end_event.raw_line,
            match_status=STATUS_MATCHED,
            duration_status=DURATION_STATUS_VALID,
            max_duration_ms=max_duration_ms,
            activity_status=STATUS_MATCHED,
            notes=note,
            start_line_number=start_event.line_number,
            end_line_number=end_event.line_number,
            sort_time=end_event.timestamp,
            sort_index=end_event.line_number,
        )

    def _build_unmatched_start_record(
        self,
        start_event: AxisLogEvent,
        rule: EventRule,
        reason: str,
        match_status: str = STATUS_UNMATCHED_START,
        closing_time=None,
        closing_line: int = 0,
        closing_raw_line: str = "",
    ) -> ActivityRecord:
        """Create one detail row for a start event that did not reach a valid end."""

        self._logger.debug("Creating unmatched-start record for axis %s", start_event.axis)
        notes = reason
        if closing_time is not None:
            notes = self._merge_notes(notes, f"Closing context time: {format_log_timestamp(closing_time)}.")
        if closing_line:
            notes = self._merge_notes(notes, f"Closing context line: {closing_line}.")
        if closing_raw_line:
            notes = self._merge_notes(notes, f"Closing context raw line: {closing_raw_line}")
        return ActivityRecord(
            axis=start_event.axis,
            rule_id=rule.rule_id,
            event_type=rule.start_label,
            start_event=rule.start_label,
            start_time=start_event.timestamp,
            start_value=start_event.inline_value,
            source_txt_start_line=start_event.raw_line,
            match_status=match_status,
            duration_status=DURATION_STATUS_NOT_APPLICABLE,
            boundary_close_reason=reason,
            status=match_status,
            activity_status=match_status,
            notes=notes,
            max_duration_ms=self._resolve_max_duration_ms(rule.rule_id),
            start_line_number=start_event.line_number,
            sort_time=closing_time or start_event.timestamp,
            sort_index=closing_line or start_event.line_number,
        )

    def _build_unmatched_end_record(
        self,
        end_event: AxisLogEvent,
        rule: EventRule,
        reason: str = "End event appeared without a matching pending start.",
    ) -> ActivityRecord:
        """Create one detail row for an end event with no known start."""

        self._logger.debug("Creating unmatched-end record for axis %s", end_event.axis)
        return ActivityRecord(
            axis=end_event.axis,
            rule_id=rule.rule_id,
            event_type=rule.start_label,
            start_event=rule.start_label,
            end_event=rule.end_label,
            end_time=end_event.timestamp,
            source_txt_end_line=end_event.raw_line,
            match_status=STATUS_UNMATCHED_END,
            duration_status=DURATION_STATUS_NOT_APPLICABLE,
            status=STATUS_UNMATCHED_END,
            activity_status=STATUS_UNMATCHED_END,
            notes=reason,
            max_duration_ms=self._resolve_max_duration_ms(rule.rule_id),
            end_line_number=end_event.line_number,
            sort_time=end_event.timestamp,
            sort_index=end_event.line_number,
        )

    def _build_boundary_closed_record(
        self,
        start_event: AxisLogEvent,
        rule: EventRule,
        boundary: BoundaryEvent | DiagnosticEvent,
    ) -> ActivityRecord:
        """Create one start-closure row caused by a workflow boundary."""

        boundary_type = self._boundary_type(boundary)
        self._logger.debug("Closing pending start for axis %s by boundary %s", start_event.axis, boundary_type)
        match_status = (
            STATUS_INITIALIZATION_FAILED
            if boundary_type == "InitializationFailed"
            else STATUS_CLOSED_BY_BOUNDARY
        )
        reason = self._boundary_reason(boundary)
        notes = self._merge_notes(
            reason,
            f"Boundary raw line: {boundary.raw_line}",
        )
        return ActivityRecord(
            axis=start_event.axis,
            rule_id=rule.rule_id,
            event_type=rule.start_label,
            start_event=rule.start_label,
            start_time=start_event.timestamp,
            start_value=start_event.inline_value,
            source_txt_start_line=start_event.raw_line,
            match_status=match_status,
            duration_status=DURATION_STATUS_NOT_APPLICABLE,
            boundary_close_reason=reason,
            closed_by_boundary_type=boundary_type,
            closed_by_boundary_time=boundary.timestamp,
            closed_by_boundary_line=boundary.line_number,
            closed_by_boundary_line_text=boundary.raw_line,
            status=match_status,
            activity_status=match_status,
            notes=notes,
            max_duration_ms=self._resolve_max_duration_ms(rule.rule_id),
            start_line_number=start_event.line_number,
            sort_time=boundary.timestamp,
            sort_index=boundary.line_number,
        )

    def _build_rejected_duration_record(
        self,
        start_event: AxisLogEvent,
        rule: EventRule,
        end_event: AxisLogEvent,
        duration_status: str,
        max_duration_ms: int,
        reason: str,
    ) -> ActivityRecord:
        """Create one unmatched-start record for a candidate pair rejected by duration checks."""

        self._logger.debug("Rejecting candidate duration for axis %s rule %s", start_event.axis, rule.rule_id)
        notes = self._merge_notes(reason, f"Rejected end raw line: {end_event.raw_line}")
        candidate_duration_ms, candidate_duration_s = calculate_duration_values(start_event.timestamp, end_event.timestamp)
        match_status = (
            STATUS_DURATION_TOO_LONG_CANDIDATE
            if duration_status == DURATION_STATUS_TOO_LONG
            else STATUS_UNMATCHED_START
        )
        return ActivityRecord(
            axis=start_event.axis,
            rule_id=rule.rule_id,
            event_type=rule.start_label,
            start_event=rule.start_label,
            end_event=rule.end_label,
            start_time=start_event.timestamp,
            end_time=end_event.timestamp,
            start_value=start_event.inline_value,
            source_txt_start_line=start_event.raw_line,
            source_txt_end_line=end_event.raw_line,
            match_status=match_status,
            duration_status=duration_status,
            boundary_close_reason=reason,
            candidate_duration_ms=candidate_duration_ms,
            candidate_duration_s=candidate_duration_s,
            max_duration_ms=max_duration_ms,
            exceeded_max_duration=duration_status == DURATION_STATUS_TOO_LONG,
            status=duration_status,
            activity_status=match_status,
            duration_warning=True,
            notes=notes,
            start_line_number=start_event.line_number,
            end_line_number=end_event.line_number,
            sort_time=end_event.timestamp,
            sort_index=end_event.line_number,
        )

    def _find_end_value(
        self,
        timeline: list[MainTimelineEvent],
        end_index: int,
        end_event: AxisLogEvent,
    ) -> tuple[float | None, str]:
        """Find an inline or companion numeric value for the end side of a match."""

        self._logger.debug("Resolving end value for axis %s line %s", end_event.axis, end_event.line_number)
        if end_event.inline_value is not None:
            return end_event.inline_value, ""
        axis_events_checked = 0
        for candidate in timeline[end_index + 1 :]:
            if not isinstance(candidate, AxisLogEvent):
                continue
            axis_events_checked += 1
            if axis_events_checked > 4:
                break
            if candidate.axis != end_event.axis:
                continue
            if candidate.inline_value is None:
                continue
            if not candidate.message.lower().startswith(COMPANION_VALUE_PREFIXES):
                continue
            if candidate.timestamp != end_event.timestamp:
                continue
            note = f"End value taken from companion line: {candidate.message}"
            return candidate.inline_value, note
        return None, ""

    def _resolve_max_duration_ms(self, rule_id: str) -> int:
        """Return the configured max duration for one rule identifier."""

        return self._max_event_duration_ms.get(rule_id, self._default_max_event_duration_ms)

    def _boundary_type(self, boundary: BoundaryEvent | DiagnosticEvent) -> str:
        """Return the boundary-like type for a real boundary or flushing diagnostic."""

        if isinstance(boundary, BoundaryEvent):
            return boundary.boundary_type
        return boundary.diagnostic_type

    def _boundary_reason(self, boundary: BoundaryEvent | DiagnosticEvent) -> str:
        """Return the human-readable close reason for a boundary event."""

        boundary_type = self._boundary_type(boundary)
        if boundary_type == "InitializationStarted":
            return "Closed because a new initialization started."
        if boundary_type == "InitializationFailed":
            return "Closed because initialization failed."
        if boundary_type == "RobotInitializationDone":
            return "Still pending at robot initialization done."
        if boundary_type == "MotorAbortClicked":
            return "Closed because motor abort was clicked."
        if boundary_type == "RobotMovingStopped":
            return "Closed because robot movement stopped."
        if boundary_type == "SystemExitSelected":
            return "Closed because system exit was selected."
        if boundary_type == "ApplicationExited":
            return "Closed because the application exited."
        if boundary_type == "McuControllerStopped":
            return "Closed because the MCU controller stopped."
        if boundary_type in {"ToolMenuSelected", "FactoryMenuSelected"}:
            return "Closed because the workflow changed before the event finished."
        if boundary_type == "FinalizationDone":
            return "Closed because finalization completed."
        if boundary_type == "SensorCut":
            return "Closed because a motor sensor cut diagnostic was reported."
        return f"Closed by boundary {boundary_type}."

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Combine existing notes with a new note without duplicating separators."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"
