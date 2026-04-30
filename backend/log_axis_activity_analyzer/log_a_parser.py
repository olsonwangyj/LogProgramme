"""Parser for the full MCU activity TXT log, including workflow boundaries."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .config import (
    AXIS_MARKER_PATTERN,
    BOUNDARY_AXIS_PATTERN,
    BOUNDARY_PATTERNS,
    BOUNDARY_RELEVANT_TOKENS,
    DIAGNOSTIC_AMX_PARTIALLY_CORRUPTED_PATTERN,
    DIAGNOSTIC_NODE_RESPONSE_TIMEOUT_PATTERN,
    DIAGNOSTIC_PARTIAL_AMX_AMENDED_PATTERN,
    DIAGNOSTIC_SENSOR_CUT_PATTERN,
    DIAGNOSTIC_SEVERITY_PATTERN,
    INLINE_VALUE_PATTERN,
    MAIN_LOG_AXIS_EVENT_PATTERN,
    MAIN_LOG_TIMESTAMP_PATTERN,
    NODE_TO_AXIS,
)
from .file_loader import TextFileLoader
from .models import AxisLogEvent, BoundaryEvent, DiagnosticEvent, MainLogParseResult, ParseWarning
from .time_utils import parse_log_timestamp


class MainLogParser:
    """Parses axis activity lines and workflow boundaries from the main runtime TXT log."""

    def __init__(self, loader: TextFileLoader, logger: logging.Logger | None = None) -> None:
        """Initialize the parser with a shared file loader."""

        self._loader = loader
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._compiled_boundary_rules = [
            (rule, re.compile(rule.pattern, re.IGNORECASE))
            for rule in BOUNDARY_PATTERNS
        ]

    def parse(
        self,
        file_path: Path | str,
        preferred_encoding: str | None = None,
    ) -> MainLogParseResult:
        """Parse the full main TXT log and return axis events, boundaries, timeline, and warnings."""

        path = Path(file_path)
        self._logger.info("Parsing main TXT log %s", path)
        iterator, encoding = self._loader.iter_lines(path, preferred_encoding)
        result = MainLogParseResult(encoding_used=encoding)
        ordinal = 0
        for line_number, line in iterator:
            parsed_event = self._build_timeline_event(path, line_number, ordinal, line)
            if parsed_event is not None:
                result.timeline.append(parsed_event)
                if isinstance(parsed_event, AxisLogEvent):
                    result.events.append(parsed_event)
                elif isinstance(parsed_event, BoundaryEvent):
                    result.boundary_events.append(parsed_event)
                else:
                    result.diagnostics.append(parsed_event)
                ordinal += 1
                continue
            warning = self._build_parse_warning(path, line_number, line)
            if warning is not None:
                result.warnings.append(warning)
        self._logger.info(
            "Parsed %s axis events, %s boundary events, %s diagnostics, and %s warnings from %s",
            len(result.events),
            len(result.boundary_events),
            len(result.diagnostics),
            len(result.warnings),
            path,
        )
        return result

    def _build_timeline_event(
        self,
        path: Path,
        line_number: int,
        ordinal: int,
        line: str,
    ) -> AxisLogEvent | BoundaryEvent | DiagnosticEvent | None:
        """Convert one relevant line into either an axis event or a boundary event."""

        self._logger.debug("Parsing main TXT line %s", line_number)
        match = MAIN_LOG_TIMESTAMP_PATTERN.match(line)
        if match is None:
            return None
        timestamp = parse_log_timestamp(match.group("timestamp"))
        if timestamp is None:
            self._logger.warning("Failed to parse TXT timestamp on %s:%s", path, line_number)
            return None
        content = match.group("content").strip()
        axis_event = self._build_axis_event(path, line_number, ordinal, timestamp, content, line)
        if axis_event is not None:
            return axis_event
        boundary_event = self._build_boundary_event(path, line_number, ordinal, timestamp, content, line)
        if boundary_event is not None:
            return boundary_event
        diagnostic_event = self._build_diagnostic_event(path, line_number, ordinal, timestamp, content, line)
        if diagnostic_event is not None:
            return diagnostic_event
        return None

    def _build_axis_event(
        self,
        path: Path,
        line_number: int,
        ordinal: int,
        timestamp,
        content: str,
        raw_line: str,
    ) -> AxisLogEvent | None:
        """Convert one valid axis-activity line into an event model."""

        match = MAIN_LOG_AXIS_EVENT_PATTERN.match(content)
        if match is None:
            return None
        message = match.group("message").strip()
        inline_value = self._extract_inline_value(message)
        return AxisLogEvent(
            source_path=path,
            line_number=line_number,
            ordinal=ordinal,
            timestamp=timestamp,
            axis=match.group("axis"),
            message=message,
            raw_line=raw_line,
            inline_value=inline_value,
        )

    def _build_boundary_event(
        self,
        path: Path,
        line_number: int,
        ordinal: int,
        timestamp,
        content: str,
        raw_line: str,
    ) -> BoundaryEvent | None:
        """Convert one boundary or failure line into a boundary event."""

        for rule, pattern in self._compiled_boundary_rules:
            match = pattern.search(content)
            if match is None:
                continue
            axis = self._resolve_boundary_axis(match, content)
            return BoundaryEvent(
                source_path=path,
                line_number=line_number,
                ordinal=ordinal,
                timestamp=timestamp,
                boundary_type=rule.boundary_type,
                raw_line=raw_line,
                axis=axis,
                message=content,
                flush_pending=rule.flush_pending,
                flush_scope=rule.flush_scope,
                close_pending_when_seen=rule.close_pending_when_seen,
            )
        return None

    def _build_diagnostic_event(
        self,
        path: Path,
        line_number: int,
        ordinal: int,
        timestamp,
        content: str,
        raw_line: str,
    ) -> DiagnosticEvent | None:
        """Convert recognized ERR/WRN/INFO diagnostic lines into structured records."""

        amx_corrupted_match = DIAGNOSTIC_AMX_PARTIALLY_CORRUPTED_PATTERN.search(content)
        if amx_corrupted_match is not None:
            return DiagnosticEvent(
                source_path=path,
                line_number=line_number,
                ordinal=ordinal,
                timestamp=timestamp,
                severity="AMD",
                diagnostic_type="AMXPartiallyCorrupted",
                axis=None,
                node_id=None,
                message=content,
                raw_line=raw_line,
            )

        partial_amx_match = DIAGNOSTIC_PARTIAL_AMX_AMENDED_PATTERN.search(content)
        if partial_amx_match is not None:
            node_id = int(partial_amx_match.group("node_id"))
            return DiagnosticEvent(
                source_path=path,
                line_number=line_number,
                ordinal=ordinal,
                timestamp=timestamp,
                severity="AMD",
                diagnostic_type="PartialAMXAmended",
                axis=NODE_TO_AXIS.get(node_id),
                node_id=node_id,
                message=content,
                raw_line=raw_line,
            )

        node_timeout_match = DIAGNOSTIC_NODE_RESPONSE_TIMEOUT_PATTERN.search(content)
        if node_timeout_match is not None:
            severity = node_timeout_match.group("severity").upper()
            return DiagnosticEvent(
                source_path=path,
                line_number=line_number,
                ordinal=ordinal,
                timestamp=timestamp,
                severity=severity,
                diagnostic_type="NodeResponseTimeout",
                axis=None,
                node_id=int(node_timeout_match.group("node_id")),
                message=content,
                raw_line=raw_line,
            )

        sensor_cut_match = DIAGNOSTIC_SENSOR_CUT_PATTERN.search(content)
        if sensor_cut_match is not None:
            severity = sensor_cut_match.group("severity").upper()
            return DiagnosticEvent(
                source_path=path,
                line_number=line_number,
                ordinal=ordinal,
                timestamp=timestamp,
                severity=severity,
                diagnostic_type="SensorCut",
                axis=sensor_cut_match.group("axis").upper(),
                node_id=None,
                message=content,
                raw_line=raw_line,
                flush_pending=True,
                flush_scope="axis",
            )

        severity_match = DIAGNOSTIC_SEVERITY_PATTERN.search(content)
        if severity_match is None:
            return None
        severity = severity_match.group("severity").upper()
        diagnostic_type = {
            "ERR": "GenericError",
            "WRN": "GenericWarning",
            "INFO": "GenericInfo",
        }.get(severity, "GenericDiagnostic")
        return DiagnosticEvent(
            source_path=path,
            line_number=line_number,
            ordinal=ordinal,
            timestamp=timestamp,
            severity=severity,
            diagnostic_type=diagnostic_type,
            axis=self._extract_warning_axis(content) or None,
            node_id=None,
            message=content,
            raw_line=raw_line,
        )

    def _build_parse_warning(
        self,
        path: Path,
        line_number: int,
        line: str,
    ) -> ParseWarning | None:
        """Create a warning for malformed but relevant main-log lines."""

        self._logger.debug("Checking main TXT line %s for parse warnings", line_number)
        match = MAIN_LOG_TIMESTAMP_PATTERN.match(line)
        timestamp = parse_log_timestamp(match.group("timestamp")) if match is not None else None
        content = match.group("content").strip() if match is not None else line.strip()
        if not self._looks_relevant(content):
            return None
        self._logger.warning("Malformed or unsupported main-log line at %s:%s", path, line_number)
        return ParseWarning(
            source_name="TXT",
            source_path=path,
            line_number=line_number,
            raw_line=line,
            message="Malformed or unsupported main-log activity/boundary line",
            axis=self._extract_warning_axis(content),
            timestamp=timestamp,
        )

    def _looks_relevant(self, content: str) -> bool:
        """Return whether a line is relevant enough to report when parsing fails."""

        return (
            AXIS_MARKER_PATTERN.search(content) is not None
            or DIAGNOSTIC_SEVERITY_PATTERN.search(content) is not None
            or any(
                token in content
                for token in BOUNDARY_RELEVANT_TOKENS
            )
        )

    def _extract_warning_axis(self, content: str) -> str:
        """Extract the most relevant axis marker for a warning row when available."""

        axis_match = AXIS_MARKER_PATTERN.search(content)
        if axis_match and len(axis_match.group("axis")) == 1:
            return axis_match.group("axis")
        boundary_match = BOUNDARY_AXIS_PATTERN.search(content)
        if boundary_match:
            return boundary_match.group("axis")
        return ""

    def _resolve_boundary_axis(self, match: re.Match[str], content: str) -> str | None:
        """Resolve the axis attached to a boundary event when present."""

        axis = match.groupdict().get("axis")
        if axis:
            return axis
        boundary_match = BOUNDARY_AXIS_PATTERN.search(content)
        if boundary_match:
            return boundary_match.group("axis")
        return None

    def _extract_inline_value(self, message: str) -> float | None:
        """Extract a trailing numeric value from an activity message when present."""

        self._logger.debug("Extracting inline numeric value from %s", message)
        match = INLINE_VALUE_PATTERN.search(message)
        if match is None:
            return None
        try:
            return float(match.group("value"))
        except ValueError:
            self._logger.warning("Failed to parse inline value from %s", message)
            return None
