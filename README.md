# Log Axis Activity Analyzer

## Project Overview

LogProgramme analyzes one main UroBiopsy TXT log together with one folder of robot control `.log` files, then exports an Excel workbook for axis activity review.

The workbook is designed to answer five questions:

- Which axis activity starts and ends matched correctly?
- Which starts were closed by workflow boundaries such as initialization failure, abort, stop, or exit?
- Which PWM duty cycle was safely associated by axis and time?
- Which ERR/WRN diagnostic lines were observed without mixing them into parse errors?
- How consistent is execution time for the same TXT file, PWM, axis, movement distance, and action?

## Input Model

The command requires:

- one main TXT file, for example `Log\UroBiopsy_20260410.txt`
- one folder containing `.log` files, for example `Log\RobotMovingValues\20260410`
- one output Excel path

`.log` files are parsed from the selected folder. Use `--recursive` only when the `.log` files are in subfolders.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## CLI Usage

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis-reviewed.xlsx" ^
  --no-gui ^
  --verbose
```

Required arguments:

- `--txt-file`
- `--log-folder`
- `--output`

Useful optional arguments:

- `--encoding-txt`
- `--encoding-logs`
- `--recursive`
- `--association-strategy same_file_then_nearest|latest_before_start|latest_known`
- `--no-gui`
- `--no-distribution`
- `--distribution-output-dir`
- `--max-distribution-charts`
- `--no-embed-distribution-charts`
- `--movement-distance-round-digits`
- `--distribution-distance-source actual_preferred|commanded_preferred|actual_only|commanded_only`
- `--distribution-distance-grouping-mode exact|round_digits|bin`
- `--movement-distance-bin-size`
- `--distribution-allow-nearest-pwm`
- `--distribution-allow-latest-before-pwm`
- `--distribution-allow-carry-forward-pwm`
- `--pwm-carry-forward`
- `--verbose`
- `--trace-lines`

Backward-compatible aliases:

- `--log-a` maps to `--txt-file`
- `--log-b` is treated as a legacy control-log input; if a `.log` file is passed, its parent folder is scanned and every `.log` file in that folder is parsed

`--log-folder` is the preferred workflow for new runs.

## Duration Matching

Duration matching is conservative and axis-local:

- starts and ends must be on the same axis
- starts and ends must belong to the same configured rule
- stale starts are closed when a newer same-axis same-rule start appears
- initialization failure closes pending starts
- abort, robot stopped, system exit, MCU stopped, and application exit close pending starts
- max duration protection rejects unrealistic candidate pairs

Duration is calculated as:

```text
End Time - Start Time
```

### April 10 Known Issue

The old bug matched a failed Z start from `2026-04-10 08:37:43:959` to a much later Z end at `2026-04-10 09:20:46:317`, producing `2582358 ms`.

The fixed behavior is:

- the `08:37:43:959` Z start is closed by `InitializationFailed` at `2026-04-10 08:38:14:121`
- the correct later pair is matched:

```text
Start:    2026-04-10 09:20:23:541 MCU @[Z] start clearing: -50.00
End:      2026-04-10 09:20:46:317 MCU @[Z] motor cleared
Duration: 22776 ms / 22.776 s
```

Rejected long candidates are shown with:

- `Match Status = Duration Too Long Candidate`
- `Duration Status = Duration Too Long`
- `Candidate Duration (ms)`
- `Candidate Duration (s)`
- `Max Duration (ms)`

Rejected candidate durations are not included in normal duration summary statistics.

## PWM Matching

PWM is parsed from all `.log` files in the selected folder and grouped by:

- source log file
- axis
- source time range

One log file may have one PWM profile per axis. Different files may legitimately contain different PWM values.

Matching order for each activity:

1. containing log files that have the same-axis PWM profile
2. nearby log files within the nearness threshold that have the same-axis PWM profile
3. latest same-axis PWM before the activity, only within the safe max delta threshold
4. no PWM attached, with a clear `PWM Match Status` and note

The tool does not stop at a containing file if that file lacks the target axis. It searches for a same-axis profile before falling back.

### Signed PWM Normalization

Signed raw PWM stores direction. Duty cycle uses the absolute value:

```text
raw -80 => PWM (%) 80, Direction Reverse
raw  80 => PWM (%) 80, Direction Forward
```

`-80` and `80` are not a PWM conflict when the normalized PWM percent is the same. The workbook records this as direction-change metadata, for example:

- `PWM Direction Changed = TRUE`
- `PWM Match Status = MatchedByContainingLogFile`, `MatchedByNearestLogFile`, or another real match method
- no `PWM Warning` unless the normalized PWM percent actually conflicts

A real PWM conflict means normalized values differ, for example `60` and `80` in the same source file for the same axis.

PWM matching status values distinguish why PWM is blank or uncertain:

- `NoControlLogsAvailable`: no control-log files were scanned
- `NoSameAxisPWMInFolder`: logs exist, but no PWM profile exists for the activity axis
- `NoRelevantLogFileFound`: same-axis PWM exists somewhere, but no safe nearby source was found
- `RelevantLogFileLacksAxisPWM`: a time-containing log exists but lacks the activity axis and no safe fallback was found
- `LatestBeforeStartTooFar`: the latest same-axis PWM before the activity exceeded the safe time threshold
- `PWMConflictInSourceFile`: one source file has conflicting normalized PWM percentages

## Normal Distribution Analysis

Distribution analysis is enabled by default. It groups valid matched activity rows by:

- TXT source file
- normalized `PWM (%)`
- axis
- rounded movement distance
- rule/action type

This answers questions such as: for `UroBiopsy_20260410.txt`, `PWM = 80%`, `Axis = Z`, `Movement Distance = 50.00`, and `Action = clear_motor`, what does the duration distribution look like?

Only reliable duration rows are included:

- `Match Status = Matched`
- `Duration Status = Valid`
- numeric `Duration (ms) > 0`
- PWM is present and matched by a reliable PWM source
- true movement distance can be derived

Rows are excluded from distribution fitting when they are unmatched, boundary-closed, initialization failures, duration-too-long candidates, diagnostics, parse warnings, missing PWM, unreliable PWM, missing true movement distance, or otherwise not valid for duration statistics. The `Summary` sheet reports exclusion counts.

PWM is grouped by normalized percent, so raw `-80` and raw `80` both belong to `PWM (%) = 80`. Direction remains visible in `Details` but does not split distribution groups.

Distribution PWM grouping uses only reliable PWM matches by default:

- `MatchedByContainingLogFile`

Nearest-file PWM and latest-before PWM remain visible in `Details`, but are excluded from distribution groups unless `--distribution-allow-nearest-pwm` or `--distribution-allow-latest-before-pwm` is supplied. Carry-forward PWM is also excluded unless `--distribution-allow-carry-forward-pwm` is supplied. Rows with PWM conflicts, stale latest-before PWM, or missing same-axis PWM evidence are excluded.

Movement distance is the physical travel distance, not the absolute value of the target text on the start line.

The matcher tracks the last known physical axis position from companion position lines such as:

```text
@[H] min: -49.02
@[N] max: 69.51
```

Then, for a start line with a target:

```text
@[H] start moving to home: -25.16
```

the values mean:

- `Movement Start Position = -49.02`
- `Movement Target Position = -25.16`
- `Movement Commanded Distance = abs(-25.16 - (-49.02)) = 23.86`

So `start moving to home: -25.16` does not mean distance `25.16`; it is a target position.

The workbook keeps commanded and actual distance separate:

- `Movement Commanded Distance = abs(Movement Target Position - Movement Start Position)`
- `Movement Actual Distance = abs(Movement End Position - Movement Start Position)`

These two columns are stable audit fields. The `Selected Movement Distance` shown in `Details` and `Distribution Raw Data` is runtime-configurable, so it can change when the same workbook is regenerated with a different `--distribution-distance-source` option:

- `actual_preferred` (default): use actual distance when available, otherwise commanded distance.
- `commanded_preferred`: use commanded distance when available, otherwise actual distance.
- `actual_only`: include only rows with an actual end distance.
- `commanded_only`: include only rows with a commanded target distance.

For `clear_motor`, the actual end position from the following same-axis `min:` or `max:` line is usually preferred. For example:

```text
@[Y] max: 0.00
@[Y] start clearing: -19.50
@[Y] motor cleared
@[Y] min: -29.51
```

Here `-19.50` is the commanded target, but the actual movement distance is `abs(-29.51 - 0.00) = 29.51`. With the default `actual_preferred` setting, the distribution group uses `29.51`, not `19.50`.

Movement position state is derived as follows:

- `min:` and `max:` companion lines update the last known physical position for that axis.
- `reset physical position to 0` also updates the last known position to `0.0`; it is a position hint, not an activity row.
- Hard workflow boundaries such as initialization start/failure, application exit, MCU controller stopped, system exit, and finalization clear remembered positions so stale positions are not reused.
- Soft workflow boundaries such as tool and factory menu selection still close pending starts, but do not reset physical position state by default.
- If a previous same-axis position and target are known, commanded distance uses `KnownStartPositionToTarget`.
- If a previous same-axis position and actual end position are known, actual distance uses `KnownStartPositionToActualEnd`.
- If the start position is missing, leave movement distance blank with `Movement Distance Method = MissingStartPosition` and exclude the row from distribution analysis by default.
- If no target or end position is available, leave movement distance blank with `Movement Distance Method = MissingValue`.
- Target-absolute fallback is disabled by default. If enabled in config, those rows are marked as `StartTargetAbsoluteValueFallback` so they do not look like true travel distances.

Distribution distance grouping is configurable from the CLI or `config.py`:

- `DISTRIBUTION_DISTANCE_GROUPING_MODE = "bin"` by default.
- `MOVEMENT_DISTANCE_BIN_SIZE = 0.1` by default, so `23.86` and `23.87` group as `23.9`.
- `round_digits` groups by `MOVEMENT_DISTANCE_ROUND_DIGITS`.
- `exact` uses the exact selected movement distance. Exact grouping uses the raw numeric value as the grouping key, so `23.861` and `23.862` remain separate groups.

The raw exact distance remains visible in `Distribution Raw Data`, while `Distribution Summary`, chart metadata, chart titles, and chart file names use the configured group value consistently. The workbook also includes a text display column so bin sizes such as `0.1` and `0.05` are not forced into a fixed two-decimal format.

For each group, the `Distribution Summary` sheet reports count, mean, median, min, max, range, sample standard deviation, sample variance, population standard deviation, population variance, coefficient of variation, P05/P25/P75/P95 percentiles, fit status, chart status, and chart file path. Sample standard deviation and sample variance are the primary SD/variance values. With one sample, they are blank and the status is `InsufficientSamples`.

Charts are saved as PNG files in a workbook-specific folder by default:

```text
<output workbook stem>_distribution_charts
```

For example, `april10-analysis.xlsx` writes charts under `april10-analysis_distribution_charts`. Use `--distribution-output-dir` to override this. The default run folder is cleaned of old PNG files before new charts are generated, so chart paths in Excel point to the current run.

Each eligible group can get a histogram of `Duration (s)` when there are at least `MIN_SAMPLES_FOR_DISTRIBUTION_CHART` samples. A fitted normal curve requires at least `MIN_SAMPLES_FOR_NORMAL_FIT` samples and non-zero variance. Single-sample groups still appear in `Distribution Summary`, but no chart is generated. If no group reaches the chart threshold, the `Distribution Charts` sheet explains that all valid groups had too few samples. `--max-distribution-charts` prevents generating thousands of PNGs; largest groups are charted first.

New workbook sheets:

- `Distribution Summary`: one row per group.
- `Distribution Raw Data`: one row per activity record used by distribution analysis.
- `Distribution Eligibility`: rows that never became distribution candidates, such as unmatched rows, diagnostics, parse warnings, and invalid durations.
- `Distribution Exclusion Summary`: grouped reasons for records excluded from distribution analysis.
- `Distribution Charts`: embedded PNG charts and group metadata when chart embedding is enabled.
- `Log Coverage Summary`: TXT/control-log time coverage and PWM evidence counts.
- `Log Coverage Gaps`: every uncovered TXT interval after merging real control-log intervals.

Disable the feature with:

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis.xlsx" ^
  --no-distribution ^
  --no-gui
```

