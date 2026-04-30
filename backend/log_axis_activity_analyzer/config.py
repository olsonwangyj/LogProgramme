"""Central configuration for regex patterns, matching rules, boundaries, and workbook columns."""

from __future__ import annotations

import re

from .models import BoundaryRule, EventRule

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S:%f"

SUPPORTED_ENCODINGS = [
    "utf-8",
    "utf-8-sig",
    "cp1252",
    "latin-1",
]

MAIN_LOG_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d{3})\s+(?P<content>.+?)\s*$"
)
MAIN_LOG_AXIS_EVENT_PATTERN = re.compile(
    r"^MCU\s+@\[(?P<axis>[A-Z])\]\s+(?P<message>.+?)\s*$"
)
AXIS_MARKER_PATTERN = re.compile(r"@\[(?P<axis>[A-Z]+)\]")
INLINE_VALUE_PATTERN = re.compile(r":\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*$")
BOUNDARY_AXIS_PATTERN = re.compile(r"\[(?P<axis>[A-Z])\]")
DIAGNOSTIC_NODE_RESPONSE_TIMEOUT_PATTERN = re.compile(
    r"@\[(?P<severity>ERR|WRN|INFO)\]\s+Node\s+(?P<node_id>\d+)\s+"
    r"\((?P<command>[^)]+)\)\s+response timeout\s+\((?P<timeout_code>\d+)\)\.\s*(?P<action>.*)$",
    re.IGNORECASE,
)
DIAGNOSTIC_SENSOR_CUT_PATTERN = re.compile(
    r"@\[(?P<severity>ERR|WRN)\]\s+motor\s+(?P<axis>[A-Z])\s+"
    r"(?P<sensor>[A-Z]+)\s+sensor cut",
    re.IGNORECASE,
)
DIAGNOSTIC_AMX_PARTIALLY_CORRUPTED_PATTERN = re.compile(
    r"@\[AMD\]\s+AMX partially corrupted\s+\[(?P<payload>.*?)\]",
    re.IGNORECASE,
)
DIAGNOSTIC_PARTIAL_AMX_AMENDED_PATTERN = re.compile(
    r"@\[AMD\]\s+\[N(?P<node_id>\d+)\]\s+partial AMX amended\s+\[(?P<payload>.*?)\]",
    re.IGNORECASE,
)
DIAGNOSTIC_SEVERITY_PATTERN = re.compile(
    r"@\[(?P<severity>ERR|WRN|INFO)\]\s+(?P<message>.+)$",
    re.IGNORECASE,
)

NODE_TO_AXIS = {
    3: "X",
    4: "Y",
    5: "V",
    6: "H",
    7: "N",
    8: "R",
    9: "P",
    12: "Z",
}

CONTROL_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d{3})\s+\[(?P<direction>IN\s?|OUT)\s*\].*$"
)
CONTROL_PWM_PATTERN = re.compile(
    r"^\s*\[(?P<node>[A-Z0-9]+):(?P<axis>[A-Z]+)\]\s+"
    r"(?P<command>RUN|VEL)(?:\s+(?P<status>'S'))?\s+"
    r"(?P<arguments>.+?)\s+\((?P<pwm>[-+]?\d+(?:\.\d+)?)\)\s*$"
)

COMPANION_VALUE_PREFIXES = ("min:", "max:")
END_VALUE_COMPANION_SEARCH_WINDOW_MS = 2000
RESET_PHYSICAL_POSITION_TO_ZERO_PATTERN = re.compile(
    r"^reset physical position to 0$",
    re.IGNORECASE,
)

DEFAULT_EVENT_RULES = [
    EventRule(
        rule_id="search_reference",
        start_label="start searching reference",
        end_label="reference found",
        start_pattern=r"^start searching reference$",
        end_pattern=r"^reference found(?:\s+\(.*\))?$",
    ),
    EventRule(
        rule_id="clear_motor",
        start_label="start clearing",
        end_label="motor cleared",
        start_pattern=r"^start clearing(?:\s*:\s*[-+]?\d+(?:\.\d+)?)?$",
        end_pattern=r"^motor cleared$",
    ),
    EventRule(
        rule_id="move_to_max",
        start_label="start moving to max pos",
        end_label="motor reached max pos",
        start_pattern=r"^start moving to max pos(?:\s*:\s*[-+]?\d+(?:\.\d+)?)?$",
        end_pattern=r"^motor reached max pos$",
    ),
    EventRule(
        rule_id="move_to_home",
        start_label="start moving to home",
        end_label="motor homed",
        start_pattern=r"^start moving to home(?:\s*:\s*[-+]?\d+(?:\.\d+)?)?$",
        end_pattern=r"^motor homed$",
    ),
]

