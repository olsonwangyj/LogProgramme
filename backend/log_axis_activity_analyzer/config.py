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
CONTROL_PWM_COMMANDS = {"RUN", "VEL"}


def build_control_pwm_pattern(commands: set[str] | frozenset[str]) -> re.Pattern[str]:
    """Build the PWM parser regex from the configured command names."""

    command_pattern = "|".join(sorted(re.escape(command) for command in commands))
    return re.compile(
        r"^\s*\[(?P<node>[A-Z0-9]+):(?P<axis>[A-Z]+)\]\s+"
        rf"(?P<command>{command_pattern})(?:\s+(?P<status>'S'))?\s+"
        r"(?P<arguments>.+?)\s+\((?P<pwm>[-+]?\d+(?:\.\d+)?)\)\s*$"
    )


CONTROL_PWM_PATTERN = build_control_pwm_pattern(CONTROL_PWM_COMMANDS)
CONTROL_TPOS_PATTERN = re.compile(
    r"^\s*\[(?P<node>[A-Z]*?(?P<node_id>\d+)[A-Z0-9]*):(?P<axis>[A-Z]+)\]\s+TPOS"
    r"(?:\s+'(?P<kind>[A-Z])')?"
    r"(?:\s+(?P<arguments>.*?))?"
    r"(?:\s+\((?P<raw>[-+]?\d+)\))?\s*$"
)

AXIS_RAW_SCALE = {
    "X": 58708.0,
    "Y": 58708.0,
    "Z": 88064.0,
    "V": -34120.0,
    "H": -34120.0,
    "N": -80058.0,
    "R": 19570.0,
    "P": 9784.0,
}
HARDWARE_SEGMENT_MATCH_WINDOW_MS = 3000
HARDWARE_TARGET_TO_START_MAX_DELTA_MS = 3000
HARDWARE_DISTANCE_SOURCE = "hardware_actual"
HARDWARE_DISTANCE_SOURCE_OPTIONS = {"hardware_actual"}
HARDWARE_STATUS_MATCHED_OVERLAP = "MatchedByOverlappingTime"
HARDWARE_STATUS_MATCHED_NEAREST = "MatchedByNearestHardwareSegment"
HARDWARE_STATUS_MATCHED_NEAREST_PREVIOUS = "MatchedByNearestPreviousHardwareSegment"
HARDWARE_STATUS_MATCHED_NEAREST_FUTURE = "MatchedByNearestFutureHardwareSegment"
HARDWARE_STATUS_MULTIPLE_CANDIDATES = "MultipleHardwareCandidates"
HARDWARE_STATUS_NO_SEGMENT = "NoHardwareSegmentFound"
HARDWARE_STATUS_INCOMPLETE = "HardwareSegmentIncomplete"
HARDWARE_STATUS_REFERENCE_NOT_APPLICABLE = "HardwareReferenceNotApplicable"
HARDWARE_DISTANCE_CONSISTENCY_TOLERANCE = 0.5
HARDWARE_REFERENCE_MATCH_WINDOW_MS = 3000
HARDWARE_REFERENCE_STATUS_FOUND = "HardwareReferenceEvidenceFound"
HARDWARE_REFERENCE_STATUS_PARTIAL = "HardwareReferenceEvidencePartial"
HARDWARE_REFERENCE_STATUS_NO_EVIDENCE = "NoHardwareReferenceEvidenceFound"
HARDWARE_REFERENCE_STATUS_NOT_APPLICABLE = "HardwareReferenceNotApplicable"
HARDWARE_POSITION_KIND_MAP = {
    "S": "Start",
    "E": "End",
    "Z": "ZeroSensor",
    "I": "ResetOrInit",
}

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
STATUS_MISSING_HARDWARE_DISTANCE = "Missing Hardware Distance"

OVERALL_STATUS_OK = "OK"
OVERALL_STATUS_DURATION_WARNING = "Duration Warning"
OVERALL_STATUS_HARDWARE_WARNING = "Hardware Warning"
OVERALL_STATUS_PWM_WARNING = "PWM Warning"
OVERALL_STATUS_BOUNDARY_CLOSED = "Boundary Closed"
OVERALL_STATUS_CLOSED_BY_NEW_START = "Closed By New Start"
OVERALL_STATUS_INITIALIZATION_FAILED = "Initialization Failed"
OVERALL_STATUS_UNMATCHED = "Unmatched"
OVERALL_STATUS_DIAGNOSTIC = "Diagnostic"
OVERALL_STATUS_PARSE_WARNING = "Parse Warning"

