"""Neutral, explicitly-polled Dartsnut input adapter.

Each batch is composed deterministically with all dart hits before all buttons.
This composition is not a claim about physical ordering across the two SDK
sources. Source reads are nontransactional: a later read or clock failure does
not roll back already-consumed SDK batches.
"""

from throw_a_strike.application import (
    ClockPort,
    InputEvent,
    InputEventKind,
    InvalidPortValueError,
    PortCapabilities,
    PortUnavailableError,
)
from throw_a_strike.platform import DartsnutSdkFacade


class DartsnutInputPort:
    """Translate one facade batch into neutral application input events."""

    def __init__(
        self,
        facade: DartsnutSdkFacade,
        clock: ClockPort,
        initial_sequence: int = 0,
    ) -> None:
        if type(facade) is not DartsnutSdkFacade:
            raise InvalidPortValueError("facade must be an exact DartsnutSdkFacade")
        if clock is None or isinstance(clock, type):
            raise InvalidPortValueError("clock must be a ClockPort instance")
        try:
            clock_valid = isinstance(clock, ClockPort)
        except Exception as error:
            raise InvalidPortValueError("clock structural validation failed") from error
        if not clock_valid:
            raise InvalidPortValueError("clock must satisfy ClockPort")
        try:
            capabilities = clock.capabilities
        except Exception as error:
            raise InvalidPortValueError("clock capabilities are unavailable") from error
        if type(capabilities) is not PortCapabilities:
            raise InvalidPortValueError("clock capabilities must be exact PortCapabilities")
        if type(initial_sequence) is not int or initial_sequence < 0:
            raise InvalidPortValueError("initial_sequence must be a nonnegative exact integer")

        self.__facade = facade
        self.__clock = clock
        self.__capabilities = PortCapabilities(capabilities.available)
        self.__next_sequence = initial_sequence

    @property
    def capabilities(self) -> PortCapabilities:
        return PortCapabilities(self.__capabilities.available)

    def poll(self) -> tuple[InputEvent, ...]:
        if not self.__capabilities.available:
            raise PortUnavailableError("input is unavailable")

        hits = self.__facade.read_dart_hits()
        buttons = self.__facade.read_button_events()
        if not hits and not buttons:
            return ()

        timestamp = self.__clock.monotonic_seconds()
        sequence = self.__next_sequence
        events: list[InputEvent] = []
        for hit in hits:
            events.append(
                InputEvent(
                    kind=InputEventKind.DART_HIT,
                    sequence=sequence,
                    timestamp=timestamp,
                    dart_index=hit.dart_index,
                    x=hit.x,
                    y=hit.y,
                )
            )
            sequence += 1
        for button in buttons:
            events.append(
                InputEvent(
                    kind=InputEventKind.CONTROL,
                    sequence=sequence,
                    timestamp=timestamp,
                    control_id=button.value,
                )
            )
            sequence += 1

        result = tuple(events)
        self.__next_sequence = sequence
        return result
