# REQ-001 Technical Design

> Status: Technical Finalized
> Requirement: requirement.md
> Created: 2026-04-27
> Updated: 2026-04-29

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Application entry | Python 3.10, `argparse`, `tkinter` | Supports automation plus optional desktop file and folder selection without a heavy GUI framework |
| Parsing and matching | Python standard library, `re`, `datetime`, `dataclasses`, `logging` | Streaming-friendly parsing with explicit typing and traceable logs |
| Tabular reporting | `pandas` | Simplifies workbook-ready table creation and consistent column ordering |
| Excel export | `openpyxl` via `pandas.ExcelWriter` | Native `.xlsx` creation with sheet formatting |
| Testing | `pytest` | Lightweight regression coverage for parsing and end-to-end analysis |

## 2. Design Principles

- High cohesion, low coupling: each module owns one stage of the pipeline and exposes a focused public interface.
- Reuse first: regex definitions, event rules, data models, and file-loading behavior are centralized.
- Testability: parsers, matcher, duty-cycle association, and workbook generation are independently callable.
- Streaming where practical: text input is processed line by line to support large files.
- Graceful degradation: malformed lines become warning records instead of fatal exceptions.

## 3. Architecture Overview

The project is organized into an `app/` entry layer and a `backend/` analysis package.

- `app.log_activity_tool`
  - Command-line interface, optional file dialogs, and run summary output.
- `backend.log_axis_activity_analyzer`
  - Reusable analysis library that handles loading, parsing, folder scanning, PWM association, validation, summary generation, and Excel export.

No code is placed directly under a root-level `src/` directory. The backend package is layered by responsibility inside `backend/`.

## 4. Module Design

### 4.1 `app.log_activity_tool`

- Responsibility: accept user input, configure logging, call the backend service, and return a process exit code.
- Public interface:
  - `main(argv: list[str] | None) -> int`
- Internal structure:
  - Argument parsing
  - Optional Tkinter file selection and folder selection
  - Service invocation and terminal summary output
- Reuse notes: thin orchestration layer only; business logic remains in backend modules.

### 4.2 `backend.log_axis_activity_analyzer.config`

- Responsibility: store regex patterns, event-pair rules, supported encodings, and column names.
- Public interface:
  - rule and pattern constants
- Internal structure:
  - `EventRule` definitions
  - compiled regex constants
- Reuse notes: shared by parsers, matcher, summary, and documentation.

### 4.3 `backend.log_axis_activity_analyzer.models`

- Responsibility: define typed data structures for parsed events, warnings, matched records, and service outputs.
- Public interface:
  - dataclasses such as `AxisLogEvent`, `DutyCycleEvent`, `ActivityRecord`, and `AnalysisRunResult`
- Internal structure:
  - field defaults for optional values
  - helper methods for workbook row conversion
- Reuse notes: shared contract across the entire backend pipeline.

### 4.4 `backend.log_axis_activity_analyzer.file_loader`

- Responsibility: open text files safely with encoding fallback and line-number preservation.
- Public interface:
  - `TextFileLoader.iter_lines(...)`
- Internal structure:
  - encoding detection helpers
  - fallback to replacement characters when the encoding cannot be trusted perfectly
- Reuse notes: shared by both parsers.

### 4.5 `backend.log_axis_activity_analyzer.log_a_parser`

- Responsibility: parse the full MCU activity log and emit timestamped axis events plus warnings.
- Public interface:
  - `MainLogParser.parse(...)`
- Internal structure:
  - line classification
  - timestamp parsing
  - numeric-value extraction
- Reuse notes: companion numeric lines remain available to the matcher.

### 4.6 `backend.log_axis_activity_analyzer.log_b_parser`

- Responsibility: parse one control-log file for PWM history and retain best-available timestamps plus per-file time range metadata.
- Public interface:
  - `DutyCycleLogParser.parse(...)`
- Internal structure:
  - timestamp tracking for indented `RUN` and `VEL` lines
  - signed percentage extraction
  - command-type capture
  - confirmation-line capture
  - warning generation for untimed or malformed records
- Reuse notes: the associator consumes the parsed history without needing raw text scanning.

### 4.7 `backend.log_axis_activity_analyzer.log_folder_scanner`

- Responsibility: discover `.log` files in the selected folder, optionally recurse into subfolders, and combine per-file PWM parsing results.
- Public interface:
  - `LogFolderScanner.scan(...)`
- Internal structure:
  - folder validation
  - glob or recursive glob discovery
  - per-file parser invocation
  - aggregate warning collection
- Reuse notes: isolates folder handling from the parser that understands only a single `.log` file.

### 4.8 `backend.log_axis_activity_analyzer.matcher`

- Responsibility: classify configured start/end events, match them by axis, calculate durations, and generate detail records.
- Public interface:
  - `EventMatcher.build_activity_records(...)`
- Internal structure:
  - rule classification
  - per-axis pending queues
  - companion end-value lookup
  - unmatched record handling
- Reuse notes: new event rules only require config changes.

### 4.9 `backend.log_axis_activity_analyzer.duty_cycle_associator`

- Responsibility: attach the most relevant axis PWM to each activity record using axis plus time-aware multi-file selection.
- Public interface:
  - `DutyCycleAssociator.attach(...)`
- Internal structure:
  - condensed per-file PWM history
  - overlapping or nearest-file candidate selection
  - latest-before-start fallback resolution
  - source metadata and match-status assignment
