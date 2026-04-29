# REQ-001 Log Axis Activity Analyzer

> Status: Requirement Finalized
> Created: 2026-04-27
> Updated: 2026-04-29

## 1. Background

Engineers currently inspect MCU runtime logs and robot control logs by hand to understand how long each axis spends on reference, clearing, homing, and maximum-position activities. Manual review is slow, easy to misread, and hard to reuse across future log captures. A reusable Python tool is required so engineers can select one compatible main TXT file plus a folder of robot control logs, parse them safely, and export a structured Excel report for analysis and traceability.

## 2. Target Users & Scenarios

- Test engineers who validate robot motion behavior after firmware or mechanical changes.
- Field or support engineers who compare runtime behavior between customer sessions.
- QA engineers who need a repeatable report instead of manual stopwatch calculations.
- Typical scenarios:
  - Analyze an initialization or runtime session from two uploaded files.
  - Confirm that one axis took longer than expected to clear or home.
  - Compare durations against axis duty-cycle settings captured in the control log.
  - Extend the parser with new start/end patterns without rewriting the full tool.

## 3. Functional Requirements

### F-01 Input Selection And Execution

- Main flow:
  - The tool shall let the user provide one main TXT file, one folder containing multiple `.log` files, and an output workbook path.
  - The tool shall support command-line execution for automation.
  - The preferred CLI parameters shall be `--txt-file`, `--log-folder`, and `--output`.
  - The tool may keep backward-compatible aliases for older parameter names when practical.
  - The tool may also offer a lightweight desktop file picker when command-line paths are omitted.
- Error handling:
  - If an input file is missing, unreadable, or empty, the tool shall stop with a clear error message.
  - If the selected log folder does not exist or contains no `.log` files, the tool shall stop with a clear error message.
  - If the output path is invalid, the tool shall report the issue before processing starts.
- Edge cases:
  - The tool shall support Unicode paths and filenames with spaces.
  - The tool shall allow different text encodings when possible.
  - The tool shall scan all `.log` files in the selected folder.
  - Recursive folder scanning may be offered as an optional setting.

### F-02 Parse Main Activity Log A Across The Full File

- Main flow:
  - The tool shall scan the entire Log File A, not just initialization blocks.
  - The tool shall detect lines with timestamps formatted as `YYYY-MM-DD HH:MM:SS:ms`, axis markers such as `@[Y]`, and the trailing activity message.
  - The parser shall preserve the raw source line and source line number for every relevant record.
- Error handling:
  - Malformed or partially readable lines shall not crash the tool.
  - Unreadable activity lines shall be recorded as parse warnings.
- Edge cases:
  - The parser shall keep chronological order across the full file.
  - Non-activity axis lines may still be retained when needed to extract companion numeric values.

### F-03 Parse PWM / Duty-Cycle Log Folder

- Main flow:
  - The tool shall scan all relevant `.log` files in the selected folder.
  - The tool shall parse axis-specific `RUN` and `VEL` lines such as `[N4:Y] RUN 0 80 (80)` and `[N5:V] VEL 0 80 (80)`.
  - The tool shall extract the axis and the final numeric percentage in parentheses.
  - The tool shall preserve the source line, source line number, filename, command type, confirmation flag, and the most recent timestamp available for each PWM event.
  - The tool shall determine the earliest and latest timestamp found in each parsed `.log` file.
  - Signed duty-cycle values such as `(-80)` shall be supported.
- Error handling:
  - Malformed `RUN` or `VEL` lines shall be logged as parse warnings instead of terminating execution.
  - If a PWM line is found before a parseable timestamp, the line shall still be retained with a warning so fallback matching remains possible.
- Edge cases:
  - Repeated confirmation lines such as `RUN 'S'` and `VEL 'S'` shall not break parsing.
  - Multi-letter axis identifiers such as `NG` shall be supported when they appear in the control logs.
  - Different log files may contain different PWM values for the same axis.
  - If multiple PWM values for the same axis appear inside one log file, the tool shall preserve the conflict context and use a deterministic selection rule.

