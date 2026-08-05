"""Pure display-neutral presentation semantics for one bowling attempt."""

from dataclasses import dataclass
from enum import Enum

from throw_a_strike.domain import (
    ControlStyle,
    CurveLevel,
    LaneArrow,
    PowerFeedback,
    ThrowControlOutcomeKind,
    ThrowControlPhase,
    ThrowControlSnapshot,
)

from .throw_control_coordinator import ThrowControlStepResult

__all__ = (
    "InvalidThrowControlPresentationValueError",
    "ThrowControlPrompt",
    "ThrowControlCurveIcon",
    "ThrowControlLaneArrowIcon",
    "ThrowControlPresentation",
    "build_throw_control_presentation",
    "build_throw_control_step_presentation",
)


class InvalidThrowControlPresentationValueError(ValueError):
    """Raised when a public presentation value violates its contract."""


class ThrowControlPrompt(str, Enum):
    SET_AIM = "set_aim"
    SET_LANE_ARROW = "set_aim"  # Backward-compatible alias.
    SET_CURVE = "set_curve"
    SET_POWER = "set_power"
    THROW_READY = "throw_ready"
    TOO_SOON = "too_soon"
    REMOVE_DART = "remove_dart"
    THROW_NOW = "throw_now"
    FOUL = "foul"
    ZERO_PINS = "zero_pins"

    @property
    def label(self) -> str:
        return _PROMPT_LABELS[self]


class ThrowControlLaneArrowIcon(str, Enum):
    FIVE_UP_MARKERS = "five_up_markers"


class ThrowControlCurveIcon(str, Enum):
    LEFT = "left_arrow"
    STRAIGHT = "straight_arrow"
    RIGHT = "right_arrow"


_PROMPT_LABELS = {
    ThrowControlPrompt.SET_CURVE: "SET CURVE",
    ThrowControlPrompt.SET_AIM: "SET AIM",
    ThrowControlPrompt.SET_POWER: "SET POWER",
    ThrowControlPrompt.THROW_READY: "THROW READY",
    ThrowControlPrompt.TOO_SOON: "TOO SOON",
    ThrowControlPrompt.REMOVE_DART: "REMOVE DART",
    ThrowControlPrompt.THROW_NOW: "THROW NOW",
    ThrowControlPrompt.FOUL: "FOUL",
    ThrowControlPrompt.ZERO_PINS: "0 PINS",
}
_CURVE_ICONS = {
    CurveLevel.LEFT_3: ThrowControlCurveIcon.LEFT,
    CurveLevel.LEFT_2: ThrowControlCurveIcon.LEFT,
    CurveLevel.LEFT_1: ThrowControlCurveIcon.LEFT,
    CurveLevel.STRAIGHT: ThrowControlCurveIcon.STRAIGHT,
    CurveLevel.RIGHT_1: ThrowControlCurveIcon.RIGHT,
    CurveLevel.RIGHT_2: ThrowControlCurveIcon.RIGHT,
    CurveLevel.RIGHT_3: ThrowControlCurveIcon.RIGHT,
}
_POWER_FEEDBACK = {
    40: PowerFeedback.WEAK,
    50: PowerFeedback.WEAK,
    60: PowerFeedback.GOOD,
    70: PowerFeedback.PERFECT,
    80: PowerFeedback.GOOD,
    90: PowerFeedback.POWER,
    100: PowerFeedback.OVERDRIVE,
}


def _prompts(
    phase: ThrowControlPhase, warning_active: bool
) -> tuple[ThrowControlPrompt | None, ThrowControlPrompt | None]:
    if phase is ThrowControlPhase.SET_AIM:
        return ThrowControlPrompt.SET_AIM, None
    if phase is ThrowControlPhase.SET_CURVE:
        return ThrowControlPrompt.SET_CURVE, None
    if phase is ThrowControlPhase.SET_POWER:
        return ThrowControlPrompt.SET_POWER, None
    if phase is ThrowControlPhase.THROW_READY:
        return (
            ThrowControlPrompt.THROW_READY,
            ThrowControlPrompt.THROW_NOW if warning_active else None,
        )
    if phase is ThrowControlPhase.EARLY_DART_RECOVERY:
        return ThrowControlPrompt.TOO_SOON, ThrowControlPrompt.REMOVE_DART
    if phase is ThrowControlPhase.FOUL:
        return ThrowControlPrompt.FOUL, ThrowControlPrompt.ZERO_PINS
    return None, None


def _invalid(message: str) -> None:
    raise InvalidThrowControlPresentationValueError(message)


