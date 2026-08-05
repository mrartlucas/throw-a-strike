"""Developer-only Screen 2 regulation event gallery for emulator preview."""
from __future__ import annotations

from collections.abc import Callable
from time import monotonic, sleep

from throw_a_strike.application.regulation_presentation import RegulationPresentationEventKind, RegulationPresentationViewModel, event_label
from throw_a_strike.runtime.secondary_display import EmulatorSecondaryDisplayPort, MemorySecondaryDisplayPort, hold_visible_frame, render_secondary_view_model_to_port

GALLERY_EVENT_KINDS = (
    RegulationPresentationEventKind.THROW_READY,
    RegulationPresentationEventKind.STRIKE,
    RegulationPresentationEventKind.SPARE,
    RegulationPresentationEventKind.SPLIT,
    RegulationPresentationEventKind.SPLIT_CONVERTED,
    RegulationPresentationEventKind.FIELD_GOAL,
    RegulationPresentationEventKind.GUTTER,
    RegulationPresentationEventKind.MISS,
    RegulationPresentationEventKind.FOUL,
    RegulationPresentationEventKind.TURKEY,
    RegulationPresentationEventKind.GAME_OVER,
)


def gallery_view_models() -> tuple[RegulationPresentationViewModel, ...]:
    return tuple(RegulationPresentationViewModel(event_label(kind), True, kind) for kind in GALLERY_EVENT_KINDS)


def render_gallery(port: MemorySecondaryDisplayPort | None = None) -> tuple[bytes, ...]:
    target = MemorySecondaryDisplayPort(history_limit=len(GALLERY_EVENT_KINDS)) if port is None else port
    return tuple(render_secondary_view_model_to_port(model, target) for model in gallery_view_models())


def run_visible_gallery(port: MemorySecondaryDisplayPort, *, hold_seconds: float = 1.0, clock: Callable[[], float] = monotonic, sleeper: Callable[[float], object] = sleep) -> tuple[str, ...]:
    labels: list[str] = []
    try:
        for model in gallery_view_models():
            if not port.pump_events():
                break
            render_secondary_view_model_to_port(model, port)
            labels.append(model.label or "")
            if not hold_visible_frame(port, hold_seconds, clock=clock, sleeper=sleeper):
                break
    finally:
        port.close()
    return tuple(labels)


def main() -> None:
    labels = run_visible_gallery(EmulatorSecondaryDisplayPort(visible=True))
    print("Screen 2 event gallery rendered: " + ", ".join(labels))


if __name__ == "__main__":
    main()
