"""Pure, hardware-independent application boundary contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real
from typing import Protocol, runtime_checkable

from .session import SessionSnapshot


class InvalidPortValueError(ValueError):
    """Raised when a port value or port object violates its contract."""


class PortUnavailableError(RuntimeError):
    """Raised when an unavailable capability is used operationally."""


def _actual_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise InvalidPortValueError(f"{name} must be a bool")


def _finite_nonnegative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidPortValueError(f"{name} must be a finite nonnegative real number")
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        raise InvalidPortValueError(
            f"{name} must be a finite nonnegative real number"
        ) from None
    if not isfinite(normalized) or normalized < 0.0:
        raise InvalidPortValueError(f"{name} must be a finite nonnegative real number")
    return normalized


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidPortValueError(f"{name} must be a finite real number")
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        raise InvalidPortValueError(f"{name} must be a finite real number") from None
    if not isfinite(normalized):
        raise InvalidPortValueError(f"{name} must be a finite real number")
    return normalized


def _opaque_id(value: object, name: str) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise InvalidPortValueError(f"{name} must be a nonempty stripped string")


@dataclass(frozen=True)
class PortCapabilities:
    available: bool

    def __post_init__(self) -> None:
        _actual_bool(self.available, "available")


@dataclass(frozen=True)
class DisplayCapabilities:
    available: bool
    width: int | None
    height: int | None

    def __post_init__(self) -> None:
        _actual_bool(self.available, "available")
        if (self.width is None) != (self.height is None):
            raise InvalidPortValueError("width and height must be supplied together")
        if self.width is not None:
            for value, name in ((self.width, "width"), (self.height, "height")):
                if type(value) is not int or value <= 0:
                    raise InvalidPortValueError(f"{name} must be a positive integer")
        if not self.available and self.width is not None:
            raise InvalidPortValueError("an unavailable display cannot have dimensions")


@dataclass(frozen=True)
class StorageCapabilities:
    available: bool
    writable: bool

    def __post_init__(self) -> None:
        _actual_bool(self.available, "available")
        _actual_bool(self.writable, "writable")
        if self.writable and not self.available:
            raise InvalidPortValueError("unavailable storage cannot be writable")


@dataclass(frozen=True)
class ApplicationCapabilities:
    main_display: DisplayCapabilities
    secondary_display: DisplayCapabilities
    input: PortCapabilities
    clock: PortCapabilities
    audio: PortCapabilities
    storage: StorageCapabilities

    def __post_init__(self) -> None:
        expected = (
            (self.main_display, DisplayCapabilities, "main_display"),
            (self.secondary_display, DisplayCapabilities, "secondary_display"),
            (self.input, PortCapabilities, "input"),
            (self.clock, PortCapabilities, "clock"),
            (self.audio, PortCapabilities, "audio"),
            (self.storage, StorageCapabilities, "storage"),
        )
        for value, kind, name in expected:
            if type(value) is not kind:
                raise InvalidPortValueError(f"{name} must be an exact {kind.__name__}")


class InputEventKind(str, Enum):
    DART_HIT = "dart_hit"
    CONTROL = "control"


@dataclass(frozen=True)
class InputEvent:
    kind: InputEventKind
    sequence: int
    timestamp: float
    dart_index: int | None = None
    x: float | None = None
    y: float | None = None
    control_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not InputEventKind:
            raise InvalidPortValueError("kind must be an InputEventKind")
        if type(self.sequence) is not int or self.sequence < 0:
            raise InvalidPortValueError("sequence must be a nonnegative integer")
        object.__setattr__(self, "timestamp", _finite_nonnegative(self.timestamp, "timestamp"))
        if self.kind is InputEventKind.DART_HIT:
            if type(self.dart_index) is not int or self.dart_index < 0:
                raise InvalidPortValueError("dart_index must be a nonnegative integer")
            if self.x is None or self.y is None:
                raise InvalidPortValueError("dart hits require x and y")
            x = _finite_real(self.x, "x")
            y = _finite_real(self.y, "y")
            if self.control_id is not None:
                raise InvalidPortValueError("dart hits cannot contain control_id")
            object.__setattr__(self, "x", x)
            object.__setattr__(self, "y", y)
        else:
            _opaque_id(self.control_id, "control_id")
            if self.dart_index is not None or self.x is not None or self.y is not None:
                raise InvalidPortValueError("control events cannot contain dart fields")


@dataclass(frozen=True)
class AudioRequest:
    cue_id: str
    loop: bool = False
    volume: float = 1.0

    def __post_init__(self) -> None:
        _opaque_id(self.cue_id, "cue_id")
        _actual_bool(self.loop, "loop")
        volume = _finite_nonnegative(self.volume, "volume")
        if volume > 1.0:
            raise InvalidPortValueError("volume must be from 0.0 through 1.0")
        object.__setattr__(self, "volume", volume)


@runtime_checkable
class MainDisplayPort(Protocol):
    @property
    def capabilities(self) -> DisplayCapabilities: ...
    def present(self, snapshot: SessionSnapshot) -> None: ...


@runtime_checkable
class SecondaryDisplayPort(Protocol):
    @property
    def capabilities(self) -> DisplayCapabilities: ...
    def present(self, snapshot: SessionSnapshot) -> None: ...


@runtime_checkable
class InputPort(Protocol):
    @property
    def capabilities(self) -> PortCapabilities: ...
    def poll(self) -> tuple[InputEvent, ...]: ...


@runtime_checkable
class ClockPort(Protocol):
    @property
    def capabilities(self) -> PortCapabilities: ...
    def monotonic_seconds(self) -> float: ...


@runtime_checkable
class AudioPort(Protocol):
    @property
    def capabilities(self) -> PortCapabilities: ...
    def play(self, request: AudioRequest) -> None: ...
    def stop(self, cue_id: str | None = None) -> None: ...


@runtime_checkable
class StoragePort(Protocol):
    @property
    def capabilities(self) -> StorageCapabilities: ...
    def load(self, key: str) -> bytes | None: ...
    def save(self, key: str, value: bytes) -> None: ...
    def delete(self, key: str) -> None: ...


def collect_application_capabilities(
    main_display: MainDisplayPort,
    input_port: InputPort,
    clock_port: ClockPort,
    secondary_display: SecondaryDisplayPort | None = None,
    audio_port: AudioPort | None = None,
    storage_port: StoragePort | None = None,
) -> ApplicationCapabilities:
    """Collect detached capability values without exercising any port operation."""
    supplied = (
        (main_display, MainDisplayPort, DisplayCapabilities, "main_display"),
        (input_port, InputPort, PortCapabilities, "input_port"),
        (clock_port, ClockPort, PortCapabilities, "clock_port"),
        (secondary_display, SecondaryDisplayPort, DisplayCapabilities, "secondary_display"),
        (audio_port, AudioPort, PortCapabilities, "audio_port"),
        (storage_port, StoragePort, StorageCapabilities, "storage_port"),
    )
    values: list[object | None] = []
    for port, protocol, capability_type, name in supplied:
        if port is None and name in ("secondary_display", "audio_port", "storage_port"):
            values.append(None)
            continue
        try:
            structurally_valid = port is not None and isinstance(port, protocol)
        except Exception as error:
            raise InvalidPortValueError(f"{name} is not a valid port") from error
        if not structurally_valid:
            raise InvalidPortValueError(f"{name} does not satisfy {protocol.__name__}")
        try:
            capability = port.capabilities
        except Exception as error:
            raise InvalidPortValueError(f"{name} has invalid capabilities") from error
        if type(capability) is not capability_type:
            raise InvalidPortValueError(f"{name} has invalid capabilities")
        values.append(capability)

    main, input_cap, clock, secondary, audio, storage = values
    return ApplicationCapabilities(
        DisplayCapabilities(main.available, main.width, main.height),
        (DisplayCapabilities(False, None, None) if secondary is None else
         DisplayCapabilities(secondary.available, secondary.width, secondary.height)),
        PortCapabilities(input_cap.available),
        PortCapabilities(clock.available),
        PortCapabilities(False) if audio is None else PortCapabilities(audio.available),
        (StorageCapabilities(False, False) if storage is None else
         StorageCapabilities(storage.available, storage.writable)),
    )


__all__ = (
    "PortCapabilities", "DisplayCapabilities", "StorageCapabilities",
    "ApplicationCapabilities", "InputEventKind", "InputEvent", "AudioRequest",
    "MainDisplayPort", "SecondaryDisplayPort", "InputPort", "ClockPort",
    "AudioPort", "StoragePort", "InvalidPortValueError", "PortUnavailableError",
    "collect_application_capabilities",
)
