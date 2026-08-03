"""Pure, dimension-independent presentation projections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.config import BrandingSnapshot, LOCKED_BRANDING, MatchConfig, Mode, Theme
from ..domain.cumulative_match import CumulativeMatchSnapshot
from ..domain.match import MatchSnapshot, PlayerColor
from ..domain.schedule import PartyFrameSchedule, RemixObject
from .ports import ApplicationCapabilities
from .session import SessionPhase, SessionSnapshot, SessionThrowSnapshot


class InvalidPresentationValueError(ValueError):
    """Raised when an input cannot safely form a presentation snapshot."""


class PresentationPrompt(str, Enum):
    CONFIGURE_MATCH = "configure_match"
    READY_TO_START = "ready_to_start"
    AWAIT_THROW = "await_throw"
    SHOW_RESULT = "show_result"
    PLAYER_TRANSITION = "player_transition"
    FRAME_TRANSITION = "frame_transition"
    GAME_OVER = "game_over"
    CANCELLED = "cancelled"


class ScoreboardPlacement(str, Enum):
    NONE = "none"
    MAIN = "main"
    SECONDARY = "secondary"


def _integer(value: object, name: str, *, positive: bool = False) -> None:
    minimum = 1 if positive else 0
    if type(value) is not int or value < minimum:
        qualifier = "positive" if positive else "nonnegative"
        raise InvalidPresentationValueError(f"{name} must be a {qualifier} integer")


def _optional_integer(value: object, name: str, *, positive: bool = False) -> None:
    if value is not None:
        _integer(value, name, positive=positive)


def _exact(value: object, kind: type, name: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if type(value) is not kind:
        suffix = " or None" if optional else ""
        raise InvalidPresentationValueError(f"{name} must be an exact {kind.__name__}{suffix}")


def _actual_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise InvalidPresentationValueError(f"{name} must be a bool")


def _string(value: object, name: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if type(value) is not str or not value or value != value.strip():
        qualifier = " or None" if optional else ""
        raise InvalidPresentationValueError(f"{name} must be a nonempty stripped string{qualifier}")


def _tuple_of(value: object, kind: type, name: str) -> None:
    if type(value) is not tuple or any(type(item) is not kind for item in value):
        raise InvalidPresentationValueError(f"{name} must be a tuple of exact {kind.__name__} values")


@dataclass(frozen=True)
class FrameScoreViewModel:
    frame_number: int
    roll_values: tuple[int, ...]
    roll_labels: tuple[str, ...]
    score: int | None
    cumulative_score: int | None
    maximum_score: int | None
    complete: bool

    def __post_init__(self) -> None:
        _integer(self.frame_number, "frame_number", positive=True)
        if type(self.roll_values) is not tuple or any(
            type(value) is not int or value < 0 for value in self.roll_values
        ):
            raise InvalidPresentationValueError("roll_values must be a tuple of nonnegative integers")
        if type(self.roll_labels) is not tuple or any(type(label) is not str for label in self.roll_labels):
            raise InvalidPresentationValueError("roll_labels must be a tuple of strings")
        if len(self.roll_values) != len(self.roll_labels):
            raise InvalidPresentationValueError("roll values and labels must have equal length")
        _optional_integer(self.score, "score")
        _optional_integer(self.cumulative_score, "cumulative_score")
        _optional_integer(self.maximum_score, "maximum_score", positive=True)
        if type(self.complete) is not bool:
            raise InvalidPresentationValueError("complete must be a bool")


@dataclass(frozen=True)
class PlayerScoreViewModel:
    player_number: int
    color: PlayerColor
    frames: tuple[FrameScoreViewModel, ...]
    total_score: int
    complete: bool

    def __post_init__(self) -> None:
        _integer(self.player_number, "player_number", positive=True)
        _exact(self.color, PlayerColor, "color")
        _tuple_of(self.frames, FrameScoreViewModel, "frames")
        _integer(self.total_score, "total_score")
        _actual_bool(self.complete, "complete")


@dataclass(frozen=True)
class StandingViewModel:
    rank: int
    player_number: int
    color: PlayerColor
    total_score: int
    provisional: bool

    def __post_init__(self) -> None:
        _integer(self.rank, "rank", positive=True)
        _integer(self.player_number, "player_number", positive=True)
        _exact(self.color, PlayerColor, "color")
        _integer(self.total_score, "total_score")
        _actual_bool(self.provisional, "provisional")


@dataclass(frozen=True)
class WinnerViewModel:
    player_number: int
    color: PlayerColor
    total_score: int

    def __post_init__(self) -> None:
        _integer(self.player_number, "player_number", positive=True)
        _exact(self.color, PlayerColor, "color")
        _integer(self.total_score, "total_score")


@dataclass(frozen=True)
class ThrowResultViewModel:
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

    def __post_init__(self) -> None:
        _exact(self.mode, Mode, "mode")
        for value, name in ((self.player_number, "player_number"), (self.frame_number, "frame_number"), (self.throw_number, "throw_number")):
            _integer(value, name, positive=True)
        _exact(self.player_color, PlayerColor, "player_color")
        for value, name in ((self.scored_value, "scored_value"), (self.available_before, "available_before"), (self.available_after, "available_after")):
            _integer(value, name)
        for value, name in ((self.turn_ended, "turn_ended"), (self.global_frame_ended, "global_frame_ended"), (self.match_complete, "match_complete")):
            _actual_bool(value, name)
        _optional_integer(self.next_player_number, "next_player_number", positive=True)
        _exact(self.next_player_color, PlayerColor, "next_player_color", optional=True)
        if (self.next_player_number is None) != (self.next_player_color is None):
            raise InvalidPresentationValueError("next player number and color must be present together")
        _exact(self.remix_object, RemixObject, "remix_object", optional=True)
        _exact(self.party_frame, PartyFrameSchedule, "party_frame", optional=True)
        if self.remix_object is not None and self.party_frame is not None:
            raise InvalidPresentationValueError("remix_object and party_frame are mutually exclusive")


@dataclass(frozen=True)
class ScoreboardViewModel:
    branding: BrandingSnapshot
    phase: SessionPhase
    mode: Mode
    mode_label: str
    theme: Theme
    theme_label: str
    player_count: int
    frame_count: int
    focus_frame_number: int | None
    focus_player_number: int | None
    focus_player_color: PlayerColor | None
    focus_throw_number: int | None
    players: tuple[PlayerScoreViewModel, ...]
    standings: tuple[StandingViewModel, ...]
    winners: tuple[WinnerViewModel, ...]
    complete: bool

    def __post_init__(self) -> None:
        _exact(self.branding, BrandingSnapshot, "branding")
        _exact(self.phase, SessionPhase, "phase")
        _exact(self.mode, Mode, "mode")
        _string(self.mode_label, "mode_label")
        _exact(self.theme, Theme, "theme")
        _string(self.theme_label, "theme_label")
        _integer(self.player_count, "player_count", positive=True)
        _integer(self.frame_count, "frame_count", positive=True)
        for value, name in ((self.focus_frame_number, "focus_frame_number"), (self.focus_player_number, "focus_player_number"), (self.focus_throw_number, "focus_throw_number")):
            _optional_integer(value, name, positive=True)
        _exact(self.focus_player_color, PlayerColor, "focus_player_color", optional=True)
        focus = (self.focus_frame_number, self.focus_player_number, self.focus_player_color, self.focus_throw_number)
        if not (all(value is None for value in focus) or all(value is not None for value in focus)):
            raise InvalidPresentationValueError("focus fields must be all present or all None")
        _tuple_of(self.players, PlayerScoreViewModel, "players")
        _tuple_of(self.standings, StandingViewModel, "standings")
        _tuple_of(self.winners, WinnerViewModel, "winners")
        _actual_bool(self.complete, "complete")


@dataclass(frozen=True)
class MainDisplayViewModel:
    branding: BrandingSnapshot | None
    phase: SessionPhase
    prompt: PresentationPrompt
    mode: Mode | None
    mode_label: str | None
    theme: Theme | None
    theme_label: str | None
    input_enabled: bool
    current_frame_number: int | None
    current_player_number: int | None
    current_player_color: PlayerColor | None
    current_throw_number: int | None
    current_available: int | None
    current_remix_object: RemixObject | None
    current_party_frame: PartyFrameSchedule | None
    result: ThrowResultViewModel | None
    scoreboard: ScoreboardViewModel | None

    def __post_init__(self) -> None:
        _exact(self.branding, BrandingSnapshot, "branding", optional=True)
        _exact(self.phase, SessionPhase, "phase")
        _exact(self.prompt, PresentationPrompt, "prompt")
        _exact(self.mode, Mode, "mode", optional=True)
        _string(self.mode_label, "mode_label", optional=True)
        _exact(self.theme, Theme, "theme", optional=True)
        _string(self.theme_label, "theme_label", optional=True)
        _actual_bool(self.input_enabled, "input_enabled")
        for value, name in ((self.current_frame_number, "current_frame_number"), (self.current_player_number, "current_player_number"), (self.current_throw_number, "current_throw_number")):
            _optional_integer(value, name, positive=True)
        _optional_integer(self.current_available, "current_available")
        _exact(self.current_player_color, PlayerColor, "current_player_color", optional=True)
        _exact(self.current_remix_object, RemixObject, "current_remix_object", optional=True)
        _exact(self.current_party_frame, PartyFrameSchedule, "current_party_frame", optional=True)
        _exact(self.result, ThrowResultViewModel, "result", optional=True)
        _exact(self.scoreboard, ScoreboardViewModel, "scoreboard", optional=True)


@dataclass(frozen=True)
class SecondaryScoreboardViewModel:
    branding: BrandingSnapshot
    phase: SessionPhase
    scoreboard: ScoreboardViewModel

    def __post_init__(self) -> None:
        _exact(self.branding, BrandingSnapshot, "branding")
        _exact(self.phase, SessionPhase, "phase")
        _exact(self.scoreboard, ScoreboardViewModel, "scoreboard")


@dataclass(frozen=True)
class PresentationBundle:
    main: MainDisplayViewModel
    secondary: SecondaryScoreboardViewModel | None
    scoreboard_placement: ScoreboardPlacement

    def __post_init__(self) -> None:
        _exact(self.main, MainDisplayViewModel, "main")
        _exact(self.secondary, SecondaryScoreboardViewModel, "secondary", optional=True)
        _exact(self.scoreboard_placement, ScoreboardPlacement, "scoreboard_placement")
        valid = {
            ScoreboardPlacement.NONE: self.main.scoreboard is None and self.secondary is None,
            ScoreboardPlacement.MAIN: self.main.scoreboard is not None and self.secondary is None,
            ScoreboardPlacement.SECONDARY: self.main.scoreboard is None and self.secondary is not None,
        }[self.scoreboard_placement]
        if not valid:
            raise InvalidPresentationValueError("scoreboard placement is inconsistent with outputs")


_PROMPTS = {
    SessionPhase.CONFIGURING: PresentationPrompt.CONFIGURE_MATCH,
    SessionPhase.READY: PresentationPrompt.READY_TO_START,
    SessionPhase.AWAITING_THROW: PresentationPrompt.AWAIT_THROW,
    SessionPhase.SHOWING_RESULT: PresentationPrompt.SHOW_RESULT,
    SessionPhase.PLAYER_TRANSITION: PresentationPrompt.PLAYER_TRANSITION,
    SessionPhase.FRAME_TRANSITION: PresentationPrompt.FRAME_TRANSITION,
    SessionPhase.GAME_OVER: PresentationPrompt.GAME_OVER,
    SessionPhase.CANCELLED: PresentationPrompt.CANCELLED,
}
_MODE_LABELS = {Mode.TEN_PIN: "10-Pin", Mode.HUNDRED_PIN: "100-Pin", Mode.REMIX: "Remix", Mode.PARTY: "Party"}
_THEME_LABELS = {Theme.REGULAR: "Regular", Theme.BLACKLIGHT: "Blacklight"}


def _validate_snapshot(snapshot: SessionSnapshot) -> None:
    _exact(snapshot.phase, SessionPhase, "snapshot.phase")
    _exact(snapshot.config, MatchConfig, "snapshot.config", optional=True)
    config = snapshot.config
    if config is not None:
        _exact(config.mode, Mode, "snapshot.config.mode")
        _exact(config.theme, Theme, "snapshot.config.theme")
    match = snapshot.match
    if match is not None and config is None:
        raise InvalidPresentationValueError("a match cannot exist without configuration")
    if match is not None:
        expected = MatchSnapshot if config.mode is Mode.TEN_PIN else CumulativeMatchSnapshot
        _exact(match, expected, "snapshot.match")

    last_throw = snapshot.last_throw
    if last_throw is not None:
        _exact(last_throw, SessionThrowSnapshot, "snapshot.last_throw")
        if config is None or last_throw.mode is not config.mode:
            raise InvalidPresentationValueError("last_throw mode conflicts with configuration")
        if last_throw.mode is Mode.REMIX:
            if last_throw.remix_object is None or last_throw.party_frame is not None:
                raise InvalidPresentationValueError("Remix result metadata is inconsistent")
        elif last_throw.mode is Mode.PARTY:
            if last_throw.party_frame is None or last_throw.remix_object is not None:
                raise InvalidPresentationValueError("Party result metadata is inconsistent")
        elif last_throw.remix_object is not None or last_throw.party_frame is not None:
            raise InvalidPresentationValueError("result schedule metadata conflicts with mode")
    if snapshot.phase is SessionPhase.SHOWING_RESULT and type(last_throw) is not SessionThrowSnapshot:
        raise InvalidPresentationValueError("showing-result phase requires an exact SessionThrowSnapshot")
    if snapshot.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION, SessionPhase.GAME_OVER) and last_throw is not None:
        _exact(last_throw, SessionThrowSnapshot, "snapshot.last_throw")

    current = (
        snapshot.current_frame_number, snapshot.current_player_number,
        snapshot.current_player_color, snapshot.current_throw_number,
        snapshot.current_available,
    )
    if snapshot.phase is SessionPhase.AWAITING_THROW:
        if match is None or any(value is None for value in current):
            raise InvalidPresentationValueError("awaiting-throw phase requires a complete input window")
        _optional_integer(snapshot.current_frame_number, "current_frame_number", positive=True)
        _optional_integer(snapshot.current_player_number, "current_player_number", positive=True)
        _exact(snapshot.current_player_color, PlayerColor, "current_player_color")
        _optional_integer(snapshot.current_throw_number, "current_throw_number", positive=True)
        _optional_integer(snapshot.current_available, "current_available")
        if config.mode is Mode.REMIX:
            _exact(snapshot.current_remix_object, RemixObject, "current_remix_object")
            if snapshot.current_party_frame is not None:
                raise InvalidPresentationValueError("Remix input cannot contain Party metadata")
        elif config.mode is Mode.PARTY:
            _exact(snapshot.current_party_frame, PartyFrameSchedule, "current_party_frame")
            if snapshot.current_remix_object is not None:
                raise InvalidPresentationValueError("Party input cannot contain Remix metadata")
        elif snapshot.current_remix_object is not None or snapshot.current_party_frame is not None:
            raise InvalidPresentationValueError("current schedule metadata conflicts with mode")
    else:
        blocked = current + (snapshot.current_remix_object, snapshot.current_party_frame)
        if any(value is not None for value in blocked):
            raise InvalidPresentationValueError("blocked phases cannot contain a current input window")


def _result(value: SessionThrowSnapshot) -> ThrowResultViewModel:
    return ThrowResultViewModel(**value.__dict__)


def _regulation(match: MatchSnapshot) -> tuple[tuple[PlayerScoreViewModel, ...], tuple[StandingViewModel, ...], tuple[WinnerViewModel, ...]]:
    players = tuple(PlayerScoreViewModel(
        player.player_number, player.color,
        tuple(FrameScoreViewModel(frame.number, frame.rolls, frame.marks, frame.score, frame.cumulative_score, None, frame.complete) for frame in player.bowling.frames),
        player.confirmed_score, player.complete,
    ) for player in match.players)
    standings = tuple(StandingViewModel(row.rank, row.player_number, row.color, row.confirmed_score, row.provisional) for row in match.standings)
    winners = tuple(WinnerViewModel(player.player_number, player.color, player.confirmed_score) for player in match.winners)
    return players, standings, winners


def _cumulative(match: CumulativeMatchSnapshot) -> tuple[tuple[PlayerScoreViewModel, ...], tuple[StandingViewModel, ...], tuple[WinnerViewModel, ...]]:
    players = []
    for player in match.players:
        running = 0
        frames = []
        for frame in player.cumulative.frames:
            values = tuple(roll.points for roll in frame.rolls)
            running += frame.score
            frames.append(FrameScoreViewModel(frame.frame_number, values, tuple(str(value) for value in values), frame.score, running if frame.rolls else None, frame.maximum_score, frame.complete))
        players.append(PlayerScoreViewModel(player.player_number, player.color, tuple(frames), player.total_score, player.complete))
    standings = tuple(StandingViewModel(row.rank, row.player_number, row.color, row.total_score, row.provisional) for row in match.standings)
    winners = tuple(WinnerViewModel(player.player_number, player.color, player.total_score) for player in match.winners)
    return tuple(players), standings, winners


def _scoreboard(snapshot: SessionSnapshot) -> ScoreboardViewModel:
    config, match = snapshot.config, snapshot.match
    if config is None or match is None:
        raise InvalidPresentationValueError("a scoreboard requires configuration and match")
    if config.mode is Mode.TEN_PIN and type(match) is MatchSnapshot:
        players, standings, winners = _regulation(match)
        frame_count = 10
        underlying = (match.current_frame, match.current_player_number, match.current_player_color, match.current_roll)
    elif config.mode is not Mode.TEN_PIN and type(match) is CumulativeMatchSnapshot:
        players, standings, winners = _cumulative(match)
        frame_count = match.frame_count
        underlying = (match.current_global_frame_number, match.current_player_number, match.current_player_color, match.current_roll_number)
    else:
        raise InvalidPresentationValueError("match type is inconsistent with configured mode")
    if snapshot.phase is SessionPhase.AWAITING_THROW:
        focus = (snapshot.current_frame_number, snapshot.current_player_number, snapshot.current_player_color, snapshot.current_throw_number)
    elif snapshot.phase is SessionPhase.SHOWING_RESULT:
        if snapshot.last_throw is None:
            raise InvalidPresentationValueError("showing-result phase requires last_throw")
        throw = snapshot.last_throw
        focus = (throw.frame_number, throw.player_number, throw.player_color, throw.throw_number)
    elif snapshot.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION):
        focus = underlying
    else:
        focus = (None, None, None, None)
    return ScoreboardViewModel(LOCKED_BRANDING, snapshot.phase, config.mode, _MODE_LABELS[config.mode], config.theme, _THEME_LABELS[config.theme], match.active_player_count, frame_count, *focus, players, standings, winners, match.complete)


def build_presentation(snapshot: SessionSnapshot, capabilities: ApplicationCapabilities) -> PresentationBundle:
    """Detach a session and capability snapshot into immutable display models."""
    if type(snapshot) is not SessionSnapshot:
        raise InvalidPresentationValueError("snapshot must be an exact SessionSnapshot")
    if type(capabilities) is not ApplicationCapabilities:
        raise InvalidPresentationValueError("capabilities must be exact ApplicationCapabilities")
    try:
        _validate_snapshot(snapshot)
        prompt = _PROMPTS[snapshot.phase]
        config = snapshot.config
        if config is None:
            branding = mode = mode_label = theme = theme_label = None
        else:
            branding, mode, theme = LOCKED_BRANDING, config.mode, config.theme
            mode_label, theme_label = _MODE_LABELS[mode], _THEME_LABELS[theme]
        scoreboard = _scoreboard(snapshot) if snapshot.match is not None else None
        visible_result = snapshot.phase not in (SessionPhase.CONFIGURING, SessionPhase.READY, SessionPhase.AWAITING_THROW)
        result = _result(snapshot.last_throw) if visible_result and snapshot.last_throw is not None else None
        secondary = None
        main_scoreboard = None
        if scoreboard is None:
            placement = ScoreboardPlacement.NONE
        elif capabilities.secondary_display.available:
            placement = ScoreboardPlacement.SECONDARY
            secondary = SecondaryScoreboardViewModel(LOCKED_BRANDING, snapshot.phase, scoreboard)
        else:
            placement = ScoreboardPlacement.MAIN
            main_scoreboard = scoreboard
        main = MainDisplayViewModel(branding, snapshot.phase, prompt, mode, mode_label, theme, theme_label, snapshot.phase is SessionPhase.AWAITING_THROW, snapshot.current_frame_number, snapshot.current_player_number, snapshot.current_player_color, snapshot.current_throw_number, snapshot.current_available, snapshot.current_remix_object, snapshot.current_party_frame, result, main_scoreboard)
        return PresentationBundle(main, secondary, placement)
    except (AttributeError, KeyError, TypeError, IndexError) as exc:
        raise InvalidPresentationValueError("session snapshot is inconsistent") from exc
