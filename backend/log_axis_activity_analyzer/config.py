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
DIAGNOSTIC_SEVERITY_PATTERN = re.compile(
    r"@\[(?P<severity>ERR|WRN|INFO)\]\s+(?P<message>.+)$",
    re.IGNORECASE,
)

CONTROL_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d{3})\s+\[(?P<direction>IN\s?|OUT)\s*\].*$"
)
CONTROL_PWM_PATTERN = re.compile(
    r"^\s*\[(?P<node>[A-Z0-9]+):(?P<axis>[A-Z]+)\]\s+"
    r"(?P<command>RUN|VEL)(?:\s+(?P<status>'S'))?\s+"
    r"(?P<arguments>.+?)\s+\((?P<pwm>[-+]?\d+(?:\.\d+)?)\)\s*$"
)

COMPANION_VALUE_PREFIXES = ("min:", "max:")

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
OVERALL_STATUS_INITIALIZATION_FAILED = "Initialization Failed"
OVERALL_STATUS_DIAGNOSTIC = "Diagnostic"
OVERALL_STATUS_PARSE_WARNING = "Parse Warning"

PWM_STATUS_MATCHED_CONTAINING = "MatchedByContainingLogFile"
PWM_STATUS_MATCHED_NEAREST = "MatchedByNearestLogFile"
PWM_STATUS_MATCHED_LATEST_BEFORE = "MatchedByLatestBeforeStartWithinThreshold"
PWM_STATUS_NO_PWM_FOUND_FOR_AXIS = "NoPWMFoundForAxis"
PWM_STATUS_NO_RELEVANT_LOG_FILE = "NoRelevantLogFileFound"
PWM_STATUS_CONFLICT = "PWMConflictInSourceFile"
PWM_STATUS_DIRECTION_CHANGED_ONLY = "DirectionChangedOnly"

DURATION_STATUS_VALID = "Valid"
DURATION_STATUS_NOT_APPLICABLE = "Not Applicable"
DURATION_STATUS_END_BEFORE_START = "End Before Start"
DURATION_STATUS_TOO_LONG = "Duration Too Long"

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
    "Initialization Failed Count",
    "Diagnostic Count",
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
    "Initialization Failed Count",
    "Diagnostic Count",
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
