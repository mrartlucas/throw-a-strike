"""Shared emulator runtime validation and active-player input policies."""
import math
from numbers import Real

from throw_a_strike.application import InputEventKind, InvalidPortValueError
from throw_a_strike.domain import is_emulator_dart_for_player, player_color_for_number


def nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidPortValueError(f"{name} must be finite nonnegative")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise InvalidPortValueError(f"{name} must be finite nonnegative")
    return result


class PlayerColorInputPort:
    """Forward controls and the first dart belonging to the active player."""

    def __init__(self, source, active_player_number):
        self.source = source
        player_color_for_number(active_player_number)
        self.active_player_number = active_player_number
        self.wrong_event = None

    @property
    def capabilities(self):
        return self.source.capabilities

    def poll(self):
        events = self.source.poll()
        self.wrong_event = None
        chosen = None
        for event in events:
            if event.kind is InputEventKind.DART_HIT:
                if is_emulator_dart_for_player(self.active_player_number, event.dart_index):
                    if chosen is None:
                        chosen = event
                elif self.wrong_event is None:
                    self.wrong_event = event
        if chosen is not None:
            self.wrong_event = None
            return tuple(
                event for event in events
                if event.kind is not InputEventKind.DART_HIT or event is chosen
            )
        return tuple(event for event in events if event.kind is not InputEventKind.DART_HIT)


def update_throw_ready_started_at(control_style, before_phase, commands, current_started_at):
    """Return the ready-start timestamp produced by actual phase transitions."""
    from throw_a_strike.domain import ControlStyle, ThrowControlCommandKind, ThrowControlPhase, THROW_FOUL_SECONDS
    if type(control_style) is not ControlStyle or type(before_phase) is not ThrowControlPhase:
        raise InvalidPortValueError("invalid throw-ready tracking state")
    phase = before_phase
    ready_started_at = current_started_at
    for command in commands:
        if phase is ThrowControlPhase.THROW_READY and ready_started_at is not None and command.timestamp >= ready_started_at + THROW_FOUL_SECONDS:
            phase = ThrowControlPhase.FOUL
        if phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL, ThrowControlPhase.EARLY_DART_RECOVERY):
            continue
        kind = command.kind
        if phase is ThrowControlPhase.SET_CURVE:
            if kind is ThrowControlCommandKind.CONFIRM:
                phase = ThrowControlPhase.SET_POWER
                ready_started_at = None
            elif kind is ThrowControlCommandKind.DART_HIT:
                phase = ThrowControlPhase.EARLY_DART_RECOVERY
        elif phase is ThrowControlPhase.SET_POWER:
            if kind is ThrowControlCommandKind.CONFIRM:
                phase = ThrowControlPhase.THROW_READY
                ready_started_at = command.timestamp
            elif kind is ThrowControlCommandKind.BACK:
                phase = ThrowControlPhase.SET_CURVE
                ready_started_at = None
            elif kind is ThrowControlCommandKind.DART_HIT:
                phase = ThrowControlPhase.EARLY_DART_RECOVERY
        elif phase is ThrowControlPhase.THROW_READY:
            if kind is ThrowControlCommandKind.BACK and control_style is ControlStyle.ADVANCED:
                phase = ThrowControlPhase.SET_POWER
                ready_started_at = None
            elif kind is ThrowControlCommandKind.DART_HIT:
                phase = ThrowControlPhase.COMPLETE
    return ready_started_at
