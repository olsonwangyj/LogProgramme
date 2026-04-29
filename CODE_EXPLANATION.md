# Code Explanation

This file explains the current implementation of the log analysis tool in `D:\LogProgramme` based on the code that exists in the repository now, after the TXT-plus-log-folder update.

## 1. Project Overview

### What problem the tool solves

The tool converts robot runtime logs into a structured Excel workbook so engineers do not have to manually trace axis activity durations and PWM settings.

It answers questions such as:

- When did axis `Y` start clearing?
- When did it finish?
- How long did it take, in milliseconds and seconds?
- What numeric target or position value was present on the start or end side?
- Which PWM setting most likely applied to that axis at that time?

### What the inputs are

The tool now works with two user-provided inputs:

- Main TXT log:
  - A UroBiopsy application log such as `Log/UroBiopsy_20260331.txt`
  - Parsed by `backend/log_axis_activity_analyzer/log_a_parser.py`
- Log folder:
  - A folder containing multiple robot control `.log` files such as `Log/RobotMovingValues/20260331/`
  - Scanned by `backend/log_axis_activity_analyzer/log_folder_scanner.py`
  - Each file is parsed by `backend/log_axis_activity_analyzer/log_b_parser.py`

### What the outputs are

The primary output is one `.xlsx` workbook, for example:

- `output/sample-folder-analysis.xlsx`

The workbook contains:

- `Details`
  - One row per matched activity, unmatched event, or parse warning
- `Summary`
  - Aggregated metrics by axis and event type, plus a second aggregation by axis only
- `PWM Sources`
  - A trace sheet containing all parsed PWM records from the log folder

## 2. Folder and File Structure

### Root-level structure

- `app/`
  - Thin runtime entry layer
- `backend/log_axis_activity_analyzer/`
  - Reusable analysis package
- `requirements/REQ-001-log-axis-activity-analyzer/`
  - Requirement and technical design docs
- `tests/`
  - Regression tests
- `scripts/`
  - Convenience wrappers for build, run, and test
- `output/`
  - Generated sample workbooks
- `README.md`
  - User-facing usage guide
- `CODE_EXPLANATION.md`
  - This developer-facing explanation

### Entrypoint

- `app/log_activity_tool.py`
  - Defines the CLI
  - Provides optional Tkinter file/folder pickers
  - Invokes the backend service
  - Prints a short run summary

### Backend package

- `backend/log_axis_activity_analyzer/config.py`
  - Centralized regex patterns, event rules, worksheet column definitions, and constants
- `backend/log_axis_activity_analyzer/models.py`
  - Dataclasses used across the pipeline
- `backend/log_axis_activity_analyzer/file_loader.py`
  - Shared text loading with encoding fallback
- `backend/log_axis_activity_analyzer/time_utils.py`
  - Timestamp parsing, formatting, duration calculation, and time-distance helpers
- `backend/log_axis_activity_analyzer/log_a_parser.py`
  - Parses the main TXT log into axis events
- `backend/log_axis_activity_analyzer/log_b_parser.py`
  - Parses one robot control `.log` file into PWM events
- `backend/log_axis_activity_analyzer/log_folder_scanner.py`
  - Finds and parses all `.log` files in a folder
- `backend/log_axis_activity_analyzer/matcher.py`
  - Matches start and end events within the same axis only
- `backend/log_axis_activity_analyzer/duty_cycle_associator.py`
  - Attaches the most relevant PWM record to each activity row
- `backend/log_axis_activity_analyzer/validation.py`
  - Recomputes durations and finalizes row status values
- `backend/log_axis_activity_analyzer/summary.py`
  - Builds `pandas` DataFrames for the Excel workbook
- `backend/log_axis_activity_analyzer/excel_exporter.py`
  - Writes the workbook with `pandas.ExcelWriter` and `openpyxl`
- `backend/log_axis_activity_analyzer/service.py`
  - Orchestrates the whole analysis run

### Tests

- `tests/test_service.py`
  - Covers timestamp parsing, duration calculation, axis-local matching, log-folder parsing, PWM association, and a real end-to-end run

### Scripts

- `scripts/build.bat` and `scripts/build.sh`
  - Run `python -m compileall app backend`
- `scripts/run.bat` and `scripts/run.sh`
  - Run the CLI entrypoint