Save external chart files without embedding them in Excel with `--no-embed-distribution-charts`.

Strict distribution PWM matching is the default. Distribution groups accept only `PWM Match Status = MatchedByContainingLogFile` unless you explicitly opt in to looser evidence with `--distribution-allow-nearest-pwm`, `--distribution-allow-latest-before-pwm`, or `--distribution-allow-carry-forward-pwm`.

`--pwm-carry-forward` can attach the latest same-axis PWM when strict time matching cannot find reliable evidence, but those rows are marked with `PWM Match Status = MatchedByCarryForward`, `PWM Match Method = CarryForwardWithinSession`, and a PWM warning. Distribution analysis still excludes carry-forward PWM by default unless `--distribution-allow-carry-forward-pwm` is supplied. The Summary and Log Coverage sheets show both settings separately:

- `PWM Carry Forward Enabled`
- `Distribution Allows Carry Forward PWM`

Latest-before and latest-known strategies only use PWM events at or before the activity time. If only future PWM exists, the row is marked `NoEarlierPWMForAxis`; nearest future evidence is labeled separately as `MatchedByNearestFutureLogFile`.

Common PWM categories are intentionally separate:

- `NoControlLogsAvailable`: no control logs were scanned.
- `NoRelevantLogFileFound`: logs exist, but none are close enough to the activity time.
- `NoSameAxisPWMInFolder`: logs exist, but no PWM profile was found for that axis.
- `RelevantLogFileLacksAxisPWM`: a containing log exists but lacks the requested axis.
- `LatestBeforeStartTooFar`: the latest earlier PWM is outside the allowed time window.
- `MatchedByNearestFutureLogFile`: nearest-file fallback selected future PWM evidence.
- `PWMConflictInSourceFile`: a source file has conflicting normalized PWM percentages.

