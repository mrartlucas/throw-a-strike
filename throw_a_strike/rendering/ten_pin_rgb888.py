"""RGB888 scoring HUD renderers for the single-player ten-pin emulator."""
from dataclasses import dataclass
from math import isfinite
from numbers import Real

from throw_a_strike.application import InvalidPortValueError, ThrowControlPresentation, ThrowControlPrompt
from throw_a_strike.domain import BowlingSnapshot, FrameSnapshot, PlayerColor, ThrowSetup, ThrowControlPhase
from throw_a_strike.domain.pinfall import PinfallResolution, PIN_CENTERS
from throw_a_strike.domain.ball_trajectory import BallTrajectorySample
from throw_a_strike.domain.bowling_round import FULL_RACK
from .throw_control_rgb888 import (_canvas, _deck, _rect, _line, _text, _center, _arrow, _power_bar,
    _HUD, _CYAN, _YELLOW, _RED, _WHITE, _MUTED, EMULATOR_MAIN_WIDTH, EMULATOR_MAIN_HEIGHT)
from .ball_animation_rgb888 import _draw_ball
from .pinfall_animation_rgb888 import _standing_during, _draw_falling_pin


@dataclass(frozen=True)
class TenPinRenderContext:
    frame_number: int
    roll_number: int

    def __post_init__(self):
        if type(self.frame_number) is not int or not 1 <= self.frame_number <= 10:
            raise InvalidPortValueError("frame_number must be an exact int from 1 through 10")
        max_roll = 3 if self.frame_number == 10 else 2
        if type(self.roll_number) is not int or not 1 <= self.roll_number <= max_roll:
            raise InvalidPortValueError("roll_number is invalid for frame")


def _require_presentation(presentation, *, terminal=None, complete=None):
    if type(presentation) is not ThrowControlPresentation:
        raise InvalidPortValueError("presentation must be exact ThrowControlPresentation")
    if terminal is not None and presentation.terminal is not terminal:
        raise InvalidPortValueError("presentation terminal state is invalid")
    if complete is not None and (presentation.phase is ThrowControlPhase.COMPLETE) is not complete:
        raise InvalidPortValueError("presentation completion state is invalid")


def _require_bowling(bowling, *, complete=None):
    if type(bowling) is not BowlingSnapshot:
        raise InvalidPortValueError("bowling must be exact BowlingSnapshot")
    if complete is not None and bowling.complete is not complete:
        raise InvalidPortValueError("bowling completion state is invalid")


def _require_context(context):
    if type(context) is not TenPinRenderContext:
        raise InvalidPortValueError("context must be exact TenPinRenderContext")


def _require_standing(standing_pins):
    if type(standing_pins) is not tuple:
        raise InvalidPortValueError("standing_pins must be an exact tuple")
    if standing_pins != tuple(sorted(standing_pins)) or len(set(standing_pins)) != len(standing_pins):
        raise InvalidPortValueError("standing_pins must be unique and ascending")
    if any(type(pin) is not int or pin not in FULL_RACK for pin in standing_pins):
        raise InvalidPortValueError("standing_pins must contain pin numbers")


def context_from_bowling(bowling: BowlingSnapshot) -> TenPinRenderContext:
    _require_bowling(bowling)
    return TenPinRenderContext(bowling.current_frame, bowling.current_roll or 1)


def _hud_base(standing_pins=FULL_RACK):
    _require_standing(standing_pins)
    buf = _canvas(); _deck(buf, standing_pins); _rect(buf, 0, 88, 128, 40, _HUD); _line(buf, 0, 88, 127, 88, _CYAN); return buf


def _frame_text(frame: FrameSnapshot):
    marks = "".join(frame.marks) or "_"
    score = "" if frame.cumulative_score is None else str(frame.cumulative_score)
    return f"F{frame.number}{marks}{score}"


def _strip(buf, bowling):
    started = [f for f in bowling.frames if f.rolls or f.number == bowling.current_frame]
    for index, frame in enumerate(started[-3:]):
        _text(buf, _frame_text(frame)[:10], 2 + index * 42, 108, _WHITE)


def _prompt_label(presentation, blink_on):
    prompt = presentation.primary_prompt
    if prompt is ThrowControlPrompt.THROW_READY and not presentation.ready_cue_visible:
        return None
    return None if prompt is None else prompt.label


def _status(buf, presentation, bowling, context, *, label=None, blink_on=True, diagnostic=None):
    """Screen 1 owns aiming and throw controls; score/frame status lives below."""
    if label is not None:
        _center(buf, label, 92, _YELLOW)
    else:
        primary = _prompt_label(presentation, blink_on)
        if primary is not None:
            _center(buf, primary, 92, _YELLOW)
        if presentation.secondary_prompt is not None:
            _center(buf, presentation.secondary_prompt.label, 99, _RED)
    if diagnostic is not None:
        _center(buf, diagnostic, 99, _RED)
    if presentation.phase is ThrowControlPhase.SET_AIM:
        from .throw_control_rgb888 import _lane_arrow_selector
        _lane_arrow_selector(buf, presentation.lane_arrow)
        return
    _arrow(buf, presentation.curve_icon, 5, 113)
    _text(buf, presentation.curve_label, 19, 113, _WHITE)
    from .throw_control_rgb888 import _lane_arrow_hud
    _lane_arrow_hud(buf, presentation.lane_arrow, x=42, y=112)
    _text(buf, f"{presentation.power_percent}%", 76, 113, _WHITE)
    _power_bar(buf, presentation.power_percent, y=120)
    _text(buf, presentation.power_feedback_label, 72, 123, _MUTED)


