# LogProgramme Handover

## 1. Executive Summary

`log_programme` is a Python log-analysis tool for Biobot/UroBiopsy engineering logs. It analyzes one main UroBiopsy TXT log together with a folder of robot control `.log` files, matches axis activity start/end pairs, attaches PWM and hardware motion evidence, computes duration statistics, generates charts, and exports Excel workbooks for review.

The project is primarily a command-line tool with optional Tkinter file-picker dialogs. It is not a long-running service, web app, or full desktop GUI.

The current entrypoint is:

```powershell
python -m app.log_activity_tool
```

The main backend orchestration class is:

```python
backend.log_axis_activity_analyzer.service.LogAnalysisService
```

The output of a normal run is usually:

```text
<output>.xlsx
<output stem>_summary.xlsx
<output stem>_distribution_image_gallery.xlsx
<output stem>_distribution_charts/
```

The current implementation is feature-rich and regression-tested. The most important current behavior is that movement-distance grouping is based only on hardware actual distance from control-log TPOS Start/End evidence. Older software/TXT distance sources are explicitly rejected.

## 2. Current Repository State

As inspected locally:

- Branch: `main`
- Remote tracking: `origin/main`
- Latest local commit: `33108f02 Add Log data folders`
- Working tree had an unrelated untracked `.DS_Store` before this handover was added.
- Tracked file count is large, around `29692` files.
- Repository size on disk is about `1.2G`.
- `DHR/` is about `872M` and tracked.
- `Log/` is about `20M` and appears tracked even though `.gitignore` contains `Log/`.
- `.venv/` is about `227M` and ignored.

Important implication: the repository contains a lot of real/sample data, not just source code. Be careful with commits, pushes, and cleanup. Do not delete or move tracked data folders unless the team explicitly decides to move data into an artifact store.

## 3. Repository Layout

```text
log_programme/
+-- app/
|   +-- __init__.py
|   +-- log_activity_tool.py
+-- backend/
|   +-- __init__.py
|   +-- log_axis_activity_analyzer/
|       +-- __init__.py
|       +-- chart_generator.py
|       +-- config.py
|       +-- distribution.py
|       +-- duty_cycle_associator.py
|       +-- excel_exporter.py
|       +-- file_loader.py
|       +-- hardware_motion_associator.py
|       +-- image_gallery_exporter.py
|       +-- log_a_parser.py
|       +-- log_b_parser.py
|       +-- log_folder_scanner.py
|       +-- matcher.py
|       +-- models.py
|       +-- service.py
|       +-- summary.py
|       +-- summary_workbook_exporter.py
|       +-- time_utils.py
|       +-- validation.py
+-- tests/
|   +-- test_service.py
|   +-- test_distribution.py
+-- requirements/
|   +-- index.md
|   +-- REQ-001-log-axis-activity-analyzer/
|   +-- REQ-002-normal-distribution-analysis/
+-- scripts/
|   +-- run.sh
|   +-- run.bat
|   +-- build.sh
|   +-- build.bat
|   +-- test.sh
|   +-- test.bat
+-- DHR/
+-- Log/
+-- CODE_EXPLANATION.md
+-- README.md
+-- HANDOVER.md
+-- LogProgramme.spec
+-- requirements.txt
+-- .gitignore
```

## 4. What The Tool Does

The tool is designed to answer engineering review questions such as:

- Which axis activities matched correctly?
- Which starts were unmatched, closed by boundaries, or closed by newer starts?
- How long did each matched activity take?
- Which PWM value was safely associated with that activity?
- Which hardware TPOS Start/End segment supports the movement distance?
- Which diagnostic lines appeared in the main TXT log?
- For the same TXT file, PWM, axis, hardware actual distance, and action, how consistent are durations?
- Where do control-log coverage gaps prevent reliable PWM or hardware grouping?

The normal input model is:

- One main UroBiopsy TXT log.
- One folder containing one or more robot control `.log` files.
- One destination `.xlsx` path.

The preferred CLI flags are:

```powershell
--txt-file
--log-folder
--output
```

Backward-compatible aliases are still accepted:

- `--log-a` maps to `--txt-file`.
- `--log-b` maps to the old control-log input. If it points to a `.log` file, the parent folder is scanned.
- `--no-gui` is a hidden alias for `--no-file-picker`.

## 5. Typical Run Commands

### 5.1 Windows Development Setup

```powershell
cd D:\LogProgramme
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5.2 Direct CLI Mode

Use this when all paths are known and no dialogs should open:

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis.xlsx" ^
  --no-file-picker ^
  --verbose
```

### 5.3 File-Picker Mode

Use this for manual users:

```powershell
python -m app.log_activity_tool
```

Dialog sequence:

1. Select main UroBiopsy TXT log file.
2. Select folder containing hardware/control `.log` files.
3. Choose output Excel workbook path.

If the user cancels a picker, the app exits gracefully with a cancellation message.

### 5.4 Disable Distribution Analysis

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-no-distribution.xlsx" ^
  --no-distribution ^
  --no-file-picker
```

### 5.5 Generate Main Workbook Without Embedded Charts

This keeps chart PNG files but does not insert them into Excel:

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis.xlsx" ^
  --no-embed-distribution-charts ^
  --no-file-picker
```

### 5.6 Recursive Log Folder Scan

Use this only when `.log` files are nested under subfolders:

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\DHR\iSRT300041\C\Biobot\System\Log\RobotMovingValues" ^
  --output "D:\LogProgramme\output\recursive-analysis.xlsx" ^
  --recursive ^
  --no-file-picker