PWM_STATUS_MATCHED_CONTAINING = "MatchedByContainingLogFile"
PWM_STATUS_MATCHED_NEAREST = "MatchedByNearestLogFile"
PWM_STATUS_MATCHED_NEAREST_FUTURE = "MatchedByNearestFutureLogFile"
PWM_STATUS_MATCHED_LATEST_BEFORE = "MatchedByLatestBeforeStartWithinThreshold"
PWM_STATUS_MATCHED_CARRY_FORWARD = "MatchedByCarryForward"
PWM_STATUS_NO_EARLIER_PWM_FOR_AXIS = "NoEarlierPWMForAxis"
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
    "hardware_actual",
}
DISTRIBUTION_DISTANCE_SOURCE = HARDWARE_DISTANCE_SOURCE
DISTRIBUTION_DISTANCE_GROUPING_MODE = "bin"
MOVEMENT_DISTANCE_GROUPING_MODES = {"round_digits", "bin", "exact"}
ALLOW_PWM_CARRY_FORWARD_ACROSS_SESSION = False
DISTRIBUTION_ALLOW_NEAREST_PWM = False
DISTRIBUTION_ALLOW_LATEST_BEFORE_PWM = False
DISTRIBUTION_ALLOW_PWM_CARRY_FORWARD = False
DISTRIBUTION_ALLOW_NEAREST_HARDWARE_SEGMENT = False
DISTRIBUTION_ALLOW_MULTIPLE_HARDWARE_CANDIDATES = False
DISTRIBUTION_ALLOWED_HARDWARE_MOTION_MATCH_STATUSES = {
    HARDWARE_STATUS_MATCHED_OVERLAP,
}
MIN_SAMPLES_FOR_NORMAL_FIT = 3
MIN_SAMPLES_FOR_DISTRIBUTION_CHART = 2
AXIS_SUMMARY_MEAN_YELLOW_THRESHOLD = 20.0
AXIS_SUMMARY_MEAN_RED_THRESHOLD = 25.0
NORMAL_CHART_BINS = "auto"
NORMAL_CHART_Y_AXIS_MODE = "count"
NORMAL_CHART_Y_AXIS_MODE_OPTIONS = {"count", "density"}
LOW_VARIANCE_STD_THRESHOLD_S = 0.02
DISABLE_IQR_OUTLIERS_FOR_LOW_VARIANCE_GROUPS = True
REFERENCE_MIN_DURATION_MS = 1000
REFERENCE_EXCLUDE_SHORT_DURATIONS_FROM_DISTRIBUTION = True
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
EXPORT_DISTRIBUTION_IMAGE_GALLERY = True
DISTRIBUTION_IMAGE_GALLERY_SHEET_NAME = "Image Gallery"
DISTRIBUTION_IMAGE_STATISTICS_SHEET_NAME = "Image Statistics"
DISTRIBUTION_IMAGE_INDEX_SHEET_NAME = "Image Index"
DISTRIBUTION_IMAGE_MAX_IMAGES = 500
DISTRIBUTION_IMAGE_WIDTH_PX = 900
DISTRIBUTION_IMAGE_HEIGHT_PX = 600
DISTRIBUTION_IMAGE_BLOCK_HEIGHT_ROWS = 35
DISTRIBUTION_IMAGE_GALLERY_INCLUDE_SKIPPED_GROUPS = False
DISTRIBUTION_IMAGE_GALLERY_LAYOUT = "vertical"
DISTRIBUTION_IMAGE_GALLERY_LAYOUT_OPTIONS = {"vertical", "compact_grid"}
DISTRIBUTION_IMAGE_GRID_COLUMNS = 2
DISTRIBUTION_IMAGE_GRID_BLOCK_WIDTH_COLUMNS = 14

DISTRIBUTION_IMAGE_GALLERY_METADATA_KEYS = [
    "Image #",
    "Chart Type",
    "Axis",
    "Action",
    "n",
    "Mean (s)",
    "SD (s)",
    "Var (s^2)",
    "Median (s)",
    "Min-Max (s)",
    "CV (%)",
    "PWM (%)",
    "Distance",
    "Reference Evidence Status",
]