DEFAULT_MAX_EVENT_DURATION_MS = 120_000
MAX_EVENT_DURATION_MS = {
    "search_reference": 120_000,
    "clear_motor": 120_000,
    "move_to_max": 120_000,
    "move_to_home": 120_000,
}

BOUNDARY_PATTERNS = [
    BoundaryRule(
        boundary_type="InitializationStarted",
        pattern=r"@on_startInitRobot_clicked",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="InitializationFailed",
        pattern=r"@\[ERR\]\s+\[(?P<axis>[A-Z])\].*initialization failed",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="RobotInitializationDone",
        pattern=r"@robot initialization done",
        flush_pending=False,
        flush_scope="all",
        close_pending_when_seen=True,
    ),
    BoundaryRule(
        boundary_type="ApplicationExited",
        pattern=r"@UroBiopsy exited",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="MotorAbortClicked",
        pattern=r"@on_functionAbortMotor_clicked",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="RobotMovingStopped",
        pattern=r"@robot moving stopped",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="SystemExitSelected",
        pattern=r"@system menu selected \(Exit\)",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="McuControllerStopped",
        pattern=r"@mcu controller stopped",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="ToolMenuSelected",
        pattern=r"@tool menu selected",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="FactoryMenuSelected",
        pattern=r"@factory menu selected",
        flush_pending=True,
        flush_scope="all",
    ),
    BoundaryRule(
        boundary_type="FinalizationDone",
        pattern=r"@robot moving \(finalization\) done",
        flush_pending=True,
        flush_scope="all",
    ),
]

BOUNDARY_RELEVANT_TOKENS = (
    "@on_startInitRobot_clicked",
    "@[ERR]",
    "@[WRN]",
    "@[AMD]",
    "@robot initialization done",
    "@UroBiopsy exited",
    "@on_functionAbortMotor_clicked",
    "@robot moving stopped",
    "@system menu selected (Exit)",
    "@mcu controller stopped",
    "@tool menu selected",
    "@factory menu selected",
    "initialization failed",
    "finalization",
)

PWM_FILE_NEARNESS_THRESHOLD_MS = 300_000
PWM_LATEST_BEFORE_MAX_DELTA_MS = 300_000

STATUS_MATCHED = "Matched"
STATUS_UNMATCHED_START = "Unmatched Start"
STATUS_UNMATCHED_END = "Unmatched End"
STATUS_INITIALIZATION_FAILED = "Initialization Failed"
STATUS_CLOSED_BY_BOUNDARY = "Closed By Boundary"
STATUS_CLOSED_BY_NEW_START = "Closed By New Start"
STATUS_DURATION_TOO_LONG_CANDIDATE = "Duration Too Long Candidate"
STATUS_DURATION_WARNING = "Duration Warning"
STATUS_DURATION_TOO_LONG = "Duration Too Long"
STATUS_PARSE_WARNING = "Parse Warning"
STATUS_DIAGNOSTIC = "Diagnostic"
STATUS_PWM_WARNING = "PWM Warning"
STATUS_NO_PWM_FOUND = "No PWM Found"
STATUS_NO_RELEVANT_LOG_FILE_FOUND = "No Relevant Log File Found"

OVERALL_STATUS_OK = "OK"
OVERALL_STATUS_DURATION_WARNING = "Duration Warning"
OVERALL_STATUS_PWM_WARNING = "PWM Warning"
OVERALL_STATUS_BOUNDARY_CLOSED = "Boundary Closed"
OVERALL_STATUS_CLOSED_BY_NEW_START = "Closed By New Start"
OVERALL_STATUS_INITIALIZATION_FAILED = "Initialization Failed"
OVERALL_STATUS_UNMATCHED = "Unmatched"
OVERALL_STATUS_DIAGNOSTIC = "Diagnostic"
OVERALL_STATUS_PARSE_WARNING = "Parse Warning"

