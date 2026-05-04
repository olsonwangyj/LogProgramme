"""Separate workbook export for distribution chart image galleries."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .config import (
    DISTRIBUTION_IMAGE_BLOCK_HEIGHT_ROWS,
    DISTRIBUTION_IMAGE_GALLERY_LAYOUT,
    DISTRIBUTION_IMAGE_GALLERY_LAYOUT_OPTIONS,
    DISTRIBUTION_IMAGE_GALLERY_METADATA_KEYS,
    DISTRIBUTION_IMAGE_GALLERY_INCLUDE_SKIPPED_GROUPS,
    DISTRIBUTION_IMAGE_GALLERY_SHEET_NAME,
    DISTRIBUTION_IMAGE_GRID_BLOCK_WIDTH_COLUMNS,
    DISTRIBUTION_IMAGE_GRID_COLUMNS,
    DISTRIBUTION_IMAGE_HEIGHT_PX,
    DISTRIBUTION_IMAGE_INDEX_COLUMNS,
    DISTRIBUTION_IMAGE_INDEX_SHEET_NAME,
    DISTRIBUTION_IMAGE_MAX_IMAGES,
    DISTRIBUTION_IMAGE_STATISTICS_COLUMNS,
    DISTRIBUTION_IMAGE_STATISTICS_SHEET_NAME,
    DISTRIBUTION_IMAGE_WIDTH_PX,
)
from .distribution import DistributionAnalysisResult, DistributionInputRow, DistributionStats


@dataclass(frozen=True)
class DistributionImageGalleryExportResult:
    """Summary of one image gallery workbook export."""

    output_path: Path
    groups_with_chart_file_path_count: int
    existing_chart_file_count: int
    image_inserted_count: int
    statistics_count: int
    groups_without_charts_count: int
    image_limit_skipped_count: int
    missing_chart_file_count: int
    image_embedding_unavailable_count: int
    image_insert_failed_count: int

    @property
    def chart_file_count(self) -> int:
        """Backward-compatible alias for existing chart files."""

        return self.existing_chart_file_count


class DistributionImageGalleryExporter:
    """Write generated distribution PNGs and key statistics into a separate workbook."""

    def __init__(
        self,
        max_images: int = DISTRIBUTION_IMAGE_MAX_IMAGES,
        image_width_px: int = DISTRIBUTION_IMAGE_WIDTH_PX,
        image_height_px: int = DISTRIBUTION_IMAGE_HEIGHT_PX,
        block_height_rows: int = DISTRIBUTION_IMAGE_BLOCK_HEIGHT_ROWS,
        include_skipped_groups: bool = DISTRIBUTION_IMAGE_GALLERY_INCLUDE_SKIPPED_GROUPS,
        layout: str = DISTRIBUTION_IMAGE_GALLERY_LAYOUT,
        grid_columns: int = DISTRIBUTION_IMAGE_GRID_COLUMNS,
        grid_block_width_columns: int = DISTRIBUTION_IMAGE_GRID_BLOCK_WIDTH_COLUMNS,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize gallery workbook layout options."""

        self.max_images = max_images
        self.image_width_px = image_width_px
        self.image_height_px = image_height_px
        image_rows = math.ceil(image_height_px / 18) + len(DISTRIBUTION_IMAGE_GALLERY_METADATA_KEYS) + 5
        self.block_height_rows = max(block_height_rows, image_rows)
        self.include_skipped_groups = include_skipped_groups
        self.layout = layout if layout in DISTRIBUTION_IMAGE_GALLERY_LAYOUT_OPTIONS else DISTRIBUTION_IMAGE_GALLERY_LAYOUT
        self.grid_columns = max(1, int(grid_columns))
        self.grid_block_width_columns = max(4, int(grid_block_width_columns))
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def export(
        self,
        output_path: Path | str,
        distribution_result: DistributionAnalysisResult,
    ) -> DistributionImageGalleryExportResult:
        """Create the image gallery workbook and return export counts."""

        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.info("Exporting distribution image gallery workbook to %s", path)

        workbook = Workbook()
        gallery_sheet = workbook.active
        gallery_sheet.title = DISTRIBUTION_IMAGE_GALLERY_SHEET_NAME
        statistics_sheet = workbook.create_sheet(DISTRIBUTION_IMAGE_STATISTICS_SHEET_NAME)
        index_sheet = workbook.create_sheet(DISTRIBUTION_IMAGE_INDEX_SHEET_NAME)

        rows_by_group = distribution_result.grouped_rows
        gallery_rows, index_rows, counts = self._build_gallery_and_index(
            gallery_sheet,
            distribution_result.stats,
            rows_by_group,
        )
        statistics_rows = [
            self._statistics_row(stats, rows_by_group.get(stats.group_id, []), gallery_rows[stats.group_id])
            for stats in distribution_result.stats
        ]
        self._write_table(statistics_sheet, DISTRIBUTION_IMAGE_STATISTICS_COLUMNS, statistics_rows)
        self._write_table(index_sheet, DISTRIBUTION_IMAGE_INDEX_COLUMNS, index_rows)
        self._format_gallery_sheet(gallery_sheet)
        self._format_table_sheet(statistics_sheet)
        self._format_table_sheet(index_sheet)

        workbook.save(path)
        self._logger.info(
            "Exported distribution image gallery with %s inserted images and %s statistics rows",
            counts["image_inserted_count"],
            len(statistics_rows),
        )
        return DistributionImageGalleryExportResult(
            output_path=path,
            groups_with_chart_file_path_count=counts["groups_with_chart_file_path_count"],
            existing_chart_file_count=counts["existing_chart_file_count"],
            image_inserted_count=counts["image_inserted_count"],
            statistics_count=len(statistics_rows),
            groups_without_charts_count=counts["groups_without_charts_count"],
            image_limit_skipped_count=counts["image_limit_skipped_count"],
            missing_chart_file_count=counts["missing_chart_file_count"],
            image_embedding_unavailable_count=counts["image_embedding_unavailable_count"],
            image_insert_failed_count=counts["image_insert_failed_count"],
        )

    def _build_gallery_and_index(
        self,
        sheet,
        stats_list: list[DistributionStats],
        rows_by_group: dict[str, list[DistributionInputRow]],
    ) -> tuple[dict[str, dict[str, object]], list[dict[str, object]], dict[str, int]]:
        """Write gallery blocks and build index rows."""

        gallery_rows: dict[str, dict[str, object]] = {}
        index_rows: list[dict[str, object]] = []
        current_row = 1
        image_class = self._openpyxl_image_class()
        image_class_available = image_class is not None
        counts = {
            "groups_with_chart_file_path_count": 0,
            "existing_chart_file_count": 0,
            "image_inserted_count": 0,
            "groups_without_charts_count": 0,
            "image_limit_skipped_count": 0,
            "missing_chart_file_count": 0,
            "image_embedding_unavailable_count": 0,
            "image_insert_failed_count": 0,
        }
        wrote_gallery_block = False
        compact_item_count = 0
        for stats in stats_list:
            first_row = self._first_row(rows_by_group, stats.group_id)
            chart_file = str(stats.chart_file or "")
            chart_path = Path(chart_file) if chart_file else None
            image_status = self._gallery_image_status(
                stats,
                chart_path,
                counts["image_inserted_count"],
                image_class_available,
            )
            image_insert_error = ""
            image_number = None
            anchor = f"A{current_row + len(DISTRIBUTION_IMAGE_GALLERY_METADATA_KEYS) + 2}"
            compact_position: tuple[int, int, str] | None = None
            if image_status == "ImageInserted":
                if self.layout == "compact_grid":
                    compact_position = self._compact_grid_position(compact_item_count)
                    anchor = compact_position[2]
                try:
                    image = image_class(str(chart_path))
                    image.width = self.image_width_px
                    image.height = self.image_height_px
                    sheet.add_image(image, anchor)
                    image_number = counts["image_inserted_count"] + 1
                except Exception as exc:
                    image_status = "ImageInsertFailed"
                    image_insert_error = str(exc)
                    image_number = None
            self._increment_gallery_counts(counts, image_status)
            gallery_row = self._gallery_metadata_row(stats, first_row, image_status, image_insert_error)
            gallery_rows[stats.group_id] = gallery_row
            if self._should_write_gallery_block(image_status):
                wrote_gallery_block = True
                if self.layout == "compact_grid":
                    start_row, start_column, anchor = compact_position or self._compact_grid_position(compact_item_count)
                    compact_item_count += 1
                    self._write_compact_grid_block(sheet, start_row, start_column, gallery_row)
                else:
                    self._write_gallery_block(sheet, current_row, gallery_row)
                if image_status != "ImageInserted" and self.layout != "compact_grid":
                    sheet.cell(
                        row=current_row + len(DISTRIBUTION_IMAGE_GALLERY_METADATA_KEYS) + 2,
                        column=1,
                        value=image_status,
                    )
                if self.layout != "compact_grid":
                    current_row += self.block_height_rows
            if self._should_write_index_row(stats, image_status):
                group_rows = rows_by_group.get(stats.group_id, [])
                index_rows.append(
                    self._index_row(
                        stats,
                        group_rows,
                        image_number,
                        chart_file,
                        anchor if image_status == "ImageInserted" else "",
                        image_status,
                        image_insert_error,
                    )
                )
        if not wrote_gallery_block:
            self._write_no_image_summary(sheet, stats_list, counts, len(stats_list))
        return gallery_rows, index_rows, counts

    def _write_no_image_summary(
        self,
        sheet,
        stats_list: list[DistributionStats],
        counts: dict[str, int],
        statistics_count: int,
    ) -> None:
        """Write a reason-specific summary when no images are inserted into the gallery sheet."""

        summary_rows = [
            ("Image Gallery Summary", ""),
            ("Statistics rows", statistics_count),
            ("Groups with chart file path", counts["groups_with_chart_file_path_count"]),
            ("Existing chart files", counts["existing_chart_file_count"]),
            ("Images inserted", counts["image_inserted_count"]),
            ("Groups without charts", counts["groups_without_charts_count"]),
            ("Images skipped due to image limit", counts["image_limit_skipped_count"]),
            ("Chart files missing", counts["missing_chart_file_count"]),
            ("Image embedding unavailable", counts["image_embedding_unavailable_count"]),
            ("Image insert failures", counts["image_insert_failed_count"]),
            ("Reason", self._no_image_reason(stats_list, counts)),
        ]
        for row_index, (key, value) in enumerate(summary_rows, start=1):
            sheet.cell(row=row_index, column=1, value=key)
            sheet.cell(row=row_index, column=2, value=value)
            sheet.cell(row=row_index, column=1).font = Font(bold=True)

    def _no_image_reason(self, stats_list: list[DistributionStats], counts: dict[str, int]) -> str:
        """Return a clear reason for an image-less gallery sheet."""

        if counts["existing_chart_file_count"] and counts["image_limit_skipped_count"] == counts["existing_chart_file_count"]:
            return f"Chart files were generated, but no images were inserted because the image limit is {self.max_images}."
        if (
            counts["existing_chart_file_count"]
            and counts["image_embedding_unavailable_count"] == counts["existing_chart_file_count"]
        ):
            return "Chart files were generated, but images could not be embedded because openpyxl/Pillow image support is unavailable."
        if counts["groups_with_chart_file_path_count"] and counts["missing_chart_file_count"] == counts["groups_with_chart_file_path_count"]:
            return "Chart metadata exists, but chart image files could not be found."
        if counts["existing_chart_file_count"] and counts["image_insert_failed_count"] == counts["existing_chart_file_count"]:
            return "Chart files were generated, but image insertion failed for every available chart file."
        statuses = {self._display_chart_status(stats) for stats in stats_list}
        if statuses and statuses <= {"SkippedInsufficientSamples", "InsufficientSamples", "InsufficientSamplesForNormalFit"}:
            return "No chart images were generated because all groups had insufficient samples. See Image Statistics."
        if counts["groups_without_charts_count"] == len(stats_list):
            return "No chart images were generated because no distribution group produced a chart file. See Image Statistics."
        return "No chart images were inserted. See Image Statistics for Distribution Status, Chart Status, and Gallery Image Status."

    def _compact_grid_position(self, item_index: int) -> tuple[int, int, str]:
        """Return title row, start column, and image anchor for one compact-grid item."""

        grid_row = item_index // self.grid_columns
        grid_column = item_index % self.grid_columns
        start_row = grid_row * self.block_height_rows + 1
        start_column = grid_column * self.grid_block_width_columns + 1
        image_anchor = f"{get_column_letter(start_column)}{start_row + 2}"
        return start_row, start_column, image_anchor

    def _write_compact_grid_block(self, sheet, start_row: int, start_column: int, metadata: dict[str, object]) -> None:
        """Write a short title block for compact image gallery layout."""

        title = (
            f"{metadata.get('Axis', '')} | PWM {metadata.get('PWM (%)', '')}% | "
            f"Hardware Actual Distance {metadata.get('Hardware Actual Distance Group Display', '')} "
            f"({metadata.get('Hardware Distance Source', '')}) | {metadata.get('Rule ID', '')}"
        )
        subtitle = (
            f"N={metadata.get('Sample Count', '')}, Mean={metadata.get('Mean Duration (s)', '')}, "
            f"SD={metadata.get('Sample SD Duration (s)', '')}, Status={metadata.get('Gallery Image Status', '')}"
        )
        title_cell = sheet.cell(row=start_row, column=start_column, value=title)
        title_cell.font = Font(bold=True)
        sheet.cell(row=start_row + 1, column=start_column, value=subtitle)

    def _write_gallery_block(self, sheet, start_row: int, metadata: dict[str, object]) -> None:
        """Write one chart metadata block."""

        sheet.cell(row=start_row, column=1, value="Distribution Image")
        sheet.cell(row=start_row, column=1).font = Font(bold=True)
        for offset, key in enumerate(DISTRIBUTION_IMAGE_GALLERY_METADATA_KEYS, start=1):
            sheet.cell(row=start_row + offset, column=1, value=key)
            sheet.cell(row=start_row + offset, column=2, value=metadata.get(key))
            sheet.cell(row=start_row + offset, column=1).font = Font(bold=True)

    def _statistics_row(
        self,
        stats: DistributionStats,
        rows: list[DistributionInputRow],
        gallery_row: dict[str, object],
    ) -> dict[str, object]:
        """Build one Image Statistics row from computed stats, not chart text."""

        first_row = rows[0] if rows else None
        population_std_s = stats.population_std_ms / 1000.0 if stats.population_std_ms is not None else None
        population_var_s2 = stats.population_var_ms2 / 1_000_000.0 if stats.population_var_ms2 is not None else None
        return {
            "Group ID": stats.group_id,
            "TXT Source File": stats.txt_source_file,
            "PWM (%)": self._abs_optional(stats.pwm_percent),
            "PWM Raw Values Seen": self._numeric_values_seen(row.pwm_raw_value for row in rows),
            "PWM Directions Seen": self._string_values_seen(row.pwm_direction for row in rows),
            "PWM Direction Mixed": self._values_mixed(row.pwm_direction for row in rows),
            "PWM Raw Value Example": first_row.pwm_raw_value if first_row is not None else None,
            "PWM Direction Example": first_row.pwm_direction if first_row is not None else "",
            "Axis": stats.axis,
            "Selected Group Distance": self._abs_optional(stats.movement_distance),
            "Hardware Actual Distance Group Value": self._abs_optional(stats.movement_distance_group_value),
            "Hardware Actual Distance Group Display": self._distance_display(stats),
            "Movement Distance Grouping Mode": stats.movement_distance_grouping_mode,
            "Movement Distance Bin Size": stats.movement_distance_bin_size,
            "Hardware Actual Distance Raw Example": self._abs_optional(stats.movement_distance_raw_example),
            "Hardware Actual Distance Min": self._abs_optional(stats.movement_distance_min),
            "Hardware Actual Distance Max": self._abs_optional(stats.movement_distance_max),
            "Hardware Motion Source File": first_row.hardware_motion_source_file if first_row is not None else "",
            "Hardware Raw Start Position": first_row.hardware_raw_start_position if first_row is not None else None,
            "Hardware Raw End Position": first_row.hardware_raw_end_position if first_row is not None else None,
            "Hardware Start Position": first_row.hardware_start_position if first_row is not None else None,
            "Hardware End Position": first_row.hardware_end_position if first_row is not None else None,
            "Hardware Actual Distance": first_row.hardware_actual_distance if first_row is not None else None,
            "Position Values Mixed": stats.position_values_mixed,
            "Hardware Distance Source": stats.movement_distance_source,
            "Hardware Distance Method": stats.movement_distance_method,
            "Rule ID": stats.rule_id,
            "Action Label": stats.action_label,
            "Sample Count": stats.sample_count,
            "Mean Duration (ms)": stats.mean_ms,
            "Mean Duration (s)": stats.mean_s,
            "Median Duration (ms)": stats.median_ms,
            "Median Duration (s)": stats.median_s,
            "Sample SD Duration (ms)": stats.sample_std_ms,
            "Sample SD Duration (s)": stats.sample_std_s,
            "Sample Variance Duration (ms^2)": stats.sample_var_ms2,
            "Sample Variance Duration (s^2)": stats.sample_var_s2,
            "Normal Fit Mean (s)": stats.normal_fit_mean_s,
            "Normal Fit Std Dev (s)": stats.normal_fit_std_s,
            "Normal Fit Variance (s^2)": stats.normal_fit_variance_s2,
            "Population SD Duration (ms)": stats.population_std_ms,
            "Population SD Duration (s)": population_std_s,
            "Population Variance Duration (ms^2)": stats.population_var_ms2,
            "Population Variance Duration (s^2)": population_var_s2,
            "Min Duration (ms)": stats.min_ms,
            "Max Duration (ms)": stats.max_ms,
            "P05 Duration (ms)": stats.p05_ms,
            "P25 Duration (ms)": stats.p25_ms,
            "P75 Duration (ms)": stats.p75_ms,
            "P95 Duration (ms)": stats.p95_ms,
            "Coefficient of Variation (%)": stats.cv_percent,
            "Distribution Status": stats.distribution_status,
            "Chart Status": gallery_row["Chart Status"],
            "Gallery Image Status": gallery_row["Gallery Image Status"],
            "Image Insert Error": gallery_row.get("Image Insert Error", ""),
            "Chart File": stats.chart_file,
            "Notes": stats.notes,
        }

    def _gallery_metadata_row(
        self,
        stats: DistributionStats,
        first_row: DistributionInputRow | None,
        image_status: str,
        image_insert_error: str = "",
    ) -> dict[str, object]:
        """Build one Image Gallery metadata block row."""

        return {
            "Group ID": stats.group_id,
            "TXT Source File": stats.txt_source_file,
            "PWM (%)": self._abs_optional(stats.pwm_percent),
            "Axis": stats.axis,
            "Hardware Actual Distance": self._abs_optional(stats.movement_distance),
            "Hardware Actual Distance Group Value": self._abs_optional(stats.movement_distance_group_value),
            "Hardware Actual Distance Group Display": self._distance_display(stats),
            "Hardware Distance Source": stats.movement_distance_source,
            "Hardware Distance Method": stats.movement_distance_method,
            "Movement Distance Grouping Mode": stats.movement_distance_grouping_mode,
            "Movement Distance Bin Size": stats.movement_distance_bin_size,
            "Rule ID": stats.rule_id,
            "Action Label": stats.action_label,
            "Sample Count": stats.sample_count,
            "Mean Duration (s)": stats.mean_s,
            "Sample SD Duration (s)": stats.sample_std_s,
            "Sample Variance Duration (s^2)": stats.sample_var_s2,
            "Chart File": stats.chart_file,
            "Distribution Status": stats.distribution_status,
            "Chart Status": self._display_chart_status(stats),
            "Gallery Image Status": image_status,
            "Image Insert Error": image_insert_error,
            "PWM Raw Value Example": first_row.pwm_raw_value if first_row is not None else None,
        }

    def _index_row(
        self,
        stats: DistributionStats,
        rows: list[DistributionInputRow],
        image_number: int | None,
        chart_file: str,
        anchor: str,
        image_status: str,
        image_insert_error: str = "",
    ) -> dict[str, object]:
        """Build one Image Index row."""

        return {
            "Image Number": image_number,
            "Group ID": stats.group_id,
            "Chart File": chart_file,
            "Excel Anchor": f"{DISTRIBUTION_IMAGE_GALLERY_SHEET_NAME}!{anchor}" if anchor else "",
            "TXT Source File": stats.txt_source_file,
            "Axis": stats.axis,
            "PWM (%)": self._abs_optional(stats.pwm_percent),
            "Hardware Actual Distance Group Value": self._abs_optional(stats.movement_distance_group_value),
            "Hardware Actual Distance Group Display": self._distance_display(stats),
            "Hardware Distance Source": stats.movement_distance_source,
            "Hardware Distance Method": stats.movement_distance_method,
            "Movement Distance Grouping Mode": stats.movement_distance_grouping_mode,
            "Movement Distance Bin Size": stats.movement_distance_bin_size,
            "PWM Raw Values Seen": self._numeric_values_seen(row.pwm_raw_value for row in rows),
            "PWM Directions Seen": self._string_values_seen(row.pwm_direction for row in rows),
            "PWM Direction Mixed": self._values_mixed(row.pwm_direction for row in rows),
            "Rule ID": stats.rule_id,
            "Sample Count": stats.sample_count,
            "Mean Duration (s)": stats.mean_s,
            "Sample SD Duration (s)": stats.sample_std_s,
            "Normal Fit Mean (s)": stats.normal_fit_mean_s,
            "Normal Fit Std Dev (s)": stats.normal_fit_std_s,
            "Normal Fit Variance (s^2)": stats.normal_fit_variance_s2,
            "Chart Status": self._display_chart_status(stats),
            "Gallery Image Status": image_status,
            "Image Insert Error": image_insert_error,
        }

    def _gallery_image_status(
        self,
        stats: DistributionStats,
        chart_path: Path | None,
        inserted_count: int,
        image_class_available: bool,
    ) -> str:
        """Return image insertion status for one group."""

        if not stats.chart_file:
            return self._display_chart_status(stats)
        if chart_path is None or not chart_path.is_file():
            return "Chart File Missing"
        if inserted_count >= self.max_images:
            return "SkippedDueToImageLimit"
        if not image_class_available:
            return "ImageEmbeddingUnavailable"
        return "ImageInserted"

    def _increment_gallery_counts(self, counts: dict[str, int], image_status: str) -> None:
        """Update gallery export counters from one image status."""

        if image_status == "Chart File Missing":
            counts["groups_with_chart_file_path_count"] += 1
            counts["missing_chart_file_count"] += 1
            return
        if image_status in {
            "ImageInserted",
            "SkippedDueToImageLimit",
            "ImageEmbeddingUnavailable",
            "ImageInsertFailed",
        }:
            counts["groups_with_chart_file_path_count"] += 1
            counts["existing_chart_file_count"] += 1
        else:
            counts["groups_without_charts_count"] += 1
            return
        if image_status == "ImageInserted":
            counts["image_inserted_count"] += 1
        if image_status == "SkippedDueToImageLimit":
            counts["image_limit_skipped_count"] += 1
        if image_status == "ImageEmbeddingUnavailable":
            counts["image_embedding_unavailable_count"] += 1
        if image_status == "ImageInsertFailed":
            counts["image_insert_failed_count"] += 1

    def _should_write_gallery_block(self, image_status: str) -> bool:
        """Return whether a full block should appear on Image Gallery."""

        return image_status == "ImageInserted" or self.include_skipped_groups

    def _should_write_index_row(self, stats: DistributionStats, image_status: str) -> bool:
        """Return whether a group should appear in Image Index."""

        return bool(stats.chart_file) or self.include_skipped_groups or image_status == "ImageInserted"

    def _display_chart_status(self, stats: DistributionStats) -> str:
        """Normalize chart status for the standalone gallery workbook."""

        if stats.chart_status == "SkippedInsufficientSamplesForChart":
            return "SkippedInsufficientSamples"
        return stats.chart_status

    def _write_table(self, sheet, columns: list[str], rows: list[dict[str, object]]) -> None:
        """Write a simple headered table."""

        for column_index, column_name in enumerate(columns, start=1):
            cell = sheet.cell(row=1, column=column_index, value=column_name)
            cell.font = Font(bold=True)
        for row_index, row in enumerate(rows, start=2):
            for column_index, column_name in enumerate(columns, start=1):
                sheet.cell(row=row_index, column=column_index, value=row.get(column_name))

    def _format_gallery_sheet(self, sheet) -> None:
        """Apply readable gallery worksheet sizing."""

        sheet.freeze_panes = "A2"
        sheet.column_dimensions["A"].width = 36
        sheet.column_dimensions["B"].width = 96
        if self.layout == "compact_grid":
            for column_index in range(1, self.grid_columns * self.grid_block_width_columns + 1):
                sheet.column_dimensions[get_column_letter(column_index)].width = 14

    def _format_table_sheet(self, sheet) -> None:
        """Apply basic formatting to an index/statistics worksheet."""

        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            values = [str(cell.value) for cell in column if cell.value is not None]
            width = min(max((len(value) for value in values), default=10) + 2, 72)
            sheet.column_dimensions[get_column_letter(column[0].column)].width = width

    def _first_row(
        self,
        rows_by_group: dict[str, list[DistributionInputRow]],
        group_id: str,
    ) -> DistributionInputRow | None:
        """Return the first raw row for one group."""

        rows = rows_by_group.get(group_id) or []
        return rows[0] if rows else None

    def _openpyxl_image_class(self):
        """Return openpyxl Image class when image support is available."""

        try:
            from openpyxl.drawing.image import Image
        except ImportError as exc:  # pragma: no cover - depends on Pillow availability.
            self._logger.warning("Image embedding unavailable for gallery workbook: %s", exc)
            return None
        return Image

    def _abs_optional(self, value: object) -> float | None:
        """Return an absolute finite float or None."""

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return abs(numeric)

    def _numeric_values_seen(self, values) -> str:
        """Return sorted unique numeric values in a compact audit string."""

        unique_values = sorted(
            {
                float(value)
                for value in values
                if value is not None and self._is_finite_number(value)
            }
        )
        return "; ".join(f"{value:g}" for value in unique_values)

    def _string_values_seen(self, values) -> str:
        """Return sorted unique non-empty strings in a compact audit string."""

        unique_values = sorted({str(value) for value in values if value})
        return "; ".join(unique_values)

    def _values_mixed(self, values) -> bool:
        """Return whether more than one non-empty value appears."""

        return len({str(value) for value in values if value}) > 1

    def _is_finite_number(self, value: object) -> bool:
        """Return whether a value can be represented as a finite float."""

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        return math.isfinite(numeric)

    def _distance_display(self, stats: DistributionStats) -> str:
        """Return a readable grouped distance display."""

        from .distribution import format_movement_distance_group_value

        return format_movement_distance_group_value(
            self._abs_optional(stats.movement_distance_group_value),
            stats.movement_distance_grouping_mode,
            stats.movement_distance_bin_size,
            stats.movement_distance_round_digits,
        )
