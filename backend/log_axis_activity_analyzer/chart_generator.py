"""Matplotlib chart generation for activity duration distributions."""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from .config import (
    MIN_SAMPLES_FOR_DISTRIBUTION_CHART,
    MIN_SAMPLES_FOR_NORMAL_FIT,
    NORMAL_CHART_BINS,
    NORMAL_DISTRIBUTION_CHART_DPI,
    NORMAL_DISTRIBUTION_CHART_FORMAT,
    NORMAL_DISTRIBUTION_MAX_CHARTS,
)
from .distribution import (
    DistributionInputRow,
    DistributionStats,
    format_movement_distance_group_value,
)


class NormalDistributionChartGenerator:
    """Generates histogram charts with an optional fitted normal PDF overlay."""

    def __init__(
        self,
        min_samples_for_normal_fit: int = MIN_SAMPLES_FOR_NORMAL_FIT,
        min_samples_for_distribution_chart: int = MIN_SAMPLES_FOR_DISTRIBUTION_CHART,
        bins: str | int = NORMAL_CHART_BINS,
        dpi: int = NORMAL_DISTRIBUTION_CHART_DPI,
        chart_format: str = NORMAL_DISTRIBUTION_CHART_FORMAT,
        max_charts: int = NORMAL_DISTRIBUTION_MAX_CHARTS,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize chart generation options."""

        self.min_samples_for_normal_fit = min_samples_for_normal_fit
        self.min_samples_for_distribution_chart = min_samples_for_distribution_chart
        self.bins = bins
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

    def _draw_chart(
        self,
        rows: list[DistributionInputRow],
        stats: DistributionStats,
        chart_path: Path,
    ) -> None:
        """Render one chart to a PNG file."""

        plt = self._pyplot()
        durations_s = [row.duration_s for row in rows]
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        is_zero_variance = stats.sample_count > 1 and len({round(value, 12) for value in durations_s}) == 1
        if is_zero_variance:
            value = durations_s[0]
            ax.axvline(value, color="#1f77b4", linewidth=2.5, label="Identical durations")
            ax.plot(durations_s, [0.02] * len(durations_s), "|", color="#d62728", markersize=16, label="Samples")
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
        else:
            ax.hist(
                durations_s,
                bins=self.bins,
                density=True,
                alpha=0.52,
                color="#4c78a8",
                edgecolor="#263238",
                label="Duration histogram",
            )
            if self._can_draw_normal_curve(stats):
                x_values = self._linspace(min(durations_s), max(durations_s), 240)
                y_values = [
                    self._normal_pdf(x_value, stats.normal_fit_mean_s, stats.normal_fit_std_s)
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
        ax.set_title(self._chart_title(stats), fontsize=10, pad=12)
        ax.set_xlabel("Duration (s)")
        ax.set_ylabel("Density")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        fig.savefig(chart_path, dpi=self.dpi, format=self.chart_format)
        plt.close(fig)

    def _can_draw_normal_curve(self, stats: DistributionStats) -> bool:
        """Return whether a fitted normal curve should be drawn."""

        return (
            stats.sample_count >= self.min_samples_for_normal_fit
            and stats.normal_fit_mean_s is not None
            and stats.normal_fit_std_s is not None
            and stats.normal_fit_std_s > 0
        )

    def _chart_note(self, stats: DistributionStats) -> str:
        """Return an in-chart note for groups without a normal curve."""

        if stats.sample_count < self.min_samples_for_normal_fit:
            return f"Fewer than {self.min_samples_for_normal_fit} samples; normal curve not drawn."
        if stats.sample_std_s in {None, 0}:
            return "Zero variance; normal curve not drawn."
        return "Normal curve not drawn."

    def _chart_title(self, stats: DistributionStats) -> str:
        """Build the required chart title with compact group metadata."""

        mean_text = self._format_number(stats.mean_s, "NA", 3)
        std_text = self._format_number(stats.sample_std_s, "NA", 3)
        return (
            f"{stats.txt_source_file} | Axis {stats.axis} | PWM {stats.pwm_percent:g}% | "
            f"Hardware Actual Distance {self._distance_label(stats)} ({stats.movement_distance_source}) | {stats.rule_id}\n"
            f"N={stats.sample_count}, Mean={mean_text}s, SD={std_text}s"
        )

    def _distance_label(self, stats: DistributionStats) -> str:
        """Return the chart display label for the grouped movement distance."""

        return format_movement_distance_group_value(
            stats.movement_distance_group_value,
            stats.movement_distance_grouping_mode,
            stats.movement_distance_bin_size,
            stats.movement_distance_round_digits,
        )

    def _chart_filename(self, stats: DistributionStats, position: int) -> str:
        """Build a safe chart file name."""

        safe_group = re.sub(r"[^A-Za-z0-9_.-]+", "_", stats.group_id).strip("_")
        return f"{position:03d}_{safe_group[:120]}.{self.chart_format}"

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
