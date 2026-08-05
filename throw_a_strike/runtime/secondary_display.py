"""Emulator-only secondary display preview adapters."""
from __future__ import annotations

from dataclasses import dataclass

from throw_a_strike.application import InvalidPortValueError
from throw_a_strike.application.regulation_presentation import RegulationPresentationViewModel
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH, render_regulation_event_view_model_rgb888


class MemorySecondaryDisplayPort:
    """Headless RGB888 Screen 2 framebuffer sink for emulator tests and tools."""

    def __init__(self) -> None:
        self._framebuffers: list[bytes] = []

    def present(self, framebuffer: bytes) -> bool:
        if type(framebuffer) is not bytes or len(framebuffer) != EMULATOR_RGB888_BYTE_LENGTH:
            raise InvalidPortValueError("secondary framebuffer must be exact RGB888 bytes")
        self._framebuffers.append(framebuffer)
        return True

    @property
    def framebuffers(self) -> tuple[bytes, ...]:
        return tuple(self._framebuffers)

    @property
    def latest_framebuffer(self) -> bytes | None:
        return None if not self._framebuffers else self._framebuffers[-1]


class EmulatorSecondaryDisplayPort(MemorySecondaryDisplayPort):
    """Emulator-only Screen 2 adapter backed by memory and optional pygame window."""

    def __init__(self, *, visible: bool = False, title: str = "Throw A Strike Screen 2") -> None:
        if type(visible) is not bool:
            raise InvalidPortValueError("visible must be exact bool")
        if type(title) is not str or not title:
            raise InvalidPortValueError("title must be a non-empty exact str")
        super().__init__()
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

    def present(self, framebuffer: bytes) -> bool:
        accepted = super().present(framebuffer)
        if self._pygame is not None and self._surface is not None:
            image = self._pygame.image.frombuffer(framebuffer, (128, 128), "RGB")
            self._surface.blit(image, (0, 0))
            self._pygame.display.flip()
        return accepted


def render_secondary_view_model_to_port(view_model: RegulationPresentationViewModel, port: MemorySecondaryDisplayPort) -> bytes:
    if type(view_model) is not RegulationPresentationViewModel:
        raise InvalidPortValueError("view_model must be exact RegulationPresentationViewModel")
    if not isinstance(port, MemorySecondaryDisplayPort):
        raise InvalidPortValueError("port must be a secondary display port")
    framebuffer = render_regulation_event_view_model_rgb888(view_model)
    port.present(framebuffer)
    return framebuffer


__all__ = ("MemorySecondaryDisplayPort", "EmulatorSecondaryDisplayPort", "render_secondary_view_model_to_port")
