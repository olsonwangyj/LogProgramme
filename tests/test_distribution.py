"""Tests for normal distribution analysis, charts, and workbook export."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import load_workbook

from backend.log_axis_activity_analyzer.chart_generator import NormalDistributionChartGenerator
from backend.log_axis_activity_analyzer.config import (
    DEFAULT_EVENT_RULES,
    DISTRIBUTION_CHART_BLOCK_HEIGHT,
    DISTRIBUTION_SUMMARY_COLUMNS,
    DURATION_STATUS_VALID,
    LOG_COVERAGE_GAPS_COLUMNS,
    LOG_COVERAGE_SUMMARY_COLUMNS,
    PWM_STATUS_LATEST_BEFORE_TOO_FAR,
    PWM_STATUS_MATCHED_CONTAINING,
    PWM_STATUS_MATCHED_NEAREST,
    PWM_STATUS_MATCHED_NEAREST_FUTURE,
    STATUS_MATCHED,
)
from backend.log_axis_activity_analyzer.distribution import DistributionAnalyzer
from backend.log_axis_activity_analyzer.file_loader import TextFileLoader
from backend.log_axis_activity_analyzer.log_a_parser import MainLogParser
from backend.log_axis_activity_analyzer.matcher import EventMatcher
from backend.log_axis_activity_analyzer.models import ActivityRecord
from backend.log_axis_activity_analyzer.service import LogAnalysisService
from backend.log_axis_activity_analyzer.validation import ActivityValidator


def _write_lines(path: Path, lines: list[str]) -> Path:
    """Write helper text content with trailing newlines preserved."""

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _record(
    *,
    seconds: float = 10.0,
    txt_offset: int = 0,
    axis: str = "Z",
    pwm_percent: float = 80,
    start_value: float | None = -50.0,
    end_value: float | None = None,
    rule_id: str = "clear_motor",
    start_event: str = "start clearing",
    end_event: str = "motor cleared",
    movement_start_position: float | None = 0.0,
    movement_target_position: float | None = None,
    movement_end_position: float | None = None,
    movement_commanded_distance: float | None = None,
    movement_actual_distance: float | None = None,
    movement_distance: float | None = None,
    movement_distance_source: str = "CommandTargetPosition",
    movement_distance_method: str = "KnownStartPositionToTarget",
    pwm_match_status: str = PWM_STATUS_MATCHED_CONTAINING,
) -> ActivityRecord:
    """Build a valid matched activity record for distribution tests."""

    start_time = datetime(2026, 1, 1, 0, 0, 0) + timedelta(seconds=txt_offset)
    end_time = start_time + timedelta(seconds=seconds)
    target_position = movement_target_position if movement_target_position is not None else start_value
    if movement_commanded_distance is None and movement_start_position is not None and target_position is not None:
        movement_commanded_distance = abs(target_position - movement_start_position)
    if movement_actual_distance is None and movement_start_position is not None and movement_end_position is not None:
        movement_actual_distance = abs(movement_end_position - movement_start_position)
    if movement_distance is None:
        movement_distance = movement_actual_distance if movement_actual_distance is not None else movement_commanded_distance
    if movement_actual_distance is not None:
        movement_distance_source = "ActualEndPosition"
        movement_distance_method = "KnownStartPositionToActualEnd"
    return ActivityRecord(
        axis=axis,
        rule_id=rule_id,
        event_type=start_event,
        start_event=start_event,
        end_event=end_event,
        start_time=start_time,
        end_time=end_time,
        duration_ms=int(seconds * 1000),
        duration_s=seconds,
        start_value=start_value,
        end_value=end_value,
        movement_start_position=movement_start_position,
        movement_target_position=target_position,
        movement_end_position=movement_end_position,
        movement_commanded_distance=movement_commanded_distance,
        movement_actual_distance=movement_actual_distance,
        movement_distance=movement_distance,
        movement_distance_source=movement_distance_source,
        movement_distance_method=movement_distance_method,
        pwm_percent=pwm_percent,
        pwm_match_status=pwm_match_status,
        match_status=STATUS_MATCHED,
        duration_status=DURATION_STATUS_VALID,
        start_line_number=txt_offset + 1,
        end_line_number=txt_offset + 2,
        pwm_source_file="pwm.log",
        pwm_source_line="RUN 0 80 (80)",
        pwm_line_number=10,
        pwm_source_time=start_time - timedelta(seconds=1),
    )


def _matched_records_from_txt(tmp_path: Path, lines: list[str]) -> list[ActivityRecord]:
    """Parse, match, and validate synthetic TXT lines."""

    txt_path = _write_lines(tmp_path / "movement.txt", lines)
    parse_result = MainLogParser(TextFileLoader()).parse(txt_path)
    records = EventMatcher(DEFAULT_EVENT_RULES).build_activity_records(parse_result.timeline)
    validated = ActivityValidator().validate(records)
    _apply_distance_selection(validated)
    return validated


def _apply_distance_selection(records: list[ActivityRecord], distance_source: str = "actual_preferred") -> None:
    """Apply the same runtime movement-distance selection the service uses for Details."""

    analyzer = DistributionAnalyzer(distance_source=distance_source)
    for record in records:
        movement = analyzer.derive_movement_distance(record)
        record.movement_distance = movement.movement_distance
        record.movement_distance_source = movement.movement_distance_source
        record.movement_distance_method = movement.movement_distance_method
        record.movement_distance_notes = movement.movement_distance_notes


def _stats_for(records: list[ActivityRecord]):
    """Return analyzer, rows, grouped rows, and stats for records."""

    analyzer = DistributionAnalyzer()
    rows = analyzer.build_input_rows(records, "UroBiopsy_20260410.txt")
    grouped = analyzer.group_rows(rows)
    stats = analyzer.compute_group_stats(grouped)
    return analyzer, rows, grouped, stats


def test_matcher_keeps_raw_distance_components_until_runtime_selection(tmp_path: Path) -> None:
    """Matcher should not bake the global distribution distance source into Details fields."""

    txt_path = _write_lines(
        tmp_path / "raw.txt",
        [
            "2026-04-30 09:50:25:829 MCU   @[Y] max: 0.00",
            "2026-04-30 09:50:27:029 MCU   @[Y] start clearing: -19.50",
            "2026-04-30 09:50:33:666 MCU   @[Y] motor cleared",
            "2026-04-30 09:50:33:667 MCU   @[Y] min: -29.51",
        ],
    )
    parse_result = MainLogParser(TextFileLoader()).parse(txt_path)
    records = EventMatcher(DEFAULT_EVENT_RULES).build_activity_records(parse_result.timeline)

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_commanded_distance == pytest.approx(19.50)
    assert record.movement_actual_distance == pytest.approx(29.51)
    assert record.movement_distance is None
    assert record.movement_distance_source == ""


def test_distribution_grouping_key_splits_only_on_configured_fields() -> None:
    """Groups should be keyed by TXT file, PWM, axis, rounded distance, and rule."""

    _, _, grouped, _ = _stats_for([_record(txt_offset=0, pwm_percent=-80), _record(txt_offset=20, pwm_percent=80)])
    assert len(grouped) == 1

    _, _, grouped, _ = _stats_for([_record(txt_offset=0), _record(txt_offset=20, pwm_percent=60)])
    assert len(grouped) == 2

    _, _, grouped, _ = _stats_for([_record(txt_offset=0), _record(txt_offset=20, axis="Y")])
    assert len(grouped) == 2

    _, _, grouped, _ = _stats_for(
        [
            _record(txt_offset=0),
            _record(txt_offset=20, start_value=-60, movement_target_position=-60, movement_distance=60),
        ]
    )
    assert len(grouped) == 2

    _, _, grouped, _ = _stats_for(
        [
            _record(txt_offset=0),
            _record(
                txt_offset=20,
                rule_id="move_to_home",
                start_event="start moving to home",
                end_event="motor homed",
            ),
        ]
    )
    assert len(grouped) == 2


def test_distribution_uses_recorded_true_movement_distance() -> None:
    """Distribution should use true movement distance fields, not target absolute values."""

    analyzer = DistributionAnalyzer()
    movement = analyzer.derive_movement_distance(
        _record(
            start_value=-25.16,
            movement_start_position=-49.02,
            movement_target_position=-25.16,
            movement_distance=23.86,
        )
    )
    assert movement.movement_start_position == -49.02
    assert movement.movement_target_position == -25.16
    assert movement.movement_distance == pytest.approx(23.86)
    assert movement.movement_distance_method == "KnownStartPositionToTarget"

    movement = analyzer.derive_movement_distance(
        _record(
            start_value=-30.0,
            end_value=-10.0,
            movement_start_position=None,
            movement_target_position=-30,
            movement_distance=None,
            movement_distance_method="MissingStartPosition",
        )
    )
    assert movement.movement_distance is None
    assert movement.movement_distance_method == "MissingStartPosition"


def test_move_to_home_distance_uses_previous_position_not_target_absolute(tmp_path: Path) -> None:
    """H home movement should use min position to target, not abs(target)."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-10 09:08:24:786 MCU   @[H] motor cleared",
            "2026-04-10 09:08:24:786 MCU   @[H] min: -49.02",
            "2026-04-10 09:08:24:987 MCU   @[H] start moving to home: -25.16",
            "2026-04-10 09:08:29:226 MCU   @[H] motor homed",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_start_position == -49.02
    assert record.movement_target_position == -25.16
    assert record.movement_distance == pytest.approx(23.86)
    assert record.movement_distance_method == "KnownStartPositionToTarget"
    assert record.movement_distance != pytest.approx(25.16)


