"""Deterministic SDK-shaped test fake."""
from .dartsnut_sdk import DartsnutButtonId, DartsnutSdkOperation, InvalidDartsnutSdkValueError, RawDartHit


class FakeDartsnutSdk:
    def __init__(self, running: bool = True) -> None:
        self._running = self._bool(running, "running")
        self._dart_batches: list[tuple[RawDartHit, ...]] = []
        self._button_batches: list[tuple[DartsnutButtonId, ...]] = []
        self._frame_results: list[bool] = []
        self._calls: list[DartsnutSdkOperation] = []
        self._frames: list[bytes] = []
        self._brightness: list[int] = []
        self._resets = 0
        self._closes = 0

    @staticmethod
    def _bool(value: bool, name: str) -> bool:
        if type(value) is not bool:
            raise InvalidDartsnutSdkValueError(f"{name} must be an exact bool")
        return value

    @property
    def running(self) -> bool:
        self._calls.append(DartsnutSdkOperation.RUNNING_STATE)
        return self._running
    def set_running(self, running: bool) -> None: self._running = self._bool(running, "running")

    def queue_dart_hits(self, hits: tuple[RawDartHit, ...]) -> None:
        if type(hits) is not tuple or any(type(hit) is not RawDartHit for hit in hits):
            raise InvalidDartsnutSdkValueError("hits must be an exact tuple of exact RawDartHit values")
        self._dart_batches.append(hits)

    def queue_button_events(self, buttons: tuple[DartsnutButtonId, ...]) -> None:
        if type(buttons) is not tuple or any(type(button) is not DartsnutButtonId for button in buttons):
            raise InvalidDartsnutSdkValueError("buttons must be an exact tuple of exact DartsnutButtonId values")
        if len(set(buttons)) != len(buttons):
            raise InvalidDartsnutSdkValueError("button batch must not contain duplicates")
        self._button_batches.append(buttons)

    def queue_framebuffer_result(self, accepted: bool) -> None: self._frame_results.append(self._bool(accepted, "accepted"))

    def get_dart_hits(self) -> list[tuple[int, int, int]]:
        self._calls.append(DartsnutSdkOperation.DART_HITS)
        batch = self._dart_batches.pop(0) if self._dart_batches else ()
        return [(hit.dart_index, hit.x, hit.y) for hit in batch]

    def get_button_events(self) -> dict[str, bool]:
        self._calls.append(DartsnutSdkOperation.BUTTON_EVENTS)
        batch = self._button_batches.pop(0) if self._button_batches else ()
        return {button.value: button in batch for button in DartsnutButtonId}

    def reset_blocking_state(self) -> None:
        self._calls.append(DartsnutSdkOperation.RESET_BLOCKING_STATE); self._resets += 1

    def update_frame_buffer(self, frame: bytearray) -> bool:
        self._calls.append(DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION); self._frames.append(bytes(frame))
        return self._frame_results.pop(0) if self._frame_results else True

    def set_brightness(self, brightness: int) -> None:
        if type(brightness) is not int or not 10 <= brightness <= 100:
            raise InvalidDartsnutSdkValueError("brightness must be an exact integer from 10 through 100")
        self._calls.append(DartsnutSdkOperation.BRIGHTNESS); self._brightness.append(brightness)

    def close(self) -> None:
        self._calls.append(DartsnutSdkOperation.CLOSE); self._closes += 1

    @property
    def calls(self) -> tuple[DartsnutSdkOperation, ...]: return tuple(self._calls)
    @property
    def submitted_framebuffers(self) -> tuple[bytes, ...]: return tuple(self._frames)
    @property
    def brightness_values(self) -> tuple[int, ...]: return tuple(self._brightness)
    @property
    def reset_blocking_count(self) -> int: return self._resets
    @property
    def close_count(self) -> int: return self._closes
    @property
    def queued_dart_batch_count(self) -> int: return len(self._dart_batches)
    @property
    def queued_button_batch_count(self) -> int: return len(self._button_batches)
    @property
    def queued_framebuffer_result_count(self) -> int: return len(self._frame_results)
