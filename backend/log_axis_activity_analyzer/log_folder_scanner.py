"""Folder discovery and aggregated parsing for PWM control-log files."""

from __future__ import annotations

import logging
from pathlib import Path

from .log_b_parser import DutyCycleLogParser
from .models import DutyCycleFolderParseResult, ParseWarning


class LogFolderScanner:
    """Scans a folder of `.log` files and parses each relevant control log."""

    def __init__(self, parser: DutyCycleLogParser, logger: logging.Logger | None = None) -> None:
        """Initialize the scanner with a single-file PWM parser."""

        self._parser = parser
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def scan(
        self,
        folder_path: Path | str,
        preferred_encoding: str | None = None,
        recursive: bool = False,
    ) -> DutyCycleFolderParseResult:
        """Parse every `.log` file in the selected folder."""

        root = Path(folder_path)
        self._logger.info("Scanning PWM log folder %s (recursive=%s)", root, recursive)
        result = DutyCycleFolderParseResult(root_path=root, recursive=recursive)
        log_paths = self._discover_log_files(root, recursive)
        if not log_paths:
            result.warnings.append(
                ParseWarning(
                    source_name="PWM Folder",
                    source_path=root,
                    line_number=0,
                    raw_line="",
                    message="No .log files were found in the selected log folder.",
                )
            )
            return result
        for log_path in log_paths:
            parsed_file = self._parse_one_file(log_path, preferred_encoding, result)
            if parsed_file is not None:
                result.files.append(parsed_file)
        self._logger.info("Scanned %s log files under %s", len(result.files), root)
        return result

    def _discover_log_files(self, root: Path, recursive: bool) -> list[Path]:
        """Return the sorted list of `.log` files that should be parsed."""

        self._logger.debug("Discovering PWM log files under %s", root)
        pattern = root.rglob("*.log") if recursive else root.glob("*.log")
        return sorted(path for path in pattern if path.is_file())

    def _parse_one_file(
        self,
        log_path: Path,
        preferred_encoding: str | None,
        aggregate_result: DutyCycleFolderParseResult,
    ):
        """Parse one file and convert file-level failures into warnings."""

        self._logger.debug("Parsing discovered PWM log file %s", log_path)
        try:
            return self._parser.parse(log_path, preferred_encoding)
        except Exception as exc:  # pragma: no cover - defensive guard for malformed files.
            self._logger.exception("Failed to parse PWM log file %s: %s", log_path, exc)
            aggregate_result.warnings.append(
                ParseWarning(
                    source_name="PWM Folder",
                    source_path=log_path,
                    line_number=0,
                    raw_line="",
                    message=f"Failed to parse log file: {exc}",
                )
            )
            return None