def test_move_to_max_distance_uses_previous_min_position(tmp_path: Path) -> None:
    """X max movement should use previous min position, not target absolute value."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-10 09:08:18:557 MCU   @[X] motor cleared",
            "2026-04-10 09:08:18:558 MCU   @[X] min: -32.01",
            "2026-04-10 09:08:18:760 MCU   @[X] start moving to max pos: -3.00",
            "2026-04-10 09:08:28:623 MCU   @[X] motor reached max pos",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_distance == pytest.approx(29.01)
    assert record.movement_distance != pytest.approx(3.00)


def test_z_move_to_home_distance_uses_previous_min_position(tmp_path: Path) -> None:
    """Z home movement should use previous min position, not target absolute value."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-10 09:22:44:008 MCU   @[Z] motor cleared",
            "2026-04-10 09:22:44:009 MCU   @[Z] min: -50.00",
            "2026-04-10 09:22:44:031 MCU   @[Z] start moving to home: -30.10",
            "2026-04-10 09:22:53:786 MCU   @[Z] motor homed",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_distance == pytest.approx(19.90)
    assert record.movement_distance != pytest.approx(30.10)


def test_end_value_search_ignores_unrelated_axes_until_companion_line(tmp_path: Path) -> None:
    """Same-axis companion min/max lines should not be missed because other axes interleave."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:50:25:829 MCU   @[Y] max: 0.00",
            "2026-04-30 09:50:27:029 MCU   @[Y] start clearing: -19.50",
            "2026-04-30 09:50:33:666 MCU   @[Y] motor cleared",
            "2026-04-30 09:50:33:667 MCU   @[X] max: 0.00",
            "2026-04-30 09:50:33:668 MCU   @[Z] max: 0.00",
            "2026-04-30 09:50:33:669 MCU   @[H] max: 0.00",
            "2026-04-30 09:50:33:670 MCU   @[N] max: 69.51",
            "2026-04-30 09:50:33:671 MCU   @[P] max: 0.00",
            "2026-04-30 09:50:33:672 MCU   @[Y] min: -29.51",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_end_position == -29.51
    assert record.movement_actual_distance == pytest.approx(29.51)
    assert record.movement_distance == pytest.approx(29.51)


def test_reset_physical_position_to_zero_updates_position_state(tmp_path: Path) -> None:
    """A reset physical position line should act as a zero-position hint."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:50:25:829 MCU   @[H] reset physical position to 0",
            "2026-04-30 09:50:27:029 MCU   @[H] start clearing: -49.00",
            "2026-04-30 09:50:33:666 MCU   @[H] motor cleared",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_start_position == 0.0
    assert record.movement_target_position == -49.0
    assert record.movement_commanded_distance == pytest.approx(49.0)
    assert record.movement_actual_distance is None
    assert record.movement_distance == pytest.approx(49.0)
    assert record.movement_distance_source == "CommandTargetPosition"


def test_position_state_resets_on_new_initialization(tmp_path: Path) -> None:
    """A hard workflow boundary must prevent stale positions from leaking into the next cycle."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:49:00:000 MCU   @[X] min: -32.01",
            "2026-04-30 09:50:00:000 User  @on_startInitRobot_clicked",
            "2026-04-30 09:50:27:029 MCU   @[X] start moving to max pos: -3.00",
            "2026-04-30 09:50:33:666 MCU   @[X] motor reached max pos",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_start_position is None
    assert record.movement_target_position == -3.0
    assert record.movement_distance is None
    assert record.movement_distance_method == "MissingStartPosition"


def test_tool_menu_boundary_does_not_reset_position_state_by_default(tmp_path: Path) -> None:
    """Soft menu boundaries should not discard physical position hints by default."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:49:00:000 MCU   @[H] min: -49.03",
            "2026-04-30 09:49:01:000 User  @tool menu selected",
            "2026-04-30 09:49:02:000 MCU   @[H] start moving to home: -25.16",
            "2026-04-30 09:49:06:000 MCU   @[H] motor homed",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_start_position == -49.03
    assert record.movement_distance == pytest.approx(23.87)