`--verbose` shows stage-level debug logging. Use `--trace-lines` with `--verbose` only when you need per-line parser logs.

## Diagnostics

Known ERR/WRN lines are parsed as diagnostics, not malformed parse warnings. Examples include:

```text
@[WRN] Node 3 (GETVER) response timeout (2016). Try again.
@[ERR] Node 3 (GETVER) response timeout (2015). Check connection.
@[ERR] motor Z RIGHT sensor cut
@[AMD] AMX partially corrupted [ ... ]
@[AMD] [N12] partial AMX amended [ ... ]
```

`[N12]` is mapped to axis `Z` in the diagnostics output.

Initialization failure remains a boundary event because it closes pending starts:

```text
@[ERR] [Z] cannot reach the target (30 seconds timeout). initialization failed.
```

Only truly malformed relevant lines become `Parse Warning` rows.

## Output Workbook

The workbook contains:

- `Details`
- `Summary`
- `PWM Sources`
- `Diagnostics`
- `Diagnostics Summary`
- `Distribution Summary`
- `Distribution Raw Data`
- `Distribution Eligibility`
- `Distribution Exclusion Summary`
- `Log Coverage Summary`
- `Log Coverage Gaps`
- `Distribution Charts` when chart embedding is enabled

### Details

Important columns include:

