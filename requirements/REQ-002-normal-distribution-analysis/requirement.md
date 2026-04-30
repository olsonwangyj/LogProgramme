# REQ-002 Normal Distribution Analysis

> Status: Completed
> Created: 2026-04-30
> Updated: 2026-04-30

## 1. Background

The analyzer already exports matched axis activity durations with PWM evidence. Engineers need an additional statistical view that shows whether repeated executions of the same motion condition behave consistently over time.

## 2. Functional Requirements

### F-01 Distribution Grouping

Group only valid matched activity rows by:

- TXT source file
- normalized `PWM (%)`
- axis
- movement distance rounded by configurable digits
- action/rule ID

Raw signed PWM direction shall not split groups. For example, raw `-80` and raw `80` both group under `PWM (%) = 80`.

### F-02 Movement Distance

The feature shall derive movement distance per activity row:

- known target-style start events use `abs(Start Value)` and record `Distance Method = StartTargetAbsoluteValue`
- generic rows with both start and end physical values use `abs(End Value - Start Value)` and record `Distance Method = StartEndValueDifference`
- rows without usable numeric values are excluded by default

The default grouping precision shall be two decimal places.

### F-03 Filtering

The distribution input shall include only rows where:

- `Match Status = Matched`
- `Duration Status = Valid`
- numeric `Duration (ms) > 0`
- PWM percent is present
- movement distance is present

Unmatched rows, boundary closures, initialization failures, duration-too-long candidates, parse warnings, diagnostics, missing PWM rows, and missing movement-distance rows shall be excluded from fitting.

### F-04 Statistics

For each group, compute sample count, mean, median, min, max, range, sample standard deviation, sample variance, population standard deviation, population variance, coefficient of variation, P05, P25, P75, and P95 over duration. Duration shall be reported in milliseconds and seconds where useful.

Single-sample groups shall keep basic metrics but leave sample SD/variance blank and use `Distribution Status = InsufficientSamples`.

### F-05 Charts

Generate PNG distribution charts with matplotlib. Eligible charts shall show a density histogram of `Duration (s)` and, when sample count and variance allow, an overlaid fitted normal curve. Small-sample and zero-variance groups shall not crash chart generation and shall explain why a normal curve was not drawn.

Chart generation shall be capped by a configurable maximum, with the largest groups charted first.

### F-06 Excel Output

The workbook shall include:

- `Distribution Summary`
- `Distribution Raw Data`
- `Distribution Charts` when chart embedding is enabled

`Distribution Summary` shall include chart file paths. `Distribution Raw Data` shall preserve source line numbers and PWM source context for every included activity row.

### F-07 CLI And Documentation

The CLI shall support:

- `--no-distribution`
- `--distribution-output-dir`
- `--max-distribution-charts`
- `--no-embed-distribution-charts`
- `--movement-distance-round-digits`

The README shall describe grouping, filtering, movement distance, PWM normalization, statistics, charts, and disable options.

## 3. Acceptance Criteria

- Distribution analysis is enabled by default and can be disabled.
- Statistics and charts are generated from valid matched rows only.
- Excel exports distribution summary/raw/chart sheets without removing existing sheets.
- Existing duration matching behavior remains unchanged, including the April 10 `22776 ms` Z pair.
- Automated tests cover grouping, distance derivation, statistics, single-sample groups, chart generation, zero variance, and Excel export.
- A real April 10 workbook is generated and inspected before completion.