```

## 6. Scripts

Shell scripts:

```text
scripts/run.sh
scripts/build.sh
scripts/test.sh
```

Windows batch scripts:

```text
scripts/run.bat
scripts/build.bat
scripts/test.bat
```

Current behavior:

| Script | Purpose |
| --- | --- |
| `scripts/run.sh` / `scripts/run.bat` | Runs `python -m app.log_activity_tool` with forwarded arguments. |
| `scripts/build.sh` / `scripts/build.bat` | Runs `python -m compileall app backend`. This is a syntax/build check, not PyInstaller packaging. |
| `scripts/test.sh` / `scripts/test.bat` | Runs `pytest tests -v`. |

## 7. Dependencies

`requirements.txt` currently contains:

```text
pandas>=2.2,<3.0
numpy>=1.26,<3.0
openpyxl>=3.1,<4.0
pytest>=8.0,<9.0
matplotlib>=3.8,<4.0
pillow>=10.0,<13.0
pyinstaller>=6.0,<7.0
```

Main dependency roles:

- `pandas`: creates workbook-ready DataFrames and computes table outputs.
- `numpy`: supports chart/statistical operations.
- `openpyxl`: writes Excel files and inserts images.
- `matplotlib`: generates chart PNGs using the non-interactive `Agg` backend.
- `Pillow`: supports image handling for Excel chart insertion.
- `pytest`: test runner.
- `pyinstaller`: Windows executable packaging.

The tool should run on Python 3.10+. The local ignored virtual environment is Python 3.12, based on `.venv/pyvenv.cfg` and local bytecode names.

## 8. Packaging

The PyInstaller spec is:

```text
LogProgramme.spec
```

Build command from README:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm LogProgramme.spec
```

Expected output:

```text
dist\LogProgramme.exe
```

The spec:

- Uses `app/log_activity_tool.py` as the entry script.
- Keeps `console=True`.
- Includes Tkinter hidden imports for file-picker and message-box support.
- Collects data, binaries, and hidden imports from `pandas`, `numpy`, `openpyxl`, `PIL`, and `matplotlib`.
- Excludes `pytest`.
- Includes `matplotlib.backends.backend_agg`.

Packaged CLI mode:

```powershell
dist\LogProgramme.exe ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-packaged.xlsx" ^
  --distribution-image-gallery ^
  --no-file-picker
```

Packaged file-picker mode:

```powershell
dist\LogProgramme.exe
```

Double-clicking the EXE uses file-picker mode if required paths are omitted.

## 9. Architecture Overview

The project has three main layers:

```text
app/
  CLI, file-picker behavior, message boxes, process exit codes.

backend/log_axis_activity_analyzer/
  Reusable parsing, matching, enrichment, statistics, charting, and export code.

tests/
  Regression tests for parsers, matching, hardware association, distribution,
  chart generation, workbook export, CLI behavior, and known real-log regressions.
```

The end-to-end flow is:

1. `app.log_activity_tool.main()` parses CLI flags.
2. The CLI configures logging.
3. The CLI resolves required paths from arguments or Tkinter dialogs.
4. The CLI rejects unsupported software distance source values.
5. `LogAnalysisService.run_analysis()` validates paths.
6. `MainLogParser.parse()` parses the main TXT timeline.
7. `LogFolderScanner.scan()` finds `.log` files.
8. `DutyCycleLogParser.parse()` parses PWM events and hardware TPOS records.
9. `EventMatcher.build_activity_records()` matches axis-local activity starts and ends.
10. `DutyCycleAssociator.attach()` attaches PWM evidence.
11. `HardwareMotionAssociator.attach()` attaches hardware motion/reference evidence.
12. Parse warnings are appended as workbook rows.
13. `ActivityValidator.validate()` finalizes row statuses and duration validity.
14. The service selects hardware actual distance as the only selected movement distance.
15. `DistributionAnalyzer.analyze()` builds motion distribution groups.
16. `ReferenceDurationAnalyzer.analyze()` builds search-reference duration groups.
17. `NormalDistributionChartGenerator` writes chart PNG files.
18. The service builds log coverage summary and coverage gaps.
19. `SummaryGenerator.build_report_frames()` creates DataFrames.
20. `ExcelExporter.export()` writes the main workbook.
21. `SummaryWorkbookExporter.export()` writes the standalone summary workbook.
22. `DistributionImageGalleryExporter.export()` writes the image gallery workbook.
23. CLI prints counts and output paths.

## 10. Module Ownership Map

### 10.1 `app/log_activity_tool.py`

Owns:

- CLI argument definitions.
- File-picker mode detection.
- Legacy argument aliases.
- Tkinter file, folder, and save dialogs.
- Message boxes for completion, cancellation, and errors.
- Console logging setup.
- Process exit codes.
- Final printed run summary.

Important functions:

- `main(argv=None)`
- `_parse_arguments()`
- `_configure_logging()`
- `_resolve_paths()`
- `_prompt_for_missing_paths()`
- `_print_summary()`

Important CLI behavior:

- `--no-file-picker` requires all required paths.
- Missing dependencies return exit code `1` with a clear message.
- Unsupported distance sources return exit code `1`.
- `ValueError` from service returns exit code `1`.
- Unexpected exceptions are logged and return exit code `1`.

### 10.2 `backend/log_axis_activity_analyzer/service.py`

Owns the full run orchestration.

Important class:

```python
LogAnalysisService
```

Important method:

```python
run_analysis(...)
```

The service is the right integration point for any future GUI, batch runner, or automated workflow. Avoid duplicating orchestration logic outside this class.

Key responsibilities:

- Validate input TXT path, log folder path, and output workbook path.
- Resolve default summary workbook path.
- Resolve default distribution image gallery path.
- Parse TXT and control logs.
- Build activity records.
- Attach PWM and hardware evidence.
- Apply validation.
- Run motion and reference distribution analysis.
- Build coverage summaries.
- Export all workbooks.
- Return an `AnalysisRunResult` with counters and output paths.

### 10.3 `backend/log_axis_activity_analyzer/config.py`

Central configuration for:

- Timestamp formats.
- Parser regex patterns.
- Node-to-axis mapping.
- Control-log command names.
- Hardware raw-count scales.
- Event-pair rules.
- Workflow boundary rules.
- Status strings.
- Distribution defaults.
- Chart defaults.
- Workbook column orders.
- Gallery workbook column orders.
- Conditional-format thresholds.

This is the first file to inspect when adding a new supported event, boundary, diagnostic, PWM command, axis scale, workbook column, or distribution rule.

Important constants:

- `DEFAULT_EVENT_RULES`
- `BOUNDARY_PATTERNS`
- `AXIS_RAW_SCALE`
- `CONTROL_PWM_COMMANDS`
- `CONTROL_PWM_PATTERN`
- `CONTROL_TPOS_PATTERN`
- `DISTRIBUTION_DISTANCE_SOURCE`
- `DISTRIBUTION_DISTANCE_GROUPING_MODE`
- `DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES`
- `DISTRIBUTION_ALLOWED_HARDWARE_MOTION_MATCH_STATUSES`
- `DETAIL_COLUMNS`

Current default activity rules:

- `search_reference`: `start searching reference` -> `reference found`
- `clear_motor`: `start clearing` -> `motor cleared`
- `move_to_max`: `start moving to max pos` -> `motor reached max pos`
- `move_to_home`: `start moving to home` -> `motor homed`

Current default distribution strictness:

- PWM must be `MatchedByContainingLogFile`.
- Hardware motion must be `MatchedByOverlappingTime`.
- Distance source must be `hardware_actual`.
- Distance grouping mode defaults to `bin`.
- Distance bin size defaults to `0.1`.

### 10.4 `backend/log_axis_activity_analyzer/models.py`

Defines the data contracts passed between every stage.

Important dataclasses:

- `EventRule`
- `BoundaryRule`
- `AxisLogEvent`
- `BoundaryEvent`
- `DiagnosticEvent`
- `PWMEvent`
- `AxisPWMProfile`
- `HardwarePositionEvent`
- `HardwareMotionSegment`
- `HardwareReferenceEvidence`
- `ParseWarning`
- `MainLogParseResult`
- `DutyCycleLogFileResult`
- `DutyCycleFolderParseResult`
- `PWMMatchSelection`
- `ActivityRecord`
- `ReportFrames`
- `AnalysisRunResult`

`ActivityRecord` is the central row model. Most backend stages add fields to it:

- Matcher fills axis, rule, start/end time, source TXT lines, durations, and match status.
- PWM associator fills PWM percent, raw value, source file/line/time, match method, and warnings.
- Hardware associator fills TPOS positions, hardware actual distance, reference evidence, and hardware warnings.
- Validator fills final duration status and overall status.
- Summary/export code turns records into Excel rows.

### 10.5 `backend/log_axis_activity_analyzer/file_loader.py`

Owns safe text file loading with encoding fallback.

The loader is shared by both TXT and control-log parsers. Keep encoding handling here rather than adding ad hoc `open()` calls in parser modules.

Supported encodings are configured in `config.py`:

- `utf-8`
- `utf-8-sig`
- `cp1252`
- `latin-1`

### 10.6 `backend/log_axis_activity_analyzer/log_a_parser.py`

Owns parsing of the main UroBiopsy TXT log.

It emits:

- `AxisLogEvent`
- `BoundaryEvent`
- `DiagnosticEvent`
- `ParseWarning`

It parses lines with:

```text
YYYY-MM-DD HH:MM:SS:ms
```

and axis messages like:

```text
MCU   @[Y] start clearing: -19.50
```

Recognized diagnostics include:

- Node response timeouts.
- Sensor cut lines.
- AMX partially corrupted lines.
- Partial AMX amended lines.
- Generic ERR/WRN/INFO diagnostic lines.

Important behavior:

- Initialization failure remains a boundary event, not a diagnostic, because it closes pending starts.
- Known diagnostics go to Diagnostics sheets, not Parse Warning rows.
- Relevant malformed lines become Parse Warning rows.

### 10.7 `backend/log_axis_activity_analyzer/log_folder_scanner.py`

Owns scanning a selected folder for `.log` files.

Important behavior:

- Non-recursive scan is default.
- Recursive scan is only enabled by CLI `--recursive`.
- If no `.log` files are found, the run fails with a clear error.
- Each discovered `.log` file is parsed independently by `DutyCycleLogParser`.

### 10.8 `backend/log_axis_activity_analyzer/log_b_parser.py`

Owns parsing one robot control `.log` file.

It extracts:

- Timestamp-bearing transport lines.
- PWM events from `RUN` and `VEL`.
- PWM status confirmations such as `RUN 'S'`.
- TPOS hardware position records.
- TPOS `S` and `E` motion segments.
- TPOS `Z` and `I` reference/reset evidence.
- Per-axis PWM profiles.
- Parse warnings for malformed relevant lines.

PWM normalization:

```text
raw -80 -> PWM (%) 80, Direction Reverse
raw  80 -> PWM (%) 80, Direction Forward
```

Direction changes are recorded but are not conflicts if normalized PWM percent is stable. A real conflict means different normalized PWM percentages in the same source file for the same axis.

Hardware position conversion uses `AXIS_RAW_SCALE`:

```text
physical position = raw position / axis scale
hardware actual distance = abs(raw end - raw start) / abs(axis scale)
```