- `Match Status`
- `Duration Status`
- `PWM Match Status`
- `PWM Missing Reason`
- `Overall Status`
- `Source TXT Start Line Number`
- `Source TXT Start Line Text`
- `Source TXT End Line Number`
- `Source TXT End Line Text`
- `Boundary Line Number`
- `Boundary Line Text`
- `PWM Source Line Number`
- `PWM Source Line Text`
- `Candidate Duration (ms)`
- `Candidate Duration (s)`
- `Movement Start Position`
- `Movement Target Position`
- `Movement End Position`
- `Movement Commanded Distance`
- `Movement Actual Distance`
- `Selected Movement Distance`
- `Movement Distance Source`
- `Movement Distance Method`

Status columns have separate meanings:

- `Match Status`: whether activity pairing itself matched, was unmatched, was boundary-closed, or was rejected
- `Duration Status`: whether duration is valid, not applicable, too long, missing, or time-ordered incorrectly
- `PWM Match Status`: how PWM was selected or why it was not reliable
- `Overall Status`: top-level review state such as `OK`, `PWM Warning`, `Duration Warning`, `Boundary Closed`, `Closed By New Start`, `Initialization Failed`, `Unmatched`, `Diagnostic`, or `Parse Warning`

A valid duration row remains `Match Status = Matched` and `Duration Status = Valid` even when `Overall Status = PWM Warning`.