def test_clearing_from_known_zero_prefers_actual_end_when_available(tmp_path: Path) -> None:
    """Clearing from known zero should prefer the actual end companion position."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-10 09:20:23:500 MCU   @[Z] max: 0.00",
            "2026-04-10 09:20:23:541 MCU   @[Z] start clearing: -50.00",
            "2026-04-10 09:20:46:317 MCU   @[Z] motor cleared",
            "2026-04-10 09:20:46:317 MCU   @[Z] min: -50.00",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_start_position == 0.0
    assert record.movement_target_position == -50.0
    assert record.movement_end_position == -50.0
    assert record.movement_commanded_distance == pytest.approx(50.0)
    assert record.movement_actual_distance == pytest.approx(50.0)
    assert record.movement_distance == pytest.approx(50.0)
    assert record.movement_distance_method == "KnownStartPositionToActualEnd"
    assert record.movement_distance_source == "ActualEndPosition"


def test_y_clear_motor_prefers_actual_end_over_command_target(tmp_path: Path) -> None:
    """Y clearing should use min position after motor cleared, not the commanded target."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:50:25:829 MCU   @[Y] max: 0.00",
            "2026-04-30 09:50:27:029 MCU   @[Y] start clearing: -19.50",
            "2026-04-30 09:50:33:666 MCU   @[Y] motor cleared",
            "2026-04-30 09:50:33:667 MCU   @[Y] min: -29.51",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_start_position == 0.0
    assert record.movement_target_position == -19.50
    assert record.movement_end_position == -29.51
    assert record.movement_commanded_distance == pytest.approx(19.50)
    assert record.movement_actual_distance == pytest.approx(29.51)
    assert record.movement_distance == pytest.approx(29.51)
    assert record.movement_distance_source == "ActualEndPosition"
    assert record.movement_distance != pytest.approx(19.50)


def test_x_clear_motor_prefers_actual_end_over_command_target(tmp_path: Path) -> None:
    """X clearing should use actual min position after completion."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:50:25:829 MCU   @[X] max: 0.00",
            "2026-04-30 09:50:27:029 MCU   @[X] start clearing: -22.00",
            "2026-04-30 09:50:33:666 MCU   @[X] motor cleared",
            "2026-04-30 09:50:33:668 MCU   @[X] min: -32.01",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_commanded_distance == pytest.approx(22.00)
    assert record.movement_actual_distance == pytest.approx(32.01)
    assert record.movement_distance == pytest.approx(32.01)
    assert record.movement_distance_source == "ActualEndPosition"
    assert record.movement_distance != pytest.approx(22.00)


def test_h_clear_motor_prefers_actual_end_when_available(tmp_path: Path) -> None:
    """H clearing should preserve both commanded and actual distance values."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-30 09:50:25:829 MCU   @[H] max: 0.00",
            "2026-04-30 09:50:27:029 MCU   @[H] start clearing: -49.00",
            "2026-04-30 09:50:33:666 MCU   @[H] motor cleared",
            "2026-04-30 09:50:33:666 MCU   @[H] min: -49.03",
        ],
    )

    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    assert record.movement_commanded_distance == pytest.approx(49.00)
    assert record.movement_actual_distance == pytest.approx(49.03)
    assert record.movement_distance == pytest.approx(49.03)
    assert record.movement_distance_source == "ActualEndPosition"