- Reuse notes: matching strategy is isolated so it can be replaced later.

### 4.10 `backend.log_axis_activity_analyzer.validation`

- Responsibility: validate matched activity durations and finalize row-level warning status.
- Public interface:
  - `ActivityValidator.validate(...)`
- Internal structure:
  - missing timestamp checks
  - negative-duration detection
  - duration recomputation verification
  - final status selection
- Reuse notes: separates correctness checks from raw event matching.

### 4.11 `backend.log_axis_activity_analyzer.summary`

- Responsibility: build the `Details`, `Summary`, and optional PWM-source tables in workbook-ready form.
- Public interface:
  - `SummaryGenerator.build_report_frames(...)`
- Internal structure:
  - detail row shaping
  - event-type aggregation
  - axis-only aggregation
  - PWM-source sheet shaping
- Reuse notes: output schema is centralized here for maintainability.

### 4.12 `backend.log_axis_activity_analyzer.excel_exporter`

- Responsibility: write the workbook and apply basic formatting.
- Public interface:
  - `ExcelExporter.export(...)`
- Internal structure:
  - sheet creation
  - metadata block
  - optional PWM-source sheet
  - width and freeze-pane formatting
- Reuse notes: the export layer is separate from data generation.

### 4.13 `backend.log_axis_activity_analyzer.service`

- Responsibility: orchestrate the end-to-end workflow for one analysis run.
- Public interface:
  - `LogAnalysisService.run_analysis(...)`
- Internal structure:
  - input validation
  - TXT parser invocation
  - log-folder scan invocation
  - matching, PWM association, and validation
  - summary generation and export
- Reuse notes: the app entry layer and future integrations can call the same service.

## 5. Data Model

- `AxisLogEvent`
  - Parsed main-log axis line with timestamp, axis, normalized numeric value, source line, and ordinal position.
- `DutyCycleEvent`
  - Parsed PWM line with axis, percentage, command type, confirmation flag, timestamp if available, and source line.
- `DutyCycleLogFileResult`
  - One parsed `.log` file with file start/end time, PWM records, warnings, and source path.
- `DutyCycleFolderParseResult`
  - Aggregated result for the selected log folder.
- `ParseWarning`
  - Warning record for malformed but relevant lines.
- `ActivityRecord`
  - Workbook detail-row model with duration, values, PWM fields, source lines, status, and notes.
- `ReportFrames`
  - `pandas` data frames for `Details`, event summary, axis summary, and optional PWM-source rows.
- `AnalysisRunResult`
  - Output path plus execution counters for the CLI summary, including duration and PWM warnings.

## 6. API Design

The solution is a local tool rather than a network API. The CLI contract is:

- `python -m app.log_activity_tool --txt-file <path> --log-folder <path> --output <path>`
- Optional flags:
  - `--encoding-a <name>`
  - `--log-folder-encoding <name>` or equivalent override for control logs
  - `--association-strategy` with transparent match-method reporting
  - `--recursive-log-folder`
  - `--verbose`
  - `--no-gui`

If path arguments are omitted and GUI mode is allowed, the application opens a file picker for the TXT file, a folder picker for the log folder, and a save dialog for the output workbook.

## 7. Key Flows

- Flow 1: User chooses the TXT file, the log folder, and the output path, then the app validates them.
- Flow 2: Main-log parser streams the TXT file and emits typed records plus warnings.
- Flow 3: Log-folder scanner discovers `.log` files and the control-log parser emits per-file PWM records plus warnings.
- Flow 4: Event matcher builds matched and unmatched activity rows per axis.
- Flow 5: PWM associator enriches each activity row using the configured multi-file strategy.
- Flow 6: Validator checks duration correctness and final warning status.
- Flow 7: Summary generator builds workbook tables and exporter writes the `.xlsx` file.

## 8. Shared Modules & Reuse Strategy

- `config.py`: single source for regex patterns, matching rules, and workbook column names.
- `models.py`: shared contracts between parsers, matcher, associator, summary, and exporter.
- `file_loader.py`: shared encoding fallback and safe line iteration for both log parsers.
- `log_folder_scanner.py`: shared folder discovery behavior for future batch workflows.
- `validation.py`: shared duration-checking rules.
- `service.py`: single orchestration entry for CLI use and future integrations.

## 9. Risks & Notes

- Control logs may include repeated `RUN`, `RUN 'S'`, `VEL`, and `VEL 'S'` lines for the same setting, so the associator should preserve source detail while avoiding accidental duplicate matches.
- Some end values live on companion lines such as `min:` or `max:` rather than on the end event itself; the matcher performs a short same-axis look-ahead.
- Some activities may start before a PWM command is seen in the same log file; those cases require transparent fallback reporting rather than silent assumptions.
- PlantUML sources are included for workflow traceability; SVG generation can be added later if a local PlantUML toolchain is introduced.
- Archive-stage completion is intentionally deferred until the user decides how they want to handle git commits.

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-04-27 | Initial version | ALL | - |
| v2 | 2026-04-29 | Updated design for TXT-plus-log-folder input, multi-file PWM parsing/association, duration validation, and optional PWM-source reporting | Modules 4.1, 4.6-4.13, Data Model 5, API 6, Key Flows 7, Shared Modules 8, Risks 9 | Align design with amended requirement and new PWM matching behavior |
