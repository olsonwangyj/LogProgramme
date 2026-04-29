"""PWM history resolution for activity records using per-file per-axis profiles."""

from __future__ import annotations

import logging

from .config import PWM_FILE_NEARNESS_THRESHOLD_MS, PWM_LATEST_BEFORE_MAX_DELTA_MS, STATUS_NO_PWM_FOUND, STATUS_NO_RELEVANT_LOG_FILE_FOUND
from .models import ActivityRecord, AxisPWMProfile, DutyCycleLogFileResult, PWMEvent, PWMMatchSelection
from .time_utils import compute_range_distance_ms, compute_time_delta_ms, format_log_timestamp


class DutyCycleAssociator:
    """Attaches the most relevant axis PWM record to each activity row."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the associator with an optional logger."""

        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def attach(
        self,
        records: list[ActivityRecord],
        log_file_results: list[DutyCycleLogFileResult],
        strategy: str = "same_file_then_nearest",
    ) -> list[ActivityRecord]:
        """Attach PWM history to activity records using the selected strategy."""

        self._logger.info(
            "Associating PWM values for %s records with strategy %s",
            len(records),
            strategy,
        )
        for record in records:
            self._attach_record_pwm(record, log_file_results, strategy)
        return records

    def _attach_record_pwm(
        self,
        record: ActivityRecord,
        log_file_results: list[DutyCycleLogFileResult],
        strategy: str,
    ) -> None:
        """Resolve and attach one PWM source to an activity record."""

        self._logger.debug("Resolving PWM for axis %s match status %s", record.axis, record.match_status)
        if not record.axis or record.match_status == "Parse Warning":
            return
        reference_time = record.start_time or record.end_time
        selection = self._select_pwm_event(record.axis, reference_time, log_file_results, strategy)
        self._apply_selection(record, selection)

    def _select_pwm_event(
        self,
        axis: str,
        reference_time,
        log_file_results: list[DutyCycleLogFileResult],
        strategy: str,
    ) -> PWMMatchSelection:
        """Select the best PWM event for one axis and reference time."""

        self._logger.debug("Selecting PWM event for axis %s", axis)
        if not log_file_results:
            return PWMMatchSelection(
                match_method="NoControlLogsAvailable",
                match_status="NoRelevantLogFileFound",
                notes="No control-log files were available for PWM matching.",
            )
        containing_files = [
            file_result
            for file_result in log_file_results
            if compute_range_distance_ms(reference_time, file_result.file_start_time, file_result.file_end_time) == 0
        ]
        if containing_files:
            selection = self._select_from_files(axis, reference_time, containing_files, "ContainingLogFile")
            if selection.event is not None:
                return selection
            return PWMMatchSelection(
                match_method="ContainingLogFile",
                match_status="NoPWMFoundForAxisInRelevantFile",
                notes=f"Relevant log file(s) contained the activity time, but no PWM profile was found for axis {axis}.",
            )

        nearby_files = [
            (compute_range_distance_ms(reference_time, file_result.file_start_time, file_result.file_end_time), file_result)
            for file_result in log_file_results
        ]
        nearby_files = [
            (distance_ms, file_result)
            for distance_ms, file_result in nearby_files
            if distance_ms is not None and distance_ms <= PWM_FILE_NEARNESS_THRESHOLD_MS
        ]
        if nearby_files:
            nearest_distance, _ = min(nearby_files, key=lambda item: (item[0], item[1].source_path.name))
            nearest_files = [
                file_result
                for distance_ms, file_result in nearby_files
                if distance_ms == nearest_distance
            ]
            selection = self._select_from_files(axis, reference_time, nearest_files, "NearestLogFile")
            if selection.event is not None:
                if selection.time_delta_ms is None:
                    selection.time_delta_ms = nearest_distance
                return selection
            return PWMMatchSelection(
                match_method="NearestLogFile",
                match_status="NoPWMFoundForAxisInRelevantFile",
                notes=f"Nearby log file(s) were found, but none contained a PWM profile for axis {axis}.",
            )

        if strategy in {"same_file_then_nearest", "latest_before_start"}:
            selection = self._select_latest_before_start(axis, reference_time, log_file_results)
            if selection.event is not None:
                return selection
        if strategy == "latest_known":
            selection = self._select_latest_known(axis, reference_time, log_file_results)
            if selection.event is not None:
                return selection
        return PWMMatchSelection(
            match_method="NoRelevantLogFile",
            match_status="NoRelevantLogFileFound",
            notes=f"No relevant control-log file was close enough to the activity time for axis {axis}.",
        )

    def _select_from_files(
        self,
        axis: str,
        reference_time,
        file_results: list[DutyCycleLogFileResult],
        context: str,
    ) -> PWMMatchSelection:
        """Select the best PWM source from a chosen set of relevant log files."""

        self._logger.debug("Selecting PWM from %s relevant files for axis %s", context, axis)
        candidates: list[tuple[PWMEvent, AxisPWMProfile, DutyCycleLogFileResult, int | None]] = []
        for file_result in file_results:
            profile = file_result.axis_profiles.get(axis)
            if profile is None:
                continue
            event = self._select_profile_event(profile, reference_time)
            if event is None:
                continue
            time_delta_ms = compute_time_delta_ms(event.timestamp, reference_time)
            candidates.append((event, profile, file_result, time_delta_ms))
        if not candidates:
            return PWMMatchSelection()
        selected_event, selected_profile, selected_file, time_delta_ms = min(
            candidates,
            key=lambda item: (
                item[3] is None,
                item[3] or 0,
                item[0].timestamp is None,
                item[0].timestamp or item[2].file_start_time,
                item[0].line_number,
            ),
        )
        if context == "ContainingLogFile":
            match_method = "ContainingLogFileLatestAtOrBeforeActivity"
            match_status = "MatchedByContainingLogFile"
        else:
            match_method = "NearestLogFileByTimeRange"
            match_status = "MatchedByNearestLogFile"
        notes = self._build_selection_note(selected_profile, selected_file, selected_event, context)
        if selected_profile.conflict:
            match_status = "PWMConflictInSourceFile"
        return PWMMatchSelection(
            event=selected_event,
            profile=selected_profile,
            match_method=match_method,
            match_status=match_status,
            time_delta_ms=time_delta_ms,
            notes=notes,
        )

    def _select_latest_before_start(
        self,
        axis: str,
        reference_time,
        file_results: list[DutyCycleLogFileResult],
    ) -> PWMMatchSelection:
        """Fallback to the latest timestamped PWM event before the activity start."""

        self._logger.debug("Selecting latest-before-start PWM for axis %s", axis)
        if reference_time is None:
            return PWMMatchSelection()
        candidates: list[tuple[PWMEvent, AxisPWMProfile, DutyCycleLogFileResult]] = []
        for file_result in file_results:
            profile = file_result.axis_profiles.get(axis)
            if profile is None:
                continue
            eligible = [
                event
                for event in profile.events
                if event.timestamp is not None and event.timestamp <= reference_time
            ]
            if not eligible:
                continue
            selected_event = self._prefer_setting_event(eligible)
            candidates.append((selected_event, profile, file_result))
        if not candidates:
            return PWMMatchSelection()
        selected_event, selected_profile, selected_file = max(
            candidates,
            key=lambda item: (item[0].timestamp, item[0].line_number),
        )
        time_delta_ms = compute_time_delta_ms(selected_event.timestamp, reference_time)
        if time_delta_ms is not None and time_delta_ms > PWM_LATEST_BEFORE_MAX_DELTA_MS:
            return PWMMatchSelection(
                match_method="LatestBeforeStartWithinFolder",
                match_status="NoRelevantLogFileFound",
                notes=(
                    f"The latest PWM record before the activity for axis {axis} was too far away "
                    f"({time_delta_ms} ms > max {PWM_LATEST_BEFORE_MAX_DELTA_MS} ms)."
                ),
            )
        notes = self._build_selection_note(selected_profile, selected_file, selected_event, "LatestBeforeStart")
        if selected_profile.conflict:
            match_status = "PWMConflictInSourceFile"
        else:
            match_status = "MatchedByLatestBeforeStartWithinRelevantFiles"
        return PWMMatchSelection(
            event=selected_event,
            profile=selected_profile,
            match_method="LatestBeforeStartWithinFolder",
            match_status=match_status,
            time_delta_ms=time_delta_ms,
            notes=notes,
        )

    def _select_latest_known(
        self,
        axis: str,
        reference_time,
        file_results: list[DutyCycleLogFileResult],
    ) -> PWMMatchSelection:
        """Fallback to the latest known PWM event across the folder when explicitly requested."""

        self._logger.debug("Selecting latest-known PWM for axis %s", axis)
        candidates: list[tuple[PWMEvent, AxisPWMProfile, DutyCycleLogFileResult]] = []
        for file_result in file_results:
            profile = file_result.axis_profiles.get(axis)
            if profile is None or not profile.events:
                continue
            candidates.append((self._select_profile_event(profile, reference_time), profile, file_result))
        candidates = [item for item in candidates if item[0] is not None]
        if not candidates:
            return PWMMatchSelection()
        selected_event, selected_profile, selected_file = max(
            candidates,
            key=lambda item: (
                item[0].timestamp is not None,
                item[0].timestamp or item[2].file_end_time,
                item[0].line_number,
            ),
        )
        time_delta_ms = compute_time_delta_ms(selected_event.timestamp, reference_time)
        if time_delta_ms is not None and time_delta_ms > PWM_LATEST_BEFORE_MAX_DELTA_MS:
            return PWMMatchSelection(
                match_method="LatestKnownAcrossFolder",
                match_status="NoRelevantLogFileFound",
                notes=(
                    f"The latest known PWM record for axis {axis} was too far away "
                    f"({time_delta_ms} ms > max {PWM_LATEST_BEFORE_MAX_DELTA_MS} ms)."
                ),
            )
        notes = self._build_selection_note(selected_profile, selected_file, selected_event, "LatestKnown")
        if selected_profile.conflict:
            match_status = "PWMConflictInSourceFile"
        else:
            match_status = "MatchedByLatestBeforeStartWithinRelevantFiles"
        return PWMMatchSelection(
            event=selected_event,
            profile=selected_profile,
            match_method="LatestKnownAcrossFolder",
            match_status=match_status,
            time_delta_ms=time_delta_ms,
            notes=notes,
        )

    def _select_profile_event(self, profile: AxisPWMProfile, reference_time) -> PWMEvent | None:
        """Select the best PWM event from one per-axis profile for the activity time."""

        self._logger.debug("Selecting PWM event from profile %s in %s", profile.axis, profile.source_path.name)
        if not profile.events:
            return None
        if reference_time is not None:
            earlier_events = [
                event
                for event in profile.events
                if event.timestamp is not None and event.timestamp <= reference_time
            ]
            if earlier_events:
                return self._prefer_setting_event(earlier_events)
            timed_events = [event for event in profile.events if event.timestamp is not None]
            if timed_events:
                candidate_pool = [event for event in timed_events if not event.is_status_confirmation] or timed_events
                return min(
                    candidate_pool,
                    key=lambda event: (
                        compute_time_delta_ms(event.timestamp, reference_time) or 0,
                        event.timestamp > reference_time,
                        event.line_number,
                    ),
                )
        setting_events = [event for event in profile.events if not event.is_status_confirmation]
        if setting_events:
            return setting_events[-1]
        return profile.events[-1]

    def _prefer_setting_event(self, events: list[PWMEvent]) -> PWMEvent:
        """Prefer a setting command over a status confirmation when timestamps tie."""

        setting_events = [event for event in events if not event.is_status_confirmation]
        if setting_events:
            return max(
                setting_events,
                key=lambda event: (event.timestamp, event.line_number),
            )
        return max(
            events,
            key=lambda event: (event.timestamp, event.line_number),
        )

    def _apply_selection(self, record: ActivityRecord, selection: PWMMatchSelection) -> None:
        """Copy a selected PWM source onto the activity record."""

        self._logger.debug("Applying PWM selection with status %s", selection.match_status)
        record.pwm_match_method = selection.match_method
        record.pwm_match_status = selection.match_status
        record.pwm_time_delta_ms = selection.time_delta_ms
        record.notes = self._merge_notes(record.notes, selection.notes)
        if selection.event is None:
            return
        record.pwm_percent = selection.event.pwm_percent
        record.pwm_raw_value = selection.event.pwm_raw_value
        record.pwm_direction = selection.event.direction
        record.pwm_source_file = selection.event.source_path.name
        record.pwm_source_line = selection.event.raw_line
        record.pwm_source_time = selection.event.timestamp
        record.pwm_line_number = selection.event.line_number
        if selection.match_status in {
            "MatchedByNearestLogFile",
            "PWMConflictInSourceFile",
            "NoPWMFoundForAxisInRelevantFile",
            "NoRelevantLogFileFound",
        }:
            record.pwm_warning = True
        if selection.match_status == "NoPWMFoundForAxisInRelevantFile":
            record.status = STATUS_NO_PWM_FOUND
        if selection.match_status == "NoRelevantLogFileFound":
            record.status = STATUS_NO_RELEVANT_LOG_FILE_FOUND

    def _build_selection_note(
        self,
        profile: AxisPWMProfile,
        file_result: DutyCycleLogFileResult,
        event: PWMEvent,
        context: str,
    ) -> str:
        """Build a note string for the selected PWM source."""

        notes = profile.notes
        if event.is_status_confirmation:
            notes = self._merge_notes(notes, "Selected PWM source is a status confirmation line.")
        if event.is_confirmed_by_status_line and not event.is_status_confirmation:
            notes = self._merge_notes(notes, "PWM setting is confirmed by a matching status line.")
        if profile.conflict:
            notes = self._merge_notes(notes, "Conflicting raw PWM values were detected in the source file.")
        if event.source_file_start_time or event.source_file_end_time:
            notes = self._merge_notes(
                notes,
                (
                    f"{context} window: "
                    f"{format_log_timestamp(file_result.file_start_time)} to "
                    f"{format_log_timestamp(file_result.file_end_time)}."
                ),
            )
        source_time = format_log_timestamp(event.timestamp)
        if source_time:
            notes = self._merge_notes(notes, f"Selected PWM source time: {source_time}.")
        return notes

    def _merge_notes(self, existing: str, new_note: str) -> str:
        """Combine existing notes with a new note without duplicating separators."""

        if not new_note:
            return existing
        if not existing:
            return new_note
        return f"{existing} | {new_note}"