- `scripts/test.bat` and `scripts/test.sh`
  - Run `pytest tests -v`

### Requirement docs

- `requirements/REQ-001-log-axis-activity-analyzer/requirement.md`
  - Functional and non-functional expectations
- `requirements/REQ-001-log-axis-activity-analyzer/technical.md`
  - Architecture and design choices
- `requirements/*.puml`
  - PlantUML source diagrams

## 3. End-to-End Execution Flow

When the user runs the tool, the pipeline is:

1. `app/log_activity_tool.py:main()` parses CLI arguments.
2. `_resolve_paths()` determines the TXT file, log folder, and output workbook path.
3. If required paths are missing and `--no-gui` was not used, `_prompt_for_missing_paths()` opens:
   - a file picker for the TXT log
   - a folder picker for the log folder
   - a save dialog for the Excel output
4. `LogAnalysisService.run_analysis()` in `service.py` validates the paths.
5. `MainLogParser.parse()` parses the full TXT file into `AxisLogEvent` objects.
6. `LogFolderScanner.scan()` finds every `.log` file in the selected folder.
7. `DutyCycleLogParser.parse()` parses each individual `.log` file into `PWMEvent` objects and file-level metadata.
8. `EventMatcher.build_activity_records()` matches configured start/end pairs within the same axis.
9. `DutyCycleAssociator.attach()` chooses the most relevant PWM record for each activity row.
10. `LogAnalysisService._append_parse_warnings()` adds parse warnings as `ActivityRecord` rows.
11. `ActivityValidator.validate()` recomputes duration and assigns final statuses such as `Matched`, `PWM Warning`, or `Duration Warning`.
12. `SummaryGenerator.build_report_frames()` converts records into workbook-ready `DataFrame` objects.
13. `ExcelExporter.export()` writes `Details`, `Summary`, and `PWM Sources`.
14. `main()` prints a concise console summary.

## 4. File-by-File Code Explanation

### `app/log_activity_tool.py`

Why it exists:

- It is the only executable entrypoint.
- It keeps CLI and GUI behavior separate from the analysis logic.

Important functions:

- `main(argv=None) -> int`
  - Top-level application flow
- `_parse_arguments()`
  - Defines the current CLI contract
- `_configure_logging(verbose)`
  - Configures console logging
- `_resolve_paths(args)`
  - Resolves preferred flags and legacy compatibility paths
- `_resolve_legacy_log_folder(legacy_value)`
  - Converts old `--log-b` input into the new folder-based model
- `_prompt_for_missing_paths(missing_keys)`
  - Opens Tkinter dialogs
- `_print_summary(result)`
  - Prints workbook path and counts after a run

Notable CLI flags:

- `--txt-file`
- `--log-folder`
- `--output`
- `--log-b`
  - Legacy compatibility alias
- `--association-strategy`
- `--recursive-log-folder`
- `--no-gui`
- `--verbose`

### `backend/log_axis_activity_analyzer/config.py`

Why it exists:

- It centralizes parsing rules and sheet schemas so they are not duplicated.

Important contents:

- `TIMESTAMP_FORMAT`
  - `"%Y-%m-%d %H:%M:%S:%f"`
- `SUPPORTED_ENCODINGS`
  - `utf-8`, `utf-8-sig`, `cp1252`, `latin-1`
- `MAIN_LOG_LINE_PATTERN`
  - Matches lines such as `2026-03-31 09:39:40:554 MCU   @[Y] start clearing: -19.50`
- `CONTROL_TIMESTAMP_PATTERN`
  - Matches timestamp-bearing lines inside robot control logs
- `CONTROL_PWM_PATTERN`
  - Matches PWM lines such as `RUN`, `RUN 'S'`, `VEL`, and `VEL 'S'`
- `DEFAULT_EVENT_RULES`
  - The central start/end matching rules
- `PWM_FILE_NEARNESS_THRESHOLD_MS`
  - Used by nearest-file PWM association
- `DETAIL_COLUMNS`, `EVENT_SUMMARY_COLUMNS`, `AXIS_SUMMARY_COLUMNS`, `PWM_SOURCE_COLUMNS`
  - Exact column order for workbook output

### `backend/log_axis_activity_analyzer/models.py`

Why it exists:

- The analysis pipeline passes through several distinct data shapes.
- Dataclasses make those shapes explicit and easier to test.

Important dataclasses:

- `EventRule`
  - One configurable start/end rule
- `AxisLogEvent`
  - One parsed activity line from the TXT log
- `PWMEvent`
  - One parsed PWM-related line from a robot control log
- `ParseWarning`
  - A recoverable parse issue that should still appear in output
- `MainLogParseResult`
  - Parsed TXT events plus warnings
- `DutyCycleLogFileResult`
  - Parsed PWM events, file time range, and conflicts for one `.log` file
- `DutyCycleFolderParseResult`
  - Aggregate result for an entire log folder
- `PWMMatchSelection`
  - Internal selection result used during PWM association
- `ActivityRecord`
  - The main row model used before DataFrame creation
- `ReportFrames`
  - Holds the `Details`, `Summary`, and `PWM Sources` DataFrames
- `AnalysisRunResult`
  - The summary returned to the CLI entrypoint

### `backend/log_axis_activity_analyzer/file_loader.py`

Why it exists:

- Both TXT parsing and PWM log parsing need identical file-loading behavior.

Main role:

- `TextFileLoader.iter_lines(...)`
  - Opens the file with encoding fallback and preserves line numbers

### `backend/log_axis_activity_analyzer/time_utils.py`

Why it exists:

- Time parsing and duration calculation are critical and reused in multiple modules.

Important functions:

- `parse_log_timestamp(text)`
  - Parses `YYYY-MM-DD HH:MM:SS:ms`
- `format_log_timestamp(dt)`
  - Converts `datetime` back into workbook-friendly text
- `calculate_duration_values(start_time, end_time)`
  - Computes milliseconds and seconds
- `compute_time_delta_ms(a, b)`
  - Absolute delta between two timestamps
- `compute_range_distance_ms(reference, start, end)`
  - Distance from a timestamp to a file time window

### `backend/log_axis_activity_analyzer/log_a_parser.py`

Why it exists:

- It owns parsing of the main UroBiopsy TXT file.

Main behavior:

- Reads the whole file, not just initialization
- Uses `MAIN_LOG_LINE_PATTERN`
- Extracts:
  - timestamp
  - axis
  - raw message
  - source line
  - line number
  - optional numeric value at the end of the line
- Produces `AxisLogEvent` objects
- Emits `ParseWarning` for malformed-but-relevant TXT lines

### `backend/log_axis_activity_analyzer/log_b_parser.py`

Why it exists:

- It parses one robot control `.log` file at a time.

Important functions:

- `parse(file_path, preferred_encoding=None)`
  - Main file parser
- `_parse_control_timestamp(...)`
  - Updates the most recent timestamp seen in the file
- `_build_pwm_event(...)`
  - Parses `RUN` and `VEL` PWM lines
- `_build_parse_warning(...)`
  - Emits warnings for malformed PWM-like lines
- `_mark_confirmed_events(...)`
  - Marks setting lines as confirmed when a matching `'S'` status line exists
- `_annotate_axis_conflicts(...)`
  - Records when one file contains multiple PWM values for the same axis

Important detail:

- PWM lines do not always carry their own timestamp.
- The parser associates each PWM line with the latest preceding control-log timestamp line in the same file.

### `backend/log_axis_activity_analyzer/log_folder_scanner.py`

Why it exists:

- The new input model is a folder, not one single PWM file.

Important functions:

- `scan(folder_path, preferred_encoding=None, recursive=False)`
  - Discovers and parses all `.log` files
- `_discover_log_files(root, recursive)`
  - Uses `glob("*.log")` or `rglob("*.log")`
- `_parse_one_file(...)`
  - Converts file-level parse failures into folder-level warnings

### `backend/log_axis_activity_analyzer/matcher.py`

Why it exists:

- It turns parsed TXT events into activity records that can later receive duration and PWM data.

Important functions:

- `build_activity_records(events)`
  - Main matching loop
- `_classify_event(message)`
  - Maps a message to a configured start or end rule
- `_register_start_event(...)`
  - Queues a start event
- `_resolve_end_event(...)`
  - Matches an end event against a pending start on the same axis and same rule
- `_build_matched_record(...)`
  - Creates a `Matched` activity row
- `_find_end_value(...)`
  - Looks for a same-axis companion `min:` or `max:` value near the end event