DISTRIBUTION_IMAGE_STATISTICS_COLUMNS = [
    "Group ID",
    "Chart Type",
    "TXT Source File",
    "PWM (%)",
    "PWM Raw Values Seen",
    "PWM Directions Seen",
    "PWM Direction Mixed",
    "PWM Raw Value Example",
    "PWM Direction Example",
    "Axis",
    "Action",
    "Selected Group Distance",
    "Hardware Actual Distance Group Value",
    "Hardware Actual Distance Group Display",
    "Distance",
    "Reference Evidence Status",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Hardware Actual Distance Raw Example",
    "Hardware Actual Distance Min",
    "Hardware Actual Distance Max",
    "Hardware Motion Source File",
    "Hardware Raw Start Position",
    "Hardware Raw End Position",
    "Hardware Start Position",
    "Hardware End Position",
    "Hardware Actual Distance",
    "Position Values Mixed",
    "Hardware Distance Source",
    "Hardware Distance Method",
    "Rule ID",
    "Action Label",
    "Sample Count",
    "Mean Duration (ms)",
    "Mean Duration (s)",
    "Median Duration (ms)",
    "Median Duration (s)",
    "Sample SD Duration (ms)",
    "Sample SD Duration (s)",
    "Sample Variance Duration (ms^2)",
    "Sample Variance Duration (s^2)",
    "Normal Fit Mean (s)",
    "Normal Fit Std Dev (s)",
    "Normal Fit Variance (s^2)",
    "Population SD Duration (ms)",
    "Population SD Duration (s)",
    "Population Variance Duration (ms^2)",
    "Population Variance Duration (s^2)",
    "Min Duration (ms)",
    "Max Duration (ms)",
    "P05 Duration (ms)",
    "P25 Duration (ms)",
    "P75 Duration (ms)",
    "P95 Duration (ms)",
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
    "Coefficient of Variation (%)",
    "Distribution Status",
    "Chart Status",
    "Gallery Image Status",
    "Image Insert Error",
    "Chart File",
    "Notes",
]

DISTRIBUTION_IMAGE_INDEX_COLUMNS = [
    "Image Number",
    "Group ID",
    "Chart File",
    "Excel Anchor",
    "Chart Type",
    "Axis",
    "Action",
    "PWM (%)",
    "Hardware Actual Distance Group Value",
    "Hardware Actual Distance Group Display",
    "Distance",
    "Reference Evidence Status",
    "Hardware Distance Source",
    "Hardware Distance Method",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "PWM Raw Values Seen",
    "PWM Directions Seen",
    "PWM Direction Mixed",
    "Rule ID",
    "Sample Count",
    "Mean Duration (s)",
    "Sample SD Duration (s)",
    "Normal Fit Mean (s)",
    "Normal Fit Std Dev (s)",
    "Normal Fit Variance (s^2)",
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
    "Chart Status",
    "Gallery Image Status",
    "Image Insert Error",
]

DISTRIBUTION_CHART_METADATA_KEYS = [
    "Chart Type",
    "TXT Source File",
    "PWM (%)",
    "Axis",
    "Action",
    "Hardware Actual Distance Group Value",
    "Hardware Actual Distance Display",
    "Distance",
    "Reference Evidence Status",
    "Hardware Distance Source",
    "Hardware Distance Method",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Rule ID",
    "Action Label",
    "Sample Count",
    "Mean Duration (s)",
    "Sample Std Dev Duration (s)",
    "Variance",
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
    "Distribution Status",
    "Chart Status",
    "Chart File",
    "Notes",
]
DISTRIBUTION_CHART_IMAGE_ROW_OFFSET = len(DISTRIBUTION_CHART_METADATA_KEYS) + 2
DISTRIBUTION_CHART_BLOCK_HEIGHT = len(DISTRIBUTION_CHART_METADATA_KEYS) + 29

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
    "Hardware Motion Match Status",
    "Hardware Motion Source File",
    "Hardware Motion Time Delta (ms)",
    "Hardware Raw Start Position",
    "Hardware Raw End Position",
    "Hardware Raw Target Position",
    "Hardware Start Position",
    "Hardware End Position",
    "Hardware Target Position",
    "Hardware Actual Distance",
    "Candidate Hardware Actual Distance",
    "Hardware Commanded Distance",
    "Hardware Distance Consistency Status",
    "Hardware Distance Consistency Delta",
    "Hardware Reference Match Status",
    "Hardware Reference Source File",
    "Hardware Reference Time Delta (ms)",
    "Hardware Reference Zero Sensor Time",
    "Hardware Reference Reset Time",
    "Hardware Reference Zero Sensor Raw Value",
    "Hardware Reference Line Number",
    "Hardware Reference Line Text",
    "Hardware Start Line Number",
    "Hardware Start Line Text",
    "Hardware End Line Number",
    "Hardware End Line Text",
    "Hardware Target Line Number",
    "Hardware Target Line Text",
    "Selected Hardware Actual Distance",
    "Selected Movement Distance",
    "Selected Movement Distance Source",
    "Selected Movement Distance Method",
    "Selected Movement Distance Notes",
    "Software TXT Start Position",
    "Software TXT Target Position",
    "Software TXT Reported End Position",
    "Software TXT Commanded Distance",
    "Software TXT Reported Distance",
    "Hardware Warning",
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
    "Hardware Warning Count",
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
    "Hardware Warning Count",
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

