"""Matplotlib chart generation for activity duration distributions."""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from .config import (
    DISABLE_IQR_OUTLIERS_FOR_LOW_VARIANCE_GROUPS,
    LOW_VARIANCE_STD_THRESHOLD_S,
    MIN_SAMPLES_FOR_DISTRIBUTION_CHART,
    MIN_SAMPLES_FOR_NORMAL_FIT,
    NORMAL_CHART_BINS,
    NORMAL_CHART_Y_AXIS_MODE,
    NORMAL_CHART_Y_AXIS_MODE_OPTIONS,
    NORMAL_DISTRIBUTION_CHART_DPI,
    NORMAL_DISTRIBUTION_CHART_FORMAT,
    NORMAL_DISTRIBUTION_MAX_CHARTS,
)
from .distribution import (
    DistributionInputRow,
    DistributionStats,
    ReferenceDurationInputRow,
    ReferenceDurationStats,
    format_movement_distance_group_value,
)


class NormalDistributionChartGenerator:
    """Generates histogram charts with an optional fitted normal PDF overlay."""

    def __init__(
        self,
        min_samples_for_normal_fit: int = MIN_SAMPLES_FOR_NORMAL_FIT,
        min_samples_for_distribution_chart: int = MIN_SAMPLES_FOR_DISTRIBUTION_CHART,
        bins: str | int = NORMAL_CHART_BINS,
        y_axis_mode: str = NORMAL_CHART_Y_AXIS_MODE,
        low_variance_std_threshold_s: float = LOW_VARIANCE_STD_THRESHOLD_S,
        dpi: int = NORMAL_DISTRIBUTION_CHART_DPI,
        chart_format: str = NORMAL_DISTRIBUTION_CHART_FORMAT,
        max_charts: int = NORMAL_DISTRIBUTION_MAX_CHARTS,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize chart generation options."""

        self.min_samples_for_normal_fit = min_samples_for_normal_fit
        self.min_samples_for_distribution_chart = min_samples_for_distribution_chart
        self.bins = bins
        self.y_axis_mode = y_axis_mode if y_axis_mode in NORMAL_CHART_Y_AXIS_MODE_OPTIONS else "count"
        self.low_variance_std_threshold_s = low_variance_std_threshold_s
        self.dpi = dpi
        self.chart_format = chart_format.lstrip(".").lower()
        self.max_charts = max_charts
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def generate_charts(
        self,
        grouped_rows: dict[str, list[DistributionInputRow]],
        stats: dict[str, DistributionStats],
        output_dir: Path,
    ) -> dict[str, Path]:
        """Generate charts for eligible groups and return group-to-file mapping."""

        output_dir.mkdir(parents=True, exist_ok=True)
        self._logger.info("Generating distribution charts in %s", output_dir)
        generated: dict[str, Path] = {}
        eligible = [
            group_stats
            for group_stats in stats.values()
            if group_stats.sample_count >= self.min_samples_for_distribution_chart
        ]
        eligible.sort(key=lambda item: (-item.sample_count, item.group_id))
        for group_stats in stats.values():
            if group_stats.sample_count < self.min_samples_for_distribution_chart:
                group_stats.chart_status = "SkippedInsufficientSamplesForChart"
                group_stats.notes = self._merge_notes(
                    group_stats.notes,
                    f"Fewer than {self.min_samples_for_distribution_chart} samples; chart not generated.",
                )
        for position, group_stats in enumerate(eligible, start=1):
            rows = grouped_rows.get(group_stats.group_id, [])
            if position > self.max_charts:
                group_stats.chart_status = "SkippedDueToMaxChartLimit"
                group_stats.notes = self._merge_notes(
                    group_stats.notes,
                    f"Chart skipped because max chart count is {self.max_charts}.",
                )
                continue
            try:
                chart_path = output_dir / self._chart_filename(group_stats, position)
                self._draw_chart(rows, group_stats, chart_path)
            except Exception as exc:  # pragma: no cover - defensive around local rendering backends.
                self._logger.exception("Failed to generate chart for group %s", group_stats.group_id)
                group_stats.chart_status = "ChartFailed"
                group_stats.notes = self._merge_notes(group_stats.notes, f"Chart generation failed: {exc}")
                continue
            group_stats.chart_file = str(chart_path)
            group_stats.chart_status = "ChartGenerated"
            generated[group_stats.group_id] = chart_path
        self._logger.info("Generated %s distribution chart files", len(generated))
        return generated

    def generate_reference_charts(
        self,
        grouped_rows: dict[str, list[ReferenceDurationInputRow]],
        stats: dict[str, ReferenceDurationStats],
        output_dir: Path,
    ) -> dict[str, Path]:
        """Generate charts for search-reference duration groups."""

        output_dir.mkdir(parents=True, exist_ok=True)
        self._logger.info("Generating reference duration charts in %s", output_dir)
        generated: dict[str, Path] = {}
        eligible = [
            group_stats
            for group_stats in stats.values()
            if group_stats.sample_count >= self.min_samples_for_distribution_chart
        ]
        eligible.sort(key=lambda item: (-item.sample_count, item.group_id))
        for group_stats in stats.values():
            if group_stats.sample_count < self.min_samples_for_distribution_chart:
                group_stats.chart_status = "SkippedInsufficientSamplesForChart"
                group_stats.notes = self._merge_notes(
                    group_stats.notes,
                    f"Fewer than {self.min_samples_for_distribution_chart} samples; chart not generated.",
                )
        for position, group_stats in enumerate(eligible, start=1):
            rows = grouped_rows.get(group_stats.group_id, [])
            if position > self.max_charts:
                group_stats.chart_status = "SkippedDueToMaxChartLimit"
                group_stats.notes = self._merge_notes(
                    group_stats.notes,
                    f"Chart skipped because max chart count is {self.max_charts}.",
                )
                continue
            try:
                chart_path = output_dir / self._chart_filename(group_stats, position, prefix="ref")
                self._draw_chart(rows, group_stats, chart_path)
            except Exception as exc:  # pragma: no cover - defensive around local rendering backends.
                self._logger.exception("Failed to generate reference chart for group %s", group_stats.group_id)
                group_stats.chart_status = "ChartFailed"
                group_stats.notes = self._merge_notes(group_stats.notes, f"Chart generation failed: {exc}")
                continue
            group_stats.chart_file = str(chart_path)
            group_stats.chart_status = "ChartGenerated"
            generated[group_stats.group_id] = chart_path
        self._logger.info("Generated %s reference duration chart files", len(generated))
        return generated

    def _draw_chart(
        self,
        rows: list[DistributionInputRow] | list[ReferenceDurationInputRow],
        stats: DistributionStats | ReferenceDurationStats,
        chart_path: Path,
    ) -> None:
        """Render one chart to a PNG file."""

        plt = self._pyplot()
        durations_s = [row.duration_s for row in rows]
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        is_zero_variance = stats.sample_count > 1 and len({round(value, 12) for value in durations_s}) == 1
        is_low_variance = (
            not is_zero_variance
            and stats.sample_std_s is not None
            and stats.sample_std_s < self.low_variance_std_threshold_s
        )
        outlier_info = self._outlier_info(durations_s)
        if is_low_variance and DISABLE_IQR_OUTLIERS_FOR_LOW_VARIANCE_GROUPS:
            outlier_info = {"outliers": [], "inliers": durations_s}
        if is_zero_variance:
            value = durations_s[0]
            ax.axvline(value, color="#1f77b4", linewidth=2.5, label="Identical durations")
            ax.plot(durations_s, [1] * len(durations_s), "|", color="#d62728", markersize=16, label="Samples")
            ax.text(
                0.02,
                0.92,
                "Zero variance; normal curve not drawn.",
                transform=ax.transAxes,
                fontsize=9,
                va="top",
            )
            pad = max(abs(value) * 0.05, 0.5)
            ax.set_xlim(value - pad, value + pad)
            ax.set_ylim(0, max(2, len(durations_s)))
        elif is_low_variance:
            self._draw_low_variance_chart(ax, durations_s, stats)
            if outlier_info["outliers"]:
                self._apply_outlier_trim(ax, durations_s, stats, outlier_info)
        else:
            density_mode = self.y_axis_mode == "density"
            histogram_values, bin_edges, _ = ax.hist(
                durations_s,
                bins=self.bins,
                density=density_mode,
                alpha=0.52,
                color="#4c78a8",
                edgecolor="#263238",
                label="Duration histogram",
            )
            if self._can_draw_normal_curve(stats):
                x_min, x_max = self._chart_x_bounds(durations_s, outlier_info)
                x_values = self._linspace(x_min, x_max, 240)
                bin_width = self._histogram_bin_width(bin_edges, durations_s)
                y_values = [
                    self._normal_curve_y_value(
                        x_value,
                        stats,
                        sample_count=len(durations_s),
                        bin_width=bin_width,
                    )
                    for x_value in x_values
                ]
                ax.plot(x_values, y_values, color="#e45756", linewidth=2.0, label="Fitted normal curve")
            else:
                ax.text(
                    0.02,
                    0.92,
                    self._chart_note(stats),
                    transform=ax.transAxes,
                    fontsize=9,
                    va="top",
                )
            if outlier_info["outliers"]:
                self._apply_outlier_trim(ax, durations_s, stats, outlier_info)
        ax.set_title(self._chart_title(stats), fontsize=10, pad=12)
        ax.set_xlabel("Duration (s)")
        ax.set_ylabel("Density" if self.y_axis_mode == "density" else "Count")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        fig.savefig(chart_path, dpi=self.dpi, format=self.chart_format)
        plt.close(fig)

    def _can_draw_normal_curve(self, stats: DistributionStats | ReferenceDurationStats) -> bool:
        """Return whether a fitted normal curve should be drawn."""

        return (
            stats.sample_count >= self.min_samples_for_normal_fit
            and stats.normal_fit_mean_s is not None
            and stats.normal_fit_std_s is not None
            and stats.normal_fit_std_s > 0
        )

    def _chart_note(self, stats: DistributionStats | ReferenceDurationStats) -> str:
        """Return an in-chart note for groups without a normal curve."""

        if stats.sample_count < self.min_samples_for_normal_fit:
            return f"Fewer than {self.min_samples_for_normal_fit} samples; normal curve not drawn."
        if stats.sample_std_s in {None, 0}:
            return "Zero variance; normal curve not drawn."
        return "Normal curve not drawn."

    def _chart_title(self, stats: DistributionStats | ReferenceDurationStats) -> str:
        """Build the required chart title with compact group metadata."""

        mean_text = self._format_number(stats.mean_s, "NA", 3)
        std_text = self._format_number(stats.sample_std_s, "NA", 3)
        if getattr(stats, "chart_type", "") == "Reference Duration Distribution":
            return (
                f"Reference Duration Distribution | Axis {stats.axis} | {stats.action_label} | "
                "Distance = Not Applicable\n"
                f"N={stats.sample_count}, Mean={mean_text}s, SD={std_text}s"
            )
        return (
            f"Motion Duration Distribution | Axis {stats.axis} | PWM {stats.pwm_percent:g}% | "
            f"Hardware Actual Distance {self._distance_label(stats)} ({stats.movement_distance_source}) | {stats.rule_id}\n"
            f"N={stats.sample_count}, Mean={mean_text}s, SD={std_text}s"
        )

    def _distance_label(self, stats: DistributionStats | ReferenceDurationStats) -> str:
        """Return the chart display label for the grouped movement distance."""

        return format_movement_distance_group_value(
            stats.movement_distance_group_value,
            stats.movement_distance_grouping_mode,
            stats.movement_distance_bin_size,
            stats.movement_distance_round_digits,
        )

    def _chart_filename(
        self,
        stats: DistributionStats | ReferenceDurationStats,
        position: int,
        prefix: str = "",
    ) -> str:
        """Build a safe chart file name."""

        safe_group = re.sub(r"[^A-Za-z0-9_.-]+", "_", stats.group_id).strip("_")
        prefix_text = f"{prefix}_" if prefix else ""
        return f"{position:03d}_{prefix_text}{safe_group[:120]}.{self.chart_format}"

    def _linspace(self, start: float, stop: float, count: int) -> list[float]:
        """Return evenly spaced values without requiring numpy in this module."""

        if count <= 1 or start == stop:
            return [start]
        span = stop - start
        pad = max(abs(span) * 0.08, 0.001)
        lower = start - pad
        upper = stop + pad
        step = (upper - lower) / (count - 1)
        return [lower + index * step for index in range(count)]

    def _normal_pdf(self, x_value: float, mean: float | None, std: float | None) -> float:
        """Compute the normal probability density function manually."""

        if mean is None or std is None or std <= 0:
            return 0.0
        coefficient = 1.0 / (std * math.sqrt(2.0 * math.pi))
        z_value = (x_value - mean) / std
        return coefficient * math.exp(-0.5 * z_value * z_value)

    def _normal_curve_y_value(
        self,
        x_value: float,
        stats: DistributionStats | ReferenceDurationStats,
        sample_count: int,
        bin_width: float,
    ) -> float:
        """Return the normal curve value in the configured y-axis units."""

        density_value = self._normal_pdf(x_value, stats.normal_fit_mean_s, stats.normal_fit_std_s)
        if self.y_axis_mode == "density":
            return density_value
        return density_value * sample_count * bin_width

    def _draw_low_variance_chart(
        self,
        ax,
        durations_s: list[float],
        stats: DistributionStats | ReferenceDurationStats,
    ) -> None:
        """Draw a clearer sample-dot chart for groups with very small variance."""

        mean_value = stats.mean_s if stats.mean_s is not None else sum(durations_s) / len(durations_s)
        median_value = stats.median_s if stats.median_s is not None else sorted(durations_s)[len(durations_s) // 2]
        std_value = stats.sample_std_s or 0.0
        y_values = [1.0 + (index % 5) * 0.08 for index, _ in enumerate(durations_s)]
        ax.plot(durations_s, y_values, "o", color="#4c78a8", markersize=4, label="Samples")
        ax.plot(durations_s, [0.35] * len(durations_s), "|", color="#263238", markersize=12, label="Rug marks")
        ax.axvline(mean_value, color="#e45756", linewidth=2.0, label="Mean")
        ax.axvline(median_value, color="#54a24b", linewidth=1.5, linestyle="--", label="Median")
        if std_value > 0:
            ax.axvspan(mean_value - std_value, mean_value + std_value, color="#f2cf5b", alpha=0.25, label="Mean +/- 1 SD")
        ax.text(0.02, 0.92, "Low variance group", transform=ax.transAxes, fontsize=9, va="top")
        lower = min(durations_s + [mean_value - std_value])
        upper = max(durations_s + [mean_value + std_value])
        pad = max((upper - lower) * 0.35, 0.05)
        ax.set_xlim(lower - pad, upper + pad)
        ax.set_ylim(0, 1.6)

    def _outlier_info(self, durations_s: list[float]) -> dict[str, object]:
        """Return IQR outlier details for chart readability."""

        if len(durations_s) < 4:
            return {"outliers": [], "inliers": durations_s}
        sorted_values = sorted(float(value) for value in durations_s)
        q1 = self._percentile(sorted_values, 0.25)
        q3 = self._percentile(sorted_values, 0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = [value for value in sorted_values if value < lower or value > upper]
        inliers = [value for value in sorted_values if lower <= value <= upper]
        return {"outliers": outliers, "inliers": inliers or sorted_values, "lower": lower, "upper": upper}

    def _apply_outlier_trim(
        self,
        ax,
        durations_s: list[float],
        stats: DistributionStats | ReferenceDurationStats,
        outlier_info: dict[str, object],
    ) -> None:
        """Trim the visible x-axis to inliers while preserving outlier annotation."""

        inliers = list(outlier_info.get("inliers") or durations_s)
        if not inliers:
            return
        lower = min(inliers)
        upper = max(inliers)
        full_lower = min(durations_s)
        full_upper = max(durations_s)
        if lower <= full_lower and upper >= full_upper:
            return
        pad = max((upper - lower) * 0.2, 0.1)
        ax.set_xlim(lower - pad, upper + pad)
        stats.chart_uses_outlier_trimmed_axis = True
        ax.text(
            0.02,
            0.82,
            "Outliers detected; x-axis trimmed for readability.",
            transform=ax.transAxes,
            fontsize=9,
            va="top",
        )

    def _chart_x_bounds(self, durations_s: list[float], outlier_info: dict[str, object]) -> tuple[float, float]:
        """Return x bounds for normal curve generation."""

        inliers = list(outlier_info.get("inliers") or durations_s)
        return min(inliers), max(inliers)

    def _histogram_bin_width(self, bin_edges, durations_s: list[float]) -> float:
        """Estimate histogram bin width for count-scaled normal curves."""

        try:
            edges = [float(value) for value in bin_edges]
        except TypeError:
            edges = []
        widths = [
            edges[index + 1] - edges[index]
            for index in range(len(edges) - 1)
            if edges[index + 1] > edges[index]
        ]
        if widths:
            return sum(widths) / len(widths)
        span = max(durations_s) - min(durations_s)
        if span > 0 and isinstance(self.bins, int) and self.bins > 0:
            return span / self.bins
        return max(span, 1.0)

    def _percentile(self, sorted_values: list[float], fraction: float) -> float:
        """Return a simple interpolated percentile."""

        if not sorted_values:
            return math.nan
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = (len(sorted_values) - 1) * fraction
        lower_index = int(math.floor(position))
        upper_index = int(math.ceil(position))
        if lower_index == upper_index:
            return sorted_values[lower_index]
        weight = position - lower_index
        return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight

    def _format_number(self, value: float | None, fallback: str, digits: int) -> str:
        """Format an optional float for chart text."""

        if value is None:
            return fallback
        return f"{value:.{digits}f}"

    def _pyplot(self):
        """Import matplotlib lazily and force a non-interactive backend."""

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Append a note using the report's existing note separator style."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"