- `_build_unmatched_start_record(...)`
  - Creates an `Unmatched Start` row
- `_build_unmatched_end_record(...)`
  - Creates an `Unmatched End` row

Important implementation choice:

- The pending queue key is `(axis, rule_id)`.
- That is the main mechanism that enforces axis-local matching.

### `backend/log_axis_activity_analyzer/duty_cycle_associator.py`

Why it exists:

- PWM association is separate from event matching because it uses a different input source and its own selection rules.

Important functions:

- `attach(records, log_file_results, strategy="same_file_then_nearest")`
  - Enriches each `ActivityRecord`
- `_select_pwm_event(...)`
  - Strategy dispatcher
- `_select_same_file_time_window(...)`
  - Best case: same axis, file time window overlaps reference time, latest PWM at or before start
- `_select_nearest_log_file(...)`
  - Fallback: closest relevant file by time range
- `_select_latest_before_start(...)`
  - Fallback: latest timestamped PWM before activity start across files
- `_select_latest_known(...)`
  - Looser fallback strategy
- `_apply_selection(...)`
  - Copies selected PWM fields into the record

Important statuses it can produce:

- `MatchedBySameFileTimeWindow`
- `MatchedByNearestLogFile`
- `MatchedByLatestBeforeStart`
- `NoPWMFoundForAxis`
- `NoRelevantLogFileFound`

Important detail:

- When selecting among multiple eligible events, the code prefers an actual setting command over a confirmation/status line.

### `backend/log_axis_activity_analyzer/validation.py`

Why it exists:

- Duration calculation and final status handling are centralized here so they are easy to verify and change.

Important functions:

- `validate(records)`
  - Validates all rows in place
- `_validate_duration(record)`
  - Recomputes duration as `end_time - start_time`
- `_validate_pwm(record)`
  - Marks uncertain or missing PWM matches as warnings
- `_finalize_status(record)`
  - Chooses `Matched`, `PWM Warning`, or `Duration Warning`

Important detail:

- This module is where the duration bug is prevented from reappearing.
- Matched rows do not trust any preexisting text duration; they recompute duration from parsed timestamps.

### `backend/log_axis_activity_analyzer/summary.py`

Why it exists:

- It converts record objects into workbook-ready tables and computes summary metrics.

Important functions:

- `build_report_frames(records, log_file_results)`
  - Produces all output tables
- `_build_detail_row(record)`
  - Shapes one row for `Details`
- `_build_event_summary_rows(records)`
  - Aggregates by `(axis, event type)`
- `_build_axis_summary_rows(records)`
  - Aggregates by `axis`
- `_build_summary_metrics(group_records)`
  - Computes averages, min, max, median, and counts
- `_build_pwm_source_rows(log_file_results)`
  - Builds the `PWM Sources` sheet

Important detail:

- Duration metrics are calculated from rows whose `activity_status` is `Matched` and that do not have a duration warning.
- A row can still contribute valid duration statistics even if its final display status is `PWM Warning`.

### `backend/log_axis_activity_analyzer/excel_exporter.py`

Why it exists:

- It isolates workbook writing and formatting from parsing logic.

Important functions:

- `export(output_path, report_frames, metadata)`
  - Main workbook writer
- `_write_summary_sheet(...)`
  - Writes metadata plus both summary blocks
- `_write_pwm_sources_sheet(...)`
  - Writes optional PWM trace rows
- `_format_details_sheet(...)`
  - Freeze panes, auto-filter, and auto-fit
- `_format_summary_sheet(...)`
  - Freeze panes and auto-fit
- `_format_pwm_sources_sheet(...)`
  - Freeze panes, auto-filter, and auto-fit

### `backend/log_axis_activity_analyzer/service.py`

Why it exists:

- It is the high-level orchestration layer and the cleanest place to understand the overall pipeline.

Important methods:

- `run_analysis(...)`
  - Main end-to-end service method
- `_validate_paths(...)`
  - Verifies TXT file, log folder, and output path
- `_append_parse_warnings(...)`
  - Converts warnings into detail rows
- `_build_warning_record(...)`
  - Shapes one warning row
- `_build_run_result(...)`
  - Produces the summary returned to the CLI

## 5. Core Logic Explanation

### Timestamp parsing

All timestamps use the form:

