"""Emulator-only secondary display preview adapters."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from time import monotonic, sleep

from throw_a_strike.application import InvalidPortValueError
from throw_a_strike.application.regulation_presentation import RegulationPresentationViewModel
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH, render_regulation_event_view_model_rgb888


def _history_limit(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise InvalidPortValueError(f"{name} must be a positive exact int")
    return value


class MemorySecondaryDisplayPort:
    """Bounded headless RGB888 Screen 2 framebuffer sink for emulator tests and tools."""

    def __init__(self, *, history_limit: int = 1) -> None:
        self._framebuffers: deque[bytes] = deque(maxlen=_history_limit(history_limit, "history_limit"))
        self._present_count = 0
        self._closed = False

    def present(self, framebuffer: bytes) -> bool:
        if self._closed:
            return False
        if type(framebuffer) is not bytes or len(framebuffer) != EMULATOR_RGB888_BYTE_LENGTH:
            raise InvalidPortValueError("secondary framebuffer must be exact RGB888 bytes")
        self._framebuffers.append(framebuffer)
        self._present_count += 1
        return True

    def pump_events(self) -> bool:
        return not self._closed

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def present_count(self) -> int:
        return self._present_count

    @property
    def framebuffers(self) -> tuple[bytes, ...]:
        return tuple(self._framebuffers)

    @property
    def latest_framebuffer(self) -> bytes | None:
        return None if not self._framebuffers else self._framebuffers[-1]


class EmulatorSecondaryDisplayPort(MemorySecondaryDisplayPort):
    """Emulator-only Screen 2 adapter backed by bounded memory and optional pygame window."""

    def __init__(self, *, visible: bool = False, title: str = "Throw A Strike Screen 2", history_limit: int = 1) -> None:
        if type(visible) is not bool:
            raise InvalidPortValueError("visible must be exact bool")
        if type(title) is not str or not title:
            raise InvalidPortValueError("title must be a non-empty exact str")
        super().__init__(history_limit=history_limit)
        self._visible = visible
        self._title = title
        self._pygame = None
        self._surface = None
        if visible:
            import pygame
            pygame.init()
            self._pygame = pygame
            self._surface = pygame.display.set_mode((128, 128))
            pygame.display.set_caption(title)

    def pump_events(self) -> bool:
        if not super().pump_events():
            return False
        if self._pygame is None:
            return True
        for event in self._pygame.event.get():
            if event.type == self._pygame.QUIT:
                self.close()
                return False
        return True

    def present(self, framebuffer: bytes) -> bool:
        if not self.pump_events():
            return False
        accepted = super().present(framebuffer)
        if accepted and self._pygame is not None and self._surface is not None:
            image = self._pygame.image.frombuffer(framebuffer, (128, 128), "RGB")
            self._surface.blit(image, (0, 0))
            self._pygame.display.flip()
        return accepted

    def close(self) -> None:
        already_closed = self.closed
        super().close()
        if not already_closed and self._pygame is not None:
            self._pygame.quit()


def render_secondary_view_model_to_port(view_model: RegulationPresentationViewModel, port: MemorySecondaryDisplayPort) -> bytes:
    if type(view_model) is not RegulationPresentationViewModel:
        raise InvalidPortValueError("view_model must be exact RegulationPresentationViewModel")
    if not isinstance(port, MemorySecondaryDisplayPort):
        raise InvalidPortValueError("port must be a secondary display port")
    framebuffer = render_regulation_event_view_model_rgb888(view_model)
    port.present(framebuffer)
    return framebuffer


def hold_visible_frame(port: MemorySecondaryDisplayPort, hold_seconds: float, *, clock: Callable[[], float] = monotonic, sleeper: Callable[[float], object] = sleep, poll_seconds: float = 1 / 30) -> bool:
    if not isinstance(port, MemorySecondaryDisplayPort):
        raise InvalidPortValueError("port must be a secondary display port")
    if type(hold_seconds) not in (int, float) or hold_seconds < 0:
        raise InvalidPortValueError("hold_seconds must be nonnegative")
    if not callable(clock) or not callable(sleeper):
        raise InvalidPortValueError("clock and sleeper must be callable")
    if type(poll_seconds) not in (int, float) or poll_seconds < 0:
        raise InvalidPortValueError("poll_seconds must be nonnegative")
    deadline = float(clock()) + float(hold_seconds)
    while float(clock()) < deadline:
        if not port.pump_events():
            return False
        sleeper(float(poll_seconds))
    return port.pump_events()


__all__ = ("MemorySecondaryDisplayPort", "EmulatorSecondaryDisplayPort", "render_secondary_view_model_to_port", "hold_visible_frame")
