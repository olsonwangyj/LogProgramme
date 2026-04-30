# Code Explanation

This document explains the current implementation of the LogProgramme log analysis tool. It is written for future maintainers who need to understand how the code fits together, where each feature lives, and which parts are risky to change.

## 1. What The Tool Does

LogProgramme analyzes one main UroBiopsy TXT log together with a folder of robot control `.log` files. It matches axis activity start/end events, calculates duration, attaches PWM evidence, derives movement distances, runs normal distribution analysis, generates chart PNGs, and exports an Excel workbook.

The workbook is meant to answer questions such as:

- Which axis activities matched correctly?
- How long did each movement take?
- Which PWM source was attached to the movement?
- What was the commanded target and, when available, the actual end position?
- For the same TXT file, PWM, axis, movement distance, and action, how consistent are durations?
- Does the control-log folder actually cover the TXT timeline well enough to trust PWM-based grouping?

## 2. Inputs And Outputs

### Inputs

The CLI accepts:

- `--txt-file`: main UroBiopsy TXT file.
- `--log-folder`: folder containing one or more robot control `.log` files.
- `--output`: destination `.xlsx` workbook.

Optional inputs control encoding, recursive log scanning, PWM matching strategy, distribution options, chart limits, chart embedding, and logging verbosity.

### Outputs

The main output is an Excel workbook with these sheets:

- `Details`
- `Summary`
- `PWM Sources`
- `Diagnostics`
- `Diagnostics Summary`
- `Distribution Summary`
- `Distribution Raw Data`
- `Distribution Exclusion Summary`
- `Log Coverage Summary`
- `Distribution Charts` when embedding is enabled

Distribution chart PNG files are saved to a per-workbook folder by default:

```text
<output workbook stem>_distribution_charts
```

## 3. Top-Level Architecture

The project has three main layers:

- `app/`
  - CLI entrypoint and optional GUI path picking.
- `backend/log_axis_activity_analyzer/`
  - Reusable parsing, matching, analysis, summary, charting, and export code.
- `tests/`
  - Regression tests for matching, PWM association, distribution statistics, chart generation, Excel output, and coverage summaries.

The service layer is the best starting point:

- `backend/log_axis_activity_analyzer/service.py`
  - Orchestrates one full analysis run.

## 4. End-To-End Flow

When the tool runs:

1. `app/log_activity_tool.py` parses CLI arguments.
2. `LogAnalysisService.run_analysis()` validates paths.
3. `MainLogParser.parse()` parses the main TXT file.
4. `LogFolderScanner.scan()` discovers `.log` files.
5. `DutyCycleLogParser.parse()` parses each control log into PWM events.
6. `EventMatcher.build_activity_records()` matches TXT start/end events and derives movement context.
7. `DutyCycleAssociator.attach()` attaches PWM evidence to each activity row.
8. Parse warnings are appended as workbook rows.
9. `ActivityValidator.validate()` recomputes durations and finalizes statuses.
10. `DistributionAnalyzer.analyze()` filters valid rows, groups them, and computes statistics.
11. `NormalDistributionChartGenerator.generate_charts()` writes chart PNGs.
12. `LogAnalysisService._build_log_coverage_summary()` computes control-log coverage using interval union.
13. `SummaryGenerator.build_report_frames()` converts objects into DataFrames.
14. `ExcelExporter.export()` writes all workbook sheets and embeds charts when enabled.
15. The CLI prints run counts.

## 5. CLI Entrypoint

File:

- `app/log_activity_tool.py`

Important functions:

- `main(argv=None)`
  - Runs the whole command-line flow.
- `_parse_arguments()`
  - Defines the CLI contract.
- `_configure_logging(verbose, trace_lines)`
  - Enables stage-level debug logging with `--verbose`.
  - Keeps per-line parser logs suppressed unless `--trace-lines` is also used.
- `_resolve_paths(args)`
  - Resolves CLI paths and optional GUI fallbacks.