Important distinction:

- `TPOS 'S'` and `TPOS 'E'` create motion segments.
- `TPOS 'Z'` and `TPOS 'I'` are reference/reset evidence.
- `TPOS 'Z'` and `TPOS 'I'` never create hardware movement distance.

### 10.9 `backend/log_axis_activity_analyzer/matcher.py`

Owns axis-local activity matching from the main TXT timeline.

Important class:

```python
EventMatcher
```

It:

- Classifies messages using `DEFAULT_EVENT_RULES`.
- Keeps pending starts by `(axis, rule_id)`.
- Matches starts and ends only on the same axis and same rule.
- Closes stale starts when a newer same-axis same-rule start appears.
- Closes pending starts on configured workflow boundaries.
- Rejects unrealistic long duration candidates.
- Emits unmatched starts and unmatched ends.
- Extracts companion end values from nearby same-axis `min:` / `max:` lines.
- Maintains software/TXT position context for audit fields.

Important current max-duration default:

```text
120000 ms
```

The README documents the April 10 regression this protects: an old failed Z start was incorrectly paired with a much later Z end. Current behavior closes the failed start at initialization failure and matches the later valid pair.

### 10.10 `backend/log_axis_activity_analyzer/duty_cycle_associator.py`

Owns PWM attachment to activity records.

Important class:

```python
DutyCycleAssociator
```

Default strategy:

```text
same_file_then_nearest
```

Supported strategies:

- `same_file_then_nearest`
- `latest_before_start`
- `latest_known`

PWM matching order for the default strategy:

1. Same-axis PWM in a log file whose time range contains the activity.
2. Same-axis PWM in a nearby log file.
3. Latest same-axis PWM before activity within safe threshold.
4. Optional carry-forward, only when `--pwm-carry-forward` is enabled.
5. Clear no-match status.

Important status examples:

- `MatchedByContainingLogFile`
- `MatchedByNearestLogFile`
- `MatchedByNearestFutureLogFile`
- `MatchedByLatestBeforeStartWithinThreshold`
- `MatchedByCarryForward`
- `NoControlLogsAvailable`
- `NoSameAxisPWMInFolder`
- `NoRelevantLogFileFound`
- `RelevantLogFileLacksAxisPWM`
- `LatestBeforeStartTooFar`
- `PWMConflictInSourceFile`

Distribution analysis accepts only strict containing-log PWM by default. Nearest, latest-before, and carry-forward rows remain visible in Details but are excluded from distribution unless specific opt-in flags are used.

### 10.11 `backend/log_axis_activity_analyzer/hardware_motion_associator.py`

Owns hardware motion and reference evidence attachment.

Important class:

```python
HardwareMotionAssociator
```

It:

- Collects all parsed hardware motion segments.
- Marks duplicate segments.
- Deduplicates exact duplicate complete segments for matching.
- Matches complete same-axis TPOS Start/End segments to TXT activity rows.
- Selects overlapping segments as reliable.
- Reports nearest previous/future segments as candidates.
- Reports multiple overlapping candidates separately.
- Reports incomplete or missing hardware evidence.
- Handles `search_reference` with TPOS `Z` / `I` reference evidence instead of motion distance.
- Applies hardware distance consistency checks.

Important match statuses:

- `MatchedByOverlappingTime`
- `MatchedByNearestHardwareSegment`
- `MatchedByNearestPreviousHardwareSegment`
- `MatchedByNearestFutureHardwareSegment`
- `MultipleHardwareCandidates`
- `NoHardwareSegmentFound`
- `HardwareSegmentIncomplete`
- `HardwareReferenceNotApplicable`

Distribution accepts only `MatchedByOverlappingTime` hardware motion by default.

### 10.12 `backend/log_axis_activity_analyzer/validation.py`

Owns final validation of durations and row status.

It separates:

- `Match Status`
- `Duration Status`
- `PWM Match Status`
- `Overall Status`

This separation matters. A row can be:

```text
Match Status = Matched
Duration Status = Valid
Overall Status = PWM Warning
```

That means the duration itself is valid, but PWM evidence was weak or missing.

### 10.13 `backend/log_axis_activity_analyzer/distribution.py`

Owns motion distribution and reference-duration distribution analysis.

Important classes:

- `DistributionAnalyzer`
- `ReferenceDurationAnalyzer`
- `DistributionInputRow`
- `DistributionStats`
- `DistributionAnalysisResult`
- `ReferenceDurationInputRow`
- `ReferenceDurationStats`
- `ReferenceDurationAnalysisResult`

Motion distribution grouping key:

```text
TXT source file
normalized PWM (%)
axis
hardware actual movement distance group value
rule/action type
```

Rows are distribution candidates only when:

- `Match Status = Matched`
- `Duration Status = Valid`
- numeric duration is greater than zero
- PWM is present and allowed by current distribution flags
- hardware actual distance exists and came from an allowed hardware match
- axis and rule are present

Default distance behavior:

- Only hardware actual distance is supported.
- Software/TXT distances are audit metadata only.
- `search_reference` has no movement distance and is excluded from motion distribution for reason `DistanceNotApplicableForReference`.

Default grouping behavior:

- Mode: `bin`
- Bin size: `0.1`
- Alternatives: `exact`, `round_digits`

Stats include:

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
- percentiles
- coefficient of variation
- outlier count/values
- normal-fit status

### 10.14 `backend/log_axis_activity_analyzer/chart_generator.py`

Owns PNG chart generation for:

- Motion duration distributions.
- Reference duration distributions.

Important behavior:

- Uses matplotlib with `Agg` backend.
- Chart y-axis defaults to count, not density.
- Generates largest groups first.
- Honors `--max-distribution-charts`.
- Handles zero-variance and low-variance groups without crashing.
- Produces dot/rug-style plots for low-variance groups instead of misleading spikes.
- Updates chart metadata on stats objects.

### 10.15 `backend/log_axis_activity_analyzer/summary.py`

Owns conversion from typed records/results into workbook DataFrames.

It builds:

- Details table.
- Summary tables.
- PWM sources table.
- Hardware motion segment table.
- Hardware reference events table.
- Diagnostics tables.
- Distribution summary/raw/eligibility/exclusion tables.
- Reference duration summary/raw/exclusion tables.
- Axis action summary.
- Log coverage summary and gaps.

If workbook columns need to change, inspect both `summary.py` and column constants in `config.py`.

### 10.16 `backend/log_axis_activity_analyzer/excel_exporter.py`

Owns the main workbook export.

It writes sheets such as:

- `Details`
- `Summary`
- `PWM Sources`
- `Hardware Motion Segments`
- `Hardware Reference Events`
- `Diagnostics`
- `Diagnostics Summary`
- `Distribution Summary`
- `Distribution Raw Data`
- `Reference Duration Summary`
- `Reference Duration Raw Data`
- `Reference Exclusion Summary`
- `Axis Action Summary`
- `Distribution Eligibility`
- `Distribution Exclusion Summary`
- `Log Coverage Summary`
- `Log Coverage Gaps`
- `Distribution Charts`
- `Reference Duration Charts`

It also applies workbook formatting:

- Header formatting.
- Freeze panes.
- Auto filters.
- Column widths.
- Conditional formatting for axis/action mean duration thresholds.
- Chart image embedding when enabled.

### 10.17 `backend/log_axis_activity_analyzer/summary_workbook_exporter.py`

Owns the standalone summary workbook:

```text
<output stem>_summary.xlsx
```

It writes one clean sheet:

```text
Overall Axis Action Summary
```

It intentionally excludes Move to Home by default:

```python
DEFAULT_EXCLUDED_SUMMARY_ACTIONS = {"Move to Home", "move_to_home"}
```

The user-facing columns are:

- `Axis`
- `Action`
- `n`
- `Mean (s)`
- `SD (s)`
- `Var (s^2)` / display equivalent
- `Median (s)`
- `IQR (s)`
- `Min-Max (s)` / display equivalent
- `CV (%)`

### 10.18 `backend/log_axis_activity_analyzer/image_gallery_exporter.py`

Owns the separate chart/statistics workbook:

```text
<output stem>_distribution_image_gallery.xlsx
```

It writes:

- `Image Gallery`
- `Image Statistics`
- `Image Index`

It reuses generated PNGs; it does not regenerate charts.

Important behavior:

- Default layout is `vertical`.
- Optional layout is `compact_grid`.
- Image insertion is capped by `DISTRIBUTION_IMAGE_MAX_IMAGES`.
- Groups without chart files still appear in `Image Statistics`.
- Missing or corrupt chart images do not fail the whole workbook.
- If image embedding is unavailable, the workbook records that status instead of crashing.

## 11. Input Data Details

### 11.1 Main TXT Log

Expected main-log examples:

```text
2026-03-31 09:39:40:554 MCU   @[Y] start clearing: -19.50
2026-03-31 09:39:47:373 MCU   @[Y] motor cleared
2026-03-31 09:39:47:373 MCU   @[Y] min: -29.51
```

The parser preserves:

- timestamp
- axis
- message
- raw line text
- source line number
- optional inline numeric value

### 11.2 Control `.log` Folder

Expected control-log examples:

```text
2026-04-10 09:20:22:000 [OUT] ...
                              [N12:Z] RUN 0 80 (80)
                              [N12:Z] TPOS 'S' 0 0 0 0 (0)
                              [N12:Z] TPOS 'E' 0 0 0 0 (-4403200)
```

The parser preserves:

- source file
- source line number
- source line text
- file start/end timestamps
- PWM raw and normalized values
- PWM command type
- PWM direction
- TPOS raw positions
- converted hardware positions
- complete/incomplete hardware motion segments
- reference/reset evidence

### 11.3 Sample Data Folders

The repo contains:

```text
Log/
DHR/
```

`Log/` contains main TXT samples and `RobotMovingValues/<date>/` control-log folders.

`DHR/` contains many deeper device-history folders with robot moving values under paths like:

```text
DHR/iSRT300041/C/Biobot/System/Log/RobotMovingValues/20260424/
```

Use `--recursive` when selecting a higher-level DHR folder. If selecting a specific date folder that directly contains `.log` files, `--recursive` is not needed.

## 12. Output Workbooks

### 12.1 Main Analysis Workbook

Default path:

```text
<output>.xlsx
```

This is the detailed analysis artifact. Use it for audit and debugging.

Important sheets:

| Sheet | Purpose |
| --- | --- |
| `Details` | One row per activity, diagnostic, parse warning, boundary closure, or unmatched item. |
| `Summary` | Metadata and aggregate counts/statistics. |
| `PWM Sources` | Parsed PWM records and per-source audit data. |
| `Hardware Motion Segments` | Parsed TPOS S/E motion segments, including duplicate and matching audit columns. |
| `Hardware Reference Events` | TPOS Z/I reference/reset evidence. |
| `Diagnostics` | Structured main-log diagnostics. |
| `Diagnostics Summary` | Diagnostic counts grouped by type/severity/axis/node. |
| `Distribution Summary` | Motion duration statistics by TXT/PWM/axis/distance/action group. |
| `Distribution Raw Data` | Rows included in motion distribution groups. |
| `Reference Duration Summary` | Search-reference duration statistics. |
| `Reference Duration Raw Data` | Search-reference rows before short-duration exclusion. |
| `Distribution Eligibility` | Rows that never became distribution candidates. |
| `Distribution Exclusion Summary` | Valid matched rows excluded from distribution and why. |
| `Log Coverage Summary` | TXT vs control-log coverage and PWM/hardware reliability counts. |
| `Log Coverage Gaps` | Every uncovered TXT time interval. |
| `Distribution Charts` | Embedded motion charts and metadata when enabled. |
| `Reference Duration Charts` | Embedded reference charts and metadata when enabled. |

