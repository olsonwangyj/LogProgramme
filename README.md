# Log Axis Activity Analyzer

## Project Overview

This project analyzes:

- one main UroBiopsy TXT log
- one folder containing multiple robot control `.log` files

It exports an Excel workbook that shows:

- axis activity start and end events
- duration in milliseconds and seconds
- source TXT lines
- PWM or duty-cycle information matched by axis and time
- workflow-boundary diagnostics such as initialization failures and boundary-closed starts

The tool is designed to be reusable for future TXT files and future log folders that follow the same general log structure.

## Input Requirements

### Main TXT File

The main TXT file contains runtime activity lines such as:

```text
@[Y] start clearing: -19.50
@[Y] motor cleared
@[Z] start moving to home: -30.10
@[X] reference found (SENSOR)
```

It can also contain workflow-boundary lines such as:

```text
User  @on_startInitRobot_clicked
MCU   @[ERR] [Z] cannot reach the target (30 seconds timeout). initialization failed.
MCU   @robot initialization done (69687ms)
Info  @UroBiopsy exited
MCU   @mcu controller stopped
```

### Log Folder

The log folder contains multiple robot control `.log` files. Typical examples include:

- initialization logs
- finalization logs
- relative logs
- absolute logs
- idle or scanning logs
- other robot control logs

The program parses `.log` files by default.

`.csv` files are ignored unless support is explicitly added later.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## CLI Usage

### Windows Example

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis-fixed.xlsx" ^
  --no-gui ^
  --verbose
```

### Unix or macOS Example

```bash
python -m app.log_activity_tool \
  --txt-file ./Log/UroBiopsy_20260410.txt \
  --log-folder ./Log/RobotMovingValues/20260410 \
  --output ./output/april10-analysis-fixed.xlsx \
  --no-gui \
  --verbose
```

### Required Arguments

- `--txt-file`
- `--log-folder`
- `--output`

### Optional Arguments

- `--encoding-txt`
- `--encoding-logs`
- `--recursive`
- `--association-strategy same_file_then_nearest|latest_before_start|latest_known`
- `--no-gui`
- `--verbose`

### Backward-Compatible Aliases

- `--log-a` maps to `--txt-file`
- `--log-b` is treated as a legacy input
  - if a `.log` file is passed, the tool uses its parent folder and logs a warning
  - if a folder is passed, that folder is used directly

## GUI Usage

If you run the tool without `--no-gui`, it can open file and folder pickers for missing paths:

```powershell
python -m app.log_activity_tool
```

The GUI flow is:

1. Select the main TXT file
2. Select the log folder
3. Select the output Excel path

## Output Workbook

The workbook contains:

- `Details`
- `Summary`
- `PWM Sources`

### Details

The `Details` sheet contains one row per matched activity, unmatched event, boundary-closed event, or parse warning.

Important columns include:

- `Axis`
- `Rule ID`
- `Start Event`
- `End Event`
- `Start Time`
- `End Time`
- `Duration (ms)`
- `Duration (s)`
- `PWM (%)`
- `PWM Raw Value`
- `PWM Direction`
- `PWM Source File`
- `PWM Match Status`
- `Match Status`
- `Duration Status`
- `Boundary Close Reason`
- `Notes`

### Summary

The `Summary` sheet contains:

1. a metadata block
2. summary by axis and event type
3. summary by axis only

Summary metrics include:

- average duration
- min and max duration
- median duration
- most common PWM (%)
- number of matched records
- number of unmatched starts
- number of unmatched ends
- number of boundary-closed records
- number of initialization-failed records
- number of duration warnings
- number of PWM warnings

### PWM Sources

The `PWM Sources` sheet lists parsed PWM records from all scanned log files.

Important columns include:

- `Log File`
- `Log File Start Time`
- `Log File End Time`
- `Axis`
- `PWM (%)`
- `PWM Raw Value`
- `Direction`
- `Command Type`
- `PWM Source Time`
- `PWM Source Line`
- `Is Status Confirmation`
- `Conflict`
- `Notes`

## Duration Matching Logic

The matcher is intentionally conservative.

Rules:

- matching is axis-local
- start and end must belong to the same configured rule
- stale starts are not kept forever
- a new start for the same axis and rule replaces the older pending start
- initialization failure closes pending starts
- a new initialization closes pending starts
- long durations are rejected instead of being silently accepted

Duration is always calculated as:

```text
End Time - Start Time
```

Known correct example:

```text
Start: 2026-03-31 09:39:40:554
End:   2026-03-31 09:39:47:373

