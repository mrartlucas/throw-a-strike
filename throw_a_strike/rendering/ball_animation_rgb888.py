"""Packed RGB888 post-throw ball frames."""

from throw_a_strike.application import ThrowControlPresentation
from throw_a_strike.domain import BallTrajectorySample, PlayerColor, ThrowSetup

from .throw_control_rgb888 import (
    EMULATOR_MAIN_HEIGHT, EMULATOR_MAIN_WIDTH, render_dart_accepted_rgb888,
    render_round_throw_rgb888,
)

_COLORS = {
    PlayerColor.BLUE: (70, 135, 255), PlayerColor.RED: (225, 55, 65),
    PlayerColor.GREEN: (55, 205, 100), PlayerColor.YELLOW: (250, 210, 55),
}
_HOLE = (8, 12, 20)


def _draw_ball(frame: bytes, sample: BallTrajectorySample, color: PlayerColor) -> bytes:
    if type(sample) is not BallTrajectorySample or type(color) is not PlayerColor:
        raise TypeError("sample and player color must be exact")
    buf = bytearray(frame)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            if dx * dx + dy * dy <= 9:
                x, y = sample.x + dx, sample.y + dy
                if 0 <= x < EMULATOR_MAIN_WIDTH and 0 <= y < EMULATOR_MAIN_HEIGHT:
                    i = (y * EMULATOR_MAIN_WIDTH + x) * 3
                    buf[i:i + 3] = bytes(_COLORS[color])
    for dx, dy in ((-1, -1), (1, -1)):
        x, y = sample.x + dx, sample.y + dy
        if 0 <= x < EMULATOR_MAIN_WIDTH and 0 <= y < EMULATOR_MAIN_HEIGHT:
            i = (y * EMULATOR_MAIN_WIDTH + x) * 3
            buf[i:i + 3] = bytes(_HOLE)
    return bytes(buf)


def render_ball_roll_rgb888(presentation: ThrowControlPresentation, throw_number: int,
                            player_number: int, player_color: PlayerColor,
                            sample: BallTrajectorySample) -> bytes:
    base = render_round_throw_rgb888(presentation, throw_number, player_number, player_color)
    return _draw_ball(base, sample, player_color)


def render_ball_arrival_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup,
                               player_color: PlayerColor, sample: BallTrajectorySample) -> bytes:
    if type(setup) is not ThrowSetup:
        raise TypeError("setup must be exact")
    base = render_dart_accepted_rgb888(presentation, setup.dart_index, setup.aim_x, setup.aim_y)
    return _draw_ball(base, sample, player_color)