### 12.2 Standalone Summary Workbook

Default path:

```text
<output stem>_summary.xlsx
```

This workbook is meant to be the clean final report. It contains only `Overall Axis Action Summary`.

It intentionally omits:

- raw data
- chart images
- full local paths
- debug metadata
- Move to Home rows

### 12.3 Distribution Image Gallery Workbook

Default path:

```text
<output stem>_distribution_image_gallery.xlsx
```

This workbook is chart/statistics focused and contains:

- `Image Gallery`
- `Image Statistics`
- `Image Index`

Disable it with:

```powershell
--no-distribution-image-gallery
```

Choose its path with:

```powershell
--distribution-image-gallery-output "D:\LogProgramme\output\april10-images.xlsx"
```

### 12.4 Chart Folder

Default path:

```text
<output stem>_distribution_charts/
```

The folder is cleaned of old PNGs before each new run when default config is used.

Override it with:

```powershell
--distribution-output-dir "D:\LogProgramme\output\charts"
```

## 13. Status Columns And Their Meaning

Do not collapse these into one concept:

| Column | Meaning |
| --- | --- |
| `Match Status` | Whether the activity start/end pairing matched, was unmatched, was boundary-closed, or was rejected. |
| `Duration Status` | Whether duration is valid, too long, end-before-start, or not applicable. |
| `PWM Match Status` | How PWM was selected, or why reliable PWM is unavailable. |
| `Hardware Motion Match Status` | How hardware TPOS motion evidence was matched. |
| `Hardware Reference Match Status` | Search-reference hardware evidence status. |
| `Overall Status` | Top-level review category for quick filtering. |

Examples:

```text
Match Status = Matched
Duration Status = Valid
Overall Status = OK
```

```text
Match Status = Matched
Duration Status = Valid
PWM Match Status = NoRelevantLogFileFound
Overall Status = PWM Warning
```

```text
Match Status = Initialization Failed
Overall Status = Initialization Failed
```

The validator intentionally keeps non-matched activity states from being overwritten by weaker PWM warnings.

## 14. Distribution Rules To Remember

Motion distribution is strict by default.

Included rows require:

- Matched activity.
- Valid positive duration.
- Reliable PWM.
- Reliable overlapping hardware motion segment.
- Hardware actual distance.
- Axis and rule/action present.

Excluded rows include:

- unmatched rows
- boundary-closed rows
- initialization failures
- duration-too-long candidates
- diagnostics
- parse warnings
- missing PWM
- unreliable PWM
- missing hardware actual distance
- nearest-only hardware segments
- ambiguous multiple hardware candidates
- search-reference distance rows

Default PWM allowed for distribution:

```text
MatchedByContainingLogFile
```

Optional looser flags:

```powershell
--distribution-allow-nearest-pwm
--distribution-allow-latest-before-pwm
--distribution-allow-carry-forward-pwm
```

Default hardware allowed for distribution:

```text
MatchedByOverlappingTime
```

Optional looser flags:

```powershell
--distribution-allow-nearest-hardware-segment
--distribution-allow-ambiguous-hardware-segment
```

Use these looser flags only when the reviewer explicitly accepts weaker evidence.

## 15. Search Reference Behavior

`search_reference` is special.

It is a timed activity:

```text
start searching reference -> reference found
```

But it is not a movement-distance activity. The tool does not expect a hardware actual distance for it.

Instead, it looks for hardware reference/reset evidence:

```text
TPOS 'Z'
TPOS 'I'
```

When evidence is found:

```text
Hardware Reference Match Status = HardwareReferenceEvidenceFound
Hardware Motion Match Status = HardwareReferenceNotApplicable
Selected Movement Distance = blank
Selected Movement Distance Method = DistanceNotApplicableForReference
```

Reference durations are analyzed separately in:

- `Reference Duration Summary`
- `Reference Duration Raw Data`
- `Reference Exclusion Summary`
- `Reference Duration Charts`

Very short reference durations are suspicious by default:

```text
REFERENCE_MIN_DURATION_MS = 1000
REFERENCE_EXCLUDE_SHORT_DURATIONS_FROM_DISTRIBUTION = True
```

Rows shorter than the threshold remain in raw data but are excluded from reference summary and charts.

## 16. Known Regression Cases

### 16.1 April 10 Bad Z Duration Pair

Old bad behavior:

```text
Start: 2026-04-10 08:37:43:959 MCU @[Z] start clearing: -50.00
End:   2026-04-10 09:20:46:317 MCU @[Z] motor cleared
Bad duration: 2582358 ms
```

Correct current behavior:

- The `08:37:43:959` start is closed by `InitializationFailed` at `08:38:14:121`.
- The later valid pair is:

```text
Start:    2026-04-10 09:20:23:541 MCU @[Z] start clearing: -50.00
End:      2026-04-10 09:20:46:317 MCU @[Z] motor cleared
Duration: 22776 ms / 22.776 s
```

Tests cover this behavior.

### 16.2 Hardware Distance Must Come From TPOS S/E