def test_completed_target_updates_next_movement_start_position(tmp_path: Path) -> None:
    """A later clear should start from the completed home target, not stale min position."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-10 09:08:24:786 MCU   @[H] motor cleared",
            "2026-04-10 09:08:24:786 MCU   @[H] min: -49.02",
            "2026-04-10 09:08:24:987 MCU   @[H] start moving to home: -25.16",
            "2026-04-10 09:08:29:226 MCU   @[H] motor homed",
            "2026-04-10 09:08:30:000 MCU   @[H] start clearing: -49.02",
            "2026-04-10 09:08:38:000 MCU   @[H] motor cleared",
            "2026-04-10 09:08:38:000 MCU   @[H] min: -49.02",
        ],
    )

    clear_record = next(
        item
        for item in records
        if item.match_status == STATUS_MATCHED and item.rule_id == "clear_motor"
    )
    assert clear_record.movement_start_position == -25.16
    assert clear_record.movement_target_position == -49.02
    assert clear_record.movement_distance == pytest.approx(23.86)


def test_missing_start_position_is_not_used_for_distribution_by_default(tmp_path: Path) -> None:
    """Rows without true movement distance should be excluded when fallback is disabled."""

    records = _matched_records_from_txt(
        tmp_path,
        [
            "2026-04-10 09:22:44:031 MCU   @[Z] start moving to home: -30.10",
            "2026-04-10 09:22:53:786 MCU   @[Z] motor homed",
        ],
    )
    record = next(item for item in records if item.match_status == STATUS_MATCHED)
    record.pwm_percent = 80
    record.pwm_match_status = PWM_STATUS_MATCHED_CONTAINING

    analyzer, rows, grouped, stats = _stats_for([record])

    assert record.movement_distance is None
    assert record.movement_distance_method == "MissingStartPosition"
    assert rows == []
    assert grouped == {}
    assert stats == []
    assert analyzer.exclusion_counts["MissingTrueMovementDistance"] == 1


def test_distribution_grouping_uses_corrected_distance() -> None:
    """Home motions should group by true travel distance, not target absolute value."""

    _, rows, grouped, stats = _stats_for(
        [
            _record(
                seconds=4,
                txt_offset=0,
                axis="H",
                start_value=-25.16,
                movement_start_position=-49.02,
                movement_target_position=-25.16,
                movement_distance=23.86,
                rule_id="move_to_home",
                start_event="start moving to home",
                end_event="motor homed",
            ),
            _record(
                seconds=5,
                txt_offset=20,
                axis="H",
                start_value=-25.16,
                movement_start_position=-49.02,
                movement_target_position=-25.16,
                movement_distance=23.86,
                rule_id="move_to_home",
                start_event="start moving to home",
                end_event="motor homed",
            ),
        ]
    )

    assert len(rows) == 2
    assert len(grouped) == 1
    assert stats[0].movement_distance_group_value == pytest.approx(23.9)
    assert stats[0].movement_distance_rounded == pytest.approx(23.9)
    assert stats[0].movement_distance_raw_example == pytest.approx(23.86)


def test_distance_binning_groups_small_float_variations_but_keeps_raw_values() -> None:
    """Default 0.1 distance bins should group near-identical physical movements."""

    _, rows, grouped, stats = _stats_for(
        [
            _record(txt_offset=0, start_value=-23.86, movement_target_position=-23.86),
            _record(txt_offset=20, start_value=-23.87, movement_target_position=-23.87),
            _record(txt_offset=40, start_value=-25.16, movement_target_position=-25.16),
        ]
    )

    assert len(rows) == 3
    assert len(grouped) == 2
    group_values = sorted(item.movement_distance_group_value for item in stats)
    assert group_values == pytest.approx([23.9, 25.2])
    assert sorted(row.movement_distance for row in rows) == pytest.approx([23.86, 23.87, 25.16])
    near_group = next(item for item in stats if item.movement_distance_group_value == pytest.approx(23.9))
    assert near_group.sample_count == 2
    assert near_group.position_values_mixed is True


def test_exact_distance_grouping_does_not_round_group_keys() -> None:
    """Exact mode should keep near-but-different distances as separate groups."""

    analyzer = DistributionAnalyzer(distance_grouping_mode="exact")
    rows = analyzer.build_input_rows(
        [
            _record(txt_offset=0, movement_distance=23.861, movement_commanded_distance=23.861),
            _record(txt_offset=20, movement_distance=23.862, movement_commanded_distance=23.862),
        ],
        "sample.txt",
    )
    grouped = analyzer.group_rows(rows)
    stats = analyzer.compute_group_stats(grouped)

    assert len(grouped) == 2
    assert sorted(item.movement_distance_group_value for item in stats) == pytest.approx([23.861, 23.862])
    assert "23.861" in stats[0].group_id or "23.862" in stats[0].group_id


def test_round_digits_distance_grouping_can_merge_exact_variations() -> None:
    """Round-digits mode should group values that round to the same configured value."""

    analyzer = DistributionAnalyzer(distance_grouping_mode="round_digits", movement_distance_round_digits=2)
    rows = analyzer.build_input_rows(
        [
            _record(txt_offset=0, movement_distance=23.861, movement_commanded_distance=23.861),
            _record(txt_offset=20, movement_distance=23.862, movement_commanded_distance=23.862),
        ],
        "sample.txt",
    )
    grouped = analyzer.group_rows(rows)

    assert len(grouped) == 1
    assert next(iter(grouped.values()))[0].movement_distance_group_value == pytest.approx(23.86)


def test_bin_distance_display_uses_bin_precision() -> None:
    """Distance display should follow bin precision instead of a fixed two-decimal format."""

    analyzer = DistributionAnalyzer(distance_grouping_mode="bin", movement_distance_bin_size=0.05)
    rows = analyzer.build_input_rows(
        [_record(txt_offset=0, movement_distance=23.861, movement_commanded_distance=23.861)],
        "sample.txt",
    )
    grouped = analyzer.group_rows(rows)
    stats = analyzer.compute_group_stats(grouped)

    assert stats[0].movement_distance_group_value == pytest.approx(23.85)
    assert "D23.85" in stats[0].group_id


def test_chart_title_uses_group_distance_display_and_source() -> None:
    """Chart titles should show grouped distance precision and movement source."""

    analyzer = DistributionAnalyzer(distance_grouping_mode="exact")
    rows = analyzer.build_input_rows(
        [_record(txt_offset=0, movement_distance=23.861, movement_commanded_distance=23.861)],
        "sample.txt",
    )
    grouped = analyzer.group_rows(rows)
    stats = analyzer.compute_group_stats(grouped)

    title = NormalDistributionChartGenerator()._chart_title(stats[0])

    assert "Distance 23.861 (CommandTargetPosition)" in title
    assert "Distance 23.86 " not in title


def test_unreliable_pwm_is_excluded_from_distribution() -> None:
    """Uncertain PWM evidence should not be used for same-PWM distribution grouping."""

    analyzer, rows, grouped, stats = _stats_for(
        [
            _record(
                pwm_match_status=PWM_STATUS_LATEST_BEFORE_TOO_FAR,
            )
        ]
    )

    assert rows == []
    assert grouped == {}
    assert stats == []
    assert analyzer.exclusion_counts["LatestBeforeStartTooFar"] == 1


def test_latest_before_too_far_exclusion_is_specific() -> None:
    """PWM time-window exclusions should not be reported as generic missing PWM."""

    analyzer = DistributionAnalyzer()
    record = _record(pwm_percent=None, pwm_match_status=PWM_STATUS_LATEST_BEFORE_TOO_FAR)
    record.pwm_missing_reason = "The latest PWM record before the activity for axis Z was too far away."
    record.pwm_time_delta_ms = 599000

    rows = analyzer.build_input_rows([record], "sample.txt")

    assert rows == []
    assert analyzer.exclusions[0].reason == "LatestBeforeStartTooFar"
    assert analyzer.exclusions[0].pwm_match_status == PWM_STATUS_LATEST_BEFORE_TOO_FAR
    assert analyzer.exclusions[0].pwm_time_delta_ms == 599000


def test_nearest_future_pwm_exclusion_is_specific() -> None:
    """Nearest future PWM should be clearly labeled when distribution rejects it."""

    analyzer = DistributionAnalyzer()
    record = _record(pwm_match_status=PWM_STATUS_MATCHED_NEAREST_FUTURE)

    rows = analyzer.build_input_rows([record], "sample.txt")

    assert rows == []
    assert analyzer.exclusions[0].reason == "NearestFuturePWMNotAllowedForDistribution"
    assert analyzer.exclusions[0].pwm_match_status == PWM_STATUS_MATCHED_NEAREST_FUTURE


def test_nearest_pwm_is_excluded_from_distribution_by_default() -> None:
    """Distribution grouping should require containing-file PWM unless explicitly relaxed."""

    analyzer, rows, grouped, stats = _stats_for(
        [
            _record(
                pwm_match_status=PWM_STATUS_MATCHED_NEAREST,
            )
        ]
    )

    assert rows == []
    assert grouped == {}
    assert stats == []
    assert analyzer.exclusion_counts["NearestLogFilePWMNotAllowedForDistribution"] == 1


def test_distribution_exclusion_keeps_movement_reason_when_pwm_is_also_bad() -> None:
    """Rows with multiple exclusion causes should show movement and PWM reasons."""

    analyzer = DistributionAnalyzer()
    record = _record(
        rule_id="search_reference",
        start_event="start searching reference",
        end_event="reference found",
        start_value=None,
        movement_start_position=None,
        movement_target_position=None,
        movement_commanded_distance=None,
        movement_actual_distance=None,
        movement_distance=None,
        movement_distance_method="MissingValue",
        pwm_match_status=PWM_STATUS_MATCHED_NEAREST_FUTURE,
    )

    rows = analyzer.build_input_rows([record], "sample.txt")

    assert rows == []
    exclusion = analyzer.exclusions[0]
    assert exclusion.reason == "MissingTrueMovementDistance"
    assert exclusion.movement_distance_exclusion_reason == "MissingTrueMovementDistance"
    assert exclusion.pwm_exclusion_reason == "NearestFuturePWMNotAllowedForDistribution"
    assert "NearestFuturePWMNotAllowedForDistribution" in exclusion.secondary_reasons


def test_nearest_pwm_can_be_explicitly_allowed_for_distribution() -> None:
    """Relaxed distribution settings should include nearest PWM only when requested."""

    analyzer = DistributionAnalyzer(
        allowed_pwm_match_statuses={PWM_STATUS_MATCHED_CONTAINING, PWM_STATUS_MATCHED_NEAREST},
    )
    rows = analyzer.build_input_rows(
        [
            _record(
                pwm_match_status=PWM_STATUS_MATCHED_NEAREST,
            )
        ],
        "sample.txt",
    )

    assert len(rows) == 1
    assert rows[0].pwm_match_status == PWM_STATUS_MATCHED_NEAREST


def test_distribution_statistics_use_sample_and_population_variance() -> None:
    """Stats should match pandas sample/population variance semantics."""

    _, _, _, stats = _stats_for(
        [
            _record(seconds=10.0, txt_offset=0),
            _record(seconds=12.0, txt_offset=20),
            _record(seconds=14.0, txt_offset=40),
        ]
    )

    result = stats[0]
    assert result.mean_s == pytest.approx(12.0)
    assert result.median_s == pytest.approx(12.0)
    assert result.sample_var_s2 == pytest.approx(4.0)
    assert result.sample_std_s == pytest.approx(2.0)
    assert result.population_var_ms2 / 1_000_000 == pytest.approx(8 / 3)
    assert result.population_std_ms / 1000 == pytest.approx(math.sqrt(8 / 3))


def test_single_sample_group_reports_insufficient_samples() -> None:
    """Single-sample groups should retain basic stats and blank sample SD/variance."""

    _, _, _, stats = _stats_for([_record(seconds=10.0)])

    result = stats[0]
    assert result.sample_count == 1
    assert result.mean_s == pytest.approx(10.0)
    assert result.sample_std_s is None
    assert result.sample_var_s2 is None
    assert result.distribution_status == "InsufficientSamples"


def test_distribution_chart_generation_creates_png(tmp_path: Path) -> None:
    """A normal-fit-ready group should generate a non-empty PNG chart."""

    _, rows, grouped, stats = _stats_for(
        [_record(seconds=value, txt_offset=index * 20) for index, value in enumerate([10, 11, 12, 13, 14])]
    )
    stats_by_group = {item.group_id: item for item in stats}

    generated = NormalDistributionChartGenerator(max_charts=10).generate_charts(grouped, stats_by_group, tmp_path)

    assert len(generated) == 1
    chart_path = next(iter(generated.values()))
    assert chart_path.exists()
    assert chart_path.stat().st_size > 0
    assert stats[0].chart_status == "ChartGenerated"
    assert rows


def test_zero_variance_chart_generation_does_not_crash(tmp_path: Path) -> None:
    """Identical durations should produce a safe chart and zero-variance status."""

    _, _, grouped, stats = _stats_for([_record(seconds=10, txt_offset=index * 20) for index in range(3)])
    stats_by_group = {item.group_id: item for item in stats}

    generated = NormalDistributionChartGenerator(max_charts=10).generate_charts(grouped, stats_by_group, tmp_path)

    assert stats[0].distribution_status == "ZeroVariance"
    assert "Zero variance" in stats[0].notes
    chart_path = next(iter(generated.values()))
    assert chart_path.exists()
    assert chart_path.stat().st_size > 0


def test_excel_export_includes_distribution_sheets_and_chart_paths(tmp_path: Path) -> None:
    """A synthetic service run should write distribution worksheets and chart files."""

    txt_lines: list[str] = []
    for index, seconds in enumerate([10, 11, 12, 13, 14]):
        start = datetime(2026, 1, 1, 0, index, 0)
        end = start + timedelta(seconds=seconds)
        txt_lines.extend(
            [
                f"{start.strftime('%Y-%m-%d %H:%M:%S')}:000 MCU   @[Z] min: -50.00",
                f"{(start + timedelta(milliseconds=1)).strftime('%Y-%m-%d %H:%M:%S')}:001 MCU   @[Z] start moving to home: -30.00",
                f"{end.strftime('%Y-%m-%d %H:%M:%S')}:000 MCU   @[Z] motor homed",
            ]
        )
    txt_path = _write_lines(tmp_path / "sample.txt", txt_lines)
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "z.log",
        [
            "2026-01-01 00:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 00:10:00:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "analysis.xlsx"
    chart_dir = tmp_path / "charts"

    result = LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        distribution_output_dir=chart_dir,
        max_distribution_charts=5,
    )

    assert result.distribution_group_count == 1
    assert result.distribution_raw_row_count == 5
    assert result.distribution_chart_count == 1
    workbook = load_workbook(output_path, data_only=True)
    assert {
        "Details",
        "Summary",
        "Distribution Summary",
        "Distribution Raw Data",
        "Distribution Charts",
        "Log Coverage Summary",
        "Log Coverage Gaps",
        "Distribution Eligibility",
        "Distribution Exclusion Summary",
    } <= set(workbook.sheetnames)
    summary_sheet = workbook["Distribution Summary"]
    headers = [cell.value for cell in summary_sheet[1]]
    for expected in DISTRIBUTION_SUMMARY_COLUMNS:
        assert expected in headers
    header_index = {header: index for index, header in enumerate(headers)}
    row = next(summary_sheet.iter_rows(min_row=2, values_only=True))
    chart_path = Path(row[header_index["Chart File"]])
    assert row[header_index["TXT Source File"]] == "sample.txt"
    assert row[header_index["PWM (%)"]] == 80
    assert row[header_index["Axis"]] == "Z"
    assert row[header_index["Example Movement Start Position"]] == -50
    assert row[header_index["Example Movement Target Position"]] == -30
    assert row[header_index["Example Movement Commanded Distance"]] == 20
    assert row[header_index["Movement Distance Group Value"]] == 20
    assert row[header_index["Selected Group Distance"]] == 20
    assert row[header_index["Movement Distance Rounded"]] == 20
    assert row[header_index["Movement Distance Method"]] == "KnownStartPositionToTarget"
    assert row[header_index["Movement Distance Source"]] == "CommandTargetPosition"
    assert row[header_index["Rule ID"]] == "move_to_home"
    assert row[header_index["Sample Count"]] == 5
    assert row[header_index["Mean Duration (s)"]] == pytest.approx(11.999)
    assert row[header_index["Sample Std Dev Duration (s)"]] == pytest.approx(math.sqrt(2.5))
    assert row[header_index["Sample Variance Duration (s^2)"]] == pytest.approx(2.5)
    assert row[header_index["Normal Fit Mean (s)"]] == pytest.approx(11.999)
    assert row[header_index["Normal Fit Std Dev (s)"]] == pytest.approx(math.sqrt(2.5))
    assert row[header_index["Chart Status"]] == "ChartGenerated"
    assert chart_path.exists()
    assert chart_path.stat().st_size > 0


def test_service_commanded_only_keeps_details_and_distribution_consistent(tmp_path: Path) -> None:
    """Runtime distance source should drive both Details selected distance and distribution grouping."""

    txt_lines: list[str] = []
    for index in range(2):
        base = datetime(2026, 1, 1, 0, index, 0)
        txt_lines.extend(
            [
                f"{base.strftime('%Y-%m-%d %H:%M:%S')}:000 MCU   @[Y] max: 0.00",
                f"{(base + timedelta(milliseconds=1)).strftime('%Y-%m-%d %H:%M:%S')}:001 MCU   @[Y] start clearing: -19.50",
                f"{(base + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S')}:000 MCU   @[Y] motor cleared",
                f"{(base + timedelta(seconds=5, milliseconds=1)).strftime('%Y-%m-%d %H:%M:%S')}:001 MCU   @[Y] min: -29.51",
            ]
        )
    txt_path = _write_lines(tmp_path / "commanded.txt", txt_lines)
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "y.log",
        [
            "2026-01-01 00:00:00:000 [OUT] sample",
            "                              [N4:Y] RUN 0 80 (80)",
            "2026-01-01 00:02:00:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "commanded.xlsx"

    LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        distribution_distance_source="commanded_only",
        max_distribution_charts=2,
    )

    workbook = load_workbook(output_path, data_only=True)
    details = workbook["Details"]
    details_headers = [cell.value for cell in details[1]]
    details_index = {header: index for index, header in enumerate(details_headers)}
    detail_row = next(
        row
        for row in details.iter_rows(min_row=2, values_only=True)
        if row[details_index["Match Status"]] == STATUS_MATCHED
    )
    assert detail_row[details_index["Movement Commanded Distance"]] == pytest.approx(19.5)
    assert detail_row[details_index["Movement Actual Distance"]] == pytest.approx(29.51)
    assert detail_row[details_index["Selected Movement Distance"]] == pytest.approx(19.5)
    assert detail_row[details_index["Movement Distance Source"]] == "CommandTargetPosition"

    summary = workbook["Distribution Summary"]
    summary_headers = [cell.value for cell in summary[1]]
    summary_index = {header: index for index, header in enumerate(summary_headers)}
    summary_row = next(summary.iter_rows(min_row=2, values_only=True))
    assert summary_row[summary_index["Movement Distance Group Value"]] == pytest.approx(19.5)
    assert summary_row[summary_index["Movement Distance Source"]] == "CommandTargetPosition"


def test_distribution_charts_sheet_explains_no_generated_charts(tmp_path: Path) -> None:
    """When all groups are below the chart threshold, Excel should explain why charts are absent."""

    txt_path = _write_lines(
        tmp_path / "single-sample.txt",
        [
            "2026-01-01 00:00:00:000 MCU   @[Z] min: -50.00",
            "2026-01-01 00:00:01:000 MCU   @[Z] start moving to home: -30.00",
            "2026-01-01 00:00:02:000 MCU   @[Z] motor homed",
        ],
    )
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "z.log",
        [
            "2026-01-01 00:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 00:00:10:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "single-sample.xlsx"

    result = LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=5,
    )

    workbook = load_workbook(output_path, data_only=True)
    assert result.distribution_group_count == 1
    assert result.distribution_chart_count == 0
    assert "Distribution Charts" in workbook.sheetnames
    message = workbook["Distribution Charts"].cell(row=1, column=1).value
    assert "No distribution charts were generated because all valid groups had fewer than 2 samples." == message


def test_distribution_chart_anchors_match_exported_blocks(tmp_path: Path) -> None:
    """Chart anchors in Distribution Summary should point at real chart metadata blocks."""

    txt_lines: list[str] = []
    axes = [("X", -32.0, -3.0, "motor reached max pos", "start moving to max pos"), ("Y", -29.0, -10.0, "motor homed", "start moving to home"), ("Z", -50.0, -30.0, "motor homed", "start moving to home")]
    for axis_index, (axis, start_position, target, end_label, start_label) in enumerate(axes):
        for sample_index in range(2):
            base = datetime(2026, 1, 1, 0, axis_index * 10 + sample_index, 0)
            txt_lines.extend(
                [
                    f"{base.strftime('%Y-%m-%d %H:%M:%S')}:000 MCU   @[{axis}] min: {start_position:.2f}",
                    f"{(base + timedelta(milliseconds=1)).strftime('%Y-%m-%d %H:%M:%S')}:001 MCU   @[{axis}] {start_label}: {target:.2f}",
                    f"{(base + timedelta(seconds=4 + sample_index)).strftime('%Y-%m-%d %H:%M:%S')}:000 MCU   @[{axis}] {end_label}",
                ]
            )
    txt_path = _write_lines(tmp_path / "anchors.txt", txt_lines)
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "all.log",
        [
            "2026-01-01 00:00:00:000 [OUT] sample",
            "                              [N3:X] RUN 0 80 (80)",
            "                              [N4:Y] RUN 0 80 (80)",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 00:30:00:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "anchors.xlsx"

    LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=3,
    )

    workbook = load_workbook(output_path, data_only=True)
    summary_sheet = workbook["Distribution Summary"]
    headers = [cell.value for cell in summary_sheet[1]]
    header_index = {header: index for index, header in enumerate(headers)}
    anchors = [
        row[header_index["Chart Sheet Anchor / Image ID"]]
        for row in summary_sheet.iter_rows(min_row=2, values_only=True)
        if row[header_index["Chart File"]]
    ]
    assert anchors == [
        f"Distribution Charts!A{1 + index * DISTRIBUTION_CHART_BLOCK_HEIGHT}"
        for index in range(3)
    ]
    chart_sheet = workbook["Distribution Charts"]
    for index in range(3):
        assert chart_sheet.cell(row=1 + index * DISTRIBUTION_CHART_BLOCK_HEIGHT, column=1).value == "Group ID"


def test_log_coverage_summary_warns_when_control_logs_cover_only_a_short_span(tmp_path: Path) -> None:
    """Coverage summary should make partial control-log folders visible."""

    txt_path = _write_lines(
        tmp_path / "long.txt",
        [
            "2026-01-01 00:00:00:000 MCU   @[Z] min: -50.00",
            "2026-01-01 00:00:01:000 MCU   @[Z] start moving to home: -30.00",
            "2026-01-01 00:00:02:000 MCU   @[Z] motor homed",
            "2026-01-01 01:00:00:000 MCU   @[H] min: -49.03",
            "2026-01-01 01:00:01:000 MCU   @[H] start moving to home: -25.16",
            "2026-01-01 01:00:02:000 MCU   @[H] motor homed",
        ],
    )
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "short.log",
        [
            "2026-01-01 00:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 00:00:10:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "coverage.xlsx"

    LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=1,
    )

    workbook = load_workbook(output_path, data_only=True)
    assert "Log Coverage Summary" in workbook.sheetnames
    sheet = workbook["Log Coverage Summary"]
    headers = [cell.value for cell in sheet[1]]
    assert headers == LOG_COVERAGE_SUMMARY_COLUMNS
    values = next(sheet.iter_rows(min_row=2, values_only=True))
    row = {header: values[index] for index, header in enumerate(headers)}
    assert row["Control Log File Count"] == 1
    assert row["Coverage Ratio (%)"] < 1
    assert row["Rows With Distribution-Accepted PWM"] == 1
    assert row["Rows With Containing-File PWM"] == 1
    assert row["Rows With No Same-Axis PWM In Folder"] >= 1
    assert row["Rows Excluded From Distribution Due To PWM Reliability"] >= 1
    assert "Control log coverage appears incomplete" in row["Notes"]
    assert "Log Coverage Gaps" in workbook.sheetnames
    exclusion_sheet = workbook["Distribution Exclusion Summary"]
    exclusion_headers = [cell.value for cell in exclusion_sheet[1]]
    exclusion_rows = list(exclusion_sheet.iter_rows(min_row=2, values_only=True))
    exclusion_index = {header: index for index, header in enumerate(exclusion_headers)}
    assert any(
        row[exclusion_index["Exclusion Reason"]] == "NoSameAxisPWMInFolder"
        and row[exclusion_index["Axis"]] == "H"
        and row[exclusion_index["PWM Match Status"]] == "NoSameAxisPWMInFolder"
        for row in exclusion_rows
    )


def test_log_coverage_summary_uses_interval_union_not_outer_range(tmp_path: Path) -> None:
    """Separated control logs should not be treated as one continuous covered window."""

    txt_path = _write_lines(
        tmp_path / "gap.txt",
        [
            "2026-01-01 09:00:00:000 MCU   @[Z] min: -50.00",
            "2026-01-01 09:00:01:000 MCU   @[Z] start moving to home: -30.00",
            "2026-01-01 09:00:02:000 MCU   @[Z] motor homed",
            "2026-01-01 10:01:00:000 MCU   @[Z] min: -50.00",
        ],
    )
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "a.log",
        [
            "2026-01-01 09:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 09:01:00:000 [OUT] sample",
        ],
    )
    _write_lines(
        log_folder / "b.log",
        [
            "2026-01-01 10:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 10:01:00:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "gap.xlsx"

    LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=1,
    )

    workbook = load_workbook(output_path, data_only=True)
    sheet = workbook["Log Coverage Summary"]
    headers = [cell.value for cell in sheet[1]]
    values = next(sheet.iter_rows(min_row=2, values_only=True))
    row = {header: values[index] for index, header in enumerate(headers)}
    assert row["Merged Control Log Interval Count"] == 2
    assert row["Covered Duration (s)"] == pytest.approx(120.0)
    assert row["Coverage Gap Count"] == 1
    assert row["Coverage Ratio (%)"] < 4
    gaps_sheet = workbook["Log Coverage Gaps"]
    gap_headers = [cell.value for cell in gaps_sheet[1]]
    assert gap_headers == LOG_COVERAGE_GAPS_COLUMNS
    gap_rows = list(gaps_sheet.iter_rows(min_row=2, values_only=True))
    assert len(gap_rows) == row["Coverage Gap Count"]
    gap_index = {header: index for index, header in enumerate(gap_headers)}
    assert gap_rows[0][gap_index["Gap Duration (s)"]] > 3500
    assert gap_rows[0][gap_index["Gap Type"]] == "BetweenControlLogs"
    assert gap_rows[0][gap_index["Nearest Previous Control Log File"]] == "a.log"
    assert gap_rows[0][gap_index["Nearest Next Control Log File"]] == "b.log"


def test_log_coverage_gaps_sheet_lists_multiple_uncovered_intervals(tmp_path: Path) -> None:
    """Multiple gaps from interval-union coverage should be individually auditable."""

    txt_path = _write_lines(
        tmp_path / "many-gaps.txt",
        [
            "2026-01-01 09:00:00:000 MCU   @[Z] min: -50.00",
            "2026-01-01 09:00:01:000 MCU   @[Z] start moving to home: -30.00",
            "2026-01-01 09:00:02:000 MCU   @[Z] motor homed",
            "2026-01-01 11:00:00:000 MCU   @[Z] min: -50.00",
        ],
    )
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "a.log",
        [
            "2026-01-01 09:10:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 09:20:00:000 [OUT] sample",
        ],
    )
    _write_lines(
        log_folder / "b.log",
        [
            "2026-01-01 10:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 10:10:00:000 [OUT] sample",
        ],
    )
    output_path = tmp_path / "many-gaps.xlsx"

    LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=1,
    )

    workbook = load_workbook(output_path, data_only=True)
    summary_sheet = workbook["Log Coverage Summary"]
    summary_headers = [cell.value for cell in summary_sheet[1]]
    summary_row = next(summary_sheet.iter_rows(min_row=2, values_only=True))
    summary = {header: summary_row[index] for index, header in enumerate(summary_headers)}
    gaps_sheet = workbook["Log Coverage Gaps"]
    gap_rows = list(gaps_sheet.iter_rows(min_row=2, values_only=True))
    gap_headers = [cell.value for cell in gaps_sheet[1]]
    gap_index = {header: index for index, header in enumerate(gap_headers)}
    gap_types = [row[gap_index["Gap Type"]] for row in gap_rows]

    assert summary["Coverage Gap Count"] == len(gap_rows)
    assert len(gap_rows) >= 3
    assert gap_types[0] == "BeforeFirstControlLog"
    assert "BetweenControlLogs" in gap_types
    assert gap_types[-1] == "AfterLastControlLog"
    assert gap_rows[0][gap_index["Nearest Next Control Log File"]] == "a.log"
    assert gap_rows[-1][gap_index["Nearest Previous Control Log File"]] == "b.log"


def test_verbose_without_trace_lines_suppresses_matcher_line_debug(tmp_path: Path) -> None:
    """CLI --verbose should keep matcher per-line debug logs hidden unless --trace-lines is supplied."""

    txt_path = _write_lines(
        tmp_path / "verbose.txt",
        [
            "2026-01-01 00:00:00:000 MCU   @[Z] min: -50.00",
            "2026-01-01 00:00:01:000 MCU   @[Z] start moving to home: -30.00",
            "2026-01-01 00:00:02:000 MCU   @[Z] motor homed",
        ],
    )
    log_folder = tmp_path / "logs"
    log_folder.mkdir()
    _write_lines(
        log_folder / "z.log",
        [
            "2026-01-01 00:00:00:000 [OUT] sample",
            "                              [N12:Z] RUN 0 80 (80)",
            "2026-01-01 00:00:10:000 [OUT] sample",
        ],
    )

    quiet_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.log_activity_tool",
            "--txt-file",
            str(txt_path),
            "--log-folder",
            str(log_folder),
            "--output",
            str(tmp_path / "quiet.xlsx"),
            "--no-gui",
            "--verbose",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    trace_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.log_activity_tool",
            "--txt-file",
            str(txt_path),
            "--log-folder",
            str(log_folder),
            "--output",
            str(tmp_path / "trace.xlsx"),
            "--no-gui",
            "--verbose",
            "--trace-lines",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    quiet_output = quiet_result.stdout + quiet_result.stderr
    trace_output = trace_result.stdout + trace_result.stderr
    assert "Classifying activity message" not in quiet_output
    assert "Registering start event" not in quiet_output
    assert "Resolving end value" not in quiet_output
    assert "Validating record for axis" not in quiet_output
    assert "Validating duration for axis" not in quiet_output
    assert "Validating PWM association for axis" not in quiet_output
    assert "Classifying activity message" in trace_output
    assert "Validating record for axis" in trace_output


def _workbook_rows(workbook, sheet_name: str) -> tuple[dict[str, int], list[tuple[object, ...]]]:
    """Return workbook rows keyed by header name for regression checks."""

    sheet = workbook[sheet_name]
    headers = [cell.value for cell in sheet[1]]
    return {header: index for index, header in enumerate(headers)}, list(sheet.iter_rows(min_row=2, values_only=True))


def test_april30_partial_log_regression_keeps_distances_and_explains_coverage(tmp_path: Path) -> None:
    """The April 30 one-log sample should keep corrected distances and show partial coverage."""

    repo_root = Path(__file__).resolve().parents[1]
    txt_path = repo_root / "Log" / "UroBiopsy_20260430.txt"
    source_log = repo_root / "Log" / "RobotMovingValues" / "20260430" / "20260430_095017586_initialization.log"
    if not txt_path.exists() or not source_log.exists():
        pytest.skip("April 30 local regression sample is not available.")
    log_folder = tmp_path / "april30_one_log"
    log_folder.mkdir()
    shutil.copy2(source_log, log_folder / source_log.name)
    output_path = tmp_path / "april30-partial.xlsx"

    result = LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=20,
    )

    workbook = load_workbook(output_path, data_only=True)
    assert {
        "Details",
        "Distribution Summary",
        "Distribution Raw Data",
        "Distribution Exclusion Summary",
        "Distribution Eligibility",
        "Log Coverage Summary",
        "Log Coverage Gaps",
        "Distribution Charts",
    } <= set(workbook.sheetnames)
    details_index, details_rows = _workbook_rows(workbook, "Details")

    y_clear = next(
        row
        for row in details_rows
        if row[details_index["Axis"]] == "Y"
        and "start clearing: -19.50" in str(row[details_index["Source TXT Start Line Text"]])
        and row[details_index["Match Status"]] == STATUS_MATCHED
    )
    assert y_clear[details_index["Movement Commanded Distance"]] == pytest.approx(19.50)
    assert y_clear[details_index["Movement Actual Distance"]] == pytest.approx(29.51)
    assert y_clear[details_index["Selected Movement Distance"]] == pytest.approx(29.51)

    x_clear = next(
        row
        for row in details_rows
        if row[details_index["Axis"]] == "X"
        and "start clearing: -22.00" in str(row[details_index["Source TXT Start Line Text"]])
        and row[details_index["Match Status"]] == STATUS_MATCHED
    )
    assert x_clear[details_index["Movement Commanded Distance"]] == pytest.approx(22.00)
    assert x_clear[details_index["Movement Actual Distance"]] == pytest.approx(32.01)
    assert x_clear[details_index["Selected Movement Distance"]] == pytest.approx(32.01)

    h_home = next(
        row
        for row in details_rows
        if row[details_index["Axis"]] == "H"
        and "start moving to home: -25.16" in str(row[details_index["Source TXT Start Line Text"]])
        and row[details_index["Match Status"]] == STATUS_MATCHED
    )
    assert h_home[details_index["Selected Movement Distance"]] == pytest.approx(23.87)

    assert result.distribution_group_count == 18
    assert result.distribution_raw_row_count == 18
    assert result.distribution_chart_count == 0
    chart_message = workbook["Distribution Charts"].cell(row=1, column=1).value
    assert "No distribution charts were generated because all valid groups had fewer than 2 samples." == chart_message

    coverage_index, coverage_rows = _workbook_rows(workbook, "Log Coverage Summary")
    coverage = coverage_rows[0]
    assert coverage[coverage_index["Coverage Ratio (%)"]] < 10
    gaps_index, gaps_rows = _workbook_rows(workbook, "Log Coverage Gaps")
    assert len(gaps_rows) >= 2
    assert gaps_rows[0][gaps_index["Gap Type"]] == "BeforeFirstControlLog"
    assert gaps_rows[-1][gaps_index["Gap Type"]] == "AfterLastControlLog"


def test_april10_bad_duration_pair_remains_rejected(tmp_path: Path) -> None:
    """The old April 10 Z clear across-initialization false match must stay fixed."""

    repo_root = Path(__file__).resolve().parents[1]
    txt_path = repo_root / "Log" / "UroBiopsy_20260410.txt"
    log_folder = repo_root / "Log" / "RobotMovingValues" / "20260410"
    if not txt_path.exists() or not log_folder.exists():
        pytest.skip("April 10 local regression sample is not available.")
    output_path = tmp_path / "april10.xlsx"

    LogAnalysisService().run_analysis(
        txt_file_path=txt_path,
        log_folder_path=log_folder,
        output_path=output_path,
        max_distribution_charts=10,
    )

    workbook = load_workbook(output_path, data_only=True)
    details_index, details_rows = _workbook_rows(workbook, "Details")
    bad_matches = [
        row
        for row in details_rows
        if row[details_index["Match Status"]] == STATUS_MATCHED
        and "2026-04-10 08:37:43:959 MCU   @[Z] start clearing: -50.00"
        in str(row[details_index["Source TXT Start Line Text"]])
        and "2026-04-10 09:20:46:317 MCU   @[Z] motor cleared"
        in str(row[details_index["Source TXT End Line Text"]])
    ]
    assert bad_matches == []

    correct = next(
        row
        for row in details_rows
        if row[details_index["Match Status"]] == STATUS_MATCHED
        and "2026-04-10 09:20:23:541 MCU   @[Z] start clearing: -50.00"
        in str(row[details_index["Source TXT Start Line Text"]])
        and "2026-04-10 09:20:46:317 MCU   @[Z] motor cleared"
        in str(row[details_index["Source TXT End Line Text"]])
    )
    assert correct[details_index["Duration (ms)"]] == 22776
    assert correct[details_index["Duration (s)"]] == pytest.approx(22.776)
