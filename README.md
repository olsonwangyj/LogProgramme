# Log Axis Activity Analyzer

## Project Overview

LogProgramme analyzes one main UroBiopsy TXT log together with one folder of robot control `.log` files, then exports an Excel workbook for axis activity review.

The workbook is designed to answer four questions:

- Which axis activity starts and ends matched correctly?
- Which starts were closed by workflow boundaries such as initialization failure, abort, stop, or exit?
- Which PWM duty cycle was safely associated by axis and time?
- Which ERR/WRN diagnostic lines were observed without mixing them into parse errors?

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
- `--verbose`

Backward-compatible aliases:

- `--log-a` maps to `--txt-file`
- `--log-b` is treated as a legacy control-log input; if a file is passed, its parent folder is scanned

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
- `PWM Match Status = DirectionChangedOnly`
- no `PWM Warning` unless the normalized PWM percent actually conflicts

A real PWM conflict means normalized values differ, for example `60` and `80` in the same source file for the same axis.

## Diagnostics

Known ERR/WRN lines are parsed as diagnostics, not malformed parse warnings. Examples include:

```text
@[WRN] Node 3 (GETVER) response timeout (2016). Try again.
@[ERR] Node 3 (GETVER) response timeout (2015). Check connection.
@[ERR] motor Z RIGHT sensor cut
```

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

### Details

Important columns include:

- `Match Status`
- `Duration Status`
- `PWM Match Status`
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

Status columns have separate meanings:

- `Match Status`: whether activity pairing itself matched, was unmatched, was boundary-closed, or was rejected
- `Duration Status`: whether duration is valid, not applicable, too long, missing, or time-ordered incorrectly
- `PWM Match Status`: how PWM was selected or why it was not reliable
- `Overall Status`: top-level review state such as `OK`, `PWM Warning`, `Duration Warning`, `Boundary Closed`, `Initialization Failed`, `Diagnostic`, or `Parse Warning`

A valid duration row remains `Match Status = Matched` and `Duration Status = Valid` even when `Overall Status = PWM Warning`.

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

Summary counts include matched rows, unmatched starts and ends, boundary closures, initialization failures, diagnostics, parse warnings, duration warnings, and PWM warnings.

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

## Troubleshooting

### Row Is Closed By Boundary

Check `Closed By Boundary Type`, `Closed By Boundary Time`, `Boundary Line Number`, and `Boundary Line Text`. Common boundary types include `InitializationFailed`, `MotorAbortClicked`, `RobotMovingStopped`, `SystemExitSelected`, `McuControllerStopped`, and `ApplicationExited`.

### PWM Is Blank

PWM is left blank when no same-axis profile can be attached safely. Check `PWM Match Status` and `Notes`; the tool prefers leaving PWM empty over attaching an old unrelated value.

### Row Has PWM Warning

PWM warnings are used for normalized PWM conflicts or no reliable PWM match. Direction changes alone are not PWM conflicts.

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
