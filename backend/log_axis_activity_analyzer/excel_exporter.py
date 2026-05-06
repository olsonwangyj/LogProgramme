"""Excel workbook export with Details, Summary, and PWM Sources worksheets."""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill

from .config import (
    AXIS_SUMMARY_MEAN_RED_THRESHOLD,
    AXIS_SUMMARY_MEAN_YELLOW_THRESHOLD,
    DISTRIBUTION_CHART_BLOCK_HEIGHT,
    DISTRIBUTION_CHART_IMAGE_ROW_OFFSET,
    DISTRIBUTION_CHART_METADATA_KEYS,
    REFERENCE_DURATION_CHART_METADATA_COLUMNS,
)


class ExcelExporter:
    """Writes workbook tables and basic formatting to an `.xlsx` file."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the exporter with an optional logger."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def export(
        self,
        output_path: Path | str,
        report_frames,
        metadata: dict[str, object],
    ) -> Path:
        """Write the workbook and return the resolved output path."""

        path = Path(output_path)
        self._logger.info("Exporting workbook to %s", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._build_writer(path) as writer:
            report_frames.details.to_excel(writer, sheet_name="Details", index=False)
            self._write_summary_sheet(writer, report_frames, metadata)
            self._write_pwm_sources_sheet(writer, report_frames)
            self._write_hardware_motion_segments_sheet(writer, report_frames)
            self._write_hardware_reference_events_sheet(writer, report_frames)
            self._write_diagnostics_sheet(writer, report_frames)
            self._write_diagnostics_summary_sheet(writer, report_frames)
            self._write_distribution_summary_sheet(writer, report_frames)
            self._write_distribution_raw_data_sheet(writer, report_frames)
            self._write_reference_duration_summary_sheet(writer, report_frames)
            self._write_reference_duration_raw_data_sheet(writer, report_frames)
            self._write_reference_exclusion_summary_sheet(writer, report_frames)
            self._write_axis_action_summary_sheet(writer, report_frames)
            self._write_distribution_eligibility_summary_sheet(writer, report_frames)
            self._write_distribution_exclusion_summary_sheet(writer, report_frames)
            self._write_log_coverage_summary_sheet(writer, report_frames)
            self._write_log_coverage_gaps_sheet(writer, report_frames)
            self._write_distribution_charts_sheet(
                writer,
                report_frames,
                embed_charts=bool(metadata.get("embed_distribution_charts", True)),
                chart_output_dir=metadata.get("distribution_output_dir_full", ""),
            )
            self._write_reference_duration_charts_sheet(
                writer,
                report_frames,
                embed_charts=bool(metadata.get("embed_distribution_charts", True)),
                chart_output_dir=metadata.get("distribution_output_dir_full", ""),
            )
            self._format_details_sheet(writer)
            self._format_summary_sheet(writer)
            self._format_pwm_sources_sheet(writer)
            self._format_hardware_motion_segments_sheet(writer)
            self._format_hardware_reference_events_sheet(writer)
            self._format_diagnostics_sheet(writer)
            self._format_diagnostics_summary_sheet(writer)
            self._format_distribution_summary_sheet(writer)
            self._format_distribution_raw_data_sheet(writer)
            self._format_reference_duration_summary_sheet(writer)
            self._format_reference_duration_raw_data_sheet(writer)
            self._format_reference_exclusion_summary_sheet(writer)
            self._format_axis_action_summary_sheet(writer)
            self._format_distribution_eligibility_summary_sheet(writer)
            self._format_distribution_exclusion_summary_sheet(writer)
            self._format_log_coverage_summary_sheet(writer)
            self._format_log_coverage_gaps_sheet(writer)
            self._format_distribution_charts_sheet(writer)
            self._format_reference_duration_charts_sheet(writer)
        self._logger.info("Workbook export completed at %s", path)
        return path

    def _build_writer(self, output_path: Path):
        """Create the pandas Excel writer used for workbook generation."""

        self._logger.debug("Creating Excel writer for %s", output_path)
        import pandas as pd

        return pd.ExcelWriter(output_path, engine="openpyxl")

    def _write_summary_sheet(self, writer, report_frames, metadata: dict[str, object]) -> None:
        """Write workbook metadata plus both summary tables."""

        self._logger.debug("Writing Summary sheet")
        summary_sheet_name = "Summary"
        metadata_rows = [
            {"Key": "TXT File", "Value": self._basename(metadata["txt_file_path"])},
            {"Key": "Log Folder", "Value": self._basename(metadata["log_folder_path"])},
            {"Key": "Generated Workbook", "Value": self._basename(metadata["output_path"])},
            {"Key": "Association Strategy", "Value": metadata["association_strategy"]},
            {"Key": "TXT Axis Events Parsed", "Value": metadata["txt_axis_event_count"]},
            {"Key": "TXT Boundary Events Parsed", "Value": metadata["boundary_event_count"]},
            {"Key": "Log Files Scanned", "Value": metadata["log_file_count"]},
            {"Key": "PWM Profiles Found", "Value": metadata["pwm_profile_count"]},
            {"Key": "Matched Count", "Value": metadata["matched_count"]},
            {"Key": "Unmatched Start Count", "Value": metadata["unmatched_start_count"]},
            {"Key": "Unmatched End Count", "Value": metadata["unmatched_end_count"]},
            {"Key": "Parse Warning Count", "Value": metadata["parse_warning_count"]},
            {"Key": "Closed By Boundary Count", "Value": metadata["closed_by_boundary_count"]},
            {"Key": "Closed By New Start Count", "Value": metadata["closed_by_new_start_count"]},
            {"Key": "Initialization Failed Count", "Value": metadata["initialization_failed_count"]},
            {"Key": "Diagnostic Count", "Value": metadata["diagnostic_count"]},
            {"Key": "Duration Warning Count", "Value": metadata["duration_warning_count"]},
            {"Key": "PWM Warning Count", "Value": metadata["pwm_warning_count"]},
            {"Key": "Hardware Matched By Overlap", "Value": metadata.get("hardware_matched_by_overlap_count", 0)},
            {"Key": "Hardware Nearest Previous", "Value": metadata.get("hardware_nearest_previous_count", 0)},
            {"Key": "Hardware Nearest Future", "Value": metadata.get("hardware_nearest_future_count", 0)},
            {"Key": "Hardware Nearest Generic", "Value": metadata.get("hardware_nearest_count", 0)},
            {"Key": "Hardware Multiple Candidates", "Value": metadata.get("hardware_multiple_candidates_count", 0)},
            {"Key": "Hardware No Segment Found", "Value": metadata.get("hardware_no_segment_found_count", 0)},
            {"Key": "Hardware Segment Incomplete", "Value": metadata.get("hardware_segment_incomplete_count", 0)},
            {"Key": "Hardware Warning Count", "Value": metadata.get("hardware_warning_count", 0)},
            {
                "Key": "Hardware Duplicate Segment Groups",
                "Value": metadata.get("hardware_duplicate_segment_group_count", 0),
            },
            {
                "Key": "Hardware Duplicate Segment Rows",
                "Value": metadata.get("hardware_duplicate_segment_row_count", 0),
            },
            {"Key": "Matched + Hardware-Overlap Rows", "Value": metadata.get("matched_hardware_overlap_count", 0)},
            {"Key": "Matched Missing Hardware Distance", "Value": metadata.get("matched_missing_hardware_distance_count", 0)},
            {"Key": "Matched Hardware Warning Rows", "Value": metadata.get("matched_hardware_warning_count", 0)},
        ]
        if metadata.get("distribution_enabled"):
            metadata_rows.extend(
                [
                    {"Key": "Distribution Groups", "Value": metadata.get("distribution_group_count", 0)},
                    {"Key": "Distribution Eligible Rows", "Value": metadata.get("distribution_eligible_row_count", 0)},
                    {"Key": "Distribution Raw Rows", "Value": metadata.get("distribution_raw_row_count", 0)},
                    {"Key": "Distribution Charts Generated", "Value": metadata.get("distribution_chart_count", 0)},
                    {"Key": "Reference Duration Groups", "Value": metadata.get("reference_distribution_group_count", 0)},
                    {"Key": "Reference Duration Raw Rows", "Value": metadata.get("reference_distribution_raw_row_count", 0)},
                    {
                        "Key": "Reference Duration Rows Excluded Too Short",
                        "Value": metadata.get("reference_distribution_excluded_short_count", 0),
                    },
                    {"Key": "Reference Duration Charts Generated", "Value": metadata.get("reference_distribution_chart_count", 0)},
                    {"Key": "Distribution Chart Output Folder", "Value": self._basename(metadata.get("distribution_output_dir", ""))},
                    {
                        "Key": "Distribution Distance Source",
                        "Value": metadata.get("distribution_distance_source", ""),
                    },
                    {
                        "Key": "Distribution Distance Grouping Mode",
                        "Value": metadata.get("distribution_distance_grouping_mode", ""),
                    },
                    {
                        "Key": "Movement Distance Bin Size",
                        "Value": metadata.get("movement_distance_bin_size", ""),
                    },
                    {
                        "Key": "Distribution Excluded Missing PWM",
                        "Value": metadata.get("distribution_excluded_missing_pwm_count", 0),
                    },
                    {
                        "Key": "Distribution Excluded Missing Movement Distance",
                        "Value": metadata.get("distribution_excluded_missing_distance_count", 0),
                    },
                    {
                        "Key": "Distribution Excluded Missing True Movement Distance",
                        "Value": metadata.get("distribution_excluded_missing_true_distance_count", 0),
                    },
                    {
                        "Key": "Distribution Excluded Unreliable PWM",
                        "Value": metadata.get("distribution_excluded_unreliable_pwm_count", 0),
                    },
                    {
                        "Key": "Distribution Excluded Unreliable Hardware Match",
                        "Value": metadata.get("distribution_excluded_unreliable_hardware_count", 0),
                    },
                    {
                        "Key": "Distribution Excluded Multiple Reasons",
                        "Value": metadata.get("distribution_excluded_multiple_reasons_count", 0),
                    },
                    {
                        "Key": "Distribution Exclusion Reason Counts",
                        "Value": metadata.get("distribution_exclusion_reason_counts", ""),
                    },
                    {
                        "Key": "Distribution Image Gallery Workbook",
                        "Value": self._basename(metadata.get("distribution_image_gallery_path", "")),
                    },
                    {
                        "Key": "Distribution Image Gallery Metadata Note",
                        "Value": metadata.get("distribution_image_gallery_metadata_note", ""),
                    },
                    {
                        "Key": "Log Coverage Warning",
                        "Value": metadata.get("log_coverage_warning", ""),
                    },
                    {
                        "Key": "PWM Carry Forward Enabled",
                        "Value": metadata.get("pwm_carry_forward_enabled", False),
                    },
                    {
                        "Key": "Distribution Allows Carry Forward PWM",
                        "Value": metadata.get("distribution_allows_carry_forward_pwm", False),
                    },
                ]
            )
        import pandas as pd

        pd.DataFrame(metadata_rows).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=0)
        event_summary_start_row = len(metadata_rows) + 3
        report_frames.event_summary.to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=event_summary_start_row)
        axis_start_row = event_summary_start_row + len(report_frames.event_summary.index) + 3
        report_frames.axis_summary.to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=axis_start_row)
        sheet = writer.sheets[summary_sheet_name]
        sheet.cell(row=event_summary_start_row, column=1, value="Summary by Axis and Event Type")
        sheet.cell(row=event_summary_start_row, column=1).font = Font(bold=True)
        sheet.cell(row=axis_start_row, column=1, value="Summary by Axis")
        sheet.cell(row=axis_start_row, column=1).font = Font(bold=True)

    def _write_pwm_sources_sheet(self, writer, report_frames) -> None:
        """Write the optional PWM Sources sheet when rows are available."""

        self._logger.debug("Writing PWM Sources sheet")
        if report_frames.pwm_sources is None:
            return
        report_frames.pwm_sources.to_excel(writer, sheet_name="PWM Sources", index=False)

    def _write_hardware_motion_segments_sheet(self, writer, report_frames) -> None:
        """Write parsed hardware TPOS motion segments for audit/debugging."""

        self._logger.debug("Writing Hardware Motion Segments sheet")
        if getattr(report_frames, "hardware_motion_segments", None) is None:
            return
        report_frames.hardware_motion_segments.to_excel(
            writer,
            sheet_name="Hardware Motion Segments",
            index=False,
        )

    def _write_hardware_reference_events_sheet(self, writer, report_frames) -> None:
        """Write parsed hardware TPOS reference evidence for audit/debugging."""

        self._logger.debug("Writing Hardware Reference Events sheet")
        if getattr(report_frames, "hardware_reference_events", None) is None:
            return
        report_frames.hardware_reference_events.to_excel(
            writer,
            sheet_name="Hardware Reference Events",
            index=False,
        )

    def _write_diagnostics_sheet(self, writer, report_frames) -> None:
        """Write the optional Diagnostics sheet when structured diagnostics are available."""

        self._logger.debug("Writing Diagnostics sheet")
        if report_frames.diagnostics is None:
            return
        report_frames.diagnostics.to_excel(writer, sheet_name="Diagnostics", index=False)

    def _write_diagnostics_summary_sheet(self, writer, report_frames) -> None:
        """Write diagnostic aggregates to their own sheet."""

        self._logger.debug("Writing Diagnostics Summary sheet")
        if report_frames.diagnostics_summary is None:
            return
        report_frames.diagnostics_summary.to_excel(writer, sheet_name="Diagnostics Summary", index=False)

    def _write_distribution_summary_sheet(self, writer, report_frames) -> None:
        """Write distribution statistics to their own sheet."""

        self._logger.debug("Writing Distribution Summary sheet")
        if report_frames.distribution_summary is None:
            return
        report_frames.distribution_summary.to_excel(writer, sheet_name="Distribution Summary", index=False)

    def _write_distribution_raw_data_sheet(self, writer, report_frames) -> None:
        """Write the valid rows used by distribution analysis."""

        self._logger.debug("Writing Distribution Raw Data sheet")
        if report_frames.distribution_raw_data is None:
            return
        report_frames.distribution_raw_data.to_excel(writer, sheet_name="Distribution Raw Data", index=False)

    def _write_reference_duration_summary_sheet(self, writer, report_frames) -> None:
        """Write search-reference duration statistics."""

        self._logger.debug("Writing Reference Duration Summary sheet")
        if getattr(report_frames, "reference_duration_summary", None) is None:
            return
        report_frames.reference_duration_summary.to_excel(
            writer,
            sheet_name="Reference Duration Summary",
            index=False,
        )

    def _write_reference_duration_raw_data_sheet(self, writer, report_frames) -> None:
        """Write search-reference rows used by reference duration statistics."""

        self._logger.debug("Writing Reference Duration Raw Data sheet")
        if getattr(report_frames, "reference_duration_raw_data", None) is None:
            return
        report_frames.reference_duration_raw_data.to_excel(
            writer,
            sheet_name="Reference Duration Raw Data",
            index=False,
        )

    def _write_reference_exclusion_summary_sheet(self, writer, report_frames) -> None:
        """Write search-reference rows excluded from reference duration statistics."""

        self._logger.debug("Writing Reference Exclusion Summary sheet")
        if getattr(report_frames, "reference_exclusion_summary", None) is None:
            return
        report_frames.reference_exclusion_summary.to_excel(
            writer,
            sheet_name="Reference Exclusion Summary",
            index=False,
        )

    def _write_axis_action_summary_sheet(self, writer, report_frames) -> None:
        """Write the final clean axis/action summary table."""

        self._logger.debug("Writing Axis Action Summary sheet")
        if getattr(report_frames, "axis_action_summary", None) is None:
            return
        report_frames.axis_action_summary.to_excel(
            writer,
            sheet_name="Axis Action Summary",
            index=False,
        )

    def _write_distribution_exclusion_summary_sheet(self, writer, report_frames) -> None:
        """Write grouped reasons for rows excluded from distribution analysis."""

        self._logger.debug("Writing Distribution Exclusion Summary sheet")
        if report_frames.distribution_exclusion_summary is None:
            return
        report_frames.distribution_exclusion_summary.to_excel(
            writer,
            sheet_name="Distribution Exclusion Summary",
            index=False,
        )

    def _write_distribution_eligibility_summary_sheet(self, writer, report_frames) -> None:
        """Write grouped reasons for rows that never became distribution candidates."""

        self._logger.debug("Writing Distribution Eligibility sheet")
        if report_frames.distribution_eligibility_summary is None:
            return
        report_frames.distribution_eligibility_summary.to_excel(
            writer,
            sheet_name="Distribution Eligibility",
            index=False,
        )

    def _write_log_coverage_summary_sheet(self, writer, report_frames) -> None:
        """Write control-log coverage visibility to its own sheet."""

        self._logger.debug("Writing Log Coverage Summary sheet")
        if report_frames.log_coverage_summary is None:
            return
        report_frames.log_coverage_summary.to_excel(writer, sheet_name="Log Coverage Summary", index=False)

    def _write_log_coverage_gaps_sheet(self, writer, report_frames) -> None:
        """Write every uncovered TXT span from the interval-union coverage calculation."""

        self._logger.debug("Writing Log Coverage Gaps sheet")
        if report_frames.log_coverage_gaps is None:
            return
        report_frames.log_coverage_gaps.to_excel(writer, sheet_name="Log Coverage Gaps", index=False)

    def _write_distribution_charts_sheet(
        self,
        writer,
        report_frames,
        embed_charts: bool,
        chart_output_dir: str | Path | None = None,
    ) -> None:
        """Optionally embed generated distribution chart PNG files."""

        self._logger.debug("Writing Distribution Charts sheet")
        if not embed_charts or report_frames.distribution_chart_metadata is None:
            return
        sheet = writer.book.create_sheet("Distribution Charts")
        writer.sheets["Distribution Charts"] = sheet
        metadata_frame = report_frames.distribution_chart_metadata
        if metadata_frame.empty:
            from .config import MIN_SAMPLES_FOR_DISTRIBUTION_CHART

            sheet.cell(
                row=1,
                column=1,
                value=(
                    "No distribution charts were generated because all valid groups had fewer than "
                    f"{MIN_SAMPLES_FOR_DISTRIBUTION_CHART} samples."
                ),
            )
            return
        try:
            from openpyxl.drawing.image import Image
        except ImportError as exc:  # pragma: no cover - only when Pillow is missing.
            sheet.cell(row=1, column=1, value=f"Chart embedding unavailable: {exc}")
            return
        current_row = 1
        for item in metadata_frame.to_dict(orient="records"):
            sheet.cell(row=current_row, column=1, value="Group ID")
            sheet.cell(row=current_row, column=2, value=item.get("Group ID"))
            sheet.cell(row=current_row, column=1).font = Font(bold=True)
            for offset, key in enumerate(DISTRIBUTION_CHART_METADATA_KEYS, start=1):
                sheet.cell(row=current_row + offset, column=1, value=key)
                sheet.cell(row=current_row + offset, column=2, value=item.get(key))
            image_row = current_row + DISTRIBUTION_CHART_IMAGE_ROW_OFFSET
            chart_file = item.get("Chart File")
            chart_path = self._resolve_chart_path(chart_file, chart_output_dir)
            if chart_path is not None and chart_path.is_file():
                image = Image(str(chart_path))
                image.width = 720
                image.height = 440
                sheet.add_image(image, f"A{image_row}")
            else:
                sheet.cell(row=image_row, column=1, value="Chart image file was not found.")
            current_row += DISTRIBUTION_CHART_BLOCK_HEIGHT

    def _write_reference_duration_charts_sheet(
        self,
        writer,
        report_frames,
        embed_charts: bool,
        chart_output_dir: str | Path | None = None,
    ) -> None:
        """Optionally embed generated reference duration chart PNG files."""

        self._logger.debug("Writing Reference Duration Charts sheet")
        if not embed_charts or getattr(report_frames, "reference_duration_chart_metadata", None) is None:
            return
        sheet = writer.book.create_sheet("Reference Duration Charts")
        writer.sheets["Reference Duration Charts"] = sheet
        metadata_frame = report_frames.reference_duration_chart_metadata
        if metadata_frame.empty:
            from .config import MIN_SAMPLES_FOR_DISTRIBUTION_CHART

            sheet.cell(
                row=1,
                column=1,
                value=(
                    "No reference duration charts were generated because all reference groups had fewer than "
                    f"{MIN_SAMPLES_FOR_DISTRIBUTION_CHART} samples."
                ),
            )
            return
        try:
            from openpyxl.drawing.image import Image
        except ImportError as exc:  # pragma: no cover - only when Pillow is missing.
            sheet.cell(row=1, column=1, value=f"Chart embedding unavailable: {exc}")
            return
        current_row = 1
        for item in metadata_frame.to_dict(orient="records"):
            sheet.cell(row=current_row, column=1, value="Group ID")
            sheet.cell(row=current_row, column=2, value=item.get("Group ID"))
            sheet.cell(row=current_row, column=1).font = Font(bold=True)
            for offset, key in enumerate(REFERENCE_DURATION_CHART_METADATA_COLUMNS[1:], start=1):
                sheet.cell(row=current_row + offset, column=1, value=key)
                sheet.cell(row=current_row + offset, column=2, value=item.get(key))
            image_row = current_row + len(REFERENCE_DURATION_CHART_METADATA_COLUMNS) + 2
            chart_path = self._resolve_chart_path(item.get("Chart File"), chart_output_dir)
            if chart_path is not None and chart_path.is_file():
                image = Image(str(chart_path))
                image.width = 720
                image.height = 440
                sheet.add_image(image, f"A{image_row}")
            else:
                sheet.cell(row=image_row, column=1, value="Chart image file was not found.")
            current_row += len(REFERENCE_DURATION_CHART_METADATA_COLUMNS) + 29

    def _format_details_sheet(self, writer) -> None:
        """Apply basic formatting to the Details sheet."""

        self._logger.debug("Formatting Details sheet")
        sheet = writer.sheets["Details"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_diagnostics_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the optional Diagnostics Summary sheet."""

        self._logger.debug("Formatting Diagnostics Summary sheet")
        if "Diagnostics Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Diagnostics Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_diagnostics_sheet(self, writer) -> None:
        """Apply basic formatting to the optional Diagnostics sheet."""

        self._logger.debug("Formatting Diagnostics sheet")
        if "Diagnostics" not in writer.sheets:
            return
        sheet = writer.sheets["Diagnostics"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Summary sheet."""

        self._logger.debug("Formatting Summary sheet")
        sheet = writer.sheets["Summary"]
        sheet.freeze_panes = "A2"
        self._auto_fit_columns(sheet)

    def _format_pwm_sources_sheet(self, writer) -> None:
        """Apply basic formatting to the optional PWM Sources sheet."""

        self._logger.debug("Formatting PWM Sources sheet")
        if "PWM Sources" not in writer.sheets:
            return
        sheet = writer.sheets["PWM Sources"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_hardware_motion_segments_sheet(self, writer) -> None:
        """Apply basic formatting to the optional Hardware Motion Segments sheet."""

        self._logger.debug("Formatting Hardware Motion Segments sheet")
        if "Hardware Motion Segments" not in writer.sheets:
            return
        sheet = writer.sheets["Hardware Motion Segments"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_hardware_reference_events_sheet(self, writer) -> None:
        """Apply basic formatting to the optional Hardware Reference Events sheet."""

        self._logger.debug("Formatting Hardware Reference Events sheet")
        if "Hardware Reference Events" not in writer.sheets:
            return
        sheet = writer.sheets["Hardware Reference Events"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_distribution_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Distribution Summary sheet."""

        self._logger.debug("Formatting Distribution Summary sheet")
        if "Distribution Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Distribution Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_distribution_raw_data_sheet(self, writer) -> None:
        """Apply basic formatting to the Distribution Raw Data sheet."""

        self._logger.debug("Formatting Distribution Raw Data sheet")
        if "Distribution Raw Data" not in writer.sheets:
            return
        sheet = writer.sheets["Distribution Raw Data"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_reference_duration_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Reference Duration Summary sheet."""

        self._logger.debug("Formatting Reference Duration Summary sheet")
        if "Reference Duration Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Reference Duration Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_reference_duration_raw_data_sheet(self, writer) -> None:
        """Apply basic formatting to the Reference Duration Raw Data sheet."""

        self._logger.debug("Formatting Reference Duration Raw Data sheet")
        if "Reference Duration Raw Data" not in writer.sheets:
            return
        sheet = writer.sheets["Reference Duration Raw Data"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_reference_exclusion_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Reference Exclusion Summary sheet."""

        self._logger.debug("Formatting Reference Exclusion Summary sheet")
        if "Reference Exclusion Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Reference Exclusion Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_axis_action_summary_sheet(self, writer) -> None:
        """Apply table styling and Mean-only conditional formatting."""

        self._logger.debug("Formatting Axis Action Summary sheet")
        if "Axis Action Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Axis Action Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        header_fill = PatternFill("solid", fgColor="1F2937")
        header_font = Font(color="FFFFFF", bold=True)
        alternate_fill = PatternFill("solid", fgColor="F3F4F6")
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
        headers = {cell.value: cell.column for cell in sheet[1]}
        for row_index in range(2, sheet.max_row + 1):
            if row_index % 2 == 0:
                for column in range(1, sheet.max_column + 1):
                    sheet.cell(row=row_index, column=column).fill = alternate_fill
            for header in ("n", "Mean (s)", "SD (s)", "Var (s^2)", "Median (s)", "CV (%)"):
                if header in headers:
                    sheet.cell(row=row_index, column=headers[header]).alignment = Alignment(horizontal="center")
            for header, number_format in {
                "Mean (s)": "0.000",
                "SD (s)": "0.0000",
                "Var (s^2)": "0.0000",
                "Median (s)": "0.000",
                "CV (%)": "0.00",
            }.items():
                if header in headers:
                    sheet.cell(row=row_index, column=headers[header]).number_format = number_format
        self._apply_axis_action_conditional_formatting(sheet, headers)
        self._auto_fit_columns(sheet)

    def _format_distribution_exclusion_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Distribution Exclusion Summary sheet."""

        self._logger.debug("Formatting Distribution Exclusion Summary sheet")
        if "Distribution Exclusion Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Distribution Exclusion Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_distribution_eligibility_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Distribution Eligibility sheet."""

        self._logger.debug("Formatting Distribution Eligibility sheet")
        if "Distribution Eligibility" not in writer.sheets:
            return
        sheet = writer.sheets["Distribution Eligibility"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_log_coverage_summary_sheet(self, writer) -> None:
        """Apply basic formatting to the Log Coverage Summary sheet."""

        self._logger.debug("Formatting Log Coverage Summary sheet")
        if "Log Coverage Summary" not in writer.sheets:
            return
        sheet = writer.sheets["Log Coverage Summary"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_log_coverage_gaps_sheet(self, writer) -> None:
        """Apply basic formatting to the Log Coverage Gaps sheet."""

        self._logger.debug("Formatting Log Coverage Gaps sheet")
        if "Log Coverage Gaps" not in writer.sheets:
            return
        sheet = writer.sheets["Log Coverage Gaps"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._auto_fit_columns(sheet)

    def _format_distribution_charts_sheet(self, writer) -> None:
        """Apply basic formatting to the optional Distribution Charts sheet."""

        self._logger.debug("Formatting Distribution Charts sheet")
        if "Distribution Charts" not in writer.sheets:
            return
        sheet = writer.sheets["Distribution Charts"]
        sheet.freeze_panes = "A1"
        self._auto_fit_columns(sheet)

    def _format_reference_duration_charts_sheet(self, writer) -> None:
        """Apply basic formatting to the optional Reference Duration Charts sheet."""

        self._logger.debug("Formatting Reference Duration Charts sheet")
        if "Reference Duration Charts" not in writer.sheets:
            return
        sheet = writer.sheets["Reference Duration Charts"]
        sheet.freeze_panes = "A1"
        self._auto_fit_columns(sheet)

    def _apply_axis_action_conditional_formatting(self, sheet, headers: dict[str, int]) -> None:
        """Highlight only Mean cells using the user-facing thresholds."""

        if "Mean (s)" not in headers:
            return
        if sheet.max_row < 2:
            return
        mean_col = headers["Mean (s)"]
        mean_letter = sheet.cell(row=1, column=mean_col).column_letter
        red_fill = PatternFill("solid", fgColor="FFC7CE")
        yellow_fill = PatternFill("solid", fgColor="FFEB9C")
        target_range = f"{mean_letter}2:{mean_letter}{sheet.max_row}"
        red_formula = f"${mean_letter}2>={AXIS_SUMMARY_MEAN_RED_THRESHOLD}"
        yellow_formula = (
            f"AND(${mean_letter}2>={AXIS_SUMMARY_MEAN_YELLOW_THRESHOLD},"
            f"${mean_letter}2<{AXIS_SUMMARY_MEAN_RED_THRESHOLD})"
        )
        sheet.conditional_formatting.add(
            target_range,
            FormulaRule(formula=[red_formula], fill=red_fill, stopIfTrue=True),
        )
        sheet.conditional_formatting.add(
            target_range,
            FormulaRule(formula=[yellow_formula], fill=yellow_fill),
        )

    def _basename(self, value: object) -> str:
        """Return a path basename without exposing local directories."""

        text = str(value or "")
        if not text:
            return ""
        return text.replace("\\", "/").rstrip("/").split("/")[-1]

    def _resolve_chart_path(self, chart_file: object, chart_output_dir: str | Path | None) -> Path | None:
        """Resolve a display chart filename back to a local file for embedding."""

        if not chart_file:
            return None
        chart_path = Path(str(chart_file))
        if chart_path.is_absolute():
            return chart_path
        if chart_output_dir:
            return Path(chart_output_dir) / chart_path.name
        return chart_path

    def _auto_fit_columns(self, sheet) -> None:
        """Adjust worksheet column widths to fit current values."""

        self._logger.debug("Auto-fitting worksheet columns")
        for column_cells in sheet.columns:
            lengths = [len(str(cell.value)) for cell in column_cells if cell.value is not None]
            width = max(lengths, default=10) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(width, 80)