@dataclass(frozen=True)
class ThrowControlPresentation:
    control_style: ControlStyle
    phase: ThrowControlPhase
    primary_prompt: ThrowControlPrompt | None
    secondary_prompt: ThrowControlPrompt | None
    curve_level: CurveLevel
    curve_icon: ThrowControlCurveIcon
    power_percent: int
    power_feedback: PowerFeedback
    power_locked: bool
    warning_active: bool
    terminal: bool
    outcome_kind: ThrowControlOutcomeKind | None
    lane_arrow: LaneArrow = LaneArrow.CENTER
    lane_arrow_icon: ThrowControlLaneArrowIcon = ThrowControlLaneArrowIcon.FIVE_UP_MARKERS
    early_warning_active: bool = False
    stale_dart_index: int | None = None
    ready_cue_visible: bool = True

    def __post_init__(self) -> None:
        if type(self.control_style) is not ControlStyle:
            _invalid("control_style must be an exact ControlStyle")
        if type(self.phase) is not ThrowControlPhase:
            _invalid("phase must be an exact ThrowControlPhase")
        if self.primary_prompt is not None and type(self.primary_prompt) is not ThrowControlPrompt:
            _invalid("primary_prompt must be an exact ThrowControlPrompt or None")
        if self.secondary_prompt is not None and type(self.secondary_prompt) is not ThrowControlPrompt:
            _invalid("secondary_prompt must be an exact ThrowControlPrompt or None")
        if type(self.curve_level) is not CurveLevel:
            _invalid("curve_level must be an exact CurveLevel")
        if type(self.curve_icon) is not ThrowControlCurveIcon:
            _invalid("curve_icon must be an exact ThrowControlCurveIcon")
        if type(self.power_percent) is not int or self.power_percent not in _POWER_FEEDBACK:
            _invalid("power_percent must be an allowed exact integer")
        if type(self.lane_arrow) is not LaneArrow or type(self.lane_arrow_icon) is not ThrowControlLaneArrowIcon:
            _invalid("lane arrow fields are invalid")
        if type(self.early_warning_active) is not bool or type(self.ready_cue_visible) is not bool:
            _invalid("warning/cue fields are invalid")
        if self.stale_dart_index is not None and (type(self.stale_dart_index) is not int or not 0 <= self.stale_dart_index <= 11):
            _invalid("stale dart index is invalid")
        if type(self.power_feedback) is not PowerFeedback:
            _invalid("power_feedback must be an exact PowerFeedback")
        for name in ("power_locked", "warning_active", "terminal"):
            if type(getattr(self, name)) is not bool:
                _invalid(f"{name} must be an exact bool")
        if self.outcome_kind is not None and type(self.outcome_kind) is not ThrowControlOutcomeKind:
            _invalid("outcome_kind must be an exact ThrowControlOutcomeKind or None")
        if self.curve_icon is not _CURVE_ICONS[self.curve_level]:
            _invalid("curve_icon does not match curve_level")
        if self.power_feedback is not _POWER_FEEDBACK[self.power_percent]:
            _invalid("power_feedback does not match power_percent")
        if self.warning_active and self.phase is not ThrowControlPhase.THROW_READY:
            _invalid("warning_active is allowed only in THROW_READY")
        if (self.primary_prompt, self.secondary_prompt) != _prompts(
            self.phase, self.warning_active
        ):
            _invalid("prompts do not match phase and warning state")
        expected_terminal = self.phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL)
        if self.terminal is not expected_terminal:
            _invalid("terminal does not match phase")
        expected_outcome = {
            ThrowControlPhase.COMPLETE: ThrowControlOutcomeKind.THROW,
            ThrowControlPhase.FOUL: ThrowControlOutcomeKind.FOUL,
        }.get(self.phase)
        if self.outcome_kind is not expected_outcome:
            _invalid("outcome_kind does not match phase")
        locked_phase = self.phase in (
            ThrowControlPhase.THROW_READY,
            ThrowControlPhase.COMPLETE,
            ThrowControlPhase.FOUL,
        )
        if self.power_locked is not locked_phase:
            _invalid("power_locked does not match phase")
        if self.control_style is ControlStyle.QUICK:
            if self.phase not in (
                ThrowControlPhase.THROW_READY,
                ThrowControlPhase.COMPLETE,
                ThrowControlPhase.FOUL,
            ):
                _invalid("Quick Play phase is invalid")
            if self.curve_level is not CurveLevel.STRAIGHT:
                _invalid("Quick Play curve must be STRAIGHT")
            if self.power_percent != 70:
                _invalid("Quick Play power must be 70")

    @property
    def control_style_label(self) -> str:
        return "Quick Play" if self.control_style is ControlStyle.QUICK else "Advanced Play"

    @property
    def primary_prompt_label(self) -> str | None:
        return None if self.primary_prompt is None else self.primary_prompt.label

    @property
    def secondary_prompt_label(self) -> str | None:
        return None if self.secondary_prompt is None else self.secondary_prompt.label

    @property
    def curve_label(self) -> str:
        return self.curve_level.label

    @property
    def curve_strength(self) -> float:
        return self.curve_level.strength

    @property
    def power_feedback_label(self) -> str:
        return self.power_feedback.name


def build_throw_control_presentation(
    snapshot: ThrowControlSnapshot,
) -> ThrowControlPresentation:
    """Translate one exact immutable snapshot without retaining state."""
    if type(snapshot) is not ThrowControlSnapshot:
        _invalid("snapshot must be an exact ThrowControlSnapshot")
    primary, secondary = _prompts(snapshot.phase, snapshot.warning_active)
    outcome_kind = None if snapshot.outcome is None else snapshot.outcome.kind
    return ThrowControlPresentation(
        control_style=snapshot.control_style,
        phase=snapshot.phase,
        primary_prompt=primary,
        secondary_prompt=secondary,
        curve_level=snapshot.curve_level,
        curve_icon=_CURVE_ICONS[snapshot.curve_level],
        power_percent=snapshot.displayed_power_percent,
        power_feedback=snapshot.power_feedback,
        power_locked=snapshot.locked_power_percent is not None,
        warning_active=snapshot.warning_active,
        terminal=snapshot.phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL),
        outcome_kind=outcome_kind,
        lane_arrow=snapshot.lane_arrow,
        early_warning_active=snapshot.early_warning_active,
        stale_dart_index=snapshot.stale_dart_index,
        ready_cue_visible=snapshot.ready_cue_visible,
    )


def build_throw_control_step_presentation(
    result: ThrowControlStepResult,
) -> ThrowControlPresentation:
    """Translate only the snapshot carried by one exact step result."""
    if type(result) is not ThrowControlStepResult:
        _invalid("result must be an exact ThrowControlStepResult")
    return build_throw_control_presentation(result.snapshot)
