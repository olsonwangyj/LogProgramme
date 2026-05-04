"""Attach hardware TPOS motion segments to matched TXT activity rows."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from .config import (
    HARDWARE_DISTANCE_CONSISTENCY_TOLERANCE,
    HARDWARE_SEGMENT_MATCH_WINDOW_MS,
    HARDWARE_STATUS_INCOMPLETE,
    HARDWARE_STATUS_MATCHED_NEAREST,
    HARDWARE_STATUS_MATCHED_NEAREST_FUTURE,
    HARDWARE_STATUS_MATCHED_NEAREST_PREVIOUS,
    HARDWARE_STATUS_MATCHED_OVERLAP,
    HARDWARE_STATUS_MULTIPLE_CANDIDATES,
    HARDWARE_STATUS_NO_SEGMENT,
    STATUS_MATCHED,
)
from .models import ActivityRecord, DutyCycleLogFileResult, HardwareMotionSegment


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

    def _mark_duplicate_segments(self, segments: list[HardwareMotionSegment]) -> None:
        """Annotate exact duplicate hardware segments while keeping audit rows intact."""

        grouped: dict[tuple, list[HardwareMotionSegment]] = defaultdict(list)
        for segment in segments:
            grouped[self._segment_key(segment)].append(segment)
        for key, group in grouped.items():
            if len(group) < 2:
                if group:
                    group[0].duplicate_segment_key = self._segment_key_text(key)
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

        selected_by_key: dict[tuple, HardwareMotionSegment] = {}
        for segment in sorted(
            segments,
            key=lambda item: (
                item.source_path.name,
                item.axis,
                item.start_time or datetime.max,
                item.end_time or datetime.max,
                item.start_line_number or 0,
            ),
        ):
            selected_by_key.setdefault(self._segment_key(segment), segment)
        return list(selected_by_key.values())

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
