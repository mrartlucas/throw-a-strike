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
