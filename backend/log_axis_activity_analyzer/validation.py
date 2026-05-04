"""Validation helpers for duration correctness, max-duration limits, and final row status selection."""

from __future__ import annotations

import logging

from .config import (
    DEFAULT_MAX_EVENT_DURATION_MS,
    DURATION_STATUS_END_BEFORE_START,
    DURATION_STATUS_NOT_APPLICABLE,
    DURATION_STATUS_TOO_LONG,
    DURATION_STATUS_VALID,
    MAX_EVENT_DURATION_MS,
    OVERALL_STATUS_BOUNDARY_CLOSED,
    OVERALL_STATUS_CLOSED_BY_NEW_START,
    OVERALL_STATUS_DIAGNOSTIC,
    OVERALL_STATUS_DURATION_WARNING,
    OVERALL_STATUS_HARDWARE_WARNING,
    OVERALL_STATUS_INITIALIZATION_FAILED,
    OVERALL_STATUS_OK,
    OVERALL_STATUS_PARSE_WARNING,
    OVERALL_STATUS_PWM_WARNING,
    OVERALL_STATUS_UNMATCHED,
    PWM_STATUS_CONFLICT,
    PWM_STATUS_LATEST_BEFORE_TOO_FAR,
    PWM_STATUS_MATCHED_CARRY_FORWARD,
    PWM_STATUS_MATCHED_NEAREST_FUTURE,
    PWM_STATUS_NO_CONTROL_LOGS_AVAILABLE,
    PWM_STATUS_NO_EARLIER_PWM_FOR_AXIS,
    PWM_STATUS_NO_RELEVANT_LOG_FILE,
    PWM_STATUS_NO_SAME_AXIS_IN_FOLDER,
    PWM_STATUS_RELEVANT_LOG_FILE_LACKS_AXIS_PWM,
    HARDWARE_STATUS_MATCHED_OVERLAP,
    STATUS_CLOSED_BY_BOUNDARY,
    STATUS_CLOSED_BY_NEW_START,
    STATUS_DIAGNOSTIC,
    STATUS_DURATION_TOO_LONG_CANDIDATE,
    STATUS_DURATION_TOO_LONG,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_PARSE_WARNING,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
)
from .models import ActivityRecord
from .time_utils import calculate_duration_values


