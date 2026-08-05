"""Deterministic regulation ten-pin presentation events."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real

from .ports import InvalidPortValueError
from .session import SessionSnapshot, SessionPhase
from ..domain.bowling_round import BowlingThrowResultKind
from ..domain.pinfall import PIN_CENTERS

THROW_READY_HOLD_SECONDS = 1.5
RESULT_HOLD_SECONDS = 1.5

class RegulationPresentationEventKind(str, Enum):
    THROW_READY = "throw_ready"
    STRIKE = "strike"
    SPARE = "spare"
    SPLIT = "split"
    SPLIT_CONVERTED = "split_converted"
    FIELD_GOAL = "field_goal"
    GUTTER = "gutter"
    MISS = "miss"
    FOUL = "foul"
    TURKEY = "turkey"
    GAME_OVER = "game_over"
    WINNER = "winner"

_EVENT_LABELS = {
    RegulationPresentationEventKind.THROW_READY: "THROW READY",
    RegulationPresentationEventKind.STRIKE: "STRIKE",
    RegulationPresentationEventKind.SPARE: "SPARE",
    RegulationPresentationEventKind.SPLIT: "SPLIT",
    RegulationPresentationEventKind.SPLIT_CONVERTED: "SPLIT CONVERTED",
    RegulationPresentationEventKind.FIELD_GOAL: "FIELD GOAL",
    RegulationPresentationEventKind.GUTTER: "GUTTER",
    RegulationPresentationEventKind.MISS: "MISS",
    RegulationPresentationEventKind.FOUL: "FOUL",
    RegulationPresentationEventKind.TURKEY: "TURKEY",
    RegulationPresentationEventKind.GAME_OVER: "GAME OVER",
    RegulationPresentationEventKind.WINNER: "WINNER",
}

def event_label(kind: RegulationPresentationEventKind) -> str:
    if type(kind) is not RegulationPresentationEventKind:
        raise InvalidPortValueError("kind must be exact RegulationPresentationEventKind")
    return _EVENT_LABELS[kind]

def _time(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidPortValueError(f"{name} must be a finite nonnegative time")
    value = float(value)
    if not isfinite(value) or value < 0:
        raise InvalidPortValueError(f"{name} must be a finite nonnegative time")
    return value

def _opt_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise InvalidPortValueError(f"{name} must be a positive exact int or None")
    return value

def is_split_leave(pins_after: tuple[int, ...], pins_before: tuple[int, ...]) -> bool:
    if type(pins_after) is not tuple or type(pins_before) is not tuple:
        raise InvalidPortValueError("split rack values must be exact tuples")
    if 1 in pins_after or 1 not in pins_before or len(pins_after) < 2:
        return False
    remaining = set(pins_after)
    groups = 0
    while remaining:
        groups += 1
        stack = [remaining.pop()]
        while stack:
            pin = stack.pop(); x, y = PIN_CENTERS[pin]
            connected = {other for other in remaining if (PIN_CENTERS[other][0] - x) ** 2 + (PIN_CENTERS[other][1] - y) ** 2 <= 23 ** 2}
            remaining.difference_update(connected); stack.extend(connected)
    return groups > 1

@dataclass(frozen=True)
class RegulationPresentationEvent:
    kind: RegulationPresentationEventKind
    started_at: float
    deadline: float
    frame_number: int | None = None
    roll_number: int | None = None
    result_label: str | None = None
    score: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not RegulationPresentationEventKind:
            raise InvalidPortValueError("kind must be exact RegulationPresentationEventKind")
        start = _time(self.started_at, "started_at")
        deadline = _time(self.deadline, "deadline")
        if deadline < start:
            raise InvalidPortValueError("deadline must not precede started_at")
        object.__setattr__(self, "started_at", start)
        object.__setattr__(self, "deadline", deadline)
        frame = _opt_int(self.frame_number, "frame_number")
        roll = _opt_int(self.roll_number, "roll_number")
        object.__setattr__(self, "frame_number", frame)
        object.__setattr__(self, "roll_number", roll)
        if self.result_label is not None and (type(self.result_label) is not str or not self.result_label):
            raise InvalidPortValueError("result_label must be a non-empty exact str or None")
        if self.score is not None and type(self.score) is not int:
            raise InvalidPortValueError("score must be exact int or None")

    @property
    def label(self) -> str:
        return self.result_label or event_label(self.kind)

@dataclass(frozen=True)
class RegulationPresentationViewModel:
    label: str | None
    visible: bool
    kind: RegulationPresentationEventKind | None = None

class RegulationPresentationTimeline:
    def __init__(self) -> None:
        self._events: list[RegulationPresentationEvent] = []
        self._active_ready: RegulationPresentationEvent | None = None
        self._active_result: RegulationPresentationEvent | None = None
        self._terminal_event: RegulationPresentationEvent | None = None
        self._game_over_emitted = False
        self._ack_keys: set[tuple[int, int, str]] = set()
        self._strike_streak = 0
        self._pending_split_frames: set[int] = set()

    @property
    def events(self) -> tuple[RegulationPresentationEvent, ...]:
        return tuple(self._events)

    def active_event(self, now: float) -> RegulationPresentationEvent | None:
        now = _time(now, "now")
        if self._terminal_event is not None:
            return self._terminal_event
        for event in reversed(self._events):
            if event.kind is not RegulationPresentationEventKind.THROW_READY and event.started_at <= now < event.deadline:
                return event
        event = self._active_ready
        return event if event is not None and now < event.deadline else None

    def view_model(self, now: float) -> RegulationPresentationViewModel:
        event = self.active_event(now)
        return RegulationPresentationViewModel(None, False) if event is None else RegulationPresentationViewModel(event.label, True, event.kind)

    def throw_ready(self, started_at: float, *, frame_number: int | None = None, roll_number: int | None = None) -> RegulationPresentationEvent:
        started_at = _time(started_at, "started_at")
        event = RegulationPresentationEvent(RegulationPresentationEventKind.THROW_READY, started_at, started_at + THROW_READY_HOLD_SECONDS, frame_number, roll_number)
        self._events.append(event); self._active_ready = event; self._active_result = None
        return event

    def cancel_throw_ready(self) -> None:
        self._active_ready = None

    def acknowledge_result(self, snapshot: SessionSnapshot, kind: BowlingThrowResultKind, started_at: float, *, pins_before: tuple[int, ...] = (), pins_after: tuple[int, ...] = ()) -> tuple[RegulationPresentationEvent, ...]:
        if type(snapshot) is not SessionSnapshot or snapshot.last_throw is None:
            raise InvalidPortValueError("snapshot must contain a last throw")
        if type(kind) is not BowlingThrowResultKind:
            raise InvalidPortValueError("kind must be exact BowlingThrowResultKind")
        throw = snapshot.last_throw
        marks = snapshot.match.players[0].bowling.frames[throw.frame_number - 1].marks
        mark = marks[-1] if marks else ""
        event_kind = None
        if mark == "X":
            event_kind = RegulationPresentationEventKind.STRIKE
        elif mark == "/":
            event_kind = RegulationPresentationEventKind.SPLIT_CONVERTED if throw.frame_number in self._pending_split_frames and throw.available_after == 0 else RegulationPresentationEventKind.SPARE
        elif kind is BowlingThrowResultKind.FIELD_GOAL:
            event_kind = RegulationPresentationEventKind.FIELD_GOAL
        elif kind is BowlingThrowResultKind.GUTTER:
            event_kind = RegulationPresentationEventKind.GUTTER
        elif kind is BowlingThrowResultKind.FOUL:
            event_kind = RegulationPresentationEventKind.FOUL
        elif kind is BowlingThrowResultKind.MISS:
            event_kind = RegulationPresentationEventKind.MISS
        elif kind is BowlingThrowResultKind.PIN_HIT and throw.throw_number == 1 and is_split_leave(pins_after, pins_before):
            event_kind = RegulationPresentationEventKind.SPLIT
        if event_kind is RegulationPresentationEventKind.SPLIT:
            self._pending_split_frames.add(throw.frame_number)
        elif throw.available_after == 0 or throw.turn_ended:
            self._pending_split_frames.discard(throw.frame_number)
        events = []
        if event_kind is not None:
            key = (throw.frame_number, throw.throw_number, event_kind.value)
            if key not in self._ack_keys:
                self._ack_keys.add(key)
                label = event_label(event_kind)
                event = RegulationPresentationEvent(event_kind, started_at, started_at + RESULT_HOLD_SECONDS, throw.frame_number, throw.throw_number, label, snapshot.match.players[0].bowling.confirmed_score)
                self._events.append(event); events.append(event); self._active_result = event
        if event_kind is RegulationPresentationEventKind.STRIKE:
            self._strike_streak += 1
        else:
            self._strike_streak = 0
        if self._strike_streak == 3:
            key = (throw.frame_number, throw.throw_number, RegulationPresentationEventKind.TURKEY.value)
            if key not in self._ack_keys:
                self._ack_keys.add(key)
                turkey_started_at = started_at + RESULT_HOLD_SECONDS
                turkey = RegulationPresentationEvent(RegulationPresentationEventKind.TURKEY, turkey_started_at, turkey_started_at + RESULT_HOLD_SECONDS, throw.frame_number, throw.throw_number, event_label(RegulationPresentationEventKind.TURKEY), snapshot.match.players[0].bowling.confirmed_score)
                self._events.append(turkey); events.append(turkey)
        self.cancel_throw_ready()
        return tuple(events)

    def observe_game_over(self, snapshot: SessionSnapshot, started_at: float) -> tuple[RegulationPresentationEvent, ...]:
        if type(snapshot) is not SessionSnapshot:
            raise InvalidPortValueError("snapshot must be exact SessionSnapshot")
        if snapshot.phase is not SessionPhase.GAME_OVER or self._game_over_emitted:
            return ()
        self.cancel_throw_ready(); self._active_result = None; self._game_over_emitted = True
        score = None if snapshot.match is None else snapshot.match.players[0].bowling.confirmed_score
        event = RegulationPresentationEvent(RegulationPresentationEventKind.GAME_OVER, started_at, started_at + RESULT_HOLD_SECONDS, result_label="GAME OVER", score=score)
        self._events.append(event); self._terminal_event = event; return (event,)
