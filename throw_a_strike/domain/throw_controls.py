"""Pure semantic controls for setting up exactly one bowling throw."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real

from .config import ControlStyle


class InvalidThrowControlError(ValueError):
    """Raised when a throw-control value or transition is invalid."""


class CurveLevel(str, Enum):
    LEFT_3 = "left_3"
    LEFT_2 = "left_2"
    LEFT_1 = "left_1"
    STRAIGHT = "straight"
    RIGHT_1 = "right_1"
    RIGHT_2 = "right_2"
    RIGHT_3 = "right_3"

    @property
    def label(self) -> str:
        return ("L3", "L2", "L1", "STR", "R1", "R2", "R3")[list(CurveLevel).index(self)]

    @property
    def strength(self) -> float:
        return (-1.0, -0.66, -0.33, 0.0, 0.33, 0.66, 1.0)[list(CurveLevel).index(self)]


class PowerFeedback(str, Enum):
    WEAK = "weak"
    GOOD = "good"
    PERFECT = "perfect"
    POWER = "power"
    OVERDRIVE = "overdrive"


class ThrowControlPhase(str, Enum):
    SET_CURVE = "set_curve"
    SET_POWER = "set_power"
    THROW_READY = "throw_ready"
    EARLY_DART_RECOVERY = "early_dart_recovery"
    COMPLETE = "complete"
    FOUL = "foul"


class ThrowControlCommandKind(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    BACK = "back"
    DART_HIT = "dart_hit"
    REARMED = "rearmed"
    TICK = "tick"


def _timestamp(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidThrowControlError(f"{name} must be a finite nonnegative real number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise InvalidThrowControlError(f"{name} must be a finite nonnegative real number")
    return normalized


def _exact_int(value: object, low: int, high: int, name: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise InvalidThrowControlError(f"{name} must be an integer from {low} to {high}")


def _feedback(power: int) -> PowerFeedback:
    return {40: PowerFeedback.WEAK, 50: PowerFeedback.WEAK,
            60: PowerFeedback.GOOD, 70: PowerFeedback.GOOD,
            80: PowerFeedback.PERFECT, 90: PowerFeedback.POWER,
            100: PowerFeedback.OVERDRIVE}[power]


@dataclass(frozen=True)
class ThrowControlCommand:
    kind: ThrowControlCommandKind
    timestamp: float
    dart_index: int | None = None
    x: int | None = None
    y: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ThrowControlCommandKind:
            raise InvalidThrowControlError("kind must be a ThrowControlCommandKind member")
        object.__setattr__(self, "timestamp", _timestamp(self.timestamp, "timestamp"))
        if self.kind is ThrowControlCommandKind.DART_HIT:
            _exact_int(self.dart_index, 0, 11, "dart_index")
            _exact_int(self.x, 0, 127, "x")
            _exact_int(self.y, 0, 127, "y")
        elif any(value is not None for value in (self.dart_index, self.x, self.y)):
            raise InvalidThrowControlError("non-dart commands cannot contain dart fields")


@dataclass(frozen=True)
class ThrowSetup:
    control_style: ControlStyle
    dart_index: int
    aim_x: int
    aim_y: int
    curve_level: CurveLevel
    power_percent: int

    def __post_init__(self) -> None:
        if type(self.control_style) is not ControlStyle:
            raise InvalidThrowControlError("control_style must be a ControlStyle member")
        _exact_int(self.dart_index, 0, 11, "dart_index")
        _exact_int(self.aim_x, 0, 127, "aim_x")
        _exact_int(self.aim_y, 0, 127, "aim_y")
        if type(self.curve_level) is not CurveLevel:
            raise InvalidThrowControlError("curve_level must be a CurveLevel member")
        if type(self.power_percent) is not int or self.power_percent not in _POWER_VALUES:
            raise InvalidThrowControlError("power_percent is invalid")

    @property
    def curve_strength(self) -> float:
        return self.curve_level.strength

    @property
    def power_feedback(self) -> PowerFeedback:
        return _feedback(self.power_percent)


class ThrowControlOutcomeKind(str, Enum):
    THROW = "throw"
    FOUL = "foul"


@dataclass(frozen=True)
class ThrowControlOutcome:
    kind: ThrowControlOutcomeKind
    setup: ThrowSetup | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ThrowControlOutcomeKind:
            raise InvalidThrowControlError("kind must be a ThrowControlOutcomeKind member")
        if self.kind is ThrowControlOutcomeKind.THROW:
            if type(self.setup) is not ThrowSetup:
                raise InvalidThrowControlError("THROW requires an exact ThrowSetup")
        elif self.setup is not None:
            raise InvalidThrowControlError("FOUL cannot contain a setup")


_POWER_VALUES = (40, 50, 60, 70, 80, 90, 100)
_METER = (70, 80, 90, 100, 90, 80, 70, 60, 50, 40, 50, 60)


@dataclass(frozen=True)
class ThrowControlSnapshot:
    control_style: ControlStyle
    phase: ThrowControlPhase
    curve_level: CurveLevel
    displayed_power_percent: int
    locked_power_percent: int | None
    power_feedback: PowerFeedback
    warning_active: bool
    recovery_return_phase: ThrowControlPhase | None
    outcome: ThrowControlOutcome | None

    def __post_init__(self) -> None:
        if type(self.control_style) is not ControlStyle or type(self.phase) is not ThrowControlPhase:
            raise InvalidThrowControlError("snapshot control style or phase is invalid")
        if type(self.curve_level) is not CurveLevel:
            raise InvalidThrowControlError("snapshot curve is invalid")
        if type(self.displayed_power_percent) is not int or self.displayed_power_percent not in _POWER_VALUES:
            raise InvalidThrowControlError("snapshot displayed power is invalid")
        if self.locked_power_percent is not None and (type(self.locked_power_percent) is not int or self.locked_power_percent not in _POWER_VALUES):
            raise InvalidThrowControlError("snapshot locked power is invalid")
        if type(self.power_feedback) is not PowerFeedback or self.power_feedback is not _feedback(self.displayed_power_percent):
            raise InvalidThrowControlError("snapshot feedback is inconsistent")
        if type(self.warning_active) is not bool:
            raise InvalidThrowControlError("snapshot warning must be boolean")
        if self.warning_active and self.phase is not ThrowControlPhase.THROW_READY:
            raise InvalidThrowControlError("warning is valid only while THROW READY")
        if self.phase is ThrowControlPhase.EARLY_DART_RECOVERY:
            if self.recovery_return_phase not in (ThrowControlPhase.SET_CURVE, ThrowControlPhase.SET_POWER) or self.outcome is not None:
                raise InvalidThrowControlError("recovery snapshot is inconsistent")
        elif self.recovery_return_phase is not None:
            raise InvalidThrowControlError("recovery return phase is invalid")
        if self.phase is ThrowControlPhase.COMPLETE:
            if type(self.outcome) is not ThrowControlOutcome or self.outcome.kind is not ThrowControlOutcomeKind.THROW:
                raise InvalidThrowControlError("complete snapshot requires a throw")
            setup = self.outcome.setup
            if (setup.control_style is not self.control_style
                    or setup.curve_level is not self.curve_level
                    or setup.power_percent != self.locked_power_percent
                    or self.displayed_power_percent != self.locked_power_percent):
                raise InvalidThrowControlError("complete snapshot does not match its setup")
        elif self.phase is ThrowControlPhase.FOUL:
            if type(self.outcome) is not ThrowControlOutcome or self.outcome.kind is not ThrowControlOutcomeKind.FOUL:
                raise InvalidThrowControlError("foul snapshot requires a foul")
        elif self.outcome is not None:
            raise InvalidThrowControlError("nonterminal snapshot cannot have an outcome")
        if self.phase is ThrowControlPhase.SET_CURVE and (self.control_style is not ControlStyle.ADVANCED or self.locked_power_percent is not None or self.displayed_power_percent != 70 or self.warning_active):
            raise InvalidThrowControlError("set-curve snapshot is inconsistent")
        if self.phase is ThrowControlPhase.SET_POWER and (self.control_style is not ControlStyle.ADVANCED or self.locked_power_percent is not None or self.warning_active):
            raise InvalidThrowControlError("set-power snapshot is inconsistent")
        if self.phase is ThrowControlPhase.EARLY_DART_RECOVERY and (self.control_style is not ControlStyle.ADVANCED or self.locked_power_percent is not None or self.warning_active):
            raise InvalidThrowControlError("recovery snapshot is inconsistent")
        if self.phase is ThrowControlPhase.THROW_READY and (self.locked_power_percent is None or self.displayed_power_percent != self.locked_power_percent):
            raise InvalidThrowControlError("ready snapshot is inconsistent")
        if self.control_style is ControlStyle.QUICK and self.phase is ThrowControlPhase.THROW_READY and (self.curve_level is not CurveLevel.STRAIGHT or self.locked_power_percent != 70):
            raise InvalidThrowControlError("Quick Play ready snapshot is inconsistent")


class ThrowControlMachine:
    def __init__(self, control_style: ControlStyle, started_at: float = 0.0):
        if type(control_style) is not ControlStyle:
            raise InvalidThrowControlError("control_style must be a ControlStyle member")
        start = _timestamp(started_at, "started_at")
        self._style = control_style
        self._phase = ThrowControlPhase.THROW_READY if control_style is ControlStyle.QUICK else ThrowControlPhase.SET_CURVE
        self._curve = CurveLevel.STRAIGHT
        self._displayed = 70
        self._locked = 70 if control_style is ControlStyle.QUICK else None
        self._warning = False
        self._recovery = None
        self._outcome = None
        self._phase_started = start
        self._last_timestamp = start

    @property
    def snapshot(self) -> ThrowControlSnapshot:
        return ThrowControlSnapshot(self._style, self._phase, self._curve, self._displayed,
                                    self._locked, _feedback(self._displayed), self._warning,
                                    self._recovery, self._outcome)

    def apply(self, command: ThrowControlCommand) -> ThrowControlSnapshot:
        if type(command) is not ThrowControlCommand:
            raise InvalidThrowControlError("command must be an exact ThrowControlCommand")
        if command.timestamp < self._last_timestamp:
            raise InvalidThrowControlError("command timestamps cannot move backward")
        self._advance(command.timestamp)
        self._last_timestamp = command.timestamp
        if self._phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL):
            return self.snapshot
        kind = command.kind
        if self._phase is ThrowControlPhase.EARLY_DART_RECOVERY:
            if kind is ThrowControlCommandKind.REARMED:
                self._phase = self._recovery
                self._recovery = None
                self._phase_started = command.timestamp
                self._displayed = 70
            return self.snapshot
        if self._phase is ThrowControlPhase.SET_CURVE:
            levels = list(CurveLevel)
            index = levels.index(self._curve)
            if kind is ThrowControlCommandKind.LEFT:
                self._curve = levels[max(0, index - 1)]
            elif kind is ThrowControlCommandKind.RIGHT:
                self._curve = levels[min(len(levels) - 1, index + 1)]
            elif kind is ThrowControlCommandKind.BACK:
                self._curve = CurveLevel.STRAIGHT
            elif kind is ThrowControlCommandKind.CONFIRM:
                self._enter_power(command.timestamp)
            elif kind is ThrowControlCommandKind.DART_HIT:
                self._enter_recovery(ThrowControlPhase.SET_CURVE)
        elif self._phase is ThrowControlPhase.SET_POWER:
            if kind is ThrowControlCommandKind.CONFIRM:
                self._locked = self._displayed
                self._enter_ready(command.timestamp)
            elif kind is ThrowControlCommandKind.BACK:
                self._phase = ThrowControlPhase.SET_CURVE
                self._locked = None
                self._displayed = 70
                self._phase_started = command.timestamp
            elif kind is ThrowControlCommandKind.DART_HIT:
                self._enter_recovery(ThrowControlPhase.SET_POWER)
        elif self._phase is ThrowControlPhase.THROW_READY:
            if kind is ThrowControlCommandKind.DART_HIT:
                setup = ThrowSetup(self._style, command.dart_index, command.x, command.y,
                                   self._curve, self._locked)  # type: ignore[arg-type]
                self._outcome = ThrowControlOutcome(ThrowControlOutcomeKind.THROW, setup)
                self._phase = ThrowControlPhase.COMPLETE
            elif kind is ThrowControlCommandKind.BACK and self._style is ControlStyle.ADVANCED:
                self._enter_power(command.timestamp)
        return self.snapshot

    def _enter_power(self, timestamp: float) -> None:
        self._phase = ThrowControlPhase.SET_POWER
        self._phase_started = timestamp
        self._displayed = 70
        self._locked = None
        self._warning = False

    def _enter_ready(self, timestamp: float) -> None:
        self._phase = ThrowControlPhase.THROW_READY
        self._phase_started = timestamp
        self._displayed = self._locked  # type: ignore[assignment]
        self._warning = False

    def _enter_recovery(self, phase: ThrowControlPhase) -> None:
        self._phase = ThrowControlPhase.EARLY_DART_RECOVERY
        self._recovery = phase
        self._warning = False

    def _advance(self, timestamp: float) -> None:
        while True:
            if self._phase is ThrowControlPhase.SET_CURVE and timestamp >= self._phase_started + 8.0:
                self._curve = CurveLevel.STRAIGHT
                self._enter_power(self._phase_started + 8.0)
                continue
            if self._phase is ThrowControlPhase.SET_POWER:
                deadline = self._phase_started + 8.0
                if timestamp >= deadline:
                    self._locked = 70
                    self._enter_ready(deadline)
                    continue
                steps = int((timestamp - self._phase_started + 1e-12) / 0.150)
                self._displayed = _METER[steps % len(_METER)]
            if self._phase is ThrowControlPhase.THROW_READY:
                elapsed = timestamp - self._phase_started
                if elapsed >= 60.0:
                    self._phase = ThrowControlPhase.FOUL
                    self._outcome = ThrowControlOutcome(ThrowControlOutcomeKind.FOUL)
                    self._warning = False
                    continue
                self._warning = elapsed >= 30.0
            return
