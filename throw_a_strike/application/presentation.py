"""Pure, dimension-independent presentation projections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.config import BrandingSnapshot, LOCKED_BRANDING, Mode, Theme
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


@dataclass(frozen=True)
class StandingViewModel:
    rank: int
    player_number: int
    color: PlayerColor
    total_score: int
    provisional: bool


@dataclass(frozen=True)
class WinnerViewModel:
    player_number: int
    color: PlayerColor
    total_score: int


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


@dataclass(frozen=True)
class SecondaryScoreboardViewModel:
    branding: BrandingSnapshot
    phase: SessionPhase
    scoreboard: ScoreboardViewModel


@dataclass(frozen=True)
class PresentationBundle:
    main: MainDisplayViewModel
    secondary: SecondaryScoreboardViewModel | None
    scoreboard_placement: ScoreboardPlacement


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
