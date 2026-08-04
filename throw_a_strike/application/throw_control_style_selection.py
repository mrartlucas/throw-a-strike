"""Pure, finite control-style selection for the emulator harness."""

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real

from throw_a_strike.domain import ControlStyle, ThrowControlCommandKind
from .ports import InputEvent
from .throw_control_input import interpret_throw_control_events

__all__ = ("InvalidThrowControlStyleSelectionValueError", "ThrowControlStyleSelectionPhase",
           "ThrowControlStyleSelectionSnapshot", "ThrowControlStyleSelector")


class InvalidThrowControlStyleSelectionValueError(ValueError):
    pass


def _timestamp(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidThrowControlStyleSelectionValueError(f"{name} must be a finite nonnegative real")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise InvalidThrowControlStyleSelectionValueError(f"{name} must be a finite nonnegative real")
    return result


class ThrowControlStyleSelectionPhase(str, Enum):
    SELECTING = "selecting"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class ThrowControlStyleSelectionSnapshot:
    phase: ThrowControlStyleSelectionPhase
    selected_style: ControlStyle
    started_at: float
    confirmed_at: float | None
    timed_out: bool

    def __post_init__(self) -> None:
        if type(self.phase) is not ThrowControlStyleSelectionPhase or type(self.selected_style) is not ControlStyle:
            raise InvalidThrowControlStyleSelectionValueError("phase and selected_style require exact enum members")
        start = _timestamp(self.started_at, "started_at")
        confirmed = None if self.confirmed_at is None else _timestamp(self.confirmed_at, "confirmed_at")
        if type(self.timed_out) is not bool:
            raise InvalidThrowControlStyleSelectionValueError("timed_out must be an exact bool")
        if (self.phase is ThrowControlStyleSelectionPhase.CONFIRMED) != (confirmed is not None):
            raise InvalidThrowControlStyleSelectionValueError("phase and confirmed_at are inconsistent")
        if confirmed is not None and confirmed < start:
            raise InvalidThrowControlStyleSelectionValueError("confirmed_at cannot precede started_at")
        if self.timed_out and (confirmed != start + 15.0 or self.selected_style is not ControlStyle.QUICK):
            raise InvalidThrowControlStyleSelectionValueError("timeout confirmation is inconsistent")
        if self.phase is ThrowControlStyleSelectionPhase.SELECTING and self.timed_out:
            raise InvalidThrowControlStyleSelectionValueError("selecting cannot be timed out")
        object.__setattr__(self, "started_at", start)
        object.__setattr__(self, "confirmed_at", confirmed)

    @property
    def confirmed(self) -> bool:
        return self.phase is ThrowControlStyleSelectionPhase.CONFIRMED


class ThrowControlStyleSelector:
    def __init__(self, started_at: float):
        start = _timestamp(started_at, "started_at")
        self.__snapshot = ThrowControlStyleSelectionSnapshot(
            ThrowControlStyleSelectionPhase.SELECTING, ControlStyle.QUICK, start, None, False)

    @property
    def snapshot(self) -> ThrowControlStyleSelectionSnapshot:
        return self.__snapshot

    def apply(self, events: tuple[InputEvent, ...], now: float) -> ThrowControlStyleSelectionSnapshot:
        if self.__snapshot.confirmed:
            return self.__snapshot
        current = _timestamp(now, "now")
        if current < self.__snapshot.started_at:
            raise InvalidThrowControlStyleSelectionValueError("now cannot precede started_at")
        if current >= self.__snapshot.started_at + 15.0:
            self.__snapshot = ThrowControlStyleSelectionSnapshot(
                ThrowControlStyleSelectionPhase.CONFIRMED, ControlStyle.QUICK,
                self.__snapshot.started_at, self.__snapshot.started_at + 15.0, True)
            return self.__snapshot
        try:
            commands = interpret_throw_control_events(events)
        except (TypeError, ValueError) as exc:
            raise InvalidThrowControlStyleSelectionValueError("events are invalid") from exc
        selected = self.__snapshot.selected_style
        for command in commands:
            if command.kind is ThrowControlCommandKind.LEFT:
                selected = ControlStyle.QUICK
            elif command.kind is ThrowControlCommandKind.RIGHT:
                selected = ControlStyle.ADVANCED
            elif command.kind is ThrowControlCommandKind.CONFIRM:
                self.__snapshot = ThrowControlStyleSelectionSnapshot(
                    ThrowControlStyleSelectionPhase.CONFIRMED, selected,
                    self.__snapshot.started_at, command.timestamp, False)
                return self.__snapshot
        self.__snapshot = ThrowControlStyleSelectionSnapshot(
            ThrowControlStyleSelectionPhase.SELECTING, selected, self.__snapshot.started_at, None, False)
        return self.__snapshot
