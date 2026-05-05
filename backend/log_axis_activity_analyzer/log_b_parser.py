"""Parser for control logs containing PWM commands and hardware TPOS records."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from pathlib import Path

from .config import (
    AXIS_RAW_SCALE,
    CONTROL_PWM_COMMANDS,
    CONTROL_PWM_PATTERN,
    CONTROL_TIMESTAMP_PATTERN,
    CONTROL_TPOS_PATTERN,
    HARDWARE_TARGET_TO_START_MAX_DELTA_MS,
    HARDWARE_POSITION_KIND_MAP,
)
from .file_loader import TextFileLoader
from .models import (
    AxisPWMProfile,
    DutyCycleLogFileResult,
    HardwareMotionSegment,
    HardwarePositionEvent,
    HardwareReferenceEvidence,
    PWMEvent,
    ParseWarning,
)
from .time_utils import normalize_pwm_percent, parse_log_timestamp, resolve_pwm_direction


class DutyCycleLogParser:
    """Parses PWM values and hardware position events from a single control-log file."""

    def __init__(self, loader: TextFileLoader, logger: logging.Logger | None = None) -> None:
        """Initialize the parser with a shared file loader."""

        self._loader = loader
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def parse(
        self,
        file_path: Path | str,
        preferred_encoding: str | None = None,
    ) -> DutyCycleLogFileResult:
        """Parse one control log file and return PWM/hardware records plus file metadata."""

        path = Path(file_path)
        self._logger.info("Parsing control log %s", path)
        iterator, encoding = self._loader.iter_lines(path, preferred_encoding)
        result = DutyCycleLogFileResult(source_path=path, encoding_used=encoding)
        current_timestamp = None
        for line_number, line in iterator:
            timestamp = self._parse_control_timestamp(path, line_number, line)
            if timestamp is not None:
                current_timestamp = timestamp
                result.file_start_time = timestamp if result.file_start_time is None else min(result.file_start_time, timestamp)
                result.file_end_time = timestamp if result.file_end_time is None else max(result.file_end_time, timestamp)
                continue
            parsed_event = self._build_pwm_event(path, line_number, line, current_timestamp)
            if parsed_event is not None:
                result.pwm_events.append(parsed_event)
                if parsed_event.timestamp is None:
                    result.warnings.append(
                        ParseWarning(
                            source_name="PWM",
                            source_path=path,
                            line_number=line_number,
                            raw_line=line,
                            message="PWM line parsed without a timestamp; fallback matching may be required",
                            axis=parsed_event.axis,
                        )
                    )
                continue
            hardware_event = self._build_hardware_position_event(path, line_number, line, current_timestamp)
            if hardware_event is not None:
                result.hardware_position_events.append(hardware_event)
                if hardware_event.timestamp is None:
                    result.warnings.append(
                        ParseWarning(
                            source_name="HardwarePosition",
                            source_path=path,
                            line_number=line_number,
                            raw_line=line,
                            message="TPOS line parsed without a timestamp; hardware distance matching may be unavailable",
                            axis=hardware_event.axis,
                        )
                    )
                continue
            warning = self._build_parse_warning(path, line_number, line)
            if warning is not None:
                result.warnings.append(warning)
        self._propagate_file_times(result)
        self._mark_confirmed_events(result)
        self._build_axis_profiles(result)
        self._build_hardware_reference_events(result)
        self._build_hardware_motion_segments(result)
        self._logger.info(
            "Parsed %s PWM events, %s hardware positions, %s hardware reference events, %s hardware segments, %s profiles, and %s warnings from %s",
            len(result.pwm_events),
            len(result.hardware_position_events),
            len(result.hardware_reference_events),
            len(result.hardware_motion_segments),
            len(result.axis_profiles),
            len(result.warnings),
            path,
        )
        return result

    def _parse_control_timestamp(self, path: Path, line_number: int, line: str):
        """Parse a timestamp-bearing transport line from a control log."""

        self._logger.debug("Checking control timestamp line %s", line_number)
        match = CONTROL_TIMESTAMP_PATTERN.match(line)
        if match is None:
            return None
        timestamp = parse_log_timestamp(match.group("timestamp"))
        if timestamp is None:
            self._logger.warning("Failed to parse control-log timestamp on %s:%s", path, line_number)
        return timestamp

    def _build_pwm_event(
        self,
        path: Path,
        line_number: int,
        line: str,
        current_timestamp,
    ) -> PWMEvent | None:
        """Convert one valid RUN or VEL line into a PWM event."""

        self._logger.debug("Parsing PWM line %s", line_number)
        match = CONTROL_PWM_PATTERN.match(line.strip())
        if match is None:
            return None
        try:
            pwm_raw_value = float(match.group("pwm"))
        except ValueError:
            self._logger.warning("Failed to parse PWM value on %s:%s", path, line_number)
            return None
        return PWMEvent(
            source_path=path,
            line_number=line_number,
            timestamp=current_timestamp,
            node_id=match.group("node"),
            axis=match.group("axis"),
            pwm_raw_value=pwm_raw_value,
            pwm_percent=normalize_pwm_percent(pwm_raw_value),
            direction=resolve_pwm_direction(pwm_raw_value),
            raw_line=line,
            command_type=match.group("command"),
            is_status_confirmation=match.group("status") is not None,
        )

    def _build_hardware_position_event(
        self,
        path: Path,
        line_number: int,
        line: str,
        current_timestamp,
    ) -> HardwarePositionEvent | None:
        """Convert one TPOS line into a hardware position event."""

        match = CONTROL_TPOS_PATTERN.match(line.strip())
        if match is None:
            return None
        raw_text = match.group("raw")
        raw_position = int(raw_text) if raw_text is not None else None
        axis = match.group("axis")
        kind_token = match.group("kind")
        position_kind = HARDWARE_POSITION_KIND_MAP.get(kind_token or "", "Target")
        is_reference_kind = position_kind in {"ZeroSensor", "ResetOrInit"}
        scale = AXIS_RAW_SCALE.get(axis)
        physical_position = (
            raw_position / scale
            if raw_position is not None
            and not is_reference_kind
            and scale not in {None, 0}
            else None
        )
        reference_raw_value = raw_position if is_reference_kind else None
        position_raw_value = None if is_reference_kind else raw_position
        node_id_text = match.group("node_id")
        return HardwarePositionEvent(
            source_path=path,
            line_number=line_number,
            timestamp=current_timestamp,
            node_id=int(node_id_text) if node_id_text else None,
            axis=axis,
            position_kind=position_kind,
            raw_position=position_raw_value,
            physical_position=physical_position,
            raw_line=line,
            reference_raw_value=reference_raw_value,
            hardware_status_value=reference_raw_value,
        )

    def _build_hardware_reference_events(self, result: DutyCycleLogFileResult) -> None:
        """Preserve TPOS Z/I reference evidence separately from motion segments."""

        for event in result.hardware_position_events:
            if event.position_kind not in {"ZeroSensor", "ResetOrInit"}:
                continue
            result.hardware_reference_events.append(
                HardwareReferenceEvidence(
                    source_path=event.source_path,
                    axis=event.axis,
                    evidence_type=event.position_kind,
                    timestamp=event.timestamp,
                    raw_value=event.reference_raw_value,
                    line_number=event.line_number,
                    line_text=event.raw_line,
                    match_status="UnmatchedHardwareReferenceEvidence",
                )
            )

    def _build_parse_warning(
        self,
        path: Path,
        line_number: int,
        line: str,
    ) -> ParseWarning | None:
        """Create a warning for malformed but relevant PWM lines."""

        self._logger.debug("Checking PWM line %s for parse warnings", line_number)
        if " TPOS" in line and "GETPOS" not in line and "[" in line and ":" in line:
            self._logger.warning("Malformed TPOS line at %s:%s", path, line_number)
            return ParseWarning(
                source_name="HardwarePosition",
                source_path=path,
                line_number=line_number,
                raw_line=line,
                message="Malformed or unsupported hardware TPOS line",
            )
        if not any(token in line for token in CONTROL_PWM_COMMANDS) or "[" not in line or ":" not in line:
            return None
        self._logger.warning("Malformed PWM line at %s:%s", path, line_number)
        return ParseWarning(
            source_name="PWM",
            source_path=path,
            line_number=line_number,
            raw_line=line,
            message="Malformed or unsupported PWM line",
        )

    def _propagate_file_times(self, result: DutyCycleLogFileResult) -> None:
        """Copy file-range metadata onto individual PWM events."""

        for event in result.pwm_events:
            event.source_file_start_time = result.file_start_time
            event.source_file_end_time = result.file_end_time

    def _mark_confirmed_events(self, result: DutyCycleLogFileResult) -> None:
        """Mark PWM events that are confirmed by a matching status line."""

        self._logger.debug("Marking confirmed PWM events for %s", result.source_path)
        grouped_confirmations: dict[tuple[str, str, float], bool] = {}
        for event in result.pwm_events:
            if event.is_status_confirmation:
                grouped_confirmations[(event.axis, event.command_type, event.pwm_raw_value)] = True
        for event in result.pwm_events:
            event.is_confirmed_by_status_line = grouped_confirmations.get(
                (event.axis, event.command_type, event.pwm_raw_value),
                False,
            )

    def _build_axis_profiles(self, result: DutyCycleLogFileResult) -> None:
        """Aggregate per-axis PWM profiles for one control-log file."""

        self._logger.debug("Building PWM profiles for %s", result.source_path)
        grouped_events: dict[str, list[PWMEvent]] = defaultdict(list)
        for event in result.pwm_events:
            grouped_events[event.axis].append(event)
        for axis, events in grouped_events.items():
            raw_values = self._unique_raw_values(events)
            percent_values = self._unique_percent_values(events)
            direction_values = self._unique_direction_values(events)
            percent_counts = Counter(event.pwm_percent for event in events)
            selected_percent = percent_counts.most_common(1)[0][0] if percent_counts else None
            conflict = len(percent_values) > 1
            direction_changed = len(direction_values) > 1
            notes = ""
            conflict_reason = ""
            if conflict:
                percent_values_text = ", ".join(
                    str(int(value)) if float(value).is_integer() else str(value)
                    for value in percent_values
                )
                conflict_reason = (
                    f"Conflicting normalized PWM percentages in file for axis {axis}: {percent_values_text}"
                )
                notes = conflict_reason
            elif direction_changed:
                notes = "Direction changed within source file; normalized PWM percent is consistent."
            result.axis_profiles[axis] = AxisPWMProfile(
                source_path=result.source_path,
                axis=axis,
                pwm_percent=selected_percent,
                pwm_percent_values=percent_values,
                pwm_raw_values=raw_values,
                direction_values=direction_values,
                first_seen_time=self._min_timestamp(events),
                last_seen_time=self._max_timestamp(events),
                source_lines=[event.line_number for event in events],
                source_line_texts=[event.raw_line for event in events],
                conflict=conflict,
                direction_changed=direction_changed,
                conflict_reason=conflict_reason,
                notes=notes,
                events=list(events),
            )

    def _build_hardware_motion_segments(self, result: DutyCycleLogFileResult) -> None:
        """Build hardware S/E motion segments from parsed TPOS events."""

        pending_by_axis: dict[str, HardwareMotionSegment] = {}
        latest_target_by_axis: dict[str, HardwarePositionEvent] = {}
        events = sorted(
            result.hardware_position_events,
            key=lambda item: (
                item.timestamp is None,
                item.timestamp,
                item.line_number,
            ),
        )
        for event in events:
            if event.position_kind == "Target":
                latest_target_by_axis[event.axis] = event
                pending = pending_by_axis.get(event.axis)
                if pending is not None and pending.raw_target_position is None:
                    if self._target_is_fresh_for_start(event, pending.start_time):
                        self._attach_target(pending, event)
                    else:
                        pending.notes = self._merge_notes(
                            pending.notes,
                            "Hardware target TPOS was not attached because it was stale.",
                        )
                continue
            if event.position_kind == "Start":
                previous = pending_by_axis.get(event.axis)
                if previous is not None:
                    previous.match_status = "HardwareSegmentIncomplete"
                    previous.notes = self._merge_notes(previous.notes, "Closed by a new hardware TPOS Start before an End.")
                    result.hardware_motion_segments.append(previous)
                segment = self._segment_from_start(event)
                target = latest_target_by_axis.get(event.axis)
                if target is not None and self._target_is_fresh_for_start(target, segment.start_time):
                    self._attach_target(segment, target)
                elif target is not None:
                    segment.notes = self._merge_notes(
                        segment.notes,
                        "Hardware target TPOS was not attached because it was stale.",
                    )
                latest_target_by_axis.pop(event.axis, None)
                pending_by_axis[event.axis] = segment
                continue
            if event.position_kind == "End":
                pending = pending_by_axis.pop(event.axis, None)
                if pending is None:
                    result.hardware_motion_segments.append(self._unmatched_end_segment(event))
                    continue
                self._attach_end(pending, event)
                result.hardware_motion_segments.append(pending)
        for segment in pending_by_axis.values():
            segment.match_status = "HardwareSegmentIncomplete"
            segment.notes = self._merge_notes(segment.notes, "Hardware TPOS Start had no following End.")
            result.hardware_motion_segments.append(segment)

    def _segment_from_start(self, event: HardwarePositionEvent) -> HardwareMotionSegment:
        """Create a pending hardware segment from a Start event."""

        return HardwareMotionSegment(
            source_path=event.source_path,
            axis=event.axis,
            start_time=event.timestamp,
            raw_start_position=event.raw_position,
            hardware_start_position=event.physical_position,
            start_line_number=event.line_number,
            start_line_text=event.raw_line,
            match_status="HardwareSegmentStarted",
        )

    def _unmatched_end_segment(self, event: HardwarePositionEvent) -> HardwareMotionSegment:
        """Create a diagnostic segment for an End with no preceding Start."""

        return HardwareMotionSegment(
            source_path=event.source_path,
            axis=event.axis,
            end_time=event.timestamp,
            raw_end_position=event.raw_position,
            hardware_end_position=event.physical_position,
            end_line_number=event.line_number,
            end_line_text=event.raw_line,
            match_status="UnmatchedHardwareEnd",
            notes="Hardware TPOS End appeared without a preceding Start.",
        )

    def _attach_target(self, segment: HardwareMotionSegment, event: HardwarePositionEvent) -> None:
        """Attach a hardware target record to a segment."""

        segment.target_time = event.timestamp
        segment.raw_target_position = event.raw_position
        segment.hardware_target_position = event.physical_position
        segment.target_line_number = event.line_number
        segment.target_line_text = event.raw_line
        self._recompute_hardware_distances(segment)

    def _target_is_fresh_for_start(
        self,
        target: HardwarePositionEvent,
        start_time,
    ) -> bool:
        """Return whether a target TPOS is close enough to belong to a segment Start."""

        if target.timestamp is None or start_time is None:
            return False
        if target.timestamp > start_time:
            return False
        delta_ms = (start_time - target.timestamp).total_seconds() * 1000.0
        return delta_ms <= HARDWARE_TARGET_TO_START_MAX_DELTA_MS

    def _attach_end(self, segment: HardwareMotionSegment, event: HardwarePositionEvent) -> None:
        """Attach a hardware End record and finish distance calculations."""

        segment.end_time = event.timestamp
        segment.raw_end_position = event.raw_position
        segment.hardware_end_position = event.physical_position
        segment.end_line_number = event.line_number
        segment.end_line_text = event.raw_line
        segment.match_status = "HardwareSegmentComplete"
        self._recompute_hardware_distances(segment)

    def _recompute_hardware_distances(self, segment: HardwareMotionSegment) -> None:
        """Compute actual and commanded hardware distances for a segment."""

        if segment.raw_start_position is not None and segment.raw_end_position is not None:
            scale = AXIS_RAW_SCALE.get(segment.axis)
            if scale not in {None, 0}:
                segment.hardware_actual_distance = abs(
                    segment.raw_end_position - segment.raw_start_position
                ) / abs(scale)
        if segment.hardware_start_position is not None and segment.hardware_target_position is not None:
            segment.hardware_commanded_distance = abs(
                segment.hardware_target_position - segment.hardware_start_position
            )

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Append one note if needed."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"

    def _unique_raw_values(self, events: list[PWMEvent]) -> list[float]:
        """Return the stable unique list of raw PWM values for one axis profile."""

        return sorted({event.pwm_raw_value for event in events})

    def _unique_percent_values(self, events: list[PWMEvent]) -> list[float]:
        """Return the sorted unique normalized PWM percentages for one axis profile."""

        return sorted({event.pwm_percent for event in events})

    def _unique_direction_values(self, events: list[PWMEvent]) -> list[str]:
        """Return the sorted unique PWM directions for one axis profile."""

        return sorted({event.direction for event in events})

    def _min_timestamp(self, events: list[PWMEvent]):
        """Return the earliest timestamp among the timed PWM events."""

        timed_events = [event.timestamp for event in events if event.timestamp is not None]
        return min(timed_events) if timed_events else None

    def _max_timestamp(self, events: list[PWMEvent]):
        """Return the latest timestamp among the timed PWM events."""

        timed_events = [event.timestamp for event in events if event.timestamp is not None]
        return max(timed_events) if timed_events else None
