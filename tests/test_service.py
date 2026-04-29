"""Regression tests for the boundary-aware TXT-plus-log-folder axis activity analyzer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from backend.log_axis_activity_analyzer.config import (
    DEFAULT_EVENT_RULES,
    DETAIL_COLUMNS,
    STATUS_INITIALIZATION_FAILED,
    STATUS_MATCHED,
    STATUS_UNMATCHED_END,
    STATUS_UNMATCHED_START,
)
from backend.log_axis_activity_analyzer.duty_cycle_associator import DutyCycleAssociator
from backend.log_axis_activity_analyzer.file_loader import TextFileLoader
from backend.log_axis_activity_analyzer.log_a_parser import MainLogParser
from backend.log_axis_activity_analyzer.log_b_parser import DutyCycleLogParser
from backend.log_axis_activity_analyzer.log_folder_scanner import LogFolderScanner
from backend.log_axis_activity_analyzer.matcher import EventMatcher
from backend.log_axis_activity_analyzer.models import ActivityRecord
from backend.log_axis_activity_analyzer.service import LogAnalysisService
from backend.log_axis_activity_analyzer.time_utils import calculate_duration_values, parse_log_timestamp
from backend.log_axis_activity_analyzer.validation import ActivityValidator


def _write_lines(path: Path, lines: list[str]) -> Path:
    """Write helper text content with trailing newlines preserved."""

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _parse_main_log(tmp_path: Path, lines: list[str]):
    """Build a parsed main-log result from synthetic lines."""

    path = _write_lines(tmp_path / "sample.txt", lines)
    parser = MainLogParser(TextFileLoader())
    return parser.parse(path)


def test_parse_log_timestamp_preserves_milliseconds() -> None:
    """Millisecond precision should survive timestamp parsing."""

    parsed = parse_log_timestamp("2026-03-31 09:39:40:554")
    assert parsed == datetime(2026, 3, 31, 9, 39, 40, 554000)


def test_calculate_duration_values_returns_expected_result() -> None:
    """Duration must be computed as end minus start with millisecond precision."""

    start_time = datetime(2026, 3, 31, 9, 39, 40, 554000)
    end_time = datetime(2026, 3, 31, 9, 39, 47, 373000)

    duration_ms, duration_s = calculate_duration_values(start_time, end_time)

    assert duration_ms == 6819
    assert duration_s == 6.819


def test_valid_same_axis_match_produces_expected_duration(tmp_path: Path) -> None:
    """A same-axis start/end pair should match with the correct rule and duration."""

    parse_result = _parse_main_log(
        tmp_path,
        [
            "2026-03-31 09:39:40:554 MCU   @[Y] start clearing: -19.50",
            "2026-03-31 09:39:47:373 MCU   @[Y] motor cleared",
            "2026-03-31 09:39:47:373 MCU   @[Y] min: -29.51",
        ],
    )

    matcher = EventMatcher(DEFAULT_EVENT_RULES)
    records = ActivityValidator().validate(matcher.build_activity_records(parse_result.timeline))

    matched = [record for record in records if record.match_status == STATUS_MATCHED]
    assert len(matched) == 1
    record = matched[0]
    assert record.axis == "Y"
    assert record.rule_id == "clear_motor"
    assert record.duration_ms == 6819
    assert record.duration_s == 6.819
    assert record.status == STATUS_MATCHED


def test_different_axis_events_do_not_match(tmp_path: Path) -> None:
    """A start on one axis must not match an end on another axis."""

    parse_result = _parse_main_log(
        tmp_path,
        [
            "2026-03-31 09:39:40:554 MCU   @[Y] start clearing: -19.50",
            "2026-03-31 09:39:47:373 MCU   @[Z] motor cleared",
        ],
    )

    matcher = EventMatcher(DEFAULT_EVENT_RULES)
    records = ActivityValidator().validate(matcher.build_activity_records(parse_result.timeline))

    assert any(record.match_status == STATUS_UNMATCHED_START and record.axis == "Y" for record in records)
    assert any(record.match_status == STATUS_UNMATCHED_END and record.axis == "Z" for record in records)
    assert not any(record.match_status == STATUS_MATCHED for record in records)


def test_initialization_failure_closes_pending_start(tmp_path: Path) -> None:
    """Initialization failure must close the stale start before a later successful attempt."""

    parse_result = _parse_main_log(
        tmp_path,
        [
            "2026-04-10 08:37:43:959 MCU   @[Z] start clearing: -50.00",
            "2026-04-10 08:38:14:121 MCU   @[ERR] [Z] cannot reach the target (30 seconds timeout). initialization failed.",
            "2026-04-10 09:20:23:541 MCU   @[Z] start clearing: -50.00",
            "2026-04-10 09:20:46:317 MCU   @[Z] motor cleared",
            "2026-04-10 09:20:46:317 MCU   @[Z] min: -50.00",
        ],
    )

    matcher = EventMatcher(DEFAULT_EVENT_RULES)
    records = ActivityValidator().validate(matcher.build_activity_records(parse_result.timeline))

    stale_rows = [
        record
        for record in records
        if record.axis == "Z" and record.start_time == datetime(2026, 4, 10, 8, 37, 43, 959000)
    ]
    assert len(stale_rows) == 1
    assert stale_rows[0].match_status == STATUS_INITIALIZATION_FAILED
    assert stale_rows[0].end_time is None

    corrected = [
        record
        for record in records
        if record.axis == "Z"
        and record.start_time == datetime(2026, 4, 10, 9, 20, 23, 541000)
        and record.end_time == datetime(2026, 4, 10, 9, 20, 46, 317000)
    ]
    assert len(corrected) == 1
    assert corrected[0].match_status == STATUS_MATCHED
    assert corrected[0].duration_ms == 22776
    assert corrected[0].duration_s == 22.776

    assert not any(
        record.match_status == STATUS_MATCHED
        and record.axis == "Z"
        and record.start_time == datetime(2026, 4, 10, 8, 37, 43, 959000)
        and record.end_time == datetime(2026, 4, 10, 9, 20, 46, 317000)
        for record in records
    )


def test_new_initialization_closes_old_pending_start(tmp_path: Path) -> None:
    """A new initialization boundary must flush any pending starts from the prior attempt."""

    parse_result = _parse_main_log(
        tmp_path,
        [
            "2026-04-10 08:37:43:959 MCU   @[Z] start clearing: -50.00",
            "2026-04-10 08:38:51:254 User  @on_startInitRobot_clicked",
            "2026-04-10 09:20:46:317 MCU   @[Z] motor cleared",
        ],
    )

    matcher = EventMatcher(DEFAULT_EVENT_RULES)
    records = ActivityValidator().validate(matcher.build_activity_records(parse_result.timeline))

    assert any(
        record.match_status == "Closed By Boundary"
        and record.axis == "Z"
        and record.start_time == datetime(2026, 4, 10, 8, 37, 43, 959000)
        for record in records
    )
    assert any(
        record.match_status == STATUS_UNMATCHED_END
        and record.axis == "Z"
        and record.end_time == datetime(2026, 4, 10, 9, 20, 46, 317000)
        for record in records
    )


def test_long_duration_is_rejected(tmp_path: Path) -> None:
    """A long-gap candidate pair must not survive as a normal matched row."""

    parse_result = _parse_main_log(
        tmp_path,
        [
            "2026-04-10 08:37:43:959 MCU   @[Z] start clearing: -50.00",
            "2026-04-10 09:20:46:317 MCU   @[Z] motor cleared",
        ],
    )

    matcher = EventMatcher(DEFAULT_EVENT_RULES)
    records = ActivityValidator().validate(matcher.build_activity_records(parse_result.timeline))

    assert not any(record.match_status == STATUS_MATCHED for record in records)
    assert any(record.status == "Duration Too Long" for record in records)
    assert not any(record.duration_ms == 2582358 and record.status == STATUS_MATCHED for record in records)


def test_pwm_signed_value_is_normalized(tmp_path: Path) -> None:
    """Signed PWM values should preserve raw sign while normalizing the percent magnitude."""

    path = _write_lines(
        tmp_path / "signed.log",
        [
            "2026-04-10 08:37:32:000 [OUT] sample",
            "                              [N6:H] RUN 255 176 (-80)",
            "2026-04-10 08:37:33:000 [IN ] sample",
            "                              [N6:H] RUN 'S' 255 176 (-80)",
        ],
    )

    result = DutyCycleLogParser(TextFileLoader()).parse(path)

    assert len(result.pwm_events) == 2
    event = result.pwm_events[0]
    assert event.axis == "H"
    assert event.pwm_raw_value == -80
    assert event.pwm_percent == 80
    assert event.direction == "Reverse"
    assert event.is_confirmed_by_status_line is True


def test_log_folder_scanner_keeps_per_file_pwm_profiles(tmp_path: Path) -> None:
    """Different files should retain separate PWM profiles for the same axis."""

    folder = tmp_path / "logs"
    folder.mkdir()
    _write_lines(
        folder / "one.log",
        [
            "2026-01-01 00:00:01:000 [OUT] sample",
            "                              [N4:Y] RUN 0 60 (60)",
            "2026-01-01 00:00:02:000 [IN ] sample",
            "                              [N4:Y] RUN 'S' 0 60 (60)",
        ],
    )
    _write_lines(
        folder / "two.log",
        [
            "2026-01-01 00:05:01:000 [OUT] sample",
            "                              [N4:Y] RUN 0 80 (80)",
            "2026-01-01 00:05:02:000 [IN ] sample",
            "                              [N4:Y] RUN 'S' 0 80 (80)",
        ],
    )

    scanner = LogFolderScanner(DutyCycleLogParser(TextFileLoader()))
    result = scanner.scan(folder)

    assert len(result.files) == 2
    file_profiles = {file_result.source_path.name: file_result.axis_profiles["Y"] for file_result in result.files}
    assert file_profiles["one.log"].pwm_percent == 60
    assert file_profiles["two.log"].pwm_percent == 80
    assert file_profiles["one.log"].pwm_raw_values == [60]
    assert file_profiles["two.log"].pwm_raw_values == [80]


def test_pwm_association_prefers_containing_log_file(tmp_path: Path) -> None:
    """PWM association should choose the relevant containing log file, not a faraway global value."""

    folder = tmp_path / "logs"
    folder.mkdir()
    _write_lines(
        folder / "near.log",
        [
            "2026-01-01 00:00:01:000 [OUT] sample",
            "                              [N4:Y] RUN 0 60 (60)",
            "2026-01-01 00:00:02:000 [IN ] sample",
            "                              [N4:Y] RUN 'S' 0 60 (60)",
            "2026-01-01 00:00:10:000 [OUT] sample",
        ],
    )
    _write_lines(
        folder / "far.log",
        [
            "2026-01-01 00:10:01:000 [OUT] sample",
            "                              [N4:Y] RUN 0 80 (80)",
            "2026-01-01 00:10:02:000 [IN ] sample",
            "                              [N4:Y] RUN 'S' 0 80 (80)",
            "2026-01-01 00:10:10:000 [OUT] sample",
        ],
    )

    files = LogFolderScanner(DutyCycleLogParser(TextFileLoader())).scan(folder).files
    record = ActivityRecord(
        axis="Y",
        rule_id="clear_motor",
        start_event="start clearing",
        end_event="motor cleared",
        start_time=datetime(2026, 1, 1, 0, 0, 5),
        end_time=datetime(2026, 1, 1, 0, 0, 6),
        match_status=STATUS_MATCHED,
    )

    ActivityValidator().validate(DutyCycleAssociator().attach([record], files))

    assert record.pwm_percent == 60
    assert record.pwm_source_file == "near.log"
    assert record.pwm_match_status == "MatchedByContainingLogFile"


def test_excel_export_validation_with_synthetic_service_run(tmp_path: Path) -> None:
    """A synthetic end-to-end run should produce workbook sheets and numeric duration values."""

    txt_path = _write_lines(
        tmp_path / "sample.txt",
        [
            "2026-03-31 09:39:40:554 MCU   @[Y] start clearing: -19.50",
            "2026-03-31 09:39:47:373 MCU   @[Y] motor cleared",
            "2026-03-31 09:39:47:373 MCU   @[Y] min: -29.51",
        ],
    )
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "initialization.log",
        [
            "2026-03-31 09:39:32:000 [OUT] sample",
            "                              [N4:Y] RUN 0 80 (80)",
            "2026-03-31 09:39:33:000 [IN ] sample",
            "                              [N4:Y] RUN 'S' 0 80 (80)",
            "2026-03-31 09:39:34:000 [OUT] sample",
            "                              [N6:H] RUN 255 176 (-80)",
            "2026-03-31 09:39:35:000 [IN ] sample",
            "                              [N6:H] RUN 'S' 255 176 (-80)",
            "2026-03-31 09:39:50:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "analysis.xlsx"

    result = LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
    )

    assert result.detail_count > 0
    workbook = load_workbook(output_path, data_only=True)
    assert {"Details", "Summary", "PWM Sources"} <= set(workbook.sheetnames)

    details_sheet = workbook["Details"]
    headers = [cell.value for cell in details_sheet[1]]
    header_index = {header: index for index, header in enumerate(headers)}
    assert headers == DETAIL_COLUMNS

    rows = list(details_sheet.iter_rows(min_row=2, values_only=True))
    assert rows
    target_row = next(
        row
        for row in rows
        if row[header_index["Axis"]] == "Y"
        and row[header_index["Start Event"]] == "start clearing"
        and row[header_index["End Event"]] == "motor cleared"
    )
    assert isinstance(target_row[header_index["Duration (ms)"]], int)
    assert target_row[header_index["Duration (ms)"]] == 6819
    assert target_row[header_index["Duration (s)"]] == 6.819
    assert target_row[header_index["PWM (%)"]] == 80
    assert target_row[header_index["PWM Raw Value"]] == 80
    assert target_row[header_index["PWM Source File"]] == "initialization.log"
    assert target_row[header_index["PWM Match Status"]] == "MatchedByContainingLogFile"

    pwm_sources_sheet = workbook["PWM Sources"]
    pwm_rows = list(pwm_sources_sheet.iter_rows(min_row=2, values_only=True))
    negative_row = next(row for row in pwm_rows if row[3] == "H")
    assert negative_row[4] == 80
    assert negative_row[5] == -80
    assert negative_row[6] == "Reverse"