def render_ten_pin_attempt_rgb888(presentation: ThrowControlPresentation, bowling: BowlingSnapshot, standing_pins=FULL_RACK, blink_on: bool=True, *, context: TenPinRenderContext | None = None) -> bytes:
    _require_presentation(presentation, terminal=False)
    _require_bowling(bowling, complete=False)
    if type(blink_on) is not bool:
        raise InvalidPortValueError("blink_on must be exact bool")
    context = context_from_bowling(bowling) if context is None else context
    _require_context(context)
    buf = _hud_base(standing_pins); _status(buf, presentation, bowling, context, blink_on=blink_on); return bytes(buf)


def render_ten_pin_ball_roll_rgb888(presentation, bowling, standing_pins, sample: BallTrajectorySample, player_color: PlayerColor, *, context: TenPinRenderContext | None = None) -> bytes:
    _require_presentation(presentation, terminal=True, complete=True); _require_bowling(bowling, complete=False)
    if type(sample) is not BallTrajectorySample or type(player_color) is not PlayerColor:
        raise InvalidPortValueError("sample and player_color must be exact")
    context = context_from_bowling(bowling) if context is None else context
    _require_context(context)
    buf = _hud_base(standing_pins); _status(buf, presentation, bowling, context)
    return _draw_ball(bytes(buf), sample, player_color)


def render_ten_pin_pinfall_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup, player_color: PlayerColor, sample: BallTrajectorySample, resolution: PinfallResolution, elapsed_seconds: float, bowling: BowlingSnapshot, *, context: TenPinRenderContext | None = None) -> bytes:
    _require_presentation(presentation, terminal=True, complete=True)
    if type(setup) is not ThrowSetup or type(player_color) is not PlayerColor or type(sample) is not BallTrajectorySample or type(resolution) is not PinfallResolution:
        raise InvalidPortValueError("pinfall renderer arguments must be exact")
    context = context_from_bowling(bowling) if context is None else context
    _require_context(context)
    _require_bowling(bowling, complete=False)
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, Real):
        raise InvalidPortValueError("elapsed_seconds must be finite nonnegative")
    elapsed = float(elapsed_seconds)
    if not isfinite(elapsed) or elapsed < 0:
        raise InvalidPortValueError("elapsed_seconds must be finite nonnegative")
    standing, falling = _standing_during(resolution, elapsed)
    buf = _hud_base(standing); _status(buf, presentation, bowling, context)
    buf = bytearray(buf)
    for pin, progress in falling:
        x, y = PIN_CENTERS[pin]; _draw_falling_pin(buf, x, y, resolution.impact_bias, progress)
    return _draw_ball(bytes(buf), sample, player_color)


def render_ten_pin_result_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup, player_color: PlayerColor, sample: BallTrajectorySample, resolution: PinfallResolution, bowling: BowlingSnapshot, result_label: str, *, context: TenPinRenderContext) -> bytes:
    _require_presentation(presentation, terminal=True, complete=True); _require_bowling(bowling)
    _require_context(context)
    if type(setup) is not ThrowSetup or type(player_color) is not PlayerColor or type(sample) is not BallTrajectorySample or type(resolution) is not PinfallResolution or type(result_label) is not str or not result_label:
        raise InvalidPortValueError("result renderer arguments must be exact")
    standing = resolution.standing_after if result_label not in ("MISS", "GUTTER") else resolution.standing_before
    buf = _hud_base(standing); _status(buf, presentation, bowling, context, label=result_label, diagnostic=f"D{setup.dart_index} X{setup.aim_x} Y{setup.aim_y}")
    return _draw_ball(bytes(buf), sample, player_color)


def render_ten_pin_wrong_color_rgb888(presentation: ThrowControlPresentation, bowling: BowlingSnapshot, standing_pins=FULL_RACK) -> bytes:
    frame = render_ten_pin_attempt_rgb888(presentation, bowling, standing_pins, blink_on=True)
    buf = bytearray(frame); _rect(buf, 0, 95, 128, 19, _HUD); _center(buf, "WRONG COLOR", 96, _YELLOW); _center(buf, "USE BLUE DART", 103, _RED); return bytes(buf)


def render_ten_pin_foul_rgb888(presentation: ThrowControlPresentation, bowling: BowlingSnapshot, standing_pins=FULL_RACK, *, context: TenPinRenderContext) -> bytes:
    _require_presentation(presentation, terminal=True, complete=False); _require_bowling(bowling)
    _require_context(context)
    buf = _hud_base(standing_pins); _status(buf, presentation, bowling, context, label="FOUL"); return bytes(buf)


def render_ten_pin_game_over_rgb888(bowling: BowlingSnapshot) -> bytes:
    _require_bowling(bowling, complete=True)
    buf = _canvas()
    _deck(buf, FULL_RACK)
    _rect(buf, 0, 88, 128, 40, _HUD)
    _line(buf, 0, 88, 127, 88, _CYAN)
    _center(buf, "GAME OVER", 96, _YELLOW, scale=2)
    _center(buf, "FINAL SCORE BELOW", 119, _WHITE)
    return bytes(buf)