PWM_STATUS_MATCHED_CONTAINING = "MatchedByContainingLogFile"
PWM_STATUS_MATCHED_NEAREST = "MatchedByNearestLogFile"
PWM_STATUS_MATCHED_LATEST_BEFORE = "MatchedByLatestBeforeStartWithinThreshold"
PWM_STATUS_MATCHED_CARRY_FORWARD = "MatchedByCarryForward"
PWM_STATUS_NO_CONTROL_LOGS_AVAILABLE = "NoControlLogsAvailable"
PWM_STATUS_NO_SAME_AXIS_IN_FOLDER = "NoSameAxisPWMInFolder"
PWM_STATUS_NO_RELEVANT_LOG_FILE = "NoRelevantLogFileFound"
PWM_STATUS_RELEVANT_LOG_FILE_LACKS_AXIS_PWM = "RelevantLogFileLacksAxisPWM"
PWM_STATUS_LATEST_BEFORE_TOO_FAR = "LatestBeforeStartTooFar"
PWM_STATUS_CONFLICT = "PWMConflictInSourceFile"
PWM_STATUS_NO_PWM_FOUND_FOR_AXIS = PWM_STATUS_NO_SAME_AXIS_IN_FOLDER

DURATION_STATUS_VALID = "Valid"
DURATION_STATUS_NOT_APPLICABLE = "Not Applicable"
DURATION_STATUS_END_BEFORE_START = "End Before Start"
DURATION_STATUS_TOO_LONG = "Duration Too Long"

ENABLE_DISTRIBUTION_ANALYSIS = True
MOVEMENT_DISTANCE_ROUND_DIGITS = 2
MOVEMENT_DISTANCE_BIN_SIZE = 0.1
HARD_POSITION_RESET_BOUNDARIES = {
    "InitializationStarted",
    "InitializationFailed",
    "ApplicationExited",
    "McuControllerStopped",
    "SystemExitSelected",
    "FinalizationDone",
}
SOFT_WORKFLOW_BOUNDARIES = {
    "FactoryMenuSelected",
    "ToolMenuSelected",
}
RESET_POSITION_ON_SOFT_WORKFLOW_BOUNDARIES = False
MOVEMENT_DISTANCE_RESET_BOUNDARY_TYPES = HARD_POSITION_RESET_BOUNDARIES | (
    SOFT_WORKFLOW_BOUNDARIES if RESET_POSITION_ON_SOFT_WORKFLOW_BOUNDARIES else set()
)
MOVEMENT_DISTANCE_SOURCE_OPTIONS = {
    "actual_preferred",
    "commanded_preferred",
    "actual_only",
    "commanded_only",
}
DISTRIBUTION_DISTANCE_SOURCE = "actual_preferred"
DISTRIBUTION_DISTANCE_GROUPING_MODE = "bin"
MOVEMENT_DISTANCE_GROUPING_MODES = {"round_digits", "bin", "exact"}
ALLOW_TARGET_ABSOLUTE_DISTANCE_FALLBACK = False
ALLOW_PWM_CARRY_FORWARD_ACROSS_SESSION = False
DISTRIBUTION_ALLOW_NEAREST_PWM = False
DISTRIBUTION_ALLOW_LATEST_BEFORE_PWM = False
DISTRIBUTION_ALLOW_PWM_CARRY_FORWARD = False
MIN_SAMPLES_FOR_NORMAL_FIT = 3
MIN_SAMPLES_FOR_DISTRIBUTION_CHART = 2
NORMAL_CHART_BINS = "auto"
NORMAL_DISTRIBUTION_CHART_DPI = 150
NORMAL_DISTRIBUTION_MAX_CHARTS = 200
NORMAL_DISTRIBUTION_CHART_FORMAT = "png"
EMBED_DISTRIBUTION_CHARTS_IN_EXCEL = True
DISTRIBUTION_OUTPUT_SUBDIR = "distribution_charts"
NORMAL_DISTRIBUTION_OUTPUT_DIR = "output/distribution_charts"
DISTRIBUTION_CHART_FOLDER_MODE = "per_workbook"
CLEAN_DISTRIBUTION_OUTPUT_DIR_BEFORE_RUN = True
DISTRIBUTION_ALLOWED_PWM_MATCH_STATUSES = {
    PWM_STATUS_MATCHED_CONTAINING,
}

