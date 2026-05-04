"""Parser for one control-log file containing PWM-related commands."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from pathlib import Path

from .config import CONTROL_PWM_COMMANDS, CONTROL_PWM_PATTERN, CONTROL_TIMESTAMP_PATTERN
from .file_loader import TextFileLoader
from .models import AxisPWMProfile, DutyCycleLogFileResult, PWMEvent, ParseWarning
from .time_utils import normalize_pwm_percent, parse_log_timestamp, resolve_pwm_direction


class DutyCycleLogParser:
    """Parses PWM values from a single control-log file."""

    def __init__(self, loader: TextFileLoader, logger: logging.Logger | None = None) -> None:
        """Initialize the parser with a shared file loader."""

        self._loader = loader
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def parse(
        self,
        file_path: Path | str,
        preferred_encoding: str | None = None,
    ) -> DutyCycleLogFileResult:
        """Parse one control log file and return PWM records plus file metadata."""

        path = Path(file_path)
        self._logger.info("Parsing PWM control log %s", path)
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
            warning = self._build_parse_warning(path, line_number, line)
            if warning is not None:
                result.warnings.append(warning)
        self._propagate_file_times(result)
        self._mark_confirmed_events(result)
        self._build_axis_profiles(result)
        self._logger.info(
            "Parsed %s PWM events, %s profiles, and %s warnings from %s",
            len(result.pwm_events),
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

    def _build_parse_warning(
        self,
        path: Path,
        line_number: int,
        line: str,
    ) -> ParseWarning | None:
        """Create a warning for malformed but relevant PWM lines."""

        self._logger.debug("Checking PWM line %s for parse warnings", line_number)
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