class ActivityValidator:
    """Validates activity durations, shape consistency, and finalizes detail-row status."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        max_event_duration_ms: dict[str, int] | None = None,
        default_max_event_duration_ms: int = DEFAULT_MAX_EVENT_DURATION_MS,
    ) -> None:
        """Initialize the validator with an optional logger and duration limits."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._max_event_duration_ms = dict(MAX_EVENT_DURATION_MS)
        if max_event_duration_ms is not None:
            self._max_event_duration_ms.update(max_event_duration_ms)
        self._default_max_event_duration_ms = default_max_event_duration_ms

    def validate(self, records: list[ActivityRecord]) -> list[ActivityRecord]:
        """Validate every activity record and finalize its display status."""

        self._logger.info("Validating %s activity records", len(records))
        for record in records:
            self._validate_record(record)
        return records

    def _validate_record(self, record: ActivityRecord) -> None:
        """Validate one activity record in place."""

        self._logger.debug("Validating record for axis %s match status %s", record.axis, record.match_status)
        if record.match_status == STATUS_PARSE_WARNING:
            record.status = OVERALL_STATUS_PARSE_WARNING
            record.duration_status = record.duration_status or DURATION_STATUS_NOT_APPLICABLE
            return
        if record.match_status == STATUS_DIAGNOSTIC:
            record.status = OVERALL_STATUS_DIAGNOSTIC
            record.duration_status = record.duration_status or DURATION_STATUS_NOT_APPLICABLE
            return
        record.max_duration_ms = record.max_duration_ms or self._resolve_max_duration_ms(record.rule_id)
        if record.match_status == STATUS_MATCHED:
            self._validate_duration(record)
            self._validate_pwm(record)
            self._validate_hardware(record)
            self._finalize_matched_status(record)
            return
        self._validate_non_matched_shape(record)
        self._validate_pwm(record)
        self._finalize_non_matched_status(record)

    def _validate_duration(self, record: ActivityRecord) -> None:
        """Recompute matched duration and enforce configured max-duration limits."""

        self._logger.debug("Validating duration for axis %s", record.axis)
        if record.start_time is None or record.end_time is None:
            record.duration_warning = True
            record.duration_status = DURATION_STATUS_NOT_APPLICABLE
            record.duration_ms = None
            record.duration_s = None
            record.notes = self._merge_notes(record.notes, "Matched record is missing a start or end timestamp.")
            return
        duration_ms, duration_s = calculate_duration_values(record.start_time, record.end_time)
        if duration_ms < 0:
            record.duration_warning = True
            record.duration_status = DURATION_STATUS_END_BEFORE_START
            record.duration_ms = None
            record.duration_s = None
            record.notes = self._merge_notes(record.notes, "End timestamp is earlier than start timestamp.")
            return
        max_duration_ms = record.max_duration_ms or self._resolve_max_duration_ms(record.rule_id)
        if duration_ms > max_duration_ms:
            record.duration_warning = True
            record.duration_status = DURATION_STATUS_TOO_LONG
            record.exceeded_max_duration = True
            record.duration_ms = duration_ms
            record.duration_s = duration_s
            record.notes = self._merge_notes(record.notes, "Duration exceeded configured max duration.")
            return
        record.duration_ms = duration_ms
        record.duration_s = duration_s
        record.duration_status = DURATION_STATUS_VALID

    def _validate_non_matched_shape(self, record: ActivityRecord) -> None:
        """Normalize non-matched records so they do not retain misleading duration values."""

        self._logger.debug("Validating non-matched record shape for axis %s", record.axis)
        if record.match_status != STATUS_MATCHED and record.duration_status != DURATION_STATUS_TOO_LONG:
            record.duration_ms = None
            record.duration_s = None
            record.duration_status = record.duration_status or DURATION_STATUS_NOT_APPLICABLE
        if record.match_status == STATUS_DURATION_TOO_LONG_CANDIDATE:
            record.duration_ms = None
            record.duration_s = None
        if record.match_status in {
            STATUS_UNMATCHED_START,
            STATUS_CLOSED_BY_BOUNDARY,
            STATUS_CLOSED_BY_NEW_START,
            STATUS_INITIALIZATION_FAILED,
        }:
            record.end_time = None if record.end_time is None else record.end_time
        if record.match_status == STATUS_UNMATCHED_END:
            record.start_time = None if record.start_time is None else record.start_time

    def _validate_pwm(self, record: ActivityRecord) -> None:
        """Set the PWM warning flag when matching failed or was uncertain."""

        self._logger.debug("Validating PWM association for axis %s", record.axis)
        if record.pwm_match_status in {
            PWM_STATUS_CONFLICT,
            PWM_STATUS_LATEST_BEFORE_TOO_FAR,
            PWM_STATUS_NO_CONTROL_LOGS_AVAILABLE,
            PWM_STATUS_NO_EARLIER_PWM_FOR_AXIS,
            PWM_STATUS_NO_RELEVANT_LOG_FILE,
            PWM_STATUS_NO_SAME_AXIS_IN_FOLDER,
            PWM_STATUS_RELEVANT_LOG_FILE_LACKS_AXIS_PWM,
            PWM_STATUS_MATCHED_CARRY_FORWARD,
            PWM_STATUS_MATCHED_NEAREST_FUTURE,
        }:
            record.pwm_warning = True

    def _validate_hardware(self, record: ActivityRecord) -> None:
        """Set the hardware warning flag when selected hardware distance is unavailable or weak."""

        self._logger.debug("Validating hardware distance for axis %s", record.axis)
        if record.match_status != STATUS_MATCHED:
            return
        if record.hardware_motion_match_status != HARDWARE_STATUS_MATCHED_OVERLAP:
            record.hardware_warning = True
            if record.hardware_actual_distance is None:
                record.notes = self._merge_notes(
                    record.notes,
                    "No hardware actual distance found; selected distance is unavailable.",
                )
            else:
                record.notes = self._merge_notes(
                    record.notes,
                    "Hardware motion match is not reliable enough to select movement distance.",
                )
            return
        if record.hardware_actual_distance is None or record.movement_distance is None:
            record.hardware_warning = True
            record.notes = self._merge_notes(
                record.notes,
                "No hardware actual distance found; selected distance is unavailable.",
            )

    def _finalize_matched_status(self, record: ActivityRecord) -> None:
        """Choose the final display status for a successfully matched record."""

        self._logger.debug("Finalizing matched display status for axis %s", record.axis)
        if record.duration_warning:
            record.status = OVERALL_STATUS_DURATION_WARNING
            return
        if record.hardware_warning:
            record.status = OVERALL_STATUS_HARDWARE_WARNING
            return
        if record.pwm_warning:
            record.status = OVERALL_STATUS_PWM_WARNING
            return
        record.status = OVERALL_STATUS_OK

    def _finalize_non_matched_status(self, record: ActivityRecord) -> None:
        """Choose the final display status for unmatched or boundary-closed records."""

        self._logger.debug("Finalizing non-matched display status for axis %s", record.axis)
        if record.match_status == STATUS_INITIALIZATION_FAILED:
            record.status = OVERALL_STATUS_INITIALIZATION_FAILED
            return
        if record.match_status == STATUS_CLOSED_BY_BOUNDARY:
            record.status = OVERALL_STATUS_BOUNDARY_CLOSED
            return
        if record.match_status == STATUS_CLOSED_BY_NEW_START:
            record.status = OVERALL_STATUS_CLOSED_BY_NEW_START
            return
        if record.match_status in {STATUS_UNMATCHED_START, STATUS_UNMATCHED_END}:
            record.status = OVERALL_STATUS_UNMATCHED
            return
        if record.match_status == STATUS_DURATION_TOO_LONG_CANDIDATE:
            record.status = OVERALL_STATUS_DURATION_WARNING
            return
        if record.duration_warning and record.duration_status == DURATION_STATUS_TOO_LONG:
            record.status = OVERALL_STATUS_DURATION_WARNING
            return
        if record.pwm_warning:
            record.status = OVERALL_STATUS_PWM_WARNING
            return
        record.status = OVERALL_STATUS_DURATION_WARNING if record.match_status else record.status

    def _resolve_max_duration_ms(self, rule_id: str) -> int:
        """Return the configured max duration for one rule identifier."""

        return self._max_event_duration_ms.get(rule_id, self._default_max_event_duration_ms)

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Combine existing notes with a new note without duplicating separators."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"
