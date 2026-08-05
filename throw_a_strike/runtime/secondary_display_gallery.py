"""Developer-only Screen 2 regulation event gallery for emulator preview."""
from __future__ import annotations

from throw_a_strike.application.regulation_presentation import RegulationPresentationEventKind, RegulationPresentationViewModel, event_label
from throw_a_strike.runtime.secondary_display import EmulatorSecondaryDisplayPort, MemorySecondaryDisplayPort, render_secondary_view_model_to_port

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
    target = MemorySecondaryDisplayPort() if port is None else port
    return tuple(render_secondary_view_model_to_port(model, target) for model in gallery_view_models())


def main() -> None:
    port = EmulatorSecondaryDisplayPort(visible=True)
    render_gallery(port)
    print("Screen 2 event gallery rendered: " + ", ".join(model.label or "" for model in gallery_view_models()))


if __name__ == "__main__":
    main()
