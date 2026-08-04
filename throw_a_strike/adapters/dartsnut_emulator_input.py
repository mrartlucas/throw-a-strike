"""Stale-safe input policy for the Dartsnut Agent emulator diagnostic."""

from throw_a_strike.application import (
    ClockPort, InputEvent, InputEventKind, InvalidPortValueError,
    PortCapabilities, PortUnavailableError,
)
from throw_a_strike.platform import DartsnutSdkFacade, RawDartHit


class DartsnutEmulatorInputPort:
    """Combine transition events with emulator active-coordinate observation."""

    def __init__(self, facade: DartsnutSdkFacade, clock: ClockPort, initial_sequence: int = 0) -> None:
        if type(facade) is not DartsnutSdkFacade:
            raise InvalidPortValueError("facade must be an exact DartsnutSdkFacade")
        if clock is None or isinstance(clock, type):
            raise InvalidPortValueError("clock must be a ClockPort instance")
        try:
            valid = isinstance(clock, ClockPort)
        except Exception as error:
            raise InvalidPortValueError("clock structural validation failed") from error
        if not valid:
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
        self.__baseline: dict[int, tuple[int, int]] | None = None

    @property
    def capabilities(self) -> PortCapabilities:
        return PortCapabilities(self.__capabilities.available)

    def poll(self) -> tuple[InputEvent, ...]:
        if not self.__capabilities.available:
            raise PortUnavailableError("input is unavailable")
        hits = self.__facade.read_dart_hits()
        active = self.__facade.read_active_darts()
        buttons = self.__facade.read_button_events()
        current = {dart.dart_index: (dart.x, dart.y) for dart in active}

        semantic_hits: dict[int, RawDartHit] = {}
        if self.__baseline is not None:
            # Normal transition evidence wins coordinates and deduplicates by index.
            semantic_hits.update((hit.dart_index, hit) for hit in hits)
            for dart in active:
                coordinate = (dart.x, dart.y)
                if self.__baseline.get(dart.dart_index) != coordinate:
                    semantic_hits.setdefault(dart.dart_index, dart)
            self.__baseline = current
            # A normal hit without a matching active entry is still the best
            # available coordinate evidence. Retaining it also prevents a
            # delayed identical active observation from being emitted twice.
            for hit in hits:
                if hit.dart_index not in current:
                    self.__baseline[hit.dart_index] = (hit.x, hit.y)
        else:
            # Startup events and all already-active darts are non-scoring baseline.
            self.__baseline = current

        if not semantic_hits and not buttons:
            return ()
        timestamp = self.__clock.monotonic_seconds()
        sequence = self.__next_sequence
        events: list[InputEvent] = []
        for index in sorted(semantic_hits):
            hit = semantic_hits[index]
            events.append(InputEvent(InputEventKind.DART_HIT, sequence, timestamp,
                                     dart_index=hit.dart_index, x=hit.x, y=hit.y))
            sequence += 1
        for button in buttons:
            events.append(InputEvent(InputEventKind.CONTROL, sequence, timestamp,
                                     control_id=button.value))
            sequence += 1
        self.__next_sequence = sequence
        return tuple(events)