HARDWARE_MOTION_SEGMENT_COLUMNS = [
    "Source Log File",
    "Axis",
    "Match Status",
    "Start Time",
    "End Time",
    "Target Time",
    "Raw Start Position",
    "Raw End Position",
    "Raw Target Position",
    "Hardware Start Position",
    "Hardware End Position",
    "Hardware Target Position",
    "Hardware Actual Distance",
    "Hardware Commanded Distance",
    "Start Line Number",
    "Start Line Text",
    "End Line Number",
    "End Line Text",
    "Target Line Number",
    "Target Line Text",
    "Duplicate Segment Key",
    "Duplicate Segment Count",
    "Possible Duplicate Hardware Segment",
    "Possible Duplicate Source Files",
    "Effective Segment Used For Matching",
    "Matched TXT Activity Count",
    "Matched TXT Rule ID",
    "Matched TXT Start Time",
    "Notes",
]

HARDWARE_REFERENCE_EVENT_COLUMNS = [
    "Source Log File",
    "Axis",
    "Evidence Type",
    "Timestamp",
    "Raw / Status Value",
    "Line Number",
    "Line Text",
    "Matched TXT Rule ID",
    "Matched TXT Start Time",
    "Matched TXT End Time",
    "Match Status",
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
    "Example Hardware Start Position",
    "Example Hardware Target Position",
    "Example Hardware End Position",
    "Example Hardware Commanded Distance",
    "Example Hardware Actual Distance",
    "Example Selected Hardware Actual Distance",
    "Hardware Start Position Min",
    "Hardware Start Position Max",
    "Hardware Target Position Min",
    "Hardware Target Position Max",
    "Hardware End Position Min",
    "Hardware End Position Max",
    "Hardware Actual Distance Min",
    "Hardware Actual Distance Max",
    "Unique Position Combination Count",
    "Hardware Actual Distance Raw Example",
    "Hardware Actual Distance Group Value",
    "Hardware Actual Distance Group Display",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Selected Group Distance",
    "Hardware Actual Distance Rounded",
    "Hardware Distance Method",
    "Hardware Distance Source",
    "Hardware Distance Notes",
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
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
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
    "Selected Hardware Start Position",
    "Selected Hardware Target Position",
    "Selected Hardware End Position",
    "Selected Hardware Commanded Distance",
    "Selected Hardware Actual Distance",
    "Hardware Motion Match Status",
    "Hardware Motion Source File",
    "Hardware Raw Start Position",
    "Hardware Raw End Position",
    "Hardware Raw Target Position",
    "Hardware Start Position",
    "Hardware End Position",
    "Hardware Target Position",
    "Hardware Actual Distance",
    "Hardware Commanded Distance",
    "Hardware Start Line Number",
    "Hardware Start Line Text",
    "Hardware End Line Number",
    "Hardware End Line Text",
    "Hardware Target Line Number",
    "Hardware Target Line Text",
    "Selected Movement Distance",
    "Selected Movement Distance Source",
    "Hardware Actual Distance Group Value",
    "Hardware Actual Distance Group Display",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Hardware Actual Distance Rounded",
    "Selected Movement Distance Method",
    "Selected Movement Distance Notes",
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
    "Chart Type",
    "TXT Source File",
    "PWM (%)",
    "Axis",
    "Action",
    "Hardware Actual Distance Group Value",
    "Hardware Actual Distance Display",
    "Distance",
    "Reference Evidence Status",
    "Hardware Distance Source",
    "Hardware Distance Method",
    "Movement Distance Grouping Mode",
    "Movement Distance Bin Size",
    "Rule ID",
    "Action Label",
    "Sample Count",
    "Mean Duration (s)",
    "Sample Std Dev Duration (s)",
    "Variance",
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
    "Distribution Status",
    "Chart Status",
    "Chart File",
    "Notes",
]

