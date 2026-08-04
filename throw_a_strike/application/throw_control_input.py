"""Pure translation from neutral input events to throw-control commands.

``InputEvent.sequence`` describes the order of the transport stream.  The
interpreter therefore consumes events in the caller's order, but does not copy
sequence values into semantic commands (which intentionally have no sequence
field).
"""

from .ports import InputEvent as _InputEvent
from .ports import InputEventKind as _InputEventKind
from throw_a_strike.domain import (
    InvalidThrowControlError as _InvalidThrowControlError,
    ThrowControlCommand as _ThrowControlCommand,
    ThrowControlCommandKind as _ThrowControlCommandKind,
)

__all__ = (
    "InvalidThrowControlInputError",
    "interpret_throw_control_event",
    "interpret_throw_control_events",
)


class InvalidThrowControlInputError(ValueError):
    """Raised when input cannot be translated under the command contract."""


_CONTROL_KINDS = {
    "btn_left": _ThrowControlCommandKind.LEFT,
    "btn_right": _ThrowControlCommandKind.RIGHT,
    "btn_a": _ThrowControlCommandKind.CONFIRM,
    "btn_b": _ThrowControlCommandKind.BACK,
}


def _integral_coordinate(value: float, name: str) -> int:
    if not value.is_integer():
        raise InvalidThrowControlInputError(f"{name} must be mathematically integral")
    try:
        return int(value)
    except Exception as exc:
        raise InvalidThrowControlInputError(
            f"integer conversion of {name} failed"
        ) from exc


def interpret_throw_control_event(
    event: _InputEvent,
) -> _ThrowControlCommand | None:
    """Translate one exact neutral event, or ignore an unmapped control."""
    if type(event) is not _InputEvent:
        raise InvalidThrowControlInputError("event must be an exact InputEvent")

    if event.kind is _InputEventKind.CONTROL:
        command_kind = _CONTROL_KINDS.get(event.control_id)
        if command_kind is None:
            return None
        return _ThrowControlCommand(command_kind, event.timestamp)

    x = _integral_coordinate(event.x, "x")
    y = _integral_coordinate(event.y, "y")
    try:
        return _ThrowControlCommand(
            _ThrowControlCommandKind.DART_HIT,
            event.timestamp,
            dart_index=event.dart_index,
            x=x,
            y=y,
        )
    except _InvalidThrowControlError as exc:
        raise InvalidThrowControlInputError(
            "dart event cannot satisfy ThrowControlCommand"
        ) from exc


def interpret_throw_control_events(
    events: tuple[_InputEvent, ...],
) -> tuple[_ThrowControlCommand, ...]:
    """Translate a finite batch in supplied order, omitting ignored controls."""
    if type(events) is not tuple:
        raise InvalidThrowControlInputError("events must be an exact tuple")
    if any(type(event) is not _InputEvent for event in events):
        raise InvalidThrowControlInputError(
            "every batch item must be an exact InputEvent"
        )

    commands = []
    for event in events:
        command = interpret_throw_control_event(event)
        if command is not None:
            commands.append(command)
    return tuple(commands)