Duration:
6819 ms
6.819 s
```

### April 10 Bug Explanation

The old bug was not the subtraction formula itself. The real problem was stale event matching.

Wrong old behavior:

```text
08:37:43.959 Z start clearing
matched to
09:20:46.317 Z motor cleared
```

That produced an unrealistic multi-minute duration because a failed initialization left the old start pending.

The fixed version closes the stale start when initialization failed and correctly matches:

```text
Start: 2026-04-10 09:20:23:541
End:   2026-04-10 09:20:46:317

Duration:
22776 ms
22.776 s
```

## PWM Matching Logic

PWM is parsed from all `.log` files in the selected folder.

The tool tracks PWM per:

- log file
- axis
- time range

It does not use one unsafe global latest PWM per axis.

Matching logic:

1. Find log files whose time range contains the activity time
2. If none contain it, find nearby files within a configurable threshold
3. Within the relevant files, select the same-axis PWM profile
4. Prefer the latest PWM command at or before the activity time
5. If the match is weak or conflicting, keep the note and warning visible

Signed raw PWM is normalized so the workbook keeps both:

- positive PWM magnitude
- original signed raw value
- direction

Example:

```text
[N6:H] RUN 255 176 (-80)
```

Becomes:

- `PWM Raw Value = -80`
- `PWM (%) = 80`
- `Direction = Reverse`

## Configuration

Most of the matching behavior is centralized in:

- `backend/log_axis_activity_analyzer/config.py`

Key configuration areas:

- event rules: `DEFAULT_EVENT_RULES`
- max duration limits: `MAX_EVENT_DURATION_MS`
- boundary patterns: `BOUNDARY_PATTERNS`
- PWM file-distance thresholds:
  - `PWM_FILE_NEARNESS_THRESHOLD_MS`
  - `PWM_LATEST_BEFORE_MAX_DELTA_MS`

## Testing

Build check:

```powershell
python -m compileall app backend
```

Run automated tests:

```powershell
python -m pytest tests -v
```

Helper scripts:

- `scripts/build.bat` and `scripts/build.sh`
- `scripts/run.bat` and `scripts/run.sh`
- `scripts/test.bat` and `scripts/test.sh`

## End-to-End Validation

Run the tool on a real TXT file and a real log folder, then inspect the workbook with `openpyxl`.

Example:

```powershell
python -m app.log_activity_tool ^
  --txt-file "D:\LogProgramme\Log\UroBiopsy_20260410.txt" ^
  --log-folder "D:\LogProgramme\Log\RobotMovingValues\20260410" ^
  --output "D:\LogProgramme\output\april10-analysis-fixed.xlsx" ^
  --no-gui ^
  --verbose
```

Generated Excel files are usually verification artifacts and are normally not committed.

## Troubleshooting

### No `.log` Files Found

- Confirm the selected folder is correct
- Use `--recursive` if the files are in subfolders
- The tool only scans `.log` files by default

### PWM Not Matched

- Check `PWM Match Status` and `Notes`
- Review the `PWM Sources` sheet
- Confirm the activity time overlaps the relevant control-log file time range

### Duration Warning or Duration Too Long

- Check whether the activity crossed a workflow boundary
- Review `Boundary Close Reason`
- Review the source TXT lines in `Details`

### Initialization Failed

- Look for `Initialization Failed` or `Closed By Boundary` in `Match Status`
- Review the original error line recorded in `Notes`

### GUI File Picker Not Opening

- Run with full CLI arguments and `--no-gui`
- Confirm the Python environment supports Tkinter

### Encoding Problems

- Try `--encoding-txt` or `--encoding-logs`
- Supported fallback encodings are defined in `config.py`

### Git Authentication Problems

- Use existing local SSH authentication if available
- If `git push` fails, do not expose credentials in the terminal output
- Complete the local commits and rerun the push command manually once SSH access is working
