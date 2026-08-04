"""Strict dependency-injected boundary for the verified Dartsnut SDK surface."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class InvalidDartsnutSdkValueError(ValueError):
    """A caller supplied an invalid facade value."""


class DartsnutButtonId(str, Enum):
    A = "btn_a"
    B = "btn_b"
    UP = "btn_up"
    RIGHT = "btn_right"
    LEFT = "btn_left"
    DOWN = "btn_down"
    HOME = "btn_home"
    RESERVED = "btn_reserved"


class DartsnutSdkOperation(str, Enum):
    RUNNING_STATE = "running_state"
    DART_HITS = "dart_hits"
    ACTIVE_DARTS = "active_darts"
    BUTTON_EVENTS = "button_events"
    RESET_BLOCKING_STATE = "reset_blocking_state"
    FRAMEBUFFER_SUBMISSION = "framebuffer_submission"
    BRIGHTNESS = "brightness"
    CLOSE = "close"


def _exact_operation(operation: DartsnutSdkOperation) -> None:
    if type(operation) is not DartsnutSdkOperation:
        raise InvalidDartsnutSdkValueError("operation must be an exact DartsnutSdkOperation")


class InvalidDartsnutSdkResponseError(RuntimeError):
    def __init__(self, operation: DartsnutSdkOperation, detail: str) -> None:
        _exact_operation(operation)
        if type(detail) is not str or not detail or detail != detail.strip():
            raise InvalidDartsnutSdkValueError("detail must be a nonempty stripped exact string")
        self._operation = operation
        self._detail = detail
        super().__init__(f"Malformed Dartsnut SDK response for {operation.value}: {detail}")

    @property
    def operation(self) -> DartsnutSdkOperation:
        return self._operation

    @property
    def detail(self) -> str:
        return self._detail


class DartsnutSdkOperationError(RuntimeError):
    def __init__(self, operation: DartsnutSdkOperation, cause: Exception) -> None:
        _exact_operation(operation)
        if not isinstance(cause, Exception):
            raise InvalidDartsnutSdkValueError("cause must be an Exception")
        self._operation = operation
        self._cause = cause
        super().__init__(f"Dartsnut SDK operation {operation.value} failed: {cause}")

    @property
    def operation(self) -> DartsnutSdkOperation:
        return self._operation

    @property
    def cause(self) -> Exception:
        return self._cause


@dataclass(frozen=True)
class RawDartHit:
    dart_index: int
    x: int
    y: int

    def __post_init__(self) -> None:
        for name, value, maximum in (("dart_index", self.dart_index, 11), ("x", self.x, 127), ("y", self.y, 127)):
            if type(value) is not int or not 0 <= value <= maximum:
                raise InvalidDartsnutSdkValueError(f"{name} must be an exact integer from 0 through {maximum}")


@runtime_checkable
class DartsnutSdkProtocol(Protocol):
    @property
    def running(self) -> bool: ...
    def get_dart_hits(self) -> list[tuple[int, int, int]]: ...
    def get_active_darts(self) -> list[tuple[int, int, int]]: ...
    def get_button_events(self) -> dict[str, bool]: ...
    def reset_blocking_state(self) -> None: ...
    def update_frame_buffer(self, frame: bytearray) -> bool: ...
    def set_brightness(self, brightness: int) -> None: ...
    def close(self) -> None: ...


class DartsnutSdkFacade:
    _METHODS = ("get_dart_hits", "get_active_darts", "get_button_events", "reset_blocking_state", "update_frame_buffer", "set_brightness", "close")

    def __init__(self, sdk: DartsnutSdkProtocol) -> None:
        if sdk is None or isinstance(sdk, type):
            raise InvalidDartsnutSdkValueError("sdk must be an SDK-shaped instance")
        for name in self._METHODS:
            try:
                member = getattr(sdk, name)
            except Exception as error:
                raise InvalidDartsnutSdkValueError(f"sdk method {name} is unavailable") from error
            if not callable(member):
                raise InvalidDartsnutSdkValueError(f"sdk method {name} must be callable")
        self.__sdk = sdk

    @staticmethod
    def _malformed(operation: DartsnutSdkOperation, detail: str) -> InvalidDartsnutSdkResponseError:
        return InvalidDartsnutSdkResponseError(operation, detail)

    def is_running(self) -> bool:
        operation = DartsnutSdkOperation.RUNNING_STATE
        try:
            value = self.__sdk.running
        except Exception as error:
            raise DartsnutSdkOperationError(operation, error) from error
        if type(value) is not bool:
            raise self._malformed(operation, "running must be an exact bool")
        return value

    def read_dart_hits(self) -> tuple[RawDartHit, ...]:
        operation = DartsnutSdkOperation.DART_HITS
        try:
            response = self.__sdk.get_dart_hits()
        except Exception as error:
            raise DartsnutSdkOperationError(operation, error) from error
        if type(response) is not list:
            raise self._malformed(operation, "response must be an exact list")
        hits = []
        for entry in response:
            if type(entry) is not tuple or len(entry) != 3:
                raise self._malformed(operation, "each hit must be an exact three-item tuple")
            try:
                hit = RawDartHit(*entry)
            except InvalidDartsnutSdkValueError as error:
                raise self._malformed(operation, str(error)) from error
            hits.append(hit)
        return tuple(hits)

    def read_active_darts(self) -> tuple[RawDartHit, ...]:
        operation = DartsnutSdkOperation.ACTIVE_DARTS
        try:
            response = self.__sdk.get_active_darts()
        except Exception as error:
            raise DartsnutSdkOperationError(operation, error) from error
        if type(response) is not list:
            raise self._malformed(operation, "response must be an exact list")
        hits = []
        for entry in response:
            if type(entry) is not tuple or len(entry) != 3:
                raise self._malformed(operation, "each active dart must be an exact three-item tuple")
            try:
                hit = RawDartHit(*entry)
            except InvalidDartsnutSdkValueError as error:
                raise self._malformed(operation, str(error)) from error
            hits.append(hit)
        return tuple(hits)

    def read_button_events(self) -> tuple[DartsnutButtonId, ...]:
        operation = DartsnutSdkOperation.BUTTON_EVENTS
        try:
            response = self.__sdk.get_button_events()
        except Exception as error:
            raise DartsnutSdkOperationError(operation, error) from error
        expected = {button.value for button in DartsnutButtonId}
        if (
            type(response) is not dict
            or len(response) != len(expected)
            or any(type(key) is not str for key in response)
            or set(response) != expected
        ):
            raise self._malformed(operation, "response must be an exact dict with all verified exact-string button keys")
        if any(type(value) is not bool for value in response.values()):
            raise self._malformed(operation, "button values must be exact bools")
        return tuple(button for button in DartsnutButtonId if response[button.value])

    def reset_blocking_state(self) -> None:
        self._none_operation(DartsnutSdkOperation.RESET_BLOCKING_STATE, lambda: self.__sdk.reset_blocking_state())

    def submit_framebuffer(self, frame: bytes | bytearray) -> bool:
        if type(frame) not in (bytes, bytearray):
            raise InvalidDartsnutSdkValueError("frame must be exact bytes or bytearray")
        operation = DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION
        forwarded = bytearray(frame)
        try:
            result = self.__sdk.update_frame_buffer(forwarded)
        except Exception as error:
            raise DartsnutSdkOperationError(operation, error) from error
        if type(result) is not bool:
            raise self._malformed(operation, "result must be an exact bool")
        return result

    def set_brightness(self, brightness: int) -> None:
        if type(brightness) is not int or not 10 <= brightness <= 100:
            raise InvalidDartsnutSdkValueError("brightness must be an exact integer from 10 through 100")
        self._none_operation(DartsnutSdkOperation.BRIGHTNESS, lambda: self.__sdk.set_brightness(brightness))

    def close(self) -> None:
        self._none_operation(DartsnutSdkOperation.CLOSE, lambda: self.__sdk.close())

    def _none_operation(self, operation: DartsnutSdkOperation, call: object) -> None:
        try:
            result = call()  # type: ignore[operator]
        except Exception as error:
            raise DartsnutSdkOperationError(operation, error) from error
        if result is not None:
            raise self._malformed(operation, "result must be None")