- `_print_summary(result)`
  - Prints workbook path, row counts, distribution counts, and chart folder.

Important CLI distribution options:

- `--no-distribution`
- `--distribution-output-dir`
- `--max-distribution-charts`
- `--no-embed-distribution-charts`
- `--distribution-distance-source actual_preferred|commanded_preferred|actual_only|commanded_only`
- `--distribution-distance-grouping-mode exact|round_digits|bin`
- `--movement-distance-round-digits`
- `--movement-distance-bin-size`
- `--distribution-allow-nearest-pwm`
- `--distribution-allow-latest-before-pwm`
- `--distribution-allow-carry-forward-pwm`
- `--pwm-carry-forward`

`--pwm-carry-forward` affects Details-level PWM association. The separate `--distribution-allow-carry-forward-pwm` flag controls whether those carry-forward rows may enter distribution groups.

## 6. Configuration

File:

- `backend/log_axis_activity_analyzer/config.py`

This file centralizes:

- regex patterns
- event rules
- boundary rules
- status strings
- distribution defaults
- workbook column order
- chart defaults

Important parser patterns:

- `MAIN_LOG_TIMESTAMP_PATTERN`
- `MAIN_LOG_AXIS_EVENT_PATTERN`
- `INLINE_VALUE_PATTERN`
- `CONTROL_TIMESTAMP_PATTERN`
- `CONTROL_PWM_PATTERN`

Important movement and distribution options:

- `END_VALUE_COMPANION_SEARCH_WINDOW_MS = 2000`
- `HARD_POSITION_RESET_BOUNDARIES`
- `SOFT_WORKFLOW_BOUNDARIES`
- `RESET_POSITION_ON_SOFT_WORKFLOW_BOUNDARIES = False`
- `DISTRIBUTION_DISTANCE_SOURCE = "actual_preferred"`
- `DISTRIBUTION_DISTANCE_GROUPING_MODE = "bin"`
- `MOVEMENT_DISTANCE_BIN_SIZE = 0.1`
- `DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES = {"MatchedByContainingLogFile"}`

Distribution is strict by default. Nearest-file, latest-before, and carry-forward PWM rows are not used for normal distribution grouping unless explicitly enabled.

## 7. Data Models

File:

- `backend/log_axis_activity_analyzer/models.py`

Important dataclasses:

- `EventRule`
  - Defines one start/end activity rule.
- `BoundaryRule`
  - Defines workflow boundary behavior.
- `AxisLogEvent`
  - One parsed axis event from the main TXT timeline.
- `BoundaryEvent`
  - One parsed workflow boundary from the main TXT timeline.
- `DiagnosticEvent`
  - One structured diagnostic from the TXT file.
- `PWMEvent`
  - One parsed PWM line from a control log.
- `AxisPWMProfile`
  - Per-axis PWM summary for one control-log file.
- `MainLogParseResult`
  - Parsed TXT events, boundaries, diagnostics, timeline, and warnings.
- `DutyCycleLogFileResult`
  - Parsed data for one `.log` file.
- `DutyCycleFolderParseResult`
  - Parsed data for the whole log folder.
- `ActivityRecord`
  - The central intermediate row model.
- `ReportFrames`
  - Holds all DataFrames used by the Excel exporter.
- `AnalysisRunResult`
  - Counts and paths returned to the CLI.

`ActivityRecord` is the most important model. It stores:

- activity identity
- start/end times
- duration fields
- source TXT line numbers and text
- PWM evidence and match status
- movement start/target/end position fields
- commanded distance
- actual distance
- selected movement distance
- movement distance source/method/notes
- validation and display statuses

## 8. TXT Parsing

File:

- `backend/log_axis_activity_analyzer/log_a_parser.py`

The main parser reads the TXT file line by line and builds a mixed timeline of:

- `AxisLogEvent`
- `BoundaryEvent`
- `DiagnosticEvent`

It extracts:

- timestamp
- axis
- message text
- raw source line
- line number
- optional inline numeric value