TXT lines such as `min:`, `max:`, `start clearing:`, and `start moving to home:` are software-layer audit metadata. They must not become selected movement distance.

Selected motion distance must come from:

```text
abs(TPOS_E_raw - TPOS_S_raw) / abs(axis_scale)
```

If no complete overlapping hardware segment exists, selected movement distance remains blank and the row is excluded from motion distribution.

### 16.3 PWM Sign Is Direction, Not Duty Conflict

Raw values:

```text
-80
80
```

both normalize to:

```text
PWM (%) = 80
```

The direction is recorded separately. A direction change alone is not a PWM conflict.

## 17. Testing

Run:

```powershell
python -m compileall app backend
python -m pytest tests -v
```

Or use scripts:

```powershell
scripts\build.bat
scripts\test.bat
```

On macOS/Linux:

```bash
./scripts/build.sh
./scripts/test.sh
```

Test coverage is broad and includes:

- timestamp parsing
- duration calculation
- same-axis matching
- unmatched starts/ends
- workflow boundary closure
- initialization failure behavior
- long-duration rejection
- diagnostic parsing
- PWM parsing and normalization
- PWM conflict detection
- PWM association strategies
- carry-forward behavior
- hardware TPOS segment parsing
- hardware reference evidence
- duplicate hardware segment handling
- hardware distance consistency
- distribution filtering and grouping
- distance binning/exact/rounding modes
- chart generation
- image gallery workbook behavior
- standalone summary workbook behavior
- log coverage summaries and gaps
- file-picker behavior
- CLI rejection of unsupported software distance sources
- real April 10/April 30 regression scenarios

## 18. End-To-End Validation Checklist

For any meaningful change:

1. Run `python -m compileall app backend`.
2. Run `pytest tests -v`.
3. Generate at least one real workbook from `Log/UroBiopsy_20260410.txt`.
4. Confirm the April 10 bad Z pair is not `Matched` + `Valid`.
5. Confirm the later April 10 Z pair has `22776 ms`.
6. Confirm diagnostics go to `Diagnostics`, not parse warnings.
7. Confirm `Distribution Summary` uses hardware actual distance.
8. Confirm missing hardware distance rows are excluded with clear reasons.
9. Open the generated workbook in Excel or LibreOffice if workbook formatting changed.
10. If chart/image code changed, confirm PNG files exist and the gallery workbook opens.

Example validation command:

```powershell
python -m app.log_activity_tool ^
  --txt-file "Log\UroBiopsy_20260410.txt" ^
  --log-folder "Log\RobotMovingValues\20260410" ^
  --output "output\april10-validation.xlsx" ^
  --no-file-picker ^
  --verbose
```

## 19. Build And Release Checklist

Before packaging:

1. Ensure the working tree contains only intentional source/doc changes.
2. Avoid committing generated `output/`, `build/`, `dist/`, `.xlsx`, or `.venv/`.
3. Run tests.
4. Build with PyInstaller:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm LogProgramme.spec
```

5. Run packaged CLI mode with a small known sample.
6. Run packaged file-picker mode.
7. Confirm `dist\LogProgramme.exe` can create:
   - main workbook
   - summary workbook
   - image gallery workbook
   - chart folder
8. Confirm Tkinter dialogs work on the target Windows machine.
9. Confirm no local absolute paths leak into the final user-facing gallery workbook.

## 20. Known Risks And Maintenance Notes

### 20.1 Large Tracked Data

`DHR/` and `Log/` contain many tracked data files. This makes the repository large and slows clone, status, and CI operations.

Recommendation:

- Keep only small canonical fixtures in Git.
- Move bulk data to an internal artifact store if the team agrees.
- Do not make this cleanup casually; tests and user workflows may depend on current data paths.

### 20.2 `.gitignore` Has Historical Mismatch

`.gitignore` contains:

```text
Log/
```

but `Log/` files are tracked. Git continues tracking files that were already added before the ignore rule. New files under `Log/` may be ignored unless force-added.

Recommendation:

- Decide whether `Log/` is intentional tracked fixture data or local-only sample data.
- Document the decision.

### 20.3 Requirement Docs Are Partly Historical

`requirements/REQ-002-normal-distribution-analysis/requirement.md` still describes older software-distance derivation. Current code and README say hardware actual distance is the only supported distance source.

Recommendation:

- Treat README, tests, and current code as the source of truth for current behavior.
- Update REQ-002 docs if formal requirement history needs to match the implementation.

### 20.4 Excel Output Is Broad

The main workbook has many sheets and many columns. Changing column names or sheet names can break downstream manual workflows or tests.

Recommendation:

- Change workbook schema deliberately.
- Update `config.py`, `summary.py`, `excel_exporter.py`, README, and tests together.

### 20.5 Evidence Strictness Is Intentional

The tool often leaves values blank rather than guessing. This is intentional.

Examples:

- Missing PWM stays missing unless safe evidence exists.
- Nearest hardware segments are candidate-only by default.
- Search-reference distance is not applicable.
- Software TXT distances do not fill selected hardware distance.

Do not loosen these defaults without explicit reviewer agreement.

### 20.6 GUI Is Only File Pickers

The README says this is not a full GUI application. Do not assume there is a persistent GUI state or GUI event loop. Tkinter is used only for file/folder/save dialogs and message boxes.

### 20.7 PyInstaller Support Depends On Hidden Imports

Tkinter and scientific Python packaging can be fragile. If packaging breaks:

- Check `LogProgramme.spec`.
- Check missing hidden imports.
- Check collected data/binaries for matplotlib/Pillow/openpyxl.
- Test file-picker mode after packaging, not only CLI mode.

### 20.8 Charts And Image Insertion Are Non-Critical

Chart generation and gallery export are valuable but should not corrupt the main workbook. The current design exports the main workbook first, then summary and gallery.

If gallery export fails, the service records an error but keeps the main workbook.

## 21. Common Troubleshooting

### Missing Required Paths

With `--no-file-picker`, all required paths must be provided:

```text
--txt-file
--log-folder
--output
```

If any are missing, the CLI exits with a clear error.

### No `.log` Files Found

Likely causes:

- Wrong folder selected.
- `.log` files are nested deeper.

Fix:

- Select the date folder that directly contains `.log` files.
- Or use `--recursive` on a higher folder.

### Software Distance Source Rejected

Current CLI accepts only:

```text
--distance-source hardware_actual
```

Old values such as `commanded_only` are rejected by design.

### PWM Is Blank

Check:

- `PWM Match Status`
- `PWM Missing Reason`
- `PWM Source File`
- `Log Coverage Summary`
- `Distribution Exclusion Summary`

Common statuses:

- `NoControlLogsAvailable`
- `NoSameAxisPWMInFolder`
- `NoRelevantLogFileFound`
- `RelevantLogFileLacksAxisPWM`
- `LatestBeforeStartTooFar`

Use `--pwm-carry-forward` only if the reviewer accepts carry-forward assumptions. Distribution still excludes carry-forward PWM unless `--distribution-allow-carry-forward-pwm` is supplied.

### Hardware Distance Is Blank

Check:

- `Hardware Motion Match Status`
- `Hardware Motion Segments`
- `Hardware Start/End Line Text`
- `Selected Movement Distance Method`

Common causes:

- No same-axis TPOS S/E segment.
- Incomplete TPOS segment.
- Segment is nearby but not overlapping.
- Multiple candidates exist.
- The row is `search_reference`, where distance is not applicable.

### Row Is Boundary-Closed

Check:

- `Closed By Boundary Type`
- `Closed By Boundary Time`
- `Boundary Line Number`
- `Boundary Line Text`

Common boundary types:

- `InitializationStarted`
- `InitializationFailed`
- `RobotInitializationDone`
- `ApplicationExited`
- `MotorAbortClicked`
- `RobotMovingStopped`
- `SystemExitSelected`
- `McuControllerStopped`
- `ToolMenuSelected`
- `FactoryMenuSelected`
- `FinalizationDone`

### No Charts Generated

Common reasons:

- No distribution groups.
- Groups have too few samples.
- Zero variance prevents normal fit.
- `--no-distribution` was used.
- `--max-distribution-charts` capped output.

The workbook should still contain distribution summary and chart-status metadata.

## 22. How To Add A New Activity Type

1. Add a new `EventRule` in `config.py` under `DEFAULT_EVENT_RULES`.
2. Ensure start/end regexes are axis-local and specific enough.
3. Add or update tests in `tests/test_service.py`.
4. If the action should appear differently in reports, update action-label logic in `distribution.py` / `summary.py`.
5. If the action should be excluded from the standalone summary, update `SummaryWorkbookExporter`.
6. Run tests and generate a real workbook.

## 23. How To Add A New Boundary

1. Add a `BoundaryRule` in `config.py` under `BOUNDARY_PATTERNS`.
2. Decide:
   - Does it flush pending starts?
   - Does it flush all axes or one axis?
   - Does it close pending when seen without being a hard failure?
3. Add any needed token to `BOUNDARY_RELEVANT_TOKENS`.
4. Add tests for pending-start closure behavior.
5. Validate with a real log containing the boundary.

## 24. How To Add A New Diagnostic Pattern

1. Add a regex in `config.py`.
2. Add parsing branch in `MainLogParser._build_diagnostic_event()`.
3. Decide severity, diagnostic type, axis mapping, and node ID behavior.
4. Add tests confirming it is not a parse warning.
5. Confirm it appears in `Diagnostics` and `Diagnostics Summary`.

## 25. How To Add A New PWM Command

1. Update `CONTROL_PWM_COMMANDS` in `config.py`.
2. Confirm `CONTROL_PWM_PATTERN = build_control_pwm_pattern(CONTROL_PWM_COMMANDS)` captures the new command.
3. Add parser tests for the new command and status-confirmation form if applicable.
4. Validate PWM source rows and activity association.

## 26. How To Change Workbook Columns

1. Update column constants in `config.py`.
2. Update row construction in `summary.py`.
3. Update writing/formatting in `excel_exporter.py`, `summary_workbook_exporter.py`, or `image_gallery_exporter.py` as needed.
4. Update README/CODE_EXPLANATION if user-facing sheets changed.
5. Update tests that assert column presence/order.
6. Generate a workbook and inspect it manually.

## 27. Handover Checklist For Next Maintainer

Before taking ownership:

- Read `README.md` for user-facing behavior.
- Read `CODE_EXPLANATION.md` for existing architecture notes.
- Read this `HANDOVER.md` for operational and maintenance notes.
- Check whether `DHR/` and `Log/` should stay tracked.
- Confirm target Python version and packaging environment.
- Run `pytest tests -v`.
- Generate one known workbook from April 10 data.
- Confirm output workbook, summary workbook, gallery workbook, and chart folder behavior.
- Confirm whether downstream users depend on current sheet/column names.
- Confirm whether future requirements should update the historical requirement docs.

Before merging a code change:

- Keep evidence strictness intentional.
- Add tests for parser/matcher/distribution behavior.
- Avoid broad refactors mixed with output schema changes.
- Check generated workbook sheets if any report logic changed.
- Avoid committing generated `.xlsx`, `dist/`, `build/`, `.venv/`, or `.DS_Store`.