DETAIL_COLUMNS = [
    "Axis",
    "Rule ID",
    "Start Event",
    "End Event",
    "Start Time",
    "End Time",
    "Duration (ms)",
    "Duration (s)",
    "Start Value",
    "End Value",
    "Movement Start Position",
    "Movement Target Position",
    "Movement End Position",
    "Movement Commanded Distance",
    "Movement Actual Distance",
    "Movement Distance",
    "Movement Distance Source",
    "Movement Distance Method",
    "Movement Distance Notes",
    "PWM (%)",
    "PWM Raw Value",
    "PWM Direction",
    "PWM Direction Changed",
    "PWM Conflict",
    "PWM Conflict Reason",
    "PWM Source File",
    "PWM Source Line Number",
    "PWM Source Line Text",
    "PWM Source Time",
    "PWM Match Method",
    "PWM Time Delta (ms)",
    "PWM Match Status",
    "PWM Missing Reason",
    "Source TXT Start Line Number",
    "Source TXT Start Line Text",
    "Source TXT End Line Number",
    "Source TXT End Line Text",
    "Match Status",
    "Duration Status",
    "Boundary Close Reason",
    "Closed By Boundary Type",
    "Closed By Boundary Time",
    "Boundary Line Number",
    "Boundary Line Text",
    "Candidate Duration (ms)",
    "Candidate Duration (s)",
    "Max Duration (ms)",
    "Exceeded Max Duration",
    "Notes",
    "Overall Status",
]

EVENT_SUMMARY_COLUMNS = [
    "Axis",
    "Event Type / Start Event",
    "Count",
    "Avg Duration (ms)",
    "Avg Duration (s)",
    "Min Duration (ms)",
    "Max Duration (ms)",
    "Median Duration (ms)",
    "Most Common PWM (%)",
    "Matched Count",
    "Unmatched Start Count",
    "Unmatched End Count",
    "Closed By Boundary Count",
    "Closed By New Start Count",
    "Initialization Failed Count",
    "Parse Warning Count",
    "Duration Warning Count",
    "PWM Warning Count",
]

AXIS_SUMMARY_COLUMNS = [
    "Axis",
    "Count",
    "Avg Duration (ms)",
    "Avg Duration (s)",
    "Min Duration (ms)",
    "Max Duration (ms)",
    "Median Duration (ms)",
    "Most Common PWM (%)",
    "Matched Count",
    "Unmatched Start Count",
    "Unmatched End Count",
    "Closed By Boundary Count",
    "Closed By New Start Count",
    "Initialization Failed Count",
    "Parse Warning Count",
    "Duration Warning Count",
    "PWM Warning Count",
]

PWM_SOURCE_COLUMNS = [
    "Log File",
    "Log File Start Time",
    "Log File End Time",
    "Axis",
    "PWM (%)",
    "PWM Raw Value",
    "Direction",
    "Direction Changed",
    "Command Type",
    "PWM Source Time",
    "PWM Source Line Number",
    "PWM Source Line Text",
    "Is Status Confirmation",
    "PWM Conflict",
    "PWM Conflict Reason",
    "Notes",
]

DIAGNOSTIC_COLUMNS = [
    "Time",
    "Severity",
    "Diagnostic Type",
    "Axis",
    "Node ID",
    "Source TXT Line Number",
    "Source TXT Line Text",
    "Notes",
]

DIAGNOSTIC_SUMMARY_COLUMNS = [
    "Diagnostic Type",
    "Severity",
    "Axis",
    "Node ID",
    "Count",
    "First Time",
    "Last Time",
]