It also recognizes diagnostics such as node response timeout, sensor cut, and AMX corruption lines. Recognized diagnostics are structured diagnostics, not parse warnings.

## 9. Control Log Parsing

Files:

- `backend/log_axis_activity_analyzer/log_folder_scanner.py`
- `backend/log_axis_activity_analyzer/log_b_parser.py`

The scanner discovers `.log` files in the selected folder. Each file is parsed independently.

The PWM parser handles timestamp-bearing transport lines and PWM command/status lines. It creates `PWMEvent` rows and builds `AxisPWMProfile` summaries.

PWM values are normalized:

```text
raw -80 -> PWM (%) 80, Direction Reverse
raw  80 -> PWM (%) 80, Direction Forward
```

Direction changes are recorded, but they are not conflicts when normalized PWM percentage is stable. A conflict means the same file has different normalized PWM percentages for the same axis.

## 10. Event Matching

File:

- `backend/log_axis_activity_analyzer/matcher.py`

The matcher converts parsed TXT timeline events into `ActivityRecord` objects.

Key ideas:

- Matching is axis-local.
- Matching is rule-local.
- Pending starts are keyed by `(axis, rule_id)`.
- Workflow boundaries close pending starts.
- Long candidate durations are rejected instead of being treated as valid matches.

Default event rules include:

- `search_reference`: `start searching reference` -> `reference found`
- `clear_motor`: `start clearing` -> `motor cleared`
- `move_to_max`: `start moving to max pos` -> `motor reached max pos`
- `move_to_home`: `start moving to home` -> `motor homed`

### End Value Companion Search

`_find_end_value()` looks for same-axis companion position lines after an end event, such as:

```text
@[Y] motor cleared
@[Y] min: -29.51
```

It scans by time window and same-axis relevance. It stops when:

- a workflow boundary is reached
- a new same-axis start event is reached
- the timestamp delta exceeds `END_VALUE_COMPANION_SEARCH_WINDOW_MS`
- the file ends

Unrelated axis lines do not consume a small fixed search budget.

### Position State

The matcher keeps `last_known_position_by_axis`.

It updates this state from:

- `min:`
- `max:`
- `reset physical position to 0`

Hard workflow boundaries reset position state:

- initialization started
- initialization failed
- application exited
- MCU controller stopped
- system exit selected
- finalization done

Soft menu boundaries such as tool/factory menu selection close pending starts but do not reset physical positions by default.

## 11. Movement Distance Model

Movement distance is not simply `abs(start line number)`.

For a start line like:

```text
@[H] start moving to home: -25.16
```

the numeric value is a target position, not a distance.

The code tracks:

- `movement_start_position`
- `movement_target_position`
- `movement_end_position`
- `movement_commanded_distance`
- `movement_actual_distance`
- `movement_distance`
- `movement_distance_source`
- `movement_distance_method`

Commanded distance:

```text
abs(movement_target_position - movement_start_position)
```

Actual distance:

```text
abs(movement_end_position - movement_start_position)
```

Default distribution source:

```text
actual_preferred
```

That means:

1. Use actual end distance when available.
2. Otherwise use commanded target distance.

Example:

```text
@[Y] max: 0.00
@[Y] start clearing: -19.50
@[Y] motor cleared
@[Y] min: -29.51
```

The commanded distance is `19.50`, but the actual distance is `29.51`. For `clear_motor`, actual end position is usually the correct grouping distance when available.

For home/max moves, there is often no explicit end position line, so commanded target distance is the fallback:

```text
@[H] min: -49.03
@[H] start moving to home: -25.16
```

Distance:

```text
abs(-25.16 - (-49.03)) = 23.87
```

## 12. PWM Association

File:

- `backend/log_axis_activity_analyzer/duty_cycle_associator.py`

The associator attaches PWM evidence to each `ActivityRecord`.

Default strategy:

```text
same_file_then_nearest
```

Selection order:

1. containing log file with same-axis PWM
2. nearest same-axis log file inside the configured nearness threshold
3. latest same-axis PWM before start within the safe time threshold
4. no PWM match

Optional carry-forward:

- enabled by `--pwm-carry-forward`
- produces `PWM Match Status = MatchedByCarryForward`
- sets a PWM warning
- remains excluded from distribution groups unless distribution carry-forward is explicitly allowed

PWM match statuses are written to Details so users can audit how PWM was attached.

## 13. Validation

File:

- `backend/log_axis_activity_analyzer/validation.py`

The validator recomputes duration and finalizes row status.

It protects the old duration bug by ensuring a matched row must have a valid same-axis start/end pair and a valid duration. Rejected long-duration candidates are not allowed into normal duration statistics.

Important statuses:

- `Matched`
- `Unmatched Start`
- `Unmatched End`
- `Closed By Boundary`
- `Closed By New Start`
- `Initialization Failed`
- `Duration Too Long Candidate`
- `Parse Warning`
- `Diagnostic`

Overall display statuses are separate from match/duration status. A row can have a valid duration but still show `PWM Warning` if PWM evidence is not reliable.

## 14. Distribution Analysis

File:

- `backend/log_axis_activity_analyzer/distribution.py`

Distribution analysis filters valid matched activity rows, groups them, and computes duration statistics.

Default grouping key:

- TXT source file
- normalized PWM percent
- axis
- movement distance group value
- rule/action type

Only rows with valid duration, accepted PWM, and true movement distance are included.

Default accepted PWM status:

- `MatchedByContainingLogFile`

Nearest, latest-before, and carry-forward PWM can be enabled separately from the CLI.

### Distance Grouping

The raw selected movement distance is preserved in `Distribution Raw Data`.

The grouping value is controlled by:

- `exact`
- `round_digits`
- `bin`

Default:

```text
bin with MOVEMENT_DISTANCE_BIN_SIZE = 0.1
```

So `23.86` and `23.87` group together as `23.9`.

### Statistics

For each group, the analyzer computes:

- count
- mean
- median
- min
- max
- range
- sample standard deviation
- sample variance
- population standard deviation
- population variance
- coefficient of variation
- P05/P25/P75/P95
- normal-fit fields
- distribution status

Sample standard deviation and sample variance use `ddof=1`.

Small-sample and zero-variance cases are handled explicitly:

- one sample: sample SD/variance are blank
- fewer than normal-fit minimum: no fitted normal curve
- zero variance: chart can be generated, but normal curve is not drawn

### Exclusions

Rows excluded from distribution are tracked as `DistributionExclusion` records. The workbook aggregates them in `Distribution Exclusion Summary` by:

- exclusion reason
- rule ID
- axis
- count
- example start line
- example notes

This helps distinguish expected exclusions such as `search_reference` missing true movement distance from real data problems.

## 15. Chart Generation

File:

- `backend/log_axis_activity_analyzer/chart_generator.py`

Charts are generated with matplotlib, not seaborn.

Each eligible group gets a PNG chart:

- histogram of duration in seconds
- fitted normal curve when sample count and variance allow it
- source-aware title, for example:

```text
Axis Y | PWM 80% | Distance 29.50 (ActualEndPosition) | clear_motor
```

The chart title and chart metadata use `Movement Distance Group Value`, not raw example distance. Raw exact distances stay in `Distribution Raw Data` and min/max fields.

## 16. Log Coverage Summary

Implemented in:

- `LogAnalysisService._build_log_coverage_summary()`

The coverage calculation uses the union of actual control-log intervals. It does not assume that earliest control-log time through latest control-log time is continuously covered.

The sheet reports:

- TXT start/end time
- control-log earliest/latest time
- control-log file count
- merged interval count
- covered duration
- uncovered duration
- coverage gap count
- coverage ratio
- rows with distribution-accepted PWM
- rows by PWM match type
- rows excluded due to PWM reliability
- notes/warnings

