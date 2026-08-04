"""Explicit-step coordination for one hardware-independent bowling attempt.

``started_at``, every ``InputEvent.timestamp``, and values returned by
``ClockPort.monotonic_seconds()`` must share one monotonic time domain.  This
module deliberately does not adjust, clamp, or reorder those values.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real

from .ports import ClockPort, InputEvent, InputPort, PortCapabilities
from .throw_control_input import (
    InvalidThrowControlInputError,
    interpret_throw_control_events,
)
from throw_a_strike.domain import (
    ControlStyle,
    InvalidThrowControlError,
    ThrowControlCommand,
    ThrowControlCommandKind,
    ThrowControlMachine,
    ThrowControlPhase,
    ThrowControlSnapshot,
)

__all__ = (
    "InvalidThrowControlCoordinatorValueError",
    "ThrowControlCoordinatorStage",
    "ThrowControlStepResult",
    "ThrowControlCoordinatorStepError",
    "ThrowControlCoordinatorTerminalError",
    "ThrowControlCoordinator",
)


class InvalidThrowControlCoordinatorValueError(ValueError):
    """Raised when a public coordinator value violates its contract."""


class ThrowControlCoordinatorStage(str, Enum):
    POLL_INPUT = "poll_input"
    INTERPRET_INPUT = "interpret_input"
    APPLY_INPUT = "apply_input"
    READ_CLOCK = "read_clock"
    APPLY_TICK = "apply_tick"


def _event_tuple(value: object) -> None:
    if type(value) is not tuple or any(type(item) is not InputEvent for item in value):
        raise InvalidThrowControlCoordinatorValueError(
            "events must be an exact tuple of exact InputEvent values"
        )


def _command_tuple(value: object) -> None:
    if type(value) is not tuple or any(
        type(item) is not ThrowControlCommand for item in value
    ):
        raise InvalidThrowControlCoordinatorValueError(
            "commands must be an exact tuple of exact ThrowControlCommand values"
        )


def _tick_timestamp(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidThrowControlCoordinatorValueError(
            "tick_timestamp must be None or a finite nonnegative real number"
        )
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        raise InvalidThrowControlCoordinatorValueError(
            "tick_timestamp must be None or a finite nonnegative real number"
        ) from None
    if not isfinite(normalized) or normalized < 0.0:
        raise InvalidThrowControlCoordinatorValueError(
            "tick_timestamp must be None or a finite nonnegative real number"
        )
    return normalized


def _snapshot(value: object) -> None:
    if type(value) is not ThrowControlSnapshot:
        raise InvalidThrowControlCoordinatorValueError(
            "snapshot must be an exact ThrowControlSnapshot"
        )


def _terminal(snapshot: ThrowControlSnapshot) -> bool:
    return snapshot.phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL)


@dataclass(frozen=True)
class ThrowControlStepResult:
    events: tuple[InputEvent, ...]
    commands: tuple[ThrowControlCommand, ...]
    applied_command_count: int
    tick_timestamp: float | None
    snapshot: ThrowControlSnapshot

    def __post_init__(self) -> None:
        _event_tuple(self.events)
        _command_tuple(self.commands)
        if type(self.applied_command_count) is not int:
            raise InvalidThrowControlCoordinatorValueError(
                "applied_command_count must be an exact integer"
            )
        if self.applied_command_count != len(self.commands):
            raise InvalidThrowControlCoordinatorValueError(
                "successful results must apply every input command"
            )
        normalized = _tick_timestamp(self.tick_timestamp)
        _snapshot(self.snapshot)
        if normalized is None and not _terminal(self.snapshot):
            raise InvalidThrowControlCoordinatorValueError(
                "a result without a tick must have a terminal snapshot"
            )
        object.__setattr__(self, "tick_timestamp", normalized)

    @property
    def terminal(self) -> bool:
        return _terminal(self.snapshot)


class ThrowControlCoordinatorStepError(RuntimeError):
    """An operational failure retaining the exact nontransactional progress."""

    def __init__(
        self,
        stage: ThrowControlCoordinatorStage,
        events: tuple[InputEvent, ...],
        commands: tuple[ThrowControlCommand, ...],
        applied_command_count: int,
        tick_timestamp: float | None,
        snapshot: ThrowControlSnapshot,
        cause: Exception,
    ) -> None:
        if type(stage) is not ThrowControlCoordinatorStage:
            raise InvalidThrowControlCoordinatorValueError(
                "stage must be an exact ThrowControlCoordinatorStage"
            )
        _event_tuple(events)
        _command_tuple(commands)
        if (
            type(applied_command_count) is not int
            or not 0 <= applied_command_count <= len(commands)
        ):
            raise InvalidThrowControlCoordinatorValueError(
                "applied_command_count must be an exact integer within commands"
            )
        normalized = _tick_timestamp(tick_timestamp)
        _snapshot(snapshot)
        if not isinstance(cause, Exception):
            raise InvalidThrowControlCoordinatorValueError(
                "cause must be an Exception"
            )
        empty_progress = not events and not commands and applied_command_count == 0
        consistent = {
            ThrowControlCoordinatorStage.POLL_INPUT: empty_progress and normalized is None,
            ThrowControlCoordinatorStage.INTERPRET_INPUT: (
                not commands and applied_command_count == 0 and normalized is None
            ),
            ThrowControlCoordinatorStage.APPLY_INPUT: normalized is None,
            ThrowControlCoordinatorStage.READ_CLOCK: (
                applied_command_count == len(commands) and normalized is None
            ),
            ThrowControlCoordinatorStage.APPLY_TICK: applied_command_count == len(commands),
        }[stage]
        if not consistent:
            raise InvalidThrowControlCoordinatorValueError(
                f"progress is inconsistent with stage {stage.value}"
            )
        self._stage = stage
        self._events = events
        self._commands = commands
        self._applied_command_count = applied_command_count
        self._tick_timestamp = normalized
        self._snapshot = snapshot
        self._cause = cause
        super().__init__(f"throw-control step failed during {stage.value}")

    @property
    def stage(self) -> ThrowControlCoordinatorStage:
        return self._stage

    @property
    def events(self) -> tuple[InputEvent, ...]:
        return self._events

    @property
    def commands(self) -> tuple[ThrowControlCommand, ...]:
        return self._commands

    @property
    def applied_command_count(self) -> int:
        return self._applied_command_count

    @property
    def tick_timestamp(self) -> float | None:
        return self._tick_timestamp

    @property
    def snapshot(self) -> ThrowControlSnapshot:
        return self._snapshot

    @property
    def cause(self) -> Exception:
        return self._cause


class ThrowControlCoordinatorTerminalError(RuntimeError):
    """Raised before polling an already terminal one-attempt coordinator."""

    def __init__(self, snapshot: ThrowControlSnapshot) -> None:
        _snapshot(snapshot)
        if not _terminal(snapshot):
            raise InvalidThrowControlCoordinatorValueError(
                "terminal error snapshot must be COMPLETE or FOUL"
            )
        self._snapshot = snapshot
        super().__init__("throw-control attempt is already terminal")

    @property
    def snapshot(self) -> ThrowControlSnapshot:
        return self._snapshot


class ThrowControlCoordinator:
    """Own one machine and advance it only through explicit finite steps."""

    def __init__(
        self,
        control_style: ControlStyle,
        input_port: InputPort,
        clock_port: ClockPort,
        started_at: float,
    ) -> None:
        if type(control_style) is not ControlStyle:
            raise InvalidThrowControlCoordinatorValueError(
                "control_style must be an exact ControlStyle"
            )
        self._input_port = self._validated_port(
            input_port, InputPort, "input_port"
        )
        self._clock_port = self._validated_port(
            clock_port, ClockPort, "clock_port"
        )
        try:
            self._machine = ThrowControlMachine(control_style, started_at)
        except InvalidThrowControlError as error:
            raise InvalidThrowControlCoordinatorValueError(
                "started_at is invalid"
            ) from error

    @staticmethod
    def _validated_port(port: object, protocol: type, name: str):
        if port is None or isinstance(port, type):
            raise InvalidThrowControlCoordinatorValueError(
                f"{name} must be a port instance"
            )
        try:
            valid = isinstance(port, protocol)
            capabilities = port.capabilities if valid else None
        except Exception as error:
            raise InvalidThrowControlCoordinatorValueError(
                f"{name} structure or capabilities are invalid"
            ) from error
        if not valid or type(capabilities) is not PortCapabilities:
            raise InvalidThrowControlCoordinatorValueError(
                f"{name} must satisfy its protocol with exact PortCapabilities"
            )
        return port

    @property
    def snapshot(self) -> ThrowControlSnapshot:
        return self._machine.snapshot

    def step(self) -> ThrowControlStepResult:
        current = self.snapshot
        if _terminal(current):
            raise ThrowControlCoordinatorTerminalError(current)

        try:
            polled = self._input_port.poll()
        except Exception as error:
            raise ThrowControlCoordinatorStepError(
                ThrowControlCoordinatorStage.POLL_INPUT,
                (), (), 0, None, self.snapshot, error,
            ) from error

        try:
            commands = interpret_throw_control_events(polled)
        except InvalidThrowControlInputError as error:
            events = polled if (
                type(polled) is tuple
                and all(type(event) is InputEvent for event in polled)
            ) else ()
            raise ThrowControlCoordinatorStepError(
                ThrowControlCoordinatorStage.INTERPRET_INPUT,
                events, (), 0, None, self.snapshot, error,
            ) from error
        events = polled

        applied = 0
        for command in commands:
            try:
                self._machine.apply(command)
            except InvalidThrowControlError as error:
                raise ThrowControlCoordinatorStepError(
                    ThrowControlCoordinatorStage.APPLY_INPUT,
                    events, commands, applied, None, self.snapshot, error,
                ) from error
            applied += 1

        after_input = self.snapshot
        if _terminal(after_input):
            return ThrowControlStepResult(
                events, commands, applied, None, after_input
            )

        try:
            clock_value = self._clock_port.monotonic_seconds()
        except Exception as error:
            raise ThrowControlCoordinatorStepError(
                ThrowControlCoordinatorStage.READ_CLOCK,
                events, commands, applied, None, self.snapshot, error,
            ) from error

        tick_timestamp = None
        try:
            tick = ThrowControlCommand(ThrowControlCommandKind.TICK, clock_value)
            tick_timestamp = tick.timestamp
            final_snapshot = self._machine.apply(tick)
        except InvalidThrowControlError as error:
            raise ThrowControlCoordinatorStepError(
                ThrowControlCoordinatorStage.APPLY_TICK,
                events, commands, applied, tick_timestamp, self.snapshot, error,
            ) from error
        return ThrowControlStepResult(
            events, commands, applied, tick_timestamp, final_snapshot
        )