REFERENCE_DURATION_SUMMARY_COLUMNS = [
    "Group ID",
    "TXT Source File",
    "Axis",
    "Action",
    "Rule ID",
    "Sample Count",
    "Mean Duration (ms)",
    "Mean Duration (s)",
    "Median Duration (s)",
    "Sample SD Duration (s)",
    "Sample Variance Duration (s^2)",
    "Population SD Duration (s)",
    "Population Variance Duration (s^2)",
    "Min Duration (s)",
    "Max Duration (s)",
    "Min-Max Display",
    "CV (%)",
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
    "Hardware Reference Evidence Found Count",
    "Hardware Reference Evidence Missing Count",
    "Distribution Status",
    "Chart Status",
    "Chart File",
    "Chart Sheet Anchor / Image ID",
    "Notes",
]

REFERENCE_DURATION_RAW_DATA_COLUMNS = [
    "Group ID",
    "TXT Source File",
    "Axis",
    "Action",
    "Rule ID",
    "Start Time",
    "End Time",
    "Duration (ms)",
    "Duration (s)",
    "Hardware Reference Match Status",
    "Hardware Reference Source File",
    "Hardware Reference Zero Sensor Raw Value",
    "Hardware Reference Line Text",
    "Included In Reference Distribution",
    "Reference Exclusion Reason",
    "Hardware Motion Match Status",
    "Selected Movement Distance Method",
    "Overall Status",
    "Match Status",
    "Duration Status",
    "Source TXT Start Line Number",
    "Source TXT Start Line Text",
    "Source TXT End Line Number",
    "Source TXT End Line Text",
    "Notes",
]

REFERENCE_DURATION_CHART_METADATA_COLUMNS = [
    "Group ID",
    "Chart Type",
    "TXT Source File",
    "Axis",
    "Action",
    "Rule ID",
    "Distance",
    "Sample Count",
    "Mean Duration (s)",
    "Sample Std Dev Duration (s)",
    "Variance",
    "Min-Max Display",
    "CV (%)",
    "Outlier Count",
    "Outlier Values",
    "Chart Uses Outlier-Trimmed Axis",
    "Reference Evidence Status",
    "Hardware Reference Evidence Found Count",
    "Hardware Reference Evidence Missing Count",
    "Distribution Status",
    "Chart Status",
    "Chart File",
    "Notes",
]

REFERENCE_EXCLUSION_SUMMARY_COLUMNS = [
    "Reference Exclusion Reason",
    "Axis",
    "Action",
    "Count",
    "Example Duration (s)",
    "Example Start Time",
    "Example Notes",
]

AXIS_ACTION_SUMMARY_COLUMNS = [
    "Axis",
    "Action",
    "n",
    "Mean (s)",
    "SD (s)",
    "Var (s^2)",
    "Median (s)",
    "Min-Max (s)",
    "CV (%)",
]

DISTRIBUTION_EXCLUSION_SUMMARY_COLUMNS = [
    "Exclusion Reason",
    "Secondary Exclusion Reasons",
    "PWM Exclusion Reason",
    "Movement Distance Exclusion Reason",
    "Rule ID",
    "Axis",
    "Count",
    "PWM Match Status",
    "PWM Missing Reason",
    "PWM Time Delta (ms)",
    "Example PWM Source File",
    "Hardware Motion Match Status",
    "Example Start Line",
    "Example Notes",
]

DISTRIBUTION_ELIGIBILITY_SUMMARY_COLUMNS = [
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
    "Rows With Nearest-Future PWM",
    "Rows With Latest-Before PWM",
    "Rows With Carry-Forward PWM",
    "Rows Without PWM",
    "Rows With No Control Logs Available",
    "Rows With No Relevant Log File",
    "Rows With No Same-Axis PWM In Folder",
    "Rows With Relevant Log File Lacking Axis PWM",
    "Rows With Latest-Before Too Far",
    "Rows With PWM Conflict",
    "Rows Excluded Due To Missing Hardware Distance",
    "Rows Excluded Due To Unreliable Hardware Match",
    "Rows Excluded Due To Missing PWM",
    "Rows Excluded Due To Unreliable PWM",
    "Rows Excluded Due To Multiple Reasons",
    "Rows Excluded From Distribution Due To PWM Reliability",
    "PWM Carry Forward Enabled",
    "Distribution Allows Carry Forward PWM",
    "Notes",
]

LOG_COVERAGE_GAPS_COLUMNS = [
    "TXT Source File",
    "Gap Index",
    "Gap Start Time",
    "Gap End Time",
    "Gap Duration (s)",
    "Gap Type",
    "Nearest Previous Control Log File",
    "Nearest Previous Control Log End Time",
    "Nearest Next Control Log File",
    "Nearest Next Control Log Start Time",
    "Notes",
]