For non-matched activity rows, PWM warnings do not override the more important activity state. For example, an initialization failure with no available PWM remains `Overall Status = Initialization Failed`.

### Summary

Summary duration statistics use only:

- `Match Status = Matched`
- `Duration Status = Valid`

They exclude:

- boundary-closed rows
- initialization-failed rows
- unmatched starts or ends
- duration-too-long candidates
- diagnostics
- parse warnings
- PWM source-only rows

Summary counts include matched rows, unmatched starts and ends, boundary closures, starts closed by a newer start, initialization failures, parse warnings, duration warnings, and PWM warnings.

Diagnostics are summarized separately in `Diagnostics Summary`, grouped by:

- diagnostic type
- severity
- axis
- node ID

`Most Common PWM (%)` uses normalized PWM percent, so `-80` and `80` both contribute to `80`.

### PWM Sources

The `PWM Sources` sheet lists parsed PWM records with raw value, normalized percent, direction, direction-change flag, conflict flag, source line number, source line text, and notes.

### Diagnostics

The `Diagnostics` sheet lists structured main-log diagnostics with:

- time
- severity
- diagnostic type
- axis
- node ID
- source TXT line number
- source TXT line text
- notes

The `Diagnostics Summary` sheet counts diagnostics by type/severity/axis/node and shows first and last occurrence times.

### Distribution Summary

Use this sheet to compare consistency for identical motion conditions. A typical group might be:

```text
TXT = UroBiopsy_20260410.txt
PWM = 80%
Axis = Z
Movement Distance = 50.00
Action = clear_motor
```

The row contains all valid matched records in that group and shows duration statistics in milliseconds and seconds. It includes example movement positions, commanded/actual distances, selected distance source, grouped distance value, grouping mode, min/max movement values, unique position-combination count, and a `Position Values Mixed` flag.

Distance columns in this sheet have different meanings:

- `Movement Distance Raw Example`: one selected raw distance from the group.
- `Movement Distance Min` / `Movement Distance Max`: original selected distances inside the group.
- `Movement Distance Group Value`: the exact value used as the grouping key after `exact`, `round_digits`, or `bin` grouping.
- `Movement Distance Group Display`: text rendering of that group value using the configured grouping precision.
- `Selected Group Distance`: the grouped selected distance used for statistics; it intentionally duplicates the numeric group value with a clearer name.

With the default `bin` mode and bin size `0.1`, raw distances such as `49.03` group as `49.0`. The raw values remain visible in `Distribution Raw Data`.

`Distribution Status` explains whether a normal fit was possible, whether the sample count was too small, or whether variance was zero. `Chart File` points to the generated PNG when one was generated.

### Distribution Raw Data

This sheet lists each activity row used in distribution analysis, including group ID, source TXT line numbers and text, PWM raw value, PWM direction, PWM conflict data, PWM match method/status, PWM source line number and text, duration, movement start/target/end positions, commanded distance, actual distance, selected movement distance, grouping value, distance source, method, and notes. It is the fastest way to audit why a group has its statistics.

### Distribution Eligibility

This sheet groups records that did not meet basic distribution eligibility before PWM or movement-distance checks were applied. Typical reasons include `NotMatched`, `DurationInvalid`, `Diagnostic`, and `ParseWarning`. Keeping these separate prevents expected non-candidate rows from drowning out real distribution-specific exclusions.

### Distribution Exclusion Summary

This sheet includes only valid matched duration rows that were excluded from distribution analysis after eligibility checks. It records a primary reason plus secondary, PWM-specific, and movement-distance-specific reasons, so rows with multiple problems do not lose important context. Typical reasons include `MissingTrueMovementDistance`, `LatestBeforeStartTooFar`, `NoRelevantLogFileFound`, `NoControlLogsAvailable`, `NoSameAxisPWMInFolder`, `RelevantLogFileLacksAxisPWM`, `NearestLogFilePWMNotAllowedForDistribution`, `NearestFuturePWMNotAllowedForDistribution`, `LatestBeforePWMNotAllowedForDistribution`, `CarryForwardPWMNotAllowedForDistribution`, `PWMConflictInSourceFile`, `MissingPWM`, and `MissingGroupField`. It also shows the example row's `PWM Match Status`, `PWM Missing Reason`, `PWM Time Delta (ms)`, and source file so PWM coverage problems are not hidden behind a generic label.