### F-04 Configurable Axis-Local Event Matching

- Main flow:
  - The tool shall match start and end events only within the same axis.
  - Matching rules shall be stored in a centralized configuration dictionary or equivalent mapping that is easy to extend.
  - The default rule set shall include at least:
    - `start clearing` -> `motor cleared`
    - `start moving to max pos` -> `motor reached max pos`
    - `start moving to home` -> `motor homed`
    - `start searching reference` -> `reference found`
- Error handling:
  - If an end event appears with no pending start event for the same axis and rule, the tool shall emit an `Unmatched End` row.
  - If a start event never receives a matching end event, the tool shall emit an `Unmatched Start` row.
- Edge cases:
  - Multiple axes may be active in interleaved order, and matching shall stay axis-local.
  - Repeated runs in one file shall be handled without resetting the parser between sections.

### F-05 Duration, Values, And Source Preservation

- Main flow:
  - For each matched pair, the tool shall record axis, normalized start event, normalized end event, start timestamp, end timestamp, duration in milliseconds, duration in seconds, and the original source lines.
  - The tool shall extract numeric values embedded in activity messages when available, such as `start clearing: -19.50`.
  - The tool shall attempt to extract end-side numeric values when present inline or on a directly related companion line for the same axis.
  - Duration shall be calculated strictly as `End Time - Start Time` using reliable timestamp parsing that preserves milliseconds.
- Error handling:
  - If a numeric value cannot be extracted, the corresponding field shall remain blank instead of failing the record.
  - If timestamps cannot be parsed for an otherwise relevant line, the tool shall create a parse warning.
  - If a matched end timestamp is earlier than its start timestamp, the tool shall create a `Duration Warning` instead of producing a fake duration.
- Edge cases:
  - Fractional values and negative values shall be supported.
  - Companion lines such as `min: -29.51` and `max: 0.00` shall be usable for end values when appropriate.
  - Duration validation shall verify that `Duration (ms)` equals `(End Time - Start Time).total_seconds() * 1000` and that `Duration (s)` equals `Duration (ms) / 1000`.

### F-06 PWM Association

- Main flow:
  - The tool shall maintain PWM history per axis and per log file from the selected log folder.
  - For each activity record, the tool shall use both axis and activity start time to find the most relevant PWM.
  - The preferred association rule shall be a PWM record for the same axis inside a log file whose time window overlaps or is close to the activity time, with preference for a PWM record at or before the activity start time.
  - If no such record exists, the tool shall fall back to the closest relevant log file by time.
  - If that still fails, the tool shall fall back to the latest known PWM for the same axis before the activity start time.
- Error handling:
  - Missing PWM data for an axis shall not fail the activity record; the PWM field may remain blank.
  - Uncertain PWM matches shall be marked transparently instead of silently guessed.
  - The chosen PWM match method, source file, source line, source time, time delta, and match status shall be written to the detail row.
- Edge cases:
  - The matching strategy shall be easy to replace later.
  - Records without a start time, such as unmatched ends, may use end time or the latest known PWM as a fallback when appropriate.
  - If multiple conflicting PWM values exist inside one log file for the same axis, the notes shall describe the conflict and the selected deterministic rule.

### F-07 Excel Workbook Export

- Main flow:
  - The tool shall export one `.xlsx` workbook containing at least `Details` and `Summary` sheets.
  - `Details` shall contain one row per detected activity or warning record.
  - `Summary` shall aggregate results by axis and event type, and may also include a second summary block grouped only by axis.
  - The workbook may include a third `PWM Sources` sheet to help reviewers inspect parsed PWM records.
- Error handling:
  - Workbook generation failures shall be reported clearly.
  - Partial analysis results shall still be preserved in memory until export is attempted.
- Edge cases:
  - Empty groups shall show blank duration statistics instead of invalid numeric output.
  - Large numbers of records shall remain exportable without manual Excel editing.

### F-08 Status, Logging, And Resilience