- `YYYY-MM-DD HH:MM:SS:milliseconds`

Example:

- `2026-03-31 09:39:40:554`

The code parses this with `parse_log_timestamp()` in `time_utils.py`, which uses:

- `TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S:%f"`

That format preserves millisecond precision because `%f` reads microseconds and the three-digit millisecond value is interpreted as `554000` microseconds.

### Regex parsing approach

The tool uses compiled regex patterns from `config.py`.

For TXT activity lines:

- `MAIN_LOG_LINE_PATTERN`
  - Extracts timestamp, axis, and message

For control log timestamps:

- `CONTROL_TIMESTAMP_PATTERN`
  - Detects timestamp-bearing transport lines

For PWM lines:

- `CONTROL_PWM_PATTERN`
  - Extracts:
    - node id such as `N4`
    - axis such as `Y` or `NG`
    - command `RUN` or `VEL`
    - optional `'S'` marker
    - final parenthesized PWM value

### Axis extraction

Axis extraction is done from:

- TXT lines via `@[Y]` inside `MAIN_LOG_LINE_PATTERN`
- PWM lines via `[N4:Y]` inside `CONTROL_PWM_PATTERN`

The TXT regex currently expects a single uppercase axis letter. The PWM regex allows one or more uppercase letters for cases like `NG`.

### Start/end event rule matching

Event matching is driven by `DEFAULT_EVENT_RULES` in `config.py`. Each rule has:

- `rule_id`
- `start_label`
- `end_label`
- `start_pattern`
- `end_pattern`

The matcher does not hardcode message strings in the loop. It classifies each TXT event by checking the configured regexes.

### Why matching is axis-local

Matching is intentionally local to the same axis because identical event phrases can appear on multiple axes in overlapping time windows.

The matcher stores pending starts in:

- `pending[(axis, rule_id)]`

That means:

- `@[X] start clearing` can only match `@[X] motor cleared`
- It cannot be consumed by a `Y` or `Z` end event

### How unmatched starts and unmatched ends are handled

If the file ends and a queued start still exists:

- the matcher creates an `Unmatched Start` record

If an end event appears and there is no pending start for `(axis, rule_id)`:

- the matcher creates an `Unmatched End` record

These rows are preserved in `Details` rather than being discarded.

### Duration calculation

Duration is not derived from row positions or string manipulation.

It is recomputed in `ActivityValidator._validate_duration()` using:

- `calculate_duration_values(record.start_time, record.end_time)`

That function returns:

- `Duration (ms)` as an integer-like millisecond count
- `Duration (s)` as a numeric seconds value with millisecond precision

If the end time is earlier than the start time:

- the record becomes a `Duration Warning`
- duration fields are left empty

### How duty cycle is associated

PWM association uses both axis and time.

For each activity row:

1. Choose the reference time:
   - `start_time` if present
   - otherwise `end_time`
2. Keep only log files that contain at least one PWM event for the same axis.
3. Apply the selected strategy.

Default strategy:

- `same_file_then_nearest`

This does:

1. Same-file time window
   - If the activity time falls inside a control log file's `[file_start_time, file_end_time]`, choose the latest same-axis PWM at or before the activity start.
2. Nearest relevant log file
   - If no same-window match exists, choose the closest file within `PWM_FILE_NEARNESS_THRESHOLD_MS`.
3. Latest before start across files
   - If still unresolved, choose the latest timestamped same-axis PWM before the activity start.
4. Otherwise emit a no-match status.

Fallback strategies also exist:

- `latest_before_start`
- `latest_known`

### How uncertain PWM matches are handled

The code does not silently treat all matches as equally reliable.

Examples:

- `MatchedBySameFileTimeWindow`
  - Considered the strongest default match
- `MatchedByNearestLogFile`
  - Marked as `PWM Warning` because the file is only a nearest-time fallback
- `NoPWMFoundForAxis`
  - Marked as `PWM Warning`
- `NoRelevantLogFileFound`
  - Marked as `PWM Warning`

The chosen source file, line, time, method, delta, and notes are all written into the workbook so a human reviewer can judge the result.

### How summary metrics are computed

`SummaryGenerator._build_summary_metrics()` computes:

