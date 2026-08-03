"""Deterministic in-memory fakes for the pure application ports."""

from __future__ import annotations

from .ports import (
    AudioRequest,
    DisplayCapabilities,
    InputEvent,
    InvalidPortValueError,
    PortCapabilities,
    PortUnavailableError,
    StorageCapabilities,
    _finite_nonnegative,
    _opaque_id,
)
from .session import SessionSnapshot


def _require_exact(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise InvalidPortValueError(f"{name} must be an exact {expected.__name__}")


class _FakeDisplayPort:
    def __init__(self, capabilities: DisplayCapabilities) -> None:
        _require_exact(capabilities, DisplayCapabilities, "capabilities")
        self._capabilities = capabilities
        self._presented: list[SessionSnapshot] = []

    @property
    def capabilities(self) -> DisplayCapabilities:
        return self._capabilities

    @property
    def presented(self) -> tuple[SessionSnapshot, ...]:
        return tuple(self._presented)

    def present(self, snapshot: SessionSnapshot) -> None:
        _require_exact(snapshot, SessionSnapshot, "snapshot")
        if not self._capabilities.available:
            raise PortUnavailableError("display is unavailable")
        self._presented.append(snapshot)


class FakeMainDisplayPort(_FakeDisplayPort):
    """In-memory main-display recorder."""


class FakeSecondaryDisplayPort(_FakeDisplayPort):
    """In-memory optional-secondary-display recorder."""


class FakeInputPort:
    def __init__(self, capabilities: PortCapabilities = PortCapabilities(True)) -> None:
        _require_exact(capabilities, PortCapabilities, "capabilities")
        self._capabilities = capabilities
        self._queued_events: list[InputEvent] = []

    @property
    def capabilities(self) -> PortCapabilities:
        return self._capabilities

    @property
    def queued_events(self) -> tuple[InputEvent, ...]:
        return tuple(self._queued_events)

    def push(self, event: InputEvent) -> None:
        _require_exact(event, InputEvent, "event")
        self._require_available()
        self._queued_events.append(event)

    def poll(self) -> tuple[InputEvent, ...]:
        self._require_available()
        events = tuple(self._queued_events)
        self._queued_events.clear()
        return events

    def _require_available(self) -> None:
        if not self._capabilities.available:
            raise PortUnavailableError("input is unavailable")


class FakeClockPort:
    def __init__(
        self,
        initial_seconds: float = 0.0,
        capabilities: PortCapabilities = PortCapabilities(True),
    ) -> None:
        _require_exact(capabilities, PortCapabilities, "capabilities")
        self._capabilities = capabilities
        self._seconds = _finite_nonnegative(initial_seconds, "initial_seconds")

    @property
    def capabilities(self) -> PortCapabilities:
        return self._capabilities

    def monotonic_seconds(self) -> float:
        self._require_available()
        return self._seconds

    def advance(self, seconds: float) -> float:
        amount = _finite_nonnegative(seconds, "seconds")
        self._require_available()
        self._seconds += amount
        return self._seconds

    def _require_available(self) -> None:
        if not self._capabilities.available:
            raise PortUnavailableError("clock is unavailable")


class FakeAudioPort:
    def __init__(self, capabilities: PortCapabilities = PortCapabilities(True)) -> None:
        _require_exact(capabilities, PortCapabilities, "capabilities")
        self._capabilities = capabilities
        self._played: list[AudioRequest] = []
        self._stopped: list[str | None] = []

    @property
    def capabilities(self) -> PortCapabilities:
        return self._capabilities

    @property
    def played(self) -> tuple[AudioRequest, ...]:
        return tuple(self._played)

    @property
    def stopped(self) -> tuple[str | None, ...]:
        return tuple(self._stopped)

    def play(self, request: AudioRequest) -> None:
        _require_exact(request, AudioRequest, "request")
        self._require_available()
        self._played.append(request)

    def stop(self, cue_id: str | None = None) -> None:
        if cue_id is not None:
            _opaque_id(cue_id, "cue_id")
        self._require_available()
        self._stopped.append(cue_id)

    def _require_available(self) -> None:
        if not self._capabilities.available:
            raise PortUnavailableError("audio is unavailable")


class FakeStoragePort:
    def __init__(
        self,
        initial: tuple[tuple[str, bytes], ...] = (),
        capabilities: StorageCapabilities = StorageCapabilities(True, True),
    ) -> None:
        _require_exact(capabilities, StorageCapabilities, "capabilities")
        if type(initial) is not tuple:
            raise InvalidPortValueError("initial must be a tuple")
        contents: dict[str, bytes] = {}
        for entry in initial:
            if type(entry) is not tuple or len(entry) != 2:
                raise InvalidPortValueError("each initial entry must be a two-item tuple")
            key, value = entry
            _opaque_id(key, "key")
            if type(value) is not bytes:
                raise InvalidPortValueError("value must be exact bytes")
            if key in contents:
                raise InvalidPortValueError("initial keys must be unique")
            contents[key] = bytes(value)
        self._capabilities = capabilities
        self._contents = contents

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    @property
    def items(self) -> tuple[tuple[str, bytes], ...]:
        return tuple((key, bytes(self._contents[key])) for key in sorted(self._contents))

    def load(self, key: str) -> bytes | None:
        _opaque_id(key, "key")
        self._require_available()
        value = self._contents.get(key)
        return None if value is None else bytes(value)

    def save(self, key: str, value: bytes) -> None:
        _opaque_id(key, "key")
        if type(value) is not bytes:
            raise InvalidPortValueError("value must be exact bytes")
        self._require_writable()
        self._contents[key] = bytes(value)

    def delete(self, key: str) -> None:
        _opaque_id(key, "key")
        self._require_writable()
        self._contents.pop(key, None)

    def _require_available(self) -> None:
        if not self._capabilities.available:
            raise PortUnavailableError("storage is unavailable")

    def _require_writable(self) -> None:
        self._require_available()
        if not self._capabilities.writable:
            raise PortUnavailableError("storage is read-only")


__all__ = (
    "FakeMainDisplayPort", "FakeSecondaryDisplayPort", "FakeInputPort",
    "FakeClockPort", "FakeAudioPort", "FakeStoragePort",
)
