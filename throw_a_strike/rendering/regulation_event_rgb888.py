"""RGB888 renderer for secondary regulation presentation events."""
from __future__ import annotations

from throw_a_strike.application import InvalidPortValueError
from throw_a_strike.application.regulation_presentation import RegulationPresentationEvent, RegulationPresentationEventKind, RegulationPresentationViewModel, event_label
from .throw_control_rgb888 import _canvas, _center, _rect, _line, _CYAN, _YELLOW, _WHITE, _HUD, EMULATOR_RGB888_BYTE_LENGTH


def render_regulation_event_rgb888(event: RegulationPresentationEvent | None, now: float) -> bytes:
    if event is not None and type(event) is not RegulationPresentationEvent:
        raise InvalidPortValueError("event must be exact RegulationPresentationEvent or None")
    if event is not None and event.kind is RegulationPresentationEventKind.THROW_READY and now >= event.deadline:
        event = None
    buf = _canvas(); _rect(buf, 0, 0, 128, 128, _HUD); _line(buf, 0, 14, 127, 14, _CYAN)
    _center(buf, "THROW A STRIKE", 5, _CYAN)
    if event is None:
        _center(buf, " ", 56, _WHITE); return bytes(buf)
    color = _CYAN if event.kind is RegulationPresentationEventKind.THROW_READY else _YELLOW
    _center(buf, event.label, 48, color)
    if event.frame_number is not None and event.roll_number is not None:
        _center(buf, f"F{event.frame_number} R{event.roll_number}", 68, _WHITE)
    if event.score is not None:
        _center(buf, f"SCORE {event.score}", 82, _WHITE)
    return bytes(buf)


def render_regulation_event_view_model_rgb888(view_model: RegulationPresentationViewModel) -> bytes:
    if type(view_model) is not RegulationPresentationViewModel:
        raise InvalidPortValueError("view_model must be exact RegulationPresentationViewModel")
    event = None if not view_model.visible or view_model.kind is None else RegulationPresentationEvent(view_model.kind, 0, 1.5, result_label=view_model.label or event_label(view_model.kind))
    frame = render_regulation_event_rgb888(event, 0)
    if len(frame) != EMULATOR_RGB888_BYTE_LENGTH:
        raise RuntimeError("secondary event renderer emitted an invalid frame")
    return frame
