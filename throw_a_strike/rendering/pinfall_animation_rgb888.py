"""Deterministic RGB888 pinfall animation frames."""
from throw_a_strike.application import ThrowControlPresentation
from throw_a_strike.domain import PlayerColor, ThrowSetup
from throw_a_strike.domain.pinfall import (PIN_CENTERS, PINFALL_PIN_DURATION_SECONDS,
    PINFALL_WAVE_DELAY_SECONDS, PinImpactBias, PinfallResolution)
from .ball_animation_rgb888 import _draw_ball
from .throw_control_rgb888 import _RED, _WHITE, _deck, _line, _rect, _canvas, _power_bar, _arrow, _text, _center, _HUD, _CYAN, _YELLOW, _MUTED, EMULATOR_MAIN_WIDTH, EMULATOR_MAIN_HEIGHT, render_dart_accepted_rgb888
from throw_a_strike.domain.ball_trajectory import BallTrajectorySample
from throw_a_strike.domain.bowling_round import BowlingThrowResultKind
from throw_a_strike.domain import ControlStyle


def _pose_offsets(bias, progress):
    if bias is PinImpactBias.LEFT: return round(-4*progress), round(-2*progress)
    if bias is PinImpactBias.RIGHT: return round(4*progress), round(-2*progress)
    return 0, round(-4*progress)

def _draw_falling_pin(buf, x, y, bias, progress):
    ox, oy = _pose_offsets(bias, progress)
    width = 7; height = max(3, round(7 - 4*progress))
    _rect(buf, x-3+ox, y-height//2+oy, width, height, _WHITE)
    _line(buf, x-2+ox, y-1+oy, x+2+ox, y-1+oy, _RED)

def _standing_during(resolution, elapsed):
    standing = set(resolution.standing_after)
    falling = []
    for wi, wave in enumerate(resolution.fall_waves):
        start = wi * PINFALL_WAVE_DELAY_SECONDS
        for pin in wave:
            if elapsed < start:
                standing.add(pin)
            elif elapsed < start + PINFALL_PIN_DURATION_SECONDS:
                falling.append((pin, (elapsed-start)/PINFALL_PIN_DURATION_SECONDS))
    return tuple(sorted(standing)), falling

def render_pinfall_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup,
                          player_color: PlayerColor, sample: BallTrajectorySample,
                          resolution: PinfallResolution, elapsed_seconds: float) -> bytes:
    standing, falling = _standing_during(resolution, max(0.0, float(elapsed_seconds)))
    buf = bytearray(render_dart_accepted_rgb888(presentation, setup.dart_index, setup.aim_x, setup.aim_y,
                                                standing_pins=standing, result_label=f"{len(resolution.knocked_down)} PINS"))
    for pin, progress in falling:
        x,y = PIN_CENTERS[pin]
        _draw_falling_pin(buf, x, y, resolution.impact_bias, progress)
    return _draw_ball(bytes(buf), sample, player_color)

def render_throw_result_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup,
                               player_color: PlayerColor, sample: BallTrajectorySample,
                               resolution: PinfallResolution) -> bytes:
    if resolution.result_kind is BowlingThrowResultKind.PIN_HIT:
        label=f"{len(resolution.knocked_down)} PINS"; standing=resolution.standing_after
    elif resolution.result_kind is BowlingThrowResultKind.GUTTER:
        label="GUTTER"; standing=resolution.standing_before
    else:
        label="MISS"; standing=resolution.standing_before
    base=render_dart_accepted_rgb888(presentation, setup.dart_index, setup.aim_x, setup.aim_y,
                                     standing_pins=standing, result_label=label)
    return _draw_ball(base, sample, player_color)