- Main flow:
  - Every detail row shall have a status of `Matched`, `Unmatched Start`, `Unmatched End`, `Parse Warning`, `Duration Warning`, or `PWM Warning`.
  - The application shall emit useful runtime logs for parsing, matching, association, and export steps.
  - The code shall be modular and maintainable, with centralized regex patterns and matching rules.
- Error handling:
  - Bad lines, encoding issues, and partially malformed data shall degrade gracefully instead of crashing the run.
  - The application shall return a non-zero exit code for fatal execution failures such as missing files or Excel write errors.
- Edge cases:
  - The parser shall remain usable for future logs that follow the same general structure.
  - The solution shall tolerate large files by streaming text input line by line where practical.

## 4. Non-functional Requirements

- N-01 Performance: The tool shall process the input files in a streaming-friendly manner and avoid loading unnecessary duplicate structures for large logs.
- N-02 Compatibility: The tool shall run on Python 3.10+ and target Windows-friendly usage while remaining cross-platform for command-line execution.
- N-03 Maintainability: Regex patterns, event rules, and association strategy choices shall be centralized and clearly documented.
- N-04 Observability: Code paths shall include sufficient logging to diagnose parse failures, matching decisions, and export outcomes.
- N-05 Robustness: The tool shall continue processing when individual lines are malformed, recording warnings rather than aborting the whole analysis.
- N-06 Usability: The generated Excel workbook shall be immediately readable, with stable column names and grouped summaries.

## 5. Out of Scope

- Editing or repairing the source log files.
- Real-time log tailing or continuous monitoring.
- Database storage, web deployment, or multi-user server features.
- Statistical trend comparison across multiple workbook runs.
- Automatic discovery of new event-pair rules without configuration updates.

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | User provides one valid TXT file, one valid log folder, and one output path | Tool completes one analysis run and writes an `.xlsx` workbook |
| AC-02 | F-02 | Log A contains `MCU   @[Y] start clearing: -19.50` and `MCU   @[Y] motor cleared` later in the file | Tool captures both lines, keeps the raw source, and treats them as the same axis activity |
| AC-03 | F-04 | Start and end events for different axes are interleaved | Matching remains axis-local and does not cross axes |
| AC-04 | F-05 | Start time is `2026-03-31 09:39:40:554` and end time is `2026-03-31 09:39:47:373` | Workbook shows duration `6819` ms and `6.819` s |
| AC-05 | F-05 | Start line contains `start moving to home: -13.58` | Workbook stores `-13.58` as the start value |
| AC-06 | F-03 | The log folder contains `[N6:H] RUN 255 176 (-80)` and `[N6:H] VEL 0 80 (80)` | Parser stores axis `H`, command types, timestamps, and preserves both PWM values for later association |
| AC-07 | F-03 | The log folder contains `[N11:NG] RUN 0 100 (100)` | Parser stores multi-letter axis `NG` and PWM `100` |
| AC-08 | F-06 | A same-axis PWM record exists in a relevant log file near the activity time | The detail row contains PWM value, source file, source line, source time, time delta, match method, and match status |
| AC-09 | F-06 | No confident PWM match exists for an activity axis/time | The workbook leaves PWM empty or marks it transparently with a warning status and notes |
| AC-10 | F-07 | Analysis finishes successfully | Workbook contains `Details` and `Summary` sheets with the requested columns and may include `PWM Sources` |
| AC-11 | F-08 | A start event never receives an end event | Workbook contains a row with status `Unmatched Start` instead of crashing |
| AC-12 | F-08 | A malformed relevant line is encountered | Workbook contains a row with status `Parse Warning` and explanatory notes |
| AC-13 | F-05 | A matched pair has an end time earlier than the start time | Workbook contains `Duration Warning` instead of a fake negative duration |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-04-27 | Initial version | ALL | - |
| v2 | 2026-04-29 | Changed input model to TXT file plus log folder, added multi-file PWM parsing and association rules, and formalized duration validation and warning outputs | F-01, F-03, F-05, F-06, F-07, F-08 | Support folder-based control logs and fix/report duration and PWM matching more transparently |