This is important for partial log folders. A folder can have early and late logs with a large gap; that gap should remain visible.

## 17. Summary And Excel Export

Files:

- `backend/log_axis_activity_analyzer/summary.py`
- `backend/log_axis_activity_analyzer/excel_exporter.py`

`SummaryGenerator` converts domain objects into DataFrames:

- Details rows
- event summary
- axis summary
- PWM sources
- diagnostics
- diagnostic summary
- distribution summary
- distribution raw data
- distribution exclusion summary
- distribution chart metadata
- log coverage summary

`ExcelExporter` writes those DataFrames to sheets and applies basic formatting:

- freeze panes
- auto filters
- auto-fit columns
- chart image embedding

The chart sheet contains metadata blocks plus embedded PNGs when embedding is enabled.

## 18. Service Layer

File:

- `backend/log_axis_activity_analyzer/service.py`

This is the orchestration layer. It owns:

- path validation
- parser/scanner calls
- matching
- PWM association
- validation
- distribution analysis
- chart generation
- coverage summary generation
- run-result counts
- workbook export

If you need to understand how a run works end to end, start here.

## 19. Tests

Main test files:

- `tests/test_service.py`
- `tests/test_distribution.py`

The tests cover:

- timestamp parsing
- duration calculation
- same-axis matching
- boundary handling
- old April 10 duration bug
- diagnostic parsing
- PWM parsing and conflicts
- PWM association statuses
- carry-forward PWM behavior
- movement distance derivation
- actual-vs-commanded clearing distance
- delayed/interleaved companion min/max lines
- position state reset rules
- distance binning
- distribution statistics
- chart generation
- Excel distribution sheets
- log coverage union behavior
- distribution exclusion summary

Useful commands:

```powershell
.\.venv\Scripts\python.exe -m compileall app backend
.\.venv\Scripts\python.exe -m pytest tests -v
```

## 20. Common Maintenance Tasks

### Add a new activity rule

Edit:

- `backend/log_axis_activity_analyzer/config.py`

Add a new `EventRule` to `DEFAULT_EVENT_RULES`, then add tests in `tests/`.

### Change a workbook column

Update both:

- the column list in `config.py`
- the row-building logic in `summary.py`

If it is a new sheet, also update:

- `ReportFrames` in `models.py`
- `ExcelExporter` in `excel_exporter.py`

### Change distribution grouping

Start with:

- `DistributionAnalyzer.build_input_rows()`
- `DistributionAnalyzer.build_group_id()`
- `DistributionAnalyzer._group_distance_value()`

Then check:

- chart title and metadata
- `Distribution Summary`
- `Distribution Raw Data`
- tests for grouping and workbook output

### Change PWM reliability rules

Start with:

- `config.py`
- `LogAnalysisService._build_distribution_allowed_pwm_statuses()`
- `DistributionAnalyzer._is_reliable_pwm()`

Remember that Details-level PWM matching and Distribution-level PWM acceptance are intentionally separate.

### Change movement distance behavior

Start with:

- `matcher.py`
- `distribution.py`

Be careful to preserve all distance fields:

- start position
- target position
- end position
- commanded distance
- actual distance
- selected distance
- source
- method
- notes

The raw data sheet should make every grouping decision auditable.

## 21. Risk Notes

Higher-risk files:

- `matcher.py`
  - Small changes can change which starts and ends pair together.
- `duty_cycle_associator.py`
  - Small changes can alter PWM evidence for many rows.
- `distribution.py`
  - Small changes can alter group counts and statistics.
- `validation.py`
  - Small changes can alter row statuses and summary inclusion.
- `service.py`
  - Orchestration changes can affect multiple output sheets at once.

Lower-risk files:

- `README.md`
- `CODE_EXPLANATION.md`
- chart styling in `chart_generator.py`, if data fields are unchanged

When changing behavior, run both compile and tests, then inspect a generated workbook with `openpyxl` if the change affects Excel output.
