"""Pure two-throw bowling-round state."""

from dataclasses import dataclass
from enum import Enum, IntEnum


class InvalidBowlingRoundValueError(ValueError):
    """Raised when a bowling-round value violates its exact contract."""


class BowlingThrowNumber(IntEnum):
    THROW_ONE = 1
    THROW_TWO = 2


class BowlingThrowResultKind(str, Enum):
    GUTTER = "gutter"
    MISS = "miss"
    FIELD_GOAL = "field_goal"
    FOUL = "foul"
    PIN_HIT = "pin_hit"


FULL_RACK = tuple(range(1, 11))
_ZERO_KINDS = (BowlingThrowResultKind.GUTTER, BowlingThrowResultKind.MISS,
               BowlingThrowResultKind.FIELD_GOAL, BowlingThrowResultKind.FOUL)


def _pins(value: object, name: str) -> tuple[int, ...]:
    if type(value) is not tuple or any(type(pin) is not int for pin in value):
        raise InvalidBowlingRoundValueError(f"{name} must be an exact tuple of exact integers")
    if any(pin < 1 or pin > 10 for pin in value):
        raise InvalidBowlingRoundValueError(f"{name} pins must be within 1 through 10")
    if len(set(value)) != len(value):
        raise InvalidBowlingRoundValueError(f"{name} must not contain duplicates")
    if value != tuple(sorted(value)):
        raise InvalidBowlingRoundValueError(f"{name} must be in ascending order")
    return value


def _bounded_int(value: object, name: str, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise InvalidBowlingRoundValueError(f"{name} must be an exact integer from 0 through {maximum}")
    return value


@dataclass(frozen=True)
class BowlingThrowResult:
    kind: BowlingThrowResultKind
    pins_before: tuple[int, ...]
    pins_knocked_down: tuple[int, ...]
    pins_after: tuple[int, ...]
    dart_index: int | None
    aim_x: int | None
    aim_y: int | None

    def __post_init__(self) -> None:
        if type(self.kind) is not BowlingThrowResultKind:
            raise InvalidBowlingRoundValueError("kind must be an exact BowlingThrowResultKind")
        before = _pins(self.pins_before, "pins_before")
        knocked = _pins(self.pins_knocked_down, "pins_knocked_down")
        after = _pins(self.pins_after, "pins_after")
        if any(pin not in before for pin in knocked):
            raise InvalidBowlingRoundValueError("every knocked pin must have been standing")
        expected_after = tuple(pin for pin in before if pin not in knocked)
        if after != expected_after:
            raise InvalidBowlingRoundValueError("pins_after is inconsistent with pins_before and pins_knocked_down")
        if self.kind in _ZERO_KINDS:
            if knocked or after != before:
                raise InvalidBowlingRoundValueError("zero results must preserve the rack")
        elif not knocked:
            raise InvalidBowlingRoundValueError("PIN_HIT must knock down at least one pin")
        if self.kind is BowlingThrowResultKind.FOUL:
            if (self.dart_index, self.aim_x, self.aim_y) != (None, None, None):
                raise InvalidBowlingRoundValueError("FOUL cannot contain dart data")
        else:
            _bounded_int(self.dart_index, "dart_index", 11)
            _bounded_int(self.aim_x, "aim_x", 127)
            _bounded_int(self.aim_y, "aim_y", 127)


@dataclass(frozen=True)
class BowlingRoundSnapshot:
    throw_number: BowlingThrowNumber
    opening_rack: tuple[int, ...]
    standing_pins: tuple[int, ...]
    first_result: BowlingThrowResult | None
    second_result: BowlingThrowResult | None
    complete: bool

    def __post_init__(self) -> None:
        if type(self.throw_number) is not BowlingThrowNumber:
            raise InvalidBowlingRoundValueError("throw_number must be exact")
        _pins(self.opening_rack, "opening_rack")
        _pins(self.standing_pins, "standing_pins")
        if self.first_result is not None and type(self.first_result) is not BowlingThrowResult:
            raise InvalidBowlingRoundValueError("first_result must be exact or None")
        if self.second_result is not None and type(self.second_result) is not BowlingThrowResult:
            raise InvalidBowlingRoundValueError("second_result must be exact or None")
        if type(self.complete) is not bool:
            raise InvalidBowlingRoundValueError("complete must be an exact bool")
        if any(pin not in self.opening_rack for pin in self.standing_pins):
            raise InvalidBowlingRoundValueError("standing_pins must be a subset of opening_rack")

        initial = (
            self.throw_number is BowlingThrowNumber.THROW_ONE
            and self.first_result is None
            and self.second_result is None
            and not self.complete
            and self.standing_pins == self.opening_rack
        )
        after_first = (
            self.throw_number is BowlingThrowNumber.THROW_TWO
            and type(self.first_result) is BowlingThrowResult
            and self.second_result is None
            and not self.complete
            and self.first_result.pins_before == self.opening_rack
            and self.standing_pins == self.first_result.pins_after
        )
        complete = (
            self.throw_number is BowlingThrowNumber.THROW_TWO
            and type(self.first_result) is BowlingThrowResult
            and type(self.second_result) is BowlingThrowResult
            and self.complete
            and self.first_result.pins_before == self.opening_rack
            and self.second_result.pins_before == self.first_result.pins_after
            and self.standing_pins == self.second_result.pins_after
        )
        if not (initial or after_first or complete):
            raise InvalidBowlingRoundValueError("snapshot does not describe a continuous two-throw round")


class BowlingRoundMachine:
    def __init__(self, opening_rack: tuple[int, ...] = FULL_RACK):
        rack = _pins(opening_rack, "opening_rack")
        self._snapshot = BowlingRoundSnapshot(
            BowlingThrowNumber.THROW_ONE, rack, rack, None, None, False)

    @property
    def snapshot(self) -> BowlingRoundSnapshot:
        return self._snapshot

    def record_throw(self, result: BowlingThrowResult) -> BowlingRoundSnapshot:
        if type(result) is not BowlingThrowResult:
            raise InvalidBowlingRoundValueError("result must be an exact BowlingThrowResult")
        current = self._snapshot
        if current.complete:
            raise InvalidBowlingRoundValueError("the round is already complete")
        if result.pins_before != current.standing_pins:
            raise InvalidBowlingRoundValueError("result pins_before must equal the standing rack")
        if current.throw_number is BowlingThrowNumber.THROW_ONE:
            self._snapshot = BowlingRoundSnapshot(BowlingThrowNumber.THROW_TWO,
                current.opening_rack, result.pins_after, result, None, False)
        else:
            self._snapshot = BowlingRoundSnapshot(BowlingThrowNumber.THROW_TWO,
                current.opening_rack, result.pins_after, current.first_result, result, True)
        return self._snapshot


__all__ = ("InvalidBowlingRoundValueError", "BowlingThrowNumber", "BowlingThrowResultKind",
           "BowlingThrowResult", "BowlingRoundSnapshot", "BowlingRoundMachine")
