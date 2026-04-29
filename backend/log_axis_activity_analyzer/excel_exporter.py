"""Excel workbook export with Details, Summary, and PWM Sources worksheets."""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl.styles import Font


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
            self._format_details_sheet(writer)
            self._format_summary_sheet(writer)
            self._format_pwm_sources_sheet(writer)
            self._format_diagnostics_sheet(writer)
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
            {"Key": "Initialization Failed Count", "Value": metadata["initialization_failed_count"]},
            {"Key": "Diagnostic Count", "Value": metadata["diagnostic_count"]},
            {"Key": "Duration Warning Count", "Value": metadata["duration_warning_count"]},
            {"Key": "PWM Warning Count", "Value": metadata["pwm_warning_count"]},
        ]
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

    def _format_details_sheet(self, writer) -> None:
        """Apply basic formatting to the Details sheet."""

        self._logger.debug("Formatting Details sheet")
        sheet = writer.sheets["Details"]
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

    def _auto_fit_columns(self, sheet) -> None:
        """Adjust worksheet column widths to fit current values."""

        self._logger.debug("Auto-fitting worksheet columns")
        for column_cells in sheet.columns:
            lengths = [len(str(cell.value)) for cell in column_cells if cell.value is not None]
            width = max(lengths, default=10) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(width, 80)