DISTRIBUTION_SUMMARY_COLUMNS = [
    "Group ID",
    "TXT Source File",
    "PWM (%)",
    "Axis",
    "Example Movement Start Position",
    "Example Movement Target Position",
    "Example Movement End Position",
    "Example Movement Commanded Distance",
    "Example Movement Actual Distance",
    "Example Movement Distance",
    "Movement Start Position Min",
    "Movement Start Position Max",
    "Movement Target Position Min",
    "Movement Target Position Max",
    "Movement End Position Min",
    "Movement End Position Max",
    "Movement Distance Min",
    "Movement Distance Max",
    "Unique Position Combination Count",
    "Movement Distance Raw Example",
    "Movement Distance Group Value",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Movement Distance",
    "Movement Distance Rounded",
    "Movement Distance Method",
    "Movement Distance Source",
    "Movement Distance Notes",
    "Position Values Mixed",
    "Rule ID",
    "Action Label",
    "Sample Count",
    "Mean Duration (ms)",
    "Mean Duration (s)",
    "Median Duration (ms)",
    "Median Duration (s)",
    "Min Duration (ms)",
    "Max Duration (ms)",
    "Range Duration (ms)",
    "Sample Std Dev Duration (ms)",
    "Sample Std Dev Duration (s)",
    "Sample Variance Duration (ms^2)",
    "Sample Variance Duration (s^2)",
    "Population Std Dev Duration (ms)",
    "Population Variance Duration (ms^2)",
    "Coefficient of Variation (%)",
    "P05 Duration (ms)",
    "P25 Duration (ms)",
    "P75 Duration (ms)",
    "P95 Duration (ms)",
    "Normal Fit Mean (s)",
    "Normal Fit Std Dev (s)",
    "Normal Fit Variance (s^2)",
    "Distribution Status",
    "Chart Status",
    "Chart File",
    "Chart Sheet Anchor / Image ID",
    "Notes",
]

DISTRIBUTION_RAW_DATA_COLUMNS = [
    "Group ID",
    "TXT Source File",
    "Axis",
    "PWM (%)",
    "Movement Start Position",
    "Movement Target Position",
    "Movement End Position",
    "Movement Commanded Distance",
    "Movement Actual Distance",
    "Movement Distance",
    "Movement Distance Source",
    "Movement Distance Group Value",
    "Movement Distance Grouping Mode",
    "Movement Distance Rounded",
    "Movement Distance Method",
    "Movement Distance Notes",
    "Rule ID",
    "Action Label",
    "Start Time",
    "End Time",
    "Duration (ms)",
    "Duration (s)",
    "Source TXT Start Line Number",
    "Source TXT Start Line Text",
    "Source TXT End Line Number",
    "Source TXT End Line Text",
    "PWM Source File",
    "PWM Raw Value",
    "PWM Direction",
    "PWM Direction Changed",
    "PWM Conflict",
    "PWM Conflict Reason",
    "PWM Source Line Number",
    "PWM Source Line Text",
    "PWM Source Time",
    "PWM Match Method",
    "PWM Match Status",
    "PWM Time Delta (ms)",
    "PWM Missing Reason",
    "Overall Status",
    "Match Status",
    "Duration Status",
    "Source Record ID",
]

DISTRIBUTION_CHART_METADATA_COLUMNS = [
    "Group ID",
    "TXT Source File",
    "PWM (%)",
    "Axis",
    "Movement Distance",
    "Movement Distance Source",
    "Movement Distance Method",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Rule ID",
    "Action Label",
    "Sample Count",
    "Mean Duration (s)",
    "Sample Std Dev Duration (s)",
    "Variance",
    "Distribution Status",
    "Chart Status",
    "Chart File",
    "Notes",
]

DISTRIBUTION_EXCLUSION_SUMMARY_COLUMNS = [
    "Exclusion Reason",
    "Rule ID",
    "Axis",
    "Count",
    "Example Start Line",
    "Example Notes",
]

LOG_COVERAGE_SUMMARY_COLUMNS = [
    "TXT Source File",
    "TXT Start Time",
    "TXT End Time",
    "Control Log Folder",
    "Control Log File Count",
    "Control Log Earliest Time",
    "Control Log Latest Time",
    "Merged Control Log Interval Count",
    "Covered Duration (s)",
    "Uncovered Duration (s)",
    "Coverage Gap Count",
    "TXT Duration (s)",
    "Coverage Ratio (%)",
    "Representative Uncovered TXT Start Time",
    "Representative Uncovered TXT End Time",
    "Rows With Distribution-Accepted PWM",
    "Rows With Containing-File PWM",
    "Rows With Nearest-File PWM",
    "Rows With Latest-Before PWM",
    "Rows With Carry-Forward PWM",
    "Rows Without PWM",
    "Rows Excluded From Distribution Due To PWM Reliability",
    "Notes",
]
