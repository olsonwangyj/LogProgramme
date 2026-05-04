"""Excel workbook export with Details, Summary, and PWM Sources worksheets."""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl.styles import Font

from .config import (
    DISTRIBUTION_CHART_BLOCK_HEIGHT,
    DISTRIBUTION_CHART_IMAGE_ROW_OFFSET,
    DISTRIBUTION_CHART_METADATA_KEYS,
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
            self._write_diagnostics_sheet(writer, report_frames)
            self._write_diagnostics_summary_sheet(writer, report_frames)
            self._write_distribution_summary_sheet(writer, report_frames)
            self._write_distribution_raw_data_sheet(writer, report_frames)
            self._write_distribution_eligibility_summary_sheet(writer, report_frames)
            self._write_distribution_exclusion_summary_sheet(writer, report_frames)
            self._write_log_coverage_summary_sheet(writer, report_frames)
            self._write_log_coverage_gaps_sheet(writer, report_frames)
            self._write_distribution_charts_sheet(
                writer,
                report_frames,
                embed_charts=bool(metadata.get("embed_distribution_charts", True)),
            )
            self._format_details_sheet(writer)
            self._format_summary_sheet(writer)
            self._format_pwm_sources_sheet(writer)
            self._format_diagnostics_sheet(writer)
            self._format_diagnostics_summary_sheet(writer)
            self._format_distribution_summary_sheet(writer)
            self._format_distribution_raw_data_sheet(writer)
            self._format_distribution_eligibility_summary_sheet(writer)
            self._format_distribution_exclusion_summary_sheet(writer)
            self._format_log_coverage_summary_sheet(writer)
            self._format_log_coverage_gaps_sheet(writer)
            self._format_distribution_charts_sheet(writer)
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
            {"Key": "TXT File", "Value": metadata["txt_file_path"]},
            {"Key": "Log Folder", "Value": metadata["log_folder_path"]},
            {"Key": "Generated Workbook", "Value": metadata["output_path"]},
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
        ]
        if metadata.get("distribution_enabled"):
            metadata_rows.extend(
                [
                    {"Key": "Distribution Groups", "Value": metadata.get("distribution_group_count", 0)},
                    {"Key": "Distribution Raw Rows", "Value": metadata.get("distribution_raw_row_count", 0)},
                    {"Key": "Distribution Charts Generated", "Value": metadata.get("distribution_chart_count", 0)},
                    {"Key": "Distribution Chart Output Folder", "Value": metadata.get("distribution_output_dir", "")},
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
                        "Key": "Distribution Exclusion Reason Counts",
                        "Value": metadata.get("distribution_exclusion_reason_counts", ""),
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

    def _write_distribution_charts_sheet(self, writer, report_frames, embed_charts: bool) -> None:
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
            chart_path = Path(chart_file) if chart_file else None
            if chart_path is not None and chart_path.is_file():
                image = Image(str(chart_path))
                image.width = 720
                image.height = 440
                sheet.add_image(image, f"A{image_row}")
            else:
                sheet.cell(row=image_row, column=1, value="Chart image file was not found.")
            current_row += DISTRIBUTION_CHART_BLOCK_HEIGHT

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

    def _auto_fit_columns(self, sheet) -> None:
        """Adjust worksheet column widths to fit current values."""

        self._logger.debug("Auto-fitting worksheet columns")
        for column_cells in sheet.columns:
            lengths = [len(str(cell.value)) for cell in column_cells if cell.value is not None]
            width = max(lengths, default=10) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(width, 80)