- `Count`
- `Avg Duration (ms)`
- `Avg Duration (s)`
- `Min Duration (ms)`
- `Max Duration (ms)`
- `Median Duration (ms)`
- `Most Common PWM (%)`
- `Number of Matched records`
- `Number of Unmatched Starts`
- `Number of Unmatched Ends`
- `Number of Duration Warnings`
- `Number of PWM Warnings`

Duration-based statistics only use rows that were actual matched activities and did not fail duration validation.

## 6. Configuration Explanation

### `DEFAULT_EVENT_RULES`

`DEFAULT_EVENT_RULES` is a list of `EventRule` objects in `config.py`.

Current defaults include:

- `start searching reference` -> `reference found`
- `start clearing` -> `motor cleared`
- `start moving to max pos` -> `motor reached max pos`
- `start moving to home` -> `motor homed`

Each rule carries both a user-facing label and the regex used to identify the message.

### Other important config values

- `MAIN_LOG_LINE_PATTERN`
  - TXT activity parser
- `CONTROL_TIMESTAMP_PATTERN`
  - Control-log time parser
- `CONTROL_PWM_PATTERN`
  - PWM parser for `RUN` and `VEL`
- `COMPANION_VALUE_PREFIXES`
  - Prefixes used when looking for end-side `min:` or `max:` values
- `PWM_FILE_NEARNESS_THRESHOLD_MS`
  - Maximum distance for nearest-log-file fallback

### How to add a new motion pattern

To support a new event pair:

1. Open `backend/log_axis_activity_analyzer/config.py`.
2. Add a new `EventRule(...)` to `DEFAULT_EVENT_RULES`.
3. Provide:
   - a unique `rule_id`
   - a readable `start_label`
   - a readable `end_label`
   - a `start_pattern`
   - an `end_pattern`
4. Add a test in `tests/test_service.py` or a new test module.

Example:

```python
EventRule(
    rule_id="move_to_safe",
    start_label="start moving to safe pos",
    end_label="motor reached safe pos",
    start_pattern=r"^start moving to safe pos(?:\s*:\s*[-+]?\d+(?:\.\d+)?)?$",
    end_pattern=r"^motor reached safe pos$",
)
```

## 7. Data Model / Important Objects

### `AxisLogEvent`

Used after TXT parsing.

Important fields:

- `timestamp`
- `axis`
- `message`
- `raw_line`
- `inline_value`
- `line_number`
- `ordinal`

### `PWMEvent`

Used after parsing one control log file.

Important fields:

- `timestamp`
- `axis`
- `pwm_value`
- `command_type`
- `is_confirmation_line`
- `is_confirmed_by_status_line`
- `raw_line`
- `notes`

### `DutyCycleLogFileResult`

Represents one parsed `.log` file.

Important fields:

- `source_path`
- `file_start_time`
- `file_end_time`
- `pwm_events`
- `warnings`
- `axis_conflicts`

### `ActivityRecord`

This is the most important intermediate object because it maps closely to the `Details` sheet.

Important fields:

- Activity identity:
  - `axis`
  - `event_type`
  - `start_event`
  - `end_event`
- Timing:
  - `start_time`
  - `end_time`
  - `duration_ms`
  - `duration_s`
- Numeric values:
  - `start_value`
  - `end_value`
- PWM traceability:
  - `pwm_value`
  - `pwm_source_file`
  - `pwm_source_line`
  - `pwm_source_time`
  - `pwm_match_method`
  - `pwm_time_delta_ms`
  - `pwm_match_status`
- Source traceability:
  - `source_txt_start_line`
  - `source_txt_end_line`
- Validation state:
  - `activity_status`
  - `status`
  - `duration_warning`
  - `pwm_warning`
- Ordering:
  - `sort_time`
  - `sort_index`

### How the data shape changes through the pipeline

The pipeline changes shape in this order:

1. Raw file lines
2. `AxisLogEvent` and `PWMEvent`
3. `DutyCycleLogFileResult` and `DutyCycleFolderParseResult`
4. `ActivityRecord`
5. `pandas.DataFrame` objects inside `ReportFrames`
6. Excel worksheets

## 8. Example Walkthrough

Consider these lines from the sample data.

### TXT start line

```text
2026-03-31 09:39:40:554 MCU   @[Y] start clearing: -19.50
```

Parsed as:

- `AxisLogEvent.axis = "Y"`
- `AxisLogEvent.timestamp = 2026-03-31 09:39:40.554`
- `AxisLogEvent.message = "start clearing: -19.50"`
- `AxisLogEvent.inline_value = -19.50`

### TXT end line

```text
2026-03-31 09:39:47:373 MCU   @[Y] motor cleared
```

Matched by `EventMatcher` against the pending `Y + clear_motor` start event.

### PWM source line

```text
[N4:Y] RUN 0 80 (80)
```

Within `20260331_093930697_initialization.log`, the parser associates that PWM line with the latest preceding timestamp line in the same file and creates a `PWMEvent` for axis `Y` with value `80`.

### Final `Details` row

After matching, PWM association, and validation, the row contains:

- `Axis = Y`
- `Start Event = start clearing`
- `End Event = motor cleared`
- `Start Time = 2026-03-31 09:39:40:554`
- `End Time = 2026-03-31 09:39:47:373`
- `Duration (ms) = 6819`
- `Duration (s) = 6.819`
- `Start Value = -19.5`
- `PWM (%) = 80`
- `PWM Source File = 20260331_093930697_initialization.log`
- `PWM Match Status = MatchedBySameFileTimeWindow`
- `Status = Matched`

## 9. Excel Output Explanation

### `Details` sheet

Built by `SummaryGenerator._build_detail_row()` using `DETAIL_COLUMNS` from `config.py`.

Current columns are:

- `Axis`
- `Start Event`
- `End Event`
- `Start Time`
- `End Time`
- `Duration (ms)`
- `Duration (s)`
- `Start Value`
- `End Value`
- `PWM (%)`
- `PWM Source File`
- `PWM Source Line`
- `PWM Source Time`
- `PWM Match Method`
- `PWM Time Delta (ms)`
- `PWM Match Status`
- `Source TXT Start Line`
- `Source TXT End Line`
- `Status`
- `Notes`

### `Summary` sheet

Written by `ExcelExporter._write_summary_sheet()`.

It contains:

1. Metadata block
   - TXT file path
   - log folder path
   - generated workbook path
   - association strategy
   - log files scanned
   - parse warning count
   - duration warning count
   - PWM warning count
2. Summary by axis and event type
3. Summary by axis only

### `PWM Sources` sheet

Built from all parsed PWM events across the scanned folder.

Important columns:

- `Log File`
- `Log File Start Time`
- `Log File End Time`
- `Axis`
- `PWM (%)`
- `PWM Command Type`
- `PWM Source Time`
- `PWM Source Line`
- `Is Confirmed By Status Line`
- `Notes`

This sheet is mainly for debugging PWM association decisions.

## 10. Tests and Validation

### What tests exist

`tests/test_service.py` currently contains:

1. `test_parse_log_timestamp_preserves_milliseconds`
2. `test_calculate_duration_values_returns_expected_result`
3. `test_event_matcher_is_axis_local`
4. `test_log_folder_scanner_parses_multiple_log_files_and_pwm_patterns`
5. `test_pwm_associator_uses_time_and_axis_without_blind_guessing`
6. `test_service_end_to_end_with_real_txt_and_log_folder`

### What they validate

- Timestamp parsing keeps millisecond precision
- Duration is computed as `end - start`
- Same-axis matching works and cross-axis matching does not
- Multiple `.log` files in a folder are parsed
- `RUN`, `RUN 'S'`, `VEL`, and multi-letter axes are supported
- PWM association uses axis and time instead of a global last-known value
- Workbook output contains expected sheets and columns
- A known sample pair produces `6819 ms` and `6.819 s`

### Verification commands used

The implementation was verified with:

```powershell
.\.venv\Scripts\python -m compileall app backend
.\.venv\Scripts\python -m pytest tests -v
.\.venv\Scripts\python -m app.log_activity_tool --txt-file "Log\UroBiopsy_20260331.txt" --log-folder "Log\RobotMovingValues\20260331" --output "output\sample-folder-analysis.xlsx" --no-gui
```

### What confidence these checks provide

- The core parsing and matching logic is exercised both synthetically and with the real sample data in the repository.
- The workbook is inspected programmatically with `openpyxl` in the end-to-end test.

### What is still not covered

- No performance benchmark test for very large folders
- No GUI automation test for Tkinter dialogs
- No recursive folder scan test yet
- No dedicated test for malformed encodings or severely corrupted files

