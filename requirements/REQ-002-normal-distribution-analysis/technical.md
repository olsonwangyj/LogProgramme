# REQ-002 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-04-30
> Updated: 2026-04-30

## 1. Technology Stack

| Area | Technology | Rationale |
|:---|:---|:---|
| Statistics | `pandas.Series` | Matches existing tabular dependency and supports sample/population variance semantics |
| Charts | `matplotlib` with `Agg` backend | Generates PNG images without a GUI and avoids additional plotting frameworks |
| Excel images | `openpyxl.drawing.image.Image` plus Pillow | Embeds generated PNG files into `.xlsx` workbooks |
| CLI | `argparse` | Extends the existing command-line entrypoint |

## 2. Module Design

### `backend.log_axis_activity_analyzer.distribution`

Owns distribution row construction, movement-distance derivation, grouping, exclusion counts, and statistical computation.

Key types:

- `DistributionInputRow`
- `DistributionStats`
- `DistributionAnalysisResult`
- `DistributionAnalyzer`

The analyzer accepts validated `ActivityRecord` objects and never changes existing duration values.

### `backend.log_axis_activity_analyzer.chart_generator`

Owns PNG chart creation. It receives grouped distribution rows plus computed stats and updates chart metadata on `DistributionStats`.

Behavior:

- chart largest groups first
- skip groups beyond `max_charts`
- draw normal PDF only when sample count and SD allow
- draw safe zero-variance charts without fitting a curve

### `backend.log_axis_activity_analyzer.summary`

Builds DataFrames for:

- `Distribution Summary`
- `Distribution Raw Data`
- `Distribution Charts` metadata

### `backend.log_axis_activity_analyzer.excel_exporter`

Writes the new distribution sheets and embeds chart images when enabled. Existing workbook sheets are written through the same exporter flow.

### `backend.log_axis_activity_analyzer.service`

Runs distribution analysis after validation and PWM attachment, then passes distribution frames into the exporter. It also returns distribution counts in `AnalysisRunResult`.

### `app.log_activity_tool`

Adds CLI flags and prints distribution run-summary counts.

## 3. Data Flow

1. Parse TXT and control-log folder.
2. Match activity start/end pairs.
3. Attach normalized PWM.
4. Validate durations and statuses.
5. Build distribution input rows from valid matched activity records.
6. Group by source file, PWM, axis, rounded movement distance, and rule ID.
7. Compute statistics for all groups.
8. Generate capped chart images for eligible groups.
9. Export existing workbook sheets plus distribution sheets.

## 4. Risk Controls

- Distribution filtering uses existing `Match Status` and `Duration Status` constants.
- Missing PWM and missing movement distance are excluded by default and counted in the summary metadata.
- Chart generation is isolated from the statistics path; failed charts do not erase computed statistics.
- Existing matching tests and end-to-end workbook checks remain in place to prevent duration regressions.