### Log Coverage Summary

This sheet compares the TXT time span with the union of scanned control-log intervals. Separate log files with gaps are not treated as one continuous covered range. It reports merged interval count, covered duration, uncovered duration, gap count, coverage ratio, distribution-accepted PWM counts, containing/nearest/future-nearest/latest-before/carry-forward PWM counts, rows without PWM, specific PWM warning categories, and rows excluded because PWM reliability was not acceptable for distribution grouping. If coverage is low, the notes warn that many TXT activities may be excluded from PWM-based distribution analysis.

### Log Coverage Gaps

This sheet lists every uncovered TXT interval with gap index, start time, end time, duration, gap type, nearest previous control log, and nearest next control log. Gap types include `BeforeFirstControlLog`, `BetweenControlLogs`, `AfterLastControlLog`, and `NoControlLogsAvailable`. Use it when the coverage summary reports multiple gaps; the representative gap in `Log Coverage Summary` is only the first uncovered span.

### Distribution Charts

When embedding is enabled, each generated PNG appears with a small metadata block including movement distance source, method, grouping mode, and bin size. Chart titles also show whether the displayed group distance came from `ActualEndPosition`, `CommandTargetPosition`, or another configured source. When embedding is disabled, use the `Chart File` path in `Distribution Summary` to open the external image.

## Troubleshooting

### Row Is Closed By Boundary

Check `Closed By Boundary Type`, `Closed By Boundary Time`, `Boundary Line Number`, and `Boundary Line Text`. Common boundary types include `InitializationFailed`, `MotorAbortClicked`, `RobotMovingStopped`, `SystemExitSelected`, `McuControllerStopped`, and `ApplicationExited`.

### PWM Is Blank

PWM is left blank when no same-axis profile can be attached safely. Check `PWM Match Status`, `PWM Missing Reason`, `Notes`, `Distribution Exclusion Summary`, and `Log Coverage Summary`; the tool prefers leaving PWM empty over attaching an old unrelated value. In incomplete log folders, `NoRelevantLogFileFound`, `NoSameAxisPWMInFolder`, `RelevantLogFileLacksAxisPWM`, or `LatestBeforeStartTooFar` usually means the duration is still valid but PWM evidence is missing.

Use `--pwm-carry-forward` only when you deliberately want to assume same-axis PWM settings persist beyond strict log coverage. Carry-forward rows are marked as warnings and are not used for distribution grouping by default.

### Row Has PWM Warning

PWM warnings are used for normalized PWM conflicts, missing/incomplete log coverage, latest-before records outside the allowed time window, future-nearest fallback, carry-forward PWM, or no reliable PWM match. Direction changes alone are not PWM conflicts.

### Diagnostics Are Not Parse Warnings

Recognized ERR/WRN diagnostic lines go to `Diagnostics`. Parse warnings are reserved for relevant lines that could not be parsed into a known structure.

## Testing

```powershell
python -m compileall app backend
python -m pytest tests -v
```

If using the checked-in virtual environment:

```powershell
.\.venv\Scripts\python.exe -m compileall app backend
.\.venv\Scripts\python.exe -m pytest tests -v
```

## End-to-End Validation

Generate and inspect a real workbook:

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis-reviewed.xlsx" ^
  --no-gui ^
  --verbose
```

Then verify with `openpyxl` that:

- the old April 10 bad Z row is not `Matched` + `Valid`
- the `09:20:23:541` to `09:20:46:317` Z row is `Matched` + `Valid` with `22776 ms`
- the `08:37:43:959` Z start is closed by `InitializationFailed`
- node response timeouts and sensor cuts appear in `Diagnostics`, not as malformed parse warnings
- line number columns contain numbers and line text columns contain raw log text