## 11. Design Decisions

### Why Python was chosen

- Fast to iterate on
- Good standard library for regex, datetime, and CLI work
- Strong ecosystem support for Excel and tabular reporting

### Why regex was used

- The log formats are line-oriented and pattern-based
- Regex is a practical fit for extracting timestamps, axes, and PWM values without a heavier parser framework

### Why `pandas` was used

- It simplifies DataFrame creation and worksheet export
- It makes column ordering and summary-table creation straightforward

### Why `openpyxl` was used

- It integrates cleanly with `pandas.ExcelWriter`
- It supports formatting steps like freeze panes, filters, and column widths

### Why rules are centralized in config

- New event patterns and log syntax changes should not require edits across many files
- Centralization reduces duplication and makes extension safer

### Why the code is modular

- TXT parsing, PWM parsing, matching, validation, and export each change for different reasons
- Keeping them separate makes the system easier to test and modify without accidental regressions

## 12. Known Limitations

- `MAIN_LOG_LINE_PATTERN` currently expects single-letter axes in the main TXT file.
- PWM association uses heuristics and can still produce a `PWM Warning` when only a near-time fallback is available.
- The code preserves conflict context when one file has multiple PWM values for the same axis, but it still must choose one deterministic value.
- The GUI is intentionally minimal and only covers file/folder selection.
- The `Summary` sheet is useful for analysis, but it is not intended to be a full audit log; the `Details` and `PWM Sources` sheets provide the deeper traceability.

## 13. How to Extend the Tool

### Add a new event pair

Edit:

- `backend/log_axis_activity_analyzer/config.py`

Then add a new `EventRule` to `DEFAULT_EVENT_RULES` and add a regression test.

### Support a new log pattern

If the new pattern is in the main TXT file:

- update `MAIN_LOG_LINE_PATTERN`
- or extend `log_a_parser.py`

If the new pattern is in robot control logs:

- update `CONTROL_TIMESTAMP_PATTERN` or `CONTROL_PWM_PATTERN`
- or extend `log_b_parser.py`

### Change PWM matching behavior

Edit:

- `backend/log_axis_activity_analyzer/duty_cycle_associator.py`

Most likely change points are:

- `_select_pwm_event(...)`
- `_select_same_file_time_window(...)`
- `_select_nearest_log_file(...)`
- `_select_latest_before_start(...)`
- `PWM_FILE_NEARNESS_THRESHOLD_MS` in `config.py`

### Add new summary columns

Edit:

- `backend/log_axis_activity_analyzer/config.py`
- `backend/log_axis_activity_analyzer/summary.py`

You must update both the column list and the row-building logic.

### Add new output sheets

Edit:

- `backend/log_axis_activity_analyzer/summary.py`
  - create a new DataFrame in `ReportFrames`
- `backend/log_axis_activity_analyzer/models.py`
  - extend `ReportFrames`
- `backend/log_axis_activity_analyzer/excel_exporter.py`
  - write and format the new sheet

## 14. Quick Maintenance Guide

When something breaks, the safest order to inspect is:

1. `backend/log_axis_activity_analyzer/service.py`
   - Best top-level view of the workflow
2. `backend/log_axis_activity_analyzer/config.py`
   - First place to check when formats or event phrases change
3. `backend/log_axis_activity_analyzer/log_a_parser.py`
   - If TXT events are missing
4. `backend/log_axis_activity_analyzer/log_b_parser.py`
   - If PWM rows are missing or malformed
5. `backend/log_axis_activity_analyzer/duty_cycle_associator.py`
   - If PWM values are present but attached incorrectly
6. `backend/log_axis_activity_analyzer/validation.py`
   - If durations or statuses look wrong
7. `backend/log_axis_activity_analyzer/summary.py`
   - If workbook tables or counts are wrong
8. `tests/test_service.py`
   - Fastest place to understand existing expected behavior

Safest code paths to modify first:

- `config.py` for new regexes or event rules
- `summary.py` for output-only changes
- `README.md` and this file for documentation changes

Higher-risk code paths:

- `duty_cycle_associator.py`
  - Small changes can alter many PWM matches
- `validation.py`
  - Small changes can affect row status and summary counts
- `matcher.py`
  - Small changes can alter which starts and ends pair together
