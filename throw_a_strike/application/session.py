"""Pure application state machine for a configured game session."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.config import MatchConfig, Mode
from ..domain.cumulative_match import CumulativeMatch, CumulativeMatchSnapshot
from ..domain.match import BowlingMatch, MatchSnapshot, PlayerColor
from ..domain.schedule import (
    PartyFrameSchedule,
    PartySchedule,
    RemixObject,
    RemixSchedule,
)


class InvalidSessionConfigurationError(ValueError):
    """Raised when configuration and schedule do not form a valid session."""


class InvalidSessionTransitionError(RuntimeError):
    """Raised when an operation is unavailable in the current phase."""


class SessionPhase(str, Enum):
    CONFIGURING = "configuring"
    READY = "ready"
    AWAITING_THROW = "awaiting_throw"
    SHOWING_RESULT = "showing_result"
    PLAYER_TRANSITION = "player_transition"
    FRAME_TRANSITION = "frame_transition"
    GAME_OVER = "game_over"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SessionThrowSnapshot:
    mode: Mode
    player_number: int
    player_color: PlayerColor
    frame_number: int
    throw_number: int
    scored_value: int
    available_before: int
    available_after: int
    turn_ended: bool
    global_frame_ended: bool
    match_complete: bool
    next_player_number: int | None
    next_player_color: PlayerColor | None
    remix_object: RemixObject | None
    party_frame: PartyFrameSchedule | None


@dataclass(frozen=True)
class SessionSnapshot:
    phase: SessionPhase
    config: MatchConfig | None
    schedule: RemixSchedule | PartySchedule | None
    match: MatchSnapshot | CumulativeMatchSnapshot | None
    current_frame_number: int | None
    current_player_number: int | None
    current_player_color: PlayerColor | None
    current_throw_number: int | None
    current_available: int | None
    current_remix_object: RemixObject | None
    current_party_frame: PartyFrameSchedule | None
    last_throw: SessionThrowSnapshot | None


class GameSession:
    """Coordinate immutable configuration with one privately-owned match engine."""

    def __init__(self) -> None:
        self._phase = SessionPhase.CONFIGURING
        self._config: MatchConfig | None = None
        self._schedule: RemixSchedule | PartySchedule | None = None
        self._match: BowlingMatch | CumulativeMatch | None = None
        self._last_throw: SessionThrowSnapshot | None = None

    def configure(
        self,
        config: MatchConfig,
        schedule: RemixSchedule | PartySchedule | None = None,
    ) -> SessionSnapshot:
        self._require_phase("configure", SessionPhase.CONFIGURING, SessionPhase.READY)
        self._validate_configuration(config, schedule)
        self._config = config
        self._schedule = schedule
        self._match = None
        self._last_throw = None
        self._phase = SessionPhase.READY
        return self.snapshot()

    def start(self) -> SessionSnapshot:
        self._require_phase("start", SessionPhase.READY)
        match = self._new_match()
        self._match = match
        self._last_throw = None
        self._phase = SessionPhase.AWAITING_THROW
        return self.snapshot()

    def submit_throw(self, value: int) -> SessionSnapshot:
        self._require_phase("submit_throw", SessionPhase.AWAITING_THROW)
        config = self._configured()
        match = self._active_match()
        before = match.snapshot()
        frame, player, color, throw, available = self._current_values(before)
        remix, party = self._schedule_metadata(frame, throw)

        # Domain validation occurs before its mutation, so errors propagate without
        # changing either the engine or session fields.
        accepted = match.roll(value)
        if isinstance(match, BowlingMatch):
            scored = accepted.rack.pins
            available_before = accepted.rack.standing_before
            available_after = accepted.rack.standing_after
        else:
            scored = accepted.roll.points
            available_before = accepted.roll.remaining_before
            available_after = accepted.roll.remaining_after

        self._last_throw = SessionThrowSnapshot(
            mode=config.mode,
            player_number=player,
            player_color=color,
            frame_number=frame,
            throw_number=throw,
            scored_value=scored,
            available_before=available_before,
            available_after=available_after,
            turn_ended=accepted.turn_ended,
            global_frame_ended=accepted.global_frame_ended,
            match_complete=accepted.match.complete,
            next_player_number=accepted.next_player_number,
            next_player_color=accepted.next_player_color,
            remix_object=remix,
            party_frame=party,
        )
        self._phase = SessionPhase.SHOWING_RESULT
        return self.snapshot()

    def acknowledge_result(self) -> SessionSnapshot:
        self._require_phase("acknowledge_result", SessionPhase.SHOWING_RESULT)
        throw = self._last_throw
        if throw is None:  # Internal invariant; retained as a defensive guard.
            raise RuntimeError("showing-result phase has no accepted throw")
        if throw.match_complete:
            self._phase = SessionPhase.GAME_OVER
        elif throw.global_frame_ended:
            self._phase = SessionPhase.FRAME_TRANSITION
        elif throw.turn_ended:
            self._phase = SessionPhase.PLAYER_TRANSITION
        else:
            self._phase = SessionPhase.AWAITING_THROW
        return self.snapshot()

    def continue_transition(self) -> SessionSnapshot:
        self._require_phase(
            "continue_transition",
            SessionPhase.PLAYER_TRANSITION,
            SessionPhase.FRAME_TRANSITION,
        )
        self._phase = SessionPhase.AWAITING_THROW
        return self.snapshot()

    def replay(self) -> SessionSnapshot:
        self._require_phase("replay", SessionPhase.GAME_OVER)
        match = self._new_match()
        self._match = match
        self._last_throw = None
        self._phase = SessionPhase.AWAITING_THROW
        return self.snapshot()

    def cancel(self) -> SessionSnapshot:
        if self._phase is SessionPhase.CANCELLED:
            raise InvalidSessionTransitionError("cancel is not valid while cancelled")
        self._phase = SessionPhase.CANCELLED
        return self.snapshot()

    def snapshot(self) -> SessionSnapshot:
        match = self._match.snapshot() if self._match is not None else None
        current = (None, None, None, None, None)
        remix = None
        party = None
        if self._phase is SessionPhase.AWAITING_THROW and match is not None:
            current = self._current_values(match)
            remix, party = self._schedule_metadata(current[0], current[3])
        frame, player, color, throw, available = current
        return SessionSnapshot(
            phase=self._phase,
            config=self._config,
            schedule=self._schedule,
            match=match,
            current_frame_number=frame,
            current_player_number=player,
            current_player_color=color,
            current_throw_number=throw,
            current_available=available,
            current_remix_object=remix,
            current_party_frame=party,
            last_throw=self._last_throw,
        )

    def _require_phase(self, operation: str, *phases: SessionPhase) -> None:
        if self._phase not in phases:
            raise InvalidSessionTransitionError(
                f"{operation} is not valid while {self._phase.value}"
            )

    @staticmethod
    def _validate_configuration(
        config: object, schedule: object
    ) -> None:
        if not isinstance(config, MatchConfig):
            raise InvalidSessionConfigurationError("config must be a MatchConfig")
        expected = {
            Mode.TEN_PIN: type(None),
            Mode.HUNDRED_PIN: type(None),
            Mode.REMIX: RemixSchedule,
            Mode.PARTY: PartySchedule,
        }[config.mode]
        if expected is type(None):
            if schedule is not None:
                raise InvalidSessionConfigurationError(
                    f"{config.mode.value} does not accept a schedule"
                )
        elif not isinstance(schedule, expected):
            raise InvalidSessionConfigurationError(
                f"{config.mode.value} requires a {expected.__name__}"
            )
        if schedule is not None and schedule.config != config:
            raise InvalidSessionConfigurationError(
                "schedule configuration must exactly match session configuration"
            )

    def _configured(self) -> MatchConfig:
        if self._config is None:
            raise RuntimeError("session has no configuration")
        return self._config

    def _active_match(self) -> BowlingMatch | CumulativeMatch:
        if self._match is None:
            raise RuntimeError("session has no active match")
        return self._match

    def _new_match(self) -> BowlingMatch | CumulativeMatch:
        config = self._configured()
        if config.mode is Mode.TEN_PIN:
            return BowlingMatch(config.player_count)
        if config.mode is Mode.HUNDRED_PIN:
            maximums = (100,) * config.frame_count
        else:
            if self._schedule is None:
                raise RuntimeError("scheduled mode has no schedule")
            maximums = self._schedule.frame_max_scores
        return CumulativeMatch(config.player_count, maximums)

    @staticmethod
    def _current_values(
        match: MatchSnapshot | CumulativeMatchSnapshot,
    ) -> tuple[int, int, PlayerColor, int, int]:
        if isinstance(match, MatchSnapshot):
            values = (
                match.current_frame,
                match.current_player_number,
                match.current_player_color,
                match.current_roll,
                match.pins_standing,
            )
        else:
            values = (
                match.current_global_frame_number,
                match.current_player_number,
                match.current_player_color,
                match.current_roll_number,
                match.current_remaining_capacity,
            )
        if any(value is None for value in values):
            raise RuntimeError("active match does not expose a current throw")
        return values  # type: ignore[return-value]

    def _schedule_metadata(
        self, frame: int, throw: int
    ) -> tuple[RemixObject | None, PartyFrameSchedule | None]:
        if isinstance(self._schedule, RemixSchedule):
            return self._schedule.frames[frame - 1].objects[throw - 1], None
        if isinstance(self._schedule, PartySchedule):
            return None, self._schedule.frames[frame - 1]
        return None, None
