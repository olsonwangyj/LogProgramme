"""Text-file loading utilities with encoding fallback and line preservation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

from .config import SUPPORTED_ENCODINGS


class TextFileLoader:
    """Streams text files with best-effort encoding detection."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the loader with an optional logger."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def iter_lines(
        self,
        file_path: Path | str,
        preferred_encoding: str | None = None,
    ) -> tuple[Iterator[tuple[int, str]], str]:
        """Open a text file and return an iterator of numbered lines."""

        path = Path(file_path)
        # 1. Resolve the encoding that will be used for this file.
        encoding = self._resolve_encoding(path, preferred_encoding)
        # 2. Open the file with replacement enabled so bad bytes do not abort the run.
        handle = path.open("r", encoding=encoding, errors="replace")
        # 3. Build a lazy iterator that yields numbered lines.
        iterator = self._yield_numbered_lines(handle)
        # 4. Return both the iterator and the selected encoding.
        return iterator, encoding

    def _resolve_encoding(self, path: Path, preferred_encoding: str | None) -> str:
        """Determine which encoding should be used to read the file."""

        self._logger.debug("Resolving encoding for %s", path)
        # 1. Try the caller-provided encoding first when present.
        if preferred_encoding and self._can_read_sample(path, preferred_encoding):
            self._logger.info("Using caller-provided encoding %s for %s", preferred_encoding, path)
            return preferred_encoding
        # 2. Try the supported fallback list in order.
        discovered = self._find_supported_encoding(path)
        if discovered:
            self._logger.info("Detected encoding %s for %s", discovered, path)
            return discovered
        # 3. Fall back to UTF-8 replacement mode if no strict read succeeds.
        self._logger.warning(
            "Could not confirm a strict encoding for %s; using utf-8 with replacement characters",
            path,
        )
        return "utf-8"

    def _find_supported_encoding(self, path: Path) -> str | None:
        """Return the first supported encoding that can decode a sample."""

        self._logger.debug("Scanning configured encodings for %s", path)
        for encoding in SUPPORTED_ENCODINGS:
            if self._can_read_sample(path, encoding):
                return encoding
        return None

    def _can_read_sample(self, path: Path, encoding: str) -> bool:
        """Check whether the first bytes of a file can be decoded strictly."""

        self._logger.debug("Testing encoding %s for %s", encoding, path)
        try:
            with path.open("r", encoding=encoding, errors="strict") as handle:
                handle.read(65536)
        except (OSError, UnicodeDecodeError):
            return False
        return True

    def _yield_numbered_lines(self, handle) -> Iterator[tuple[int, str]]:
        """Yield numbered lines and close the file handle when finished."""

        self._logger.debug("Starting line iteration")
        try:
            for line_number, line in enumerate(handle, start=1):
                yield line_number, line.rstrip("\r\n")
        finally:
            handle.close()
