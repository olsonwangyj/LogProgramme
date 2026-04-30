"""Distribution-ready row building, grouping, and duration statistics."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import (
    ALLOW_TARGET_ABSOLUTE_DISTANCE_FALLBACK,
    DISTRIBUTION_ALLOW_PWM_CARRY_FORWARD,
    DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES,
    DISTRIBUTION_DISTANCE_GROUPING_MODE,
    DISTRIBUTION_DISTANCE_SOURCE,
    DURATION_STATUS_VALID,
    MIN_SAMPLES_FOR_NORMAL_FIT,
    MOVEMENT_DISTANCE_BIN_SIZE,
    MOVEMENT_DISTANCE_GROUPING_MODES,
    MOVEMENT_DISTANCE_ROUND_DIGITS,
    MOVEMENT_DISTANCE_SOURCE_OPTIONS,
    PWM_STATUS_MATCHED_CARRY_FORWARD,
    STATUS_MATCHED,
)
from .models import ActivityRecord


@dataclass
class DistributionInputRow:
    """One validated activity record prepared for distribution grouping."""

    group_id: str
    txt_source_file: str
    axis: str
    pwm_percent: float
    movement_start_position: float | None
    movement_target_position: float | None
    movement_end_position: float | None
    movement_commanded_distance: float | None
    movement_actual_distance: float | None
    movement_distance: float
    movement_distance_source: str
    movement_distance_group_value: float
    movement_distance_grouping_mode: str
    movement_distance_rounded: float
    movement_distance_method: str
    movement_distance_notes: str
    rule_id: str
    action_label: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    duration_s: float
    source_record_id: str | None = None
    source_txt_start_line_number: int | None = None
    source_txt_start_line_text: str = ""
    source_txt_end_line_number: int | None = None
    source_txt_end_line_text: str = ""
    pwm_source_file: str = ""
    pwm_raw_value: float | None = None
    pwm_direction: str = ""
    pwm_direction_changed: bool = False
    pwm_conflict: bool = False
    pwm_conflict_reason: str = ""
    pwm_source_line_number: int | None = None
    pwm_source_line_text: str = ""
    pwm_source_time: datetime | None = None
    pwm_match_method: str = ""
    pwm_match_status: str = ""
    pwm_time_delta_ms: int | None = None
    pwm_missing_reason: str = ""
    overall_status: str = ""
    match_status: str = ""
    duration_status: str = ""


@dataclass
class DistributionStats:
    """Statistical result for one distribution group."""

    group_id: str
    txt_source_file: str
    pwm_percent: float
    axis: str
    example_movement_start_position: float | None
    example_movement_target_position: float | None
    example_movement_end_position: float | None
    example_movement_commanded_distance: float | None
    example_movement_actual_distance: float | None
    example_movement_distance: float
    movement_start_position_min: float | None
    movement_start_position_max: float | None
    movement_target_position_min: float | None
    movement_target_position_max: float | None
    movement_end_position_min: float | None
    movement_end_position_max: float | None
    movement_distance_min: float | None
    movement_distance_max: float | None
    unique_position_combination_count: int
    movement_distance_raw_example: float
    movement_distance_group_value: float
    movement_distance_grouping_mode: str
    movement_distance_bin_size: float | None
    movement_distance: float
    movement_distance_rounded: float
    movement_distance_method: str
    movement_distance_source: str
    movement_distance_notes: str
    position_values_mixed: bool
    rule_id: str
    action_label: str
    sample_count: int
    mean_ms: float | None
    mean_s: float | None
    median_ms: float | None
    median_s: float | None
    min_ms: float | None
    max_ms: float | None
    range_ms: float | None
    sample_std_ms: float | None
    sample_std_s: float | None
    sample_var_ms2: float | None
    sample_var_s2: float | None
    population_std_ms: float | None
    population_var_ms2: float | None
    cv_percent: float | None
    p05_ms: float | None
    p25_ms: float | None
    p75_ms: float | None
    p95_ms: float | None
    normal_fit_mean_s: float | None
    normal_fit_std_s: float | None
    normal_fit_variance_s2: float | None
    distribution_status: str
    chart_file: str | None = None
    chart_status: str = "NotGenerated"
    chart_sheet_anchor: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class DistributionExclusion:
    """One activity row excluded from distribution analysis with audit context."""

    reason: str
    rule_id: str
    axis: str
    start_line: str
    notes: str


@dataclass
class DistributionAnalysisResult:
    """Full distribution analysis payload used by service, summary, and export layers."""

    input_rows: list[DistributionInputRow] = field(default_factory=list)
    grouped_rows: dict[str, list[DistributionInputRow]] = field(default_factory=dict)
    stats: list[DistributionStats] = field(default_factory=list)
    exclusion_counts: Counter = field(default_factory=Counter)
    exclusions: list[DistributionExclusion] = field(default_factory=list)
    chart_output_dir: Path | None = None


@dataclass(frozen=True)
class MovementDerivation:
    """Resolved movement fields used for distribution grouping."""

    movement_start_position: float | None
    movement_target_position: float | None
    movement_end_position: float | None
    movement_commanded_distance: float | None
    movement_actual_distance: float | None
    movement_distance: float | None
    movement_distance_source: str
    movement_distance_method: str
    movement_distance_notes: str


class DistributionAnalyzer:
    """Builds distribution groups and computes duration statistics."""

    def __init__(
        self,
        movement_distance_round_digits: int = MOVEMENT_DISTANCE_ROUND_DIGITS,
        min_samples_for_normal_fit: int = MIN_SAMPLES_FOR_NORMAL_FIT,
        include_missing_pwm: bool = False,
        include_missing_movement_distance: bool = False,
        allow_target_absolute_distance_fallback: bool = ALLOW_TARGET_ABSOLUTE_DISTANCE_FALLBACK,
        allowed_pwm_match_statuses: set[str] | None = None,
        distance_source: str = DISTRIBUTION_DISTANCE_SOURCE,
        distance_grouping_mode: str = DISTRIBUTION_DISTANCE_GROUPING_MODE,
        movement_distance_bin_size: float = MOVEMENT_DISTANCE_BIN_SIZE,
        distribution_allow_pwm_carry_forward: bool = DISTRIBUTION_ALLOW_PWM_CARRY_FORWARD,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize distribution analysis options."""

        self.movement_distance_round_digits = movement_distance_round_digits
        self.min_samples_for_normal_fit = min_samples_for_normal_fit
        self.include_missing_pwm = include_missing_pwm
        self.include_missing_movement_distance = include_missing_movement_distance
        self.allow_target_absolute_distance_fallback = allow_target_absolute_distance_fallback
        self.allowed_pwm_match_statuses = (
            set(DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES)
            if allowed_pwm_match_statuses is None
            else set(allowed_pwm_match_statuses)
        )
        self.distance_source = distance_source if distance_source in MOVEMENT_DISTANCE_SOURCE_OPTIONS else "actual_preferred"
        self.distance_grouping_mode = (
            distance_grouping_mode
            if distance_grouping_mode in MOVEMENT_DISTANCE_GROUPING_MODES
            else "bin"
        )
        self.movement_distance_bin_size = movement_distance_bin_size
        self.distribution_allow_pwm_carry_forward = distribution_allow_pwm_carry_forward
        if self.distribution_allow_pwm_carry_forward:
            self.allowed_pwm_match_statuses.add(PWM_STATUS_MATCHED_CARRY_FORWARD)
        self.exclusion_counts: Counter = Counter()
        self.exclusions: list[DistributionExclusion] = []
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def analyze(self, records: list[ActivityRecord], txt_source_file: str) -> DistributionAnalysisResult:
        """Build rows, group them, and compute statistics in one call."""

        input_rows = self.build_input_rows(records, txt_source_file)
        grouped_rows = self.group_rows(input_rows)
        stats = self.compute_group_stats(grouped_rows)
        return DistributionAnalysisResult(
            input_rows=input_rows,
            grouped_rows=grouped_rows,
            stats=stats,
            exclusion_counts=Counter(self.exclusion_counts),
            exclusions=list(self.exclusions),
        )

    def build_input_rows(
        self,
        records: list[ActivityRecord],
        txt_source_file: str,
    ) -> list[DistributionInputRow]:
        """Filter valid matched records and convert them into distribution-ready rows."""

        self._logger.info("Building distribution input rows from %s activity records", len(records))
        self.exclusion_counts = Counter()
        self.exclusions = []
        rows: list[DistributionInputRow] = []
        source_name = Path(txt_source_file).name
        for index, record in enumerate(records, start=1):
            if not self._is_valid_duration_record(record):
                self.exclusion_counts["invalid_status_or_duration"] += 1
                self._record_exclusion("InvalidStatusOrDuration", record)
                continue
            pwm_percent = self._normalize_pwm_percent(record.pwm_percent)
            if pwm_percent is None:
                self.exclusion_counts["missing_pwm"] += 1
                if not self.include_missing_pwm:
                    self._record_exclusion("MissingPWM", record)
                    continue
            if not self._is_reliable_pwm(record):
                self.exclusion_counts["unreliable_pwm"] += 1
                self._record_exclusion("UnreliablePWM", record)
                continue
            movement = self.derive_movement_distance(record)
            if movement.movement_distance is None:
                self.exclusion_counts["missing_true_movement_distance"] += 1
                self.exclusion_counts["missing_movement_distance"] += 1
                if not self.include_missing_movement_distance:
                    self._record_exclusion("MissingTrueMovementDistance", record)
                    continue
            if not record.axis or not record.rule_id:
                self.exclusion_counts["missing_group_field"] += 1
                self._record_exclusion("MissingGroupField", record)
                continue
            movement_distance = movement.movement_distance if movement.movement_distance is not None else math.nan
            movement_distance_rounded = (
                round(movement_distance, self.movement_distance_round_digits)
                if self._is_numeric(movement_distance)
                else math.nan
            )
            movement_distance_group_value = self._group_distance_value(movement_distance)
            duration_ms = float(record.duration_ms)
            duration_s = (
                float(record.duration_s)
                if self._is_numeric(record.duration_s)
                else duration_ms / 1000.0
            )
            action_label = self._action_label(record)
            group_id = self.build_group_id(
                txt_source_file=source_name,
                pwm_percent=pwm_percent,
                axis=record.axis,
                movement_distance_group_value=movement_distance_group_value,
                rule_id=record.rule_id,
            )
            rows.append(
                DistributionInputRow(
                    group_id=group_id,
                    txt_source_file=source_name,
                    axis=record.axis,
                    pwm_percent=float(pwm_percent) if pwm_percent is not None else math.nan,
                    movement_start_position=movement.movement_start_position,
                    movement_target_position=movement.movement_target_position,
                    movement_end_position=movement.movement_end_position,
                    movement_commanded_distance=movement.movement_commanded_distance,
                    movement_actual_distance=movement.movement_actual_distance,
                    movement_distance=float(movement_distance),
                    movement_distance_source=movement.movement_distance_source,
                    movement_distance_group_value=float(movement_distance_group_value),
                    movement_distance_grouping_mode=self.distance_grouping_mode,
                    movement_distance_rounded=float(movement_distance_rounded),
                    movement_distance_method=movement.movement_distance_method,
                    movement_distance_notes=movement.movement_distance_notes,
                    rule_id=record.rule_id,
                    action_label=action_label,
                    start_time=record.start_time,
                    end_time=record.end_time,
                    duration_ms=duration_ms,
                    duration_s=duration_s,
                    source_record_id=self._source_record_id(record, index),
                    source_txt_start_line_number=record.start_line_number or None,
                    source_txt_start_line_text=record.source_txt_start_line,
                    source_txt_end_line_number=record.end_line_number or None,
                    source_txt_end_line_text=record.source_txt_end_line,
                    pwm_source_file=record.pwm_source_file,
                    pwm_raw_value=record.pwm_raw_value,
                    pwm_direction=record.pwm_direction,
                    pwm_direction_changed=record.pwm_direction_changed,
                    pwm_conflict=record.pwm_conflict,
                    pwm_conflict_reason=record.pwm_conflict_reason,
                    pwm_source_line_number=record.pwm_line_number or None,
                    pwm_source_line_text=record.pwm_source_line,
                    pwm_source_time=record.pwm_source_time,
                    pwm_match_method=record.pwm_match_method,
                    pwm_match_status=record.pwm_match_status,
                    pwm_time_delta_ms=record.pwm_time_delta_ms,
                    pwm_missing_reason=record.pwm_missing_reason,
                    overall_status=record.status,
                    match_status=record.match_status,
                    duration_status=record.duration_status,
                )
            )
        self._logger.info("Prepared %s distribution input rows; exclusions: %s", len(rows), dict(self.exclusion_counts))
        return rows

    def group_rows(self, rows: list[DistributionInputRow]) -> dict[str, list[DistributionInputRow]]:
        """Group distribution rows by source, PWM, axis, grouped distance, and rule."""

        grouped: dict[str, list[DistributionInputRow]] = defaultdict(list)
        for row in rows:
            grouped[row.group_id].append(row)
        return dict(grouped)

    def compute_group_stats(
        self,
        grouped_rows: dict[str, list[DistributionInputRow]] | list[DistributionInputRow],
    ) -> list[DistributionStats]:
        """Compute descriptive and normal-fit statistics for every group."""

        if isinstance(grouped_rows, list):
            grouped_rows = self.group_rows(grouped_rows)
        return [
            self._compute_one_group(group_id, rows)
            for group_id, rows in sorted(grouped_rows.items(), key=self._group_sort_key)
        ]

    def derive_movement_distance(self, record: ActivityRecord) -> MovementDerivation:
        """Return selected movement-distance fields according to configured source policy."""

        start_position = self._to_float_or_none(record.movement_start_position)
        target_position = self._to_float_or_none(record.movement_target_position)
        end_position = self._to_float_or_none(record.movement_end_position)
        commanded_distance = self._to_float_or_none(record.movement_commanded_distance)
        actual_distance = self._to_float_or_none(record.movement_actual_distance)
        if commanded_distance is None and start_position is not None and target_position is not None:
            commanded_distance = abs(target_position - start_position)
        if actual_distance is None and start_position is not None and end_position is not None:
            actual_distance = abs(end_position - start_position)

        distance, method, source = self._select_distance(commanded_distance, actual_distance)
        notes = record.movement_distance_notes
        if distance is None and self.allow_target_absolute_distance_fallback and target_position is not None:
            distance = abs(target_position)
            method = "StartTargetAbsoluteValueFallback"
            source = "TargetAbsoluteFallback"
            notes = self._merge_notes(notes, "Target absolute value used because true start position was unavailable.")
        if distance is None:
            method = record.movement_distance_method or "MissingStartOrEndPosition"
            source = ""
        return MovementDerivation(
            movement_start_position=start_position,
            movement_target_position=target_position,
            movement_end_position=end_position,
            movement_commanded_distance=commanded_distance,
            movement_actual_distance=actual_distance,
            movement_distance=distance,
            movement_distance_source=source,
            movement_distance_method=method,
            movement_distance_notes=notes,
        )

    def build_group_id(
        self,
        txt_source_file: str,
        pwm_percent: float | None,
        axis: str,
        movement_distance_group_value: float | None,
        rule_id: str,
    ) -> str:
        """Build a stable, readable group identifier."""

        pwm_label = "Unknown" if pwm_percent is None else f"{float(pwm_percent):g}"
        distance_label = (
            "Missing"
            if movement_distance_group_value is None or not self._is_numeric(movement_distance_group_value)
            else f"{float(movement_distance_group_value):.{self.movement_distance_round_digits}f}"
        )
        base = f"{Path(txt_source_file).stem}_PWM{pwm_label}_Axis{axis}_D{distance_label}_{rule_id}"
        safe_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("_")
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        return f"{safe_base[:90]}_{digest}"

    def _compute_one_group(self, group_id: str, rows: list[DistributionInputRow]) -> DistributionStats:
        """Compute statistics for a single distribution group."""

        first = rows[0]
        series = pd.Series([row.duration_ms for row in rows], dtype="float64")
        sample_count = int(series.count())
        mean_ms = self._finite_or_none(series.mean())
        median_ms = self._finite_or_none(series.median())
        min_ms = self._finite_or_none(series.min())
        max_ms = self._finite_or_none(series.max())
        range_ms = max_ms - min_ms if max_ms is not None and min_ms is not None else None
        sample_std_ms = self._finite_or_none(series.std(ddof=1)) if sample_count > 1 else None
        sample_var_ms2 = self._finite_or_none(series.var(ddof=1)) if sample_count > 1 else None
        population_std_ms = self._finite_or_none(series.std(ddof=0)) if sample_count > 0 else None
        population_var_ms2 = self._finite_or_none(series.var(ddof=0)) if sample_count > 0 else None
        p05_ms = self._finite_or_none(series.quantile(0.05)) if sample_count > 0 else None
        p25_ms = self._finite_or_none(series.quantile(0.25)) if sample_count > 0 else None
        p75_ms = self._finite_or_none(series.quantile(0.75)) if sample_count > 0 else None
        p95_ms = self._finite_or_none(series.quantile(0.95)) if sample_count > 0 else None
        sample_std_s = sample_std_ms / 1000.0 if sample_std_ms is not None else None
        sample_var_s2 = sample_var_ms2 / 1_000_000.0 if sample_var_ms2 is not None else None
        mean_s = mean_ms / 1000.0 if mean_ms is not None else None
        median_s = median_ms / 1000.0 if median_ms is not None else None
        cv_percent = sample_std_ms / mean_ms * 100.0 if sample_std_ms is not None and mean_ms not in {None, 0} else None
        distribution_status, notes = self._distribution_status(sample_count, sample_std_ms)
        normal_fit_mean_s = mean_s if distribution_status == "NormalFitReady" else None
        normal_fit_std_s = sample_std_s if distribution_status == "NormalFitReady" else None
        normal_fit_variance_s2 = sample_var_s2 if distribution_status == "NormalFitReady" else None
        position_values_mixed = self._position_values_mixed(rows)
        movement_notes = self._combine_unique_notes([row.movement_distance_notes for row in rows])
        if position_values_mixed:
            movement_notes = self._merge_notes(movement_notes, "Position values vary within this grouped-distance bin.")
        methods = sorted({row.movement_distance_method for row in rows})
        sources = sorted({row.movement_distance_source for row in rows})
        distance_method = methods[0] if len(methods) == 1 else "Mixed"
        distance_source = sources[0] if len(sources) == 1 else "Mixed"
        if distance_method == "Mixed":
            notes = self._merge_notes(notes, f"Mixed distance methods: {', '.join(methods)}.")
        if distance_source == "Mixed":
            notes = self._merge_notes(notes, f"Mixed distance sources: {', '.join(sources)}.")
        return DistributionStats(
            group_id=group_id,
            txt_source_file=first.txt_source_file,
            pwm_percent=first.pwm_percent,
            axis=first.axis,
            example_movement_start_position=first.movement_start_position,
            example_movement_target_position=first.movement_target_position,
            example_movement_end_position=first.movement_end_position,
            example_movement_commanded_distance=first.movement_commanded_distance,
            example_movement_actual_distance=first.movement_actual_distance,
            example_movement_distance=first.movement_distance,
            movement_start_position_min=self._min_optional(row.movement_start_position for row in rows),
            movement_start_position_max=self._max_optional(row.movement_start_position for row in rows),
            movement_target_position_min=self._min_optional(row.movement_target_position for row in rows),
            movement_target_position_max=self._max_optional(row.movement_target_position for row in rows),
            movement_end_position_min=self._min_optional(row.movement_end_position for row in rows),
            movement_end_position_max=self._max_optional(row.movement_end_position for row in rows),
            movement_distance_min=self._min_optional(row.movement_distance for row in rows),
            movement_distance_max=self._max_optional(row.movement_distance for row in rows),
            unique_position_combination_count=len({self._position_tuple_key(row) for row in rows}),
            movement_distance_raw_example=first.movement_distance,
            movement_distance_group_value=first.movement_distance_group_value,
            movement_distance_grouping_mode=first.movement_distance_grouping_mode,
            movement_distance_bin_size=self.movement_distance_bin_size if self.distance_grouping_mode == "bin" else None,
            movement_distance=first.movement_distance_group_value,
            movement_distance_rounded=first.movement_distance_group_value,
            movement_distance_method=distance_method,
            movement_distance_source=distance_source,
            movement_distance_notes=movement_notes,
            position_values_mixed=position_values_mixed,
            rule_id=first.rule_id,
            action_label=first.action_label,
            sample_count=sample_count,
            mean_ms=mean_ms,
            mean_s=mean_s,
            median_ms=median_ms,
            median_s=median_s,
            min_ms=min_ms,
            max_ms=max_ms,
            range_ms=range_ms,
            sample_std_ms=sample_std_ms,
            sample_std_s=sample_std_s,
            sample_var_ms2=sample_var_ms2,
            sample_var_s2=sample_var_s2,
            population_std_ms=population_std_ms,
            population_var_ms2=population_var_ms2,
            cv_percent=cv_percent,
            p05_ms=p05_ms,
            p25_ms=p25_ms,
            p75_ms=p75_ms,
            p95_ms=p95_ms,
            normal_fit_mean_s=normal_fit_mean_s,
            normal_fit_std_s=normal_fit_std_s,
            normal_fit_variance_s2=normal_fit_variance_s2,
            distribution_status=distribution_status,
            notes=notes,
        )

    def _select_distance(
        self,
        commanded_distance: float | None,
        actual_distance: float | None,
    ) -> tuple[float | None, str, str]:
        """Choose movement distance according to the configured source policy."""

        if self.distance_source == "actual_only":
            if actual_distance is not None:
                return actual_distance, "KnownStartPositionToActualEnd", "ActualEndPosition"
            return None, "MissingStartOrEndPosition", ""
        if self.distance_source == "commanded_only":
            if commanded_distance is not None:
                return commanded_distance, "KnownStartPositionToTarget", "CommandTargetPosition"
            return None, "MissingStartOrTargetPosition", ""
        if self.distance_source == "commanded_preferred":
            if commanded_distance is not None:
                return commanded_distance, "KnownStartPositionToTarget", "CommandTargetPosition"
            if actual_distance is not None:
                return actual_distance, "KnownStartPositionToActualEnd", "ActualEndPosition"
        else:
            if actual_distance is not None:
                return actual_distance, "KnownStartPositionToActualEnd", "ActualEndPosition"
            if commanded_distance is not None:
                return commanded_distance, "KnownStartPositionToTarget", "CommandTargetPosition"
        return None, "MissingStartOrEndPosition", ""

    def _group_distance_value(self, movement_distance: float) -> float:
        """Return the distance value used for distribution grouping."""

        if not self._is_numeric(movement_distance):
            return math.nan
        if self.distance_grouping_mode == "exact":
            return float(movement_distance)
        if self.distance_grouping_mode == "round_digits":
            return round(float(movement_distance), self.movement_distance_round_digits)
        bin_size = self.movement_distance_bin_size
        if not self._is_numeric(bin_size) or bin_size <= 0:
            return round(float(movement_distance), self.movement_distance_round_digits)
        return round(round(float(movement_distance) / bin_size) * bin_size, self.movement_distance_round_digits)

    def _distribution_status(self, sample_count: int, sample_std_ms: float | None) -> tuple[str, str]:
        """Resolve distribution status and note text for a group."""

        if sample_count == 1:
            return "InsufficientSamples", "Only one valid sample; sample SD and variance are not meaningful."
        if sample_count < self.min_samples_for_normal_fit:
            return "InsufficientSamplesForNormalFit", f"Fewer than {self.min_samples_for_normal_fit} samples; normal curve is not drawn."
        if sample_std_ms is None or sample_std_ms == 0:
            return "ZeroVariance", "Zero variance; normal curve not drawn."
        return "NormalFitReady", ""

    def _is_valid_duration_record(self, record: ActivityRecord) -> bool:
        """Return whether a record may be used for duration distribution analysis."""

        return (
            record.match_status == STATUS_MATCHED
            and record.duration_status == DURATION_STATUS_VALID
            and not record.duration_warning
            and self._is_numeric(record.duration_ms)
            and float(record.duration_ms) > 0
            and record.start_time is not None
            and record.end_time is not None
        )

    def _is_reliable_pwm(self, record: ActivityRecord) -> bool:
        """Return whether PWM evidence is reliable enough for same-PWM grouping."""

        return not record.pwm_conflict and record.pwm_match_status in self.allowed_pwm_match_statuses

    def _record_exclusion(self, reason: str, record: ActivityRecord) -> None:
        """Store an auditable exclusion example for workbook aggregation."""

        self.exclusions.append(
            DistributionExclusion(
                reason=reason,
                rule_id=record.rule_id,
                axis=record.axis,
                start_line=record.source_txt_start_line,
                notes=record.notes or record.pwm_missing_reason or record.movement_distance_notes,
            )
        )

    def _normalize_pwm_percent(self, value: object) -> float | None:
        """Normalize signed PWM values to an absolute percentage."""

        numeric = self._to_float_or_none(value)
        return abs(numeric) if numeric is not None else None

    def _action_label(self, record: ActivityRecord) -> str:
        """Build a readable action label from start and end event names."""

        if record.start_event and record.end_event:
            return f"{record.start_event} -> {record.end_event}"
        return record.start_event or record.end_event or record.rule_id

    def _source_record_id(self, record: ActivityRecord, index: int) -> str:
        """Build a small stable source identifier for raw distribution rows."""

        start_line = record.start_line_number or "?"
        end_line = record.end_line_number or "?"
        return f"{start_line}:{end_line}:{index}"

    def _group_sort_key(self, item: tuple[str, list[DistributionInputRow]]) -> tuple:
        """Sort distribution groups by their visible grouping fields."""

        first = item[1][0]
        return (
            first.txt_source_file,
            first.pwm_percent,
            first.axis,
            first.movement_distance_group_value,
            first.rule_id,
        )

    def _position_values_mixed(self, rows: list[DistributionInputRow]) -> bool:
        """Return whether any position or raw distance field varies inside a group."""

        return any(
            len({self._position_key(getattr(row, field_name)) for row in rows}) > 1
            for field_name in (
                "movement_start_position",
                "movement_target_position",
                "movement_end_position",
                "movement_distance",
            )
        )

    def _position_tuple_key(self, row: DistributionInputRow) -> tuple[str, str, str, str]:
        """Return a stable key for unique position combination counts."""

        return (
            self._position_key(row.movement_start_position),
            self._position_key(row.movement_target_position),
            self._position_key(row.movement_end_position),
            self._position_key(row.movement_distance),
        )

    def _position_key(self, value: float | None) -> str:
        """Build a stable comparison key for optional position values."""

        if value is None or not self._is_numeric(value):
            return "None"
        return f"{float(value):.8f}"

    def _min_optional(self, values) -> float | None:
        """Return minimum finite value from an iterable, or None."""

        numbers = [float(value) for value in values if self._is_numeric(value)]
        return min(numbers) if numbers else None

    def _max_optional(self, values) -> float | None:
        """Return maximum finite value from an iterable, or None."""

        numbers = [float(value) for value in values if self._is_numeric(value)]
        return max(numbers) if numbers else None

    def _combine_unique_notes(self, notes: list[str]) -> str:
        """Combine distinct non-empty notes while preserving order."""

        unique_notes: list[str] = []
        for note in notes:
            if note and note not in unique_notes:
                unique_notes.append(note)
        return " | ".join(unique_notes)

    def _to_float_or_none(self, value: object) -> float | None:
        """Convert a numeric-looking value to float, rejecting NaN and infinities."""

        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) else None

    def _is_numeric(self, value: object) -> bool:
        """Return whether a value is a finite number."""

        return self._to_float_or_none(value) is not None

    def _finite_or_none(self, value: object) -> float | None:
        """Return finite floats and turn NaN/infinity into None."""

        return self._to_float_or_none(value)

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Append a note using the report's existing note separator style."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"
