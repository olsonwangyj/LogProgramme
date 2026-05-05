"""Attach hardware TPOS motion segments to matched TXT activity rows."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from .config import (
    HARDWARE_DISTANCE_CONSISTENCY_TOLERANCE,
    HARDWARE_REFERENCE_MATCH_WINDOW_MS,
    HARDWARE_REFERENCE_STATUS_FOUND,
    HARDWARE_REFERENCE_STATUS_NO_EVIDENCE,
    HARDWARE_REFERENCE_STATUS_NOT_APPLICABLE,
    HARDWARE_SEGMENT_MATCH_WINDOW_MS,
    HARDWARE_STATUS_INCOMPLETE,
    HARDWARE_STATUS_MATCHED_NEAREST,
    HARDWARE_STATUS_MATCHED_NEAREST_FUTURE,
    HARDWARE_STATUS_MATCHED_NEAREST_PREVIOUS,
    HARDWARE_STATUS_MATCHED_OVERLAP,
    HARDWARE_STATUS_MULTIPLE_CANDIDATES,
    HARDWARE_STATUS_NO_SEGMENT,
    HARDWARE_STATUS_REFERENCE_NOT_APPLICABLE,
    STATUS_MATCHED,
)
from .models import ActivityRecord, DutyCycleLogFileResult, HardwareMotionSegment, HardwareReferenceEvidence


class HardwareMotionAssociator:
    """Matches complete hardware S/E motion segments onto activity records."""

    def __init__(
        self,
        match_window_ms: int = HARDWARE_SEGMENT_MATCH_WINDOW_MS,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize hardware motion matching options."""

        self.match_window_ms = match_window_ms
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def attach(
        self,
        records: list[ActivityRecord],
        log_file_results: list[DutyCycleLogFileResult],
    ) -> list[ActivityRecord]:
        """Attach the nearest reliable same-axis hardware motion segment to each activity."""

        segments = [
            segment
            for file_result in log_file_results
            for segment in file_result.hardware_motion_segments
        ]
        reference_events = [
            event
            for file_result in log_file_results
            for event in file_result.hardware_reference_events
        ]
        self._reset_matching_audit(segments)
        self._reset_reference_audit(reference_events)
        self._mark_duplicate_segments(segments)
        complete_segments = [
            segment
            for segment in segments
            if segment.raw_start_position is not None
            and segment.raw_end_position is not None
            and segment.hardware_actual_distance is not None
        ]
        effective_complete_segments = self._dedupe_complete_segments(complete_segments)
        incomplete_segments = [
            segment
            for segment in segments
            if segment.raw_start_position is not None
            and segment.raw_end_position is None
        ]
        self._logger.info(
            "Attaching hardware motion distances using %s effective complete TPOS segments",
            len(effective_complete_segments),
        )
        for record in records:
            if record.match_status and record.match_status != STATUS_MATCHED:
                self._clear_selected_distance(record, "MissingHardwareActualDistance")
                continue
            if not record.axis or record.start_time is None or record.end_time is None:
                self._clear_selected_distance(record, "MissingHardwareActualDistance")
                continue
            if record.rule_id == "search_reference":
                self._apply_reference_evidence(record, reference_events)
                continue
            record.hardware_reference_match_status = HARDWARE_REFERENCE_STATUS_NOT_APPLICABLE
            selected, status, delta_ms, notes = self._select_segment(record, effective_complete_segments)
            if selected is None:
                incomplete = self._has_near_incomplete_segment(record, incomplete_segments)
                self._apply_missing(record, HARDWARE_STATUS_INCOMPLETE if incomplete else HARDWARE_STATUS_NO_SEGMENT)
                continue
            self._apply_segment(record, selected, status, delta_ms, notes)
        return records

    def _select_segment(
        self,
        record: ActivityRecord,
        segments: list[HardwareMotionSegment],
    ) -> tuple[HardwareMotionSegment | None, str, float | None, str]:
        """Select the best complete same-axis segment for one activity."""

        same_axis = [segment for segment in segments if segment.axis == record.axis]
        overlapping = [
            segment
            for segment in same_axis
            if self._overlaps(record.start_time, record.end_time, segment.start_time, segment.end_time)
        ]
        if overlapping:
            selected = min(overlapping, key=lambda item: self._start_delta_ms(record.start_time, item.start_time))
            notes = "Multiple overlapping hardware candidates; nearest start time selected." if len(overlapping) > 1 else ""
            status = HARDWARE_STATUS_MULTIPLE_CANDIDATES if len(overlapping) > 1 else HARDWARE_STATUS_MATCHED_OVERLAP
            return selected, status, self._start_delta_ms(record.start_time, selected.start_time), notes
        nearest = self._nearest_segment(record.start_time, same_axis)
        if nearest is None:
            return None, HARDWARE_STATUS_NO_SEGMENT, None, ""
        delta_ms = self._start_delta_ms(record.start_time, nearest.start_time)
        if delta_ms is None or delta_ms > self.match_window_ms:
            return None, HARDWARE_STATUS_NO_SEGMENT, delta_ms, ""
        return nearest, self._nearest_status(record, nearest), delta_ms, ""

    def _nearest_segment(
        self,
        reference_time: datetime,
        segments: list[HardwareMotionSegment],
    ) -> HardwareMotionSegment | None:
        """Return the same-axis segment with closest start time."""

        timed = [segment for segment in segments if segment.start_time is not None]
        if not timed:
            return None
        return min(timed, key=lambda segment: self._nearest_key(reference_time, segment))

    def _nearest_key(self, reference_time: datetime, segment: HardwareMotionSegment) -> float:
        """Return nearest-start sort key without treating exact zero as missing."""

        delta_ms = self._start_delta_ms(reference_time, segment.start_time)
        return delta_ms if delta_ms is not None else float("inf")

    def _nearest_status(self, record: ActivityRecord, segment: HardwareMotionSegment) -> str:
        """Classify a nearest fallback as previous, future, or generic."""

        if record.start_time is None or segment.start_time is None:
            return HARDWARE_STATUS_MATCHED_NEAREST
        if segment.end_time is not None and segment.end_time <= record.start_time:
            return HARDWARE_STATUS_MATCHED_NEAREST_PREVIOUS
        if record.end_time is not None and segment.start_time >= record.end_time:
            return HARDWARE_STATUS_MATCHED_NEAREST_FUTURE
        if segment.start_time > record.start_time:
            return HARDWARE_STATUS_MATCHED_NEAREST_FUTURE
        if segment.start_time < record.start_time:
            return HARDWARE_STATUS_MATCHED_NEAREST_PREVIOUS
        return HARDWARE_STATUS_MATCHED_NEAREST

    def _has_near_incomplete_segment(
        self,
        record: ActivityRecord,
        segments: list[HardwareMotionSegment],
    ) -> bool:
        """Return whether a same-axis incomplete segment is near the activity start."""

        for segment in segments:
            if segment.axis != record.axis or segment.start_time is None or record.start_time is None:
                continue
            delta_ms = self._start_delta_ms(record.start_time, segment.start_time)
            if delta_ms is not None and delta_ms <= self.match_window_ms:
                return True
        return False

    def _apply_segment(
        self,
        record: ActivityRecord,
        segment: HardwareMotionSegment,
        status: str,
        delta_ms: float | None,
        notes: str,
    ) -> None:
        """Copy hardware segment fields onto an activity record."""

        record.hardware_motion_source_file = segment.source_path.name
        record.hardware_motion_match_status = status
        record.hardware_motion_time_delta_ms = delta_ms
        record.hardware_raw_start_position = segment.raw_start_position
        record.hardware_raw_end_position = segment.raw_end_position
        record.hardware_raw_target_position = segment.raw_target_position
        record.hardware_start_position = segment.hardware_start_position
        record.hardware_end_position = segment.hardware_end_position
        record.hardware_target_position = segment.hardware_target_position
        record.hardware_actual_distance = segment.hardware_actual_distance
        record.hardware_commanded_distance = segment.hardware_commanded_distance
        record.hardware_start_line_number = segment.start_line_number
        record.hardware_end_line_number = segment.end_line_number
        record.hardware_target_line_number = segment.target_line_number
        record.hardware_start_line_text = segment.start_line_text
        record.hardware_end_line_text = segment.end_line_text
        record.hardware_target_line_text = segment.target_line_text
        self._apply_distance_consistency(record)
        if segment.hardware_actual_distance is not None:
            if status == HARDWARE_STATUS_MATCHED_OVERLAP:
                record.movement_distance = abs(segment.hardware_actual_distance)
                record.movement_distance_source = "HardwareActualDistance"
                record.movement_distance_method = "TPOSStartEndRawDifference"
                record.movement_distance_notes = self._merge_notes(segment.notes, notes)
                self._register_selected_match(segment, record)
            else:
                self._clear_selected_distance(record, "UnreliableHardwareMotionMatch")
                record.movement_distance_notes = self._merge_notes(record.movement_distance_notes, segment.notes)
                record.movement_distance_notes = self._merge_notes(record.movement_distance_notes, notes)
                record.movement_distance_notes = self._merge_notes(
                    record.movement_distance_notes,
                    "Hardware actual distance is shown as a candidate only; selected distance requires an overlapping hardware segment.",
                )
        else:
            self._clear_selected_distance(record, "MissingHardwareActualDistance")

    def _apply_missing(self, record: ActivityRecord, status: str) -> None:
        """Mark a row that has no usable hardware actual distance."""

        record.hardware_motion_match_status = status
        record.hardware_actual_distance = None
        self._apply_distance_consistency(record)
        self._clear_selected_distance(record, "MissingHardwareActualDistance")

    def _apply_reference_evidence(
        self,
        record: ActivityRecord,
        reference_events: list[HardwareReferenceEvidence],
    ) -> None:
        """Attach hardware reference evidence to a search-reference activity row."""

        record.hardware_motion_match_status = HARDWARE_STATUS_REFERENCE_NOT_APPLICABLE
        record.hardware_actual_distance = None
        candidates = self._reference_candidates(record, reference_events)
        if not candidates:
            record.hardware_reference_match_status = HARDWARE_REFERENCE_STATUS_NO_EVIDENCE
            record.hardware_reference_source_file = ""
            record.hardware_reference_time_delta_ms = None
            record.hardware_reference_zero_sensor_time = None
            record.hardware_reference_reset_time = None
            record.hardware_reference_zero_sensor_raw_value = None
            record.hardware_reference_line_number = None
            record.hardware_reference_line_text = ""
            self._clear_selected_distance(record, "DistanceNotApplicableForReference")
            record.movement_distance_notes = self._merge_notes(
                record.movement_distance_notes,
                "Search-reference distance is not applicable; no hardware TPOS Z/I reference evidence was matched.",
            )
            return

        candidate_events = [event for event, _ in candidates]
        zero = self._first_reference_of_type(candidate_events, "ZeroSensor")
        reset = self._first_reference_of_type(candidate_events, "ResetOrInit")
        representative = zero or reset or candidate_events[0]
        record.hardware_reference_match_status = HARDWARE_REFERENCE_STATUS_FOUND
        record.hardware_reference_source_file = representative.source_path.name
        record.hardware_reference_time_delta_ms = min(delta for _, delta in candidates)
        record.hardware_reference_zero_sensor_time = zero.timestamp if zero is not None else None
        record.hardware_reference_reset_time = reset.timestamp if reset is not None else None
        record.hardware_reference_zero_sensor_raw_value = zero.raw_value if zero is not None else None
        record.hardware_reference_line_number = representative.line_number
        record.hardware_reference_line_text = representative.line_text
        self._register_reference_matches(candidate_events, record)
        self._clear_selected_distance(record, "DistanceNotApplicableForReference")
        record.movement_distance_notes = self._merge_notes(
            record.movement_distance_notes,
            "Search-reference uses hardware TPOS Z/I reference evidence; movement distance is not applicable.",
        )

    def _reference_candidates(
        self,
        record: ActivityRecord,
        reference_events: list[HardwareReferenceEvidence],
    ) -> list[tuple[HardwareReferenceEvidence, float]]:
        """Return same-axis reference evidence inside or near the TXT reference activity."""

        candidates: list[tuple[HardwareReferenceEvidence, float]] = []
        for event in reference_events:
            if event.axis != record.axis:
                continue
            delta = self._reference_delta_ms(record, event)
            if delta is not None and delta <= HARDWARE_REFERENCE_MATCH_WINDOW_MS:
                candidates.append((event, delta))
        return sorted(
            candidates,
            key=lambda item: (
                item[1],
                item[0].timestamp or datetime.max,
                item[0].line_number or 0,
            ),
        )

    def _reference_delta_ms(
        self,
        record: ActivityRecord,
        event: HardwareReferenceEvidence,
    ) -> float | None:
        """Return zero for in-window evidence, otherwise nearest boundary distance."""

        if record.start_time is None or record.end_time is None or event.timestamp is None:
            return None
        if record.start_time <= event.timestamp <= record.end_time:
            return 0.0
        return min(
            abs((event.timestamp - record.start_time).total_seconds() * 1000.0),
            abs((event.timestamp - record.end_time).total_seconds() * 1000.0),
        )

    def _first_reference_of_type(
        self,
        events: list[HardwareReferenceEvidence],
        evidence_type: str,
    ) -> HardwareReferenceEvidence | None:
        """Return the first reference evidence of a requested type."""

        for event in events:
            if event.evidence_type == evidence_type:
                return event
        return None

    def _register_reference_matches(
        self,
        events: list[HardwareReferenceEvidence],
        record: ActivityRecord,
    ) -> None:
        """Mark reference evidence rows that were used by a TXT search-reference activity."""

        for event in events:
            event.match_status = HARDWARE_REFERENCE_STATUS_FOUND
            event.matched_txt_rule_id = record.rule_id
            event.matched_txt_start_time = record.start_time
            event.matched_txt_end_time = record.end_time

    def _mark_duplicate_segments(self, segments: list[HardwareMotionSegment]) -> None:
        """Annotate exact duplicate hardware segments while keeping audit rows intact."""

        grouped: dict[tuple, list[HardwareMotionSegment]] = defaultdict(list)
        for segment in segments:
            grouped[self._segment_key(segment)].append(segment)
        for key, group in grouped.items():
            if len(group) < 2:
                continue
            source_files = sorted({item.source_path.name for item in group})
            source_text = "; ".join(source_files)
            key_text = self._segment_key_text(key)
            for segment in group:
                segment.duplicate_segment_key = key_text
                segment.duplicate_segment_count = len(group)
                segment.possible_duplicate_source_files = source_text
                segment.possible_duplicate_hardware_segment = True
                segment.notes = self._merge_notes(
                    segment.notes,
                    f"PossibleDuplicateHardwareSegment: exact duplicate appears {len(group)} times.",
                )

    def _dedupe_complete_segments(self, segments: list[HardwareMotionSegment]) -> list[HardwareMotionSegment]:
        """Return one effective segment for each exact duplicate key."""

        grouped: dict[tuple, list[HardwareMotionSegment]] = defaultdict(list)
        for segment in segments:
            grouped[self._segment_key(segment)].append(segment)

        effective_segments: list[HardwareMotionSegment] = []
        for group in grouped.values():
            selected = self._choose_effective_segment(group)
            self._merge_best_target_fields(selected, group)
            selected.effective_segment_used_for_matching = True
            effective_segments.append(selected)
        return sorted(
            effective_segments,
            key=lambda item: (
                item.source_path.name,
                item.axis,
                item.start_time or datetime.max,
                item.end_time or datetime.max,
                item.start_line_number or 0,
            ),
        )

    def _reset_matching_audit(self, segments: list[HardwareMotionSegment]) -> None:
        """Clear matching/duplicate audit fields before a fresh association pass."""

        for segment in segments:
            segment.duplicate_segment_key = ""
            segment.duplicate_segment_count = 0
            segment.possible_duplicate_source_files = ""
            segment.possible_duplicate_hardware_segment = False
            segment.effective_segment_used_for_matching = False
            segment.matched_txt_activity_count = 0
            segment.matched_txt_rule_id = ""
            segment.matched_txt_start_time = None

    def _reset_reference_audit(self, events: list[HardwareReferenceEvidence]) -> None:
        """Clear reference evidence matching audit fields before a fresh association pass."""

        for event in events:
            event.match_status = "UnmatchedHardwareReferenceEvidence"
            event.matched_txt_rule_id = ""
            event.matched_txt_start_time = None
            event.matched_txt_end_time = None

    def _choose_effective_segment(self, segments: list[HardwareMotionSegment]) -> HardwareMotionSegment:
        """Choose the duplicate representative with the richest audit data."""

        return max(
            sorted(
                segments,
                key=lambda item: (
                    item.source_path.name,
                    item.start_line_number or 0,
                    item.end_line_number or 0,
                ),
            ),
            key=self._segment_completeness_score,
        )

    def _segment_completeness_score(self, segment: HardwareMotionSegment) -> tuple[int, int, int, int]:
        """Score duplicate representatives by target and text completeness."""

        return (
            int(segment.raw_target_position is not None),
            int(segment.hardware_target_position is not None),
            int(segment.hardware_commanded_distance is not None),
            sum(
                bool(value)
                for value in (
                    segment.start_line_text,
                    segment.end_line_text,
                    segment.target_line_text,
                )
            ),
        )

    def _merge_best_target_fields(
        self,
        selected: HardwareMotionSegment,
        group: list[HardwareMotionSegment],
    ) -> None:
        """Preserve target/commanded data from duplicates even when the first copy lacks it."""

        if selected.raw_target_position is not None and selected.hardware_commanded_distance is not None:
            return
        with_target = [
            segment
            for segment in group
            if segment.raw_target_position is not None
            or segment.hardware_target_position is not None
            or segment.hardware_commanded_distance is not None
        ]
        if not with_target:
            return
        best = self._choose_effective_segment(with_target)
        selected.target_time = selected.target_time or best.target_time
        selected.raw_target_position = selected.raw_target_position if selected.raw_target_position is not None else best.raw_target_position
        selected.hardware_target_position = (
            selected.hardware_target_position
            if selected.hardware_target_position is not None
            else best.hardware_target_position
        )
        selected.hardware_commanded_distance = (
            selected.hardware_commanded_distance
            if selected.hardware_commanded_distance is not None
            else best.hardware_commanded_distance
        )
        selected.target_line_number = selected.target_line_number or best.target_line_number
        selected.target_line_text = selected.target_line_text or best.target_line_text

    def _register_selected_match(self, segment: HardwareMotionSegment, record: ActivityRecord) -> None:
        """Record which effective segment produced a selected hardware distance."""

        segment.matched_txt_activity_count += 1
        rule_ids = [
            value
            for value in segment.matched_txt_rule_id.split("; ")
            if value
        ]
        if record.rule_id and record.rule_id not in rule_ids:
            rule_ids.append(record.rule_id)
        segment.matched_txt_rule_id = "; ".join(rule_ids)
        if segment.matched_txt_start_time is None:
            segment.matched_txt_start_time = record.start_time

    def _segment_key(self, segment: HardwareMotionSegment) -> tuple:
        """Build a duplicate-detection key from physical motion identity fields."""

        return (
            segment.axis,
            segment.start_time,
            segment.end_time,
            segment.raw_start_position,
            segment.raw_end_position,
        )

    def _segment_key_text(self, key: tuple) -> str:
        """Format a duplicate segment key for workbook audit columns."""

        return "|".join("" if value is None else str(value) for value in key)

    def _apply_distance_consistency(self, record: ActivityRecord) -> None:
        """Compare TXT target-derived distance with hardware command/actual distance for diagnostics."""

        expected = self._txt_target_distance_for_check(record)
        observed = self._hardware_distance_for_check(record)
        if expected is None:
            record.hardware_distance_consistency_status = "NoTXTTargetForCheck"
            record.hardware_distance_consistency_delta = None
            return
        if observed is None:
            record.hardware_distance_consistency_status = "NoHardwareTargetForCheck"
            record.hardware_distance_consistency_delta = None
            return
        delta = abs(abs(observed) - abs(expected))
        record.hardware_distance_consistency_delta = delta
        if record.hardware_motion_match_status != HARDWARE_STATUS_MATCHED_OVERLAP:
            record.hardware_distance_consistency_status = "CandidateOnlyNotValidated"
            return
        record.hardware_distance_consistency_status = (
            "ConsistentWithTXTTarget"
            if delta <= HARDWARE_DISTANCE_CONSISTENCY_TOLERANCE
            else "DistanceDiffTooLarge"
        )

    def _txt_target_distance_for_check(self, record: ActivityRecord) -> float | None:
        """Return a software target-derived command distance for diagnostics only."""

        if record.start_value is None and record.movement_commanded_distance is None:
            return None
        if record.movement_commanded_distance is not None:
            return abs(float(record.movement_commanded_distance))
        return abs(float(record.start_value))

    def _hardware_distance_for_check(self, record: ActivityRecord) -> float | None:
        """Return hardware command distance when present, otherwise actual distance."""

        if record.hardware_commanded_distance is not None:
            return abs(float(record.hardware_commanded_distance))
        if record.hardware_actual_distance is not None:
            return abs(float(record.hardware_actual_distance))
        return None

    def _clear_selected_distance(self, record: ActivityRecord, method: str) -> None:
        """Clear selected distance while preserving software audit fields."""

        record.movement_distance = None
        record.movement_distance_source = ""
        record.movement_distance_method = method
        if method == "MissingHardwareActualDistance":
            record.movement_distance_notes = self._merge_notes(
                record.movement_distance_notes,
                "No complete same-axis hardware TPOS Start/End segment was matched; software TXT positions are not used as selected distance.",
            )

    def _overlaps(
        self,
        start_a: datetime | None,
        end_a: datetime | None,
        start_b: datetime | None,
        end_b: datetime | None,
    ) -> bool:
        """Return whether two optional time ranges overlap."""

        if start_a is None or end_a is None or start_b is None or end_b is None:
            return False
        return start_b <= end_a and end_b >= start_a

    def _start_delta_ms(self, reference_time: datetime | None, segment_start: datetime | None) -> float | None:
        """Return absolute start-time delta in milliseconds."""

        if reference_time is None or segment_start is None:
            return None
        return abs((segment_start - reference_time).total_seconds() * 1000.0)

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Append a note if both note strings are present."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"
