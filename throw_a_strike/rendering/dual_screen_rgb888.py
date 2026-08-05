"""Dartsnut 128x160 full-frame composition and compact 64x32 bowling display."""

from __future__ import annotations

from math import isfinite
from numbers import Real

from throw_a_strike.application import InvalidPortValueError
from throw_a_strike.domain import BallTrajectorySample, BowlingSnapshot, PlayerColor
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.domain.pinfall import PinfallResolution
from .throw_control_rgb888 import _FONT

MAIN_WIDTH = 128
MAIN_HEIGHT = 128
MAIN_RGB888_BYTE_LENGTH = MAIN_WIDTH * MAIN_HEIGHT * 3
SECONDARY_WIDTH = 64
SECONDARY_HEIGHT = 32
SECONDARY_RGB888_BYTE_LENGTH = SECONDARY_WIDTH * SECONDARY_HEIGHT * 3
FULL_FRAME_WIDTH = 128
FULL_FRAME_HEIGHT = 160
FULL_FRAME_RGB888_BYTE_LENGTH = FULL_FRAME_WIDTH * FULL_FRAME_HEIGHT * 3

_BG = (5, 9, 16)
_PANEL = (226, 235, 224)
_DARK = (8, 12, 20)
_WHITE = (245, 246, 239)
_BLACK = (8, 12, 20)
_BLUE = (55, 135, 255)
_RED = (225, 55, 65)
_GREEN = (50, 220, 100)
_YELLOW = (250, 210, 55)
_CYAN = (55, 220, 225)
_MUTED = (90, 110, 120)
_PLAYER_COLORS = {
    PlayerColor.BLUE: _BLUE,
    PlayerColor.RED: _RED,
    PlayerColor.GREEN: _GREEN,
    PlayerColor.YELLOW: _YELLOW,
}


def _secondary_canvas(color: tuple[int, int, int] = _BG) -> bytearray:
    return bytearray(color * (SECONDARY_WIDTH * SECONDARY_HEIGHT))


def _pixel(buf: bytearray, x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= x < SECONDARY_WIDTH and 0 <= y < SECONDARY_HEIGHT:
        offset = (y * SECONDARY_WIDTH + x) * 3
        buf[offset:offset + 3] = bytes(color)


def _rect(buf: bytearray, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
    for yy in range(y, y + height):
        for xx in range(x, x + width):
            _pixel(buf, xx, yy, color)


def _line(buf: bytearray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        _pixel(buf, x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def _text(buf: bytearray, text: str, x: int, y: int, color: tuple[int, int, int], scale: int = 1) -> None:
    for character in text.upper():
        glyph = _FONT.get(character)
        if glyph is not None:
            for gy, row in enumerate(glyph):
                for gx, enabled in enumerate(row):
                    if enabled == "1":
                        _rect(buf, x + gx * scale, y + gy * scale, scale, scale, color)
        x += 4 * scale


def _center(buf: bytearray, text: str, y: int, color: tuple[int, int, int], scale: int = 1) -> None:
    width = max(0, (len(text) * 4 - 1) * scale)
    _text(buf, text, (SECONDARY_WIDTH - width) // 2, y, color, scale)


def _border(buf: bytearray, color: tuple[int, int, int] = _CYAN) -> None:
    _line(buf, 0, 0, 63, 0, color)
    _line(buf, 0, 31, 63, 31, color)
    _line(buf, 0, 0, 0, 31, color)
    _line(buf, 63, 0, 63, 31, color)


def compose_dartsnut_full_frame(main_framebuffer: bytes, secondary_framebuffer: bytes) -> bytes:
    """Place a 128x128 main frame and 64x32 secondary frame into one 128x160 buffer."""
    if type(main_framebuffer) is not bytes or len(main_framebuffer) != MAIN_RGB888_BYTE_LENGTH:
        raise InvalidPortValueError("main framebuffer must be exact 128x128 RGB888 bytes")
    if type(secondary_framebuffer) is not bytes or len(secondary_framebuffer) != SECONDARY_RGB888_BYTE_LENGTH:
        raise InvalidPortValueError("secondary framebuffer must be exact 64x32 RGB888 bytes")
    full = bytearray(_DARK * (FULL_FRAME_WIDTH * FULL_FRAME_HEIGHT))
    full[:MAIN_RGB888_BYTE_LENGTH] = main_framebuffer
    secondary_row_bytes = SECONDARY_WIDTH * 3
    full_row_bytes = FULL_FRAME_WIDTH * 3
    for row in range(SECONDARY_HEIGHT):
        source = row * secondary_row_bytes
        destination = (MAIN_HEIGHT + row) * full_row_bytes
        full[destination:destination + secondary_row_bytes] = secondary_framebuffer[source:source + secondary_row_bytes]
    return bytes(full)


def _validate_score_inputs(bowling: BowlingSnapshot, frame_number: int, roll_number: int, player_number: int) -> None:
    if type(bowling) is not BowlingSnapshot:
        raise InvalidPortValueError("bowling must be exact BowlingSnapshot")
    if type(frame_number) is not int or not 1 <= frame_number <= 10:
        raise InvalidPortValueError("frame_number must be from 1 through 10")
    if type(roll_number) is not int or not 1 <= roll_number <= 3:
        raise InvalidPortValueError("roll_number must be from 1 through 3")
    if type(player_number) is not int or not 1 <= player_number <= 4:
        raise InvalidPortValueError("player_number must be from 1 through 4")


def render_secondary_waiting_rgb888(label: str = "SELECT PLAY") -> bytes:
    if type(label) is not str or not label or len(label) > 15:
        raise InvalidPortValueError("label must be a nonempty string of at most 15 characters")
    buf = _secondary_canvas()
    _border(buf)
    _center(buf, "THROW STRIKE", 5, _CYAN)
    _center(buf, label, 18, _YELLOW)
    return bytes(buf)


def render_secondary_scoreboard_rgb888(
    bowling: BowlingSnapshot,
    frame_number: int,
    roll_number: int,
    *,
    player_number: int = 1,
    player_color: PlayerColor = PlayerColor.BLUE,
    status: str | None = None,
) -> bytes:
    """Render the always-readable compact scoreboard used before each dart."""
    _validate_score_inputs(bowling, frame_number, roll_number, player_number)
    if type(player_color) is not PlayerColor:
        raise InvalidPortValueError("player_color must be exact PlayerColor")
    if status is not None and (type(status) is not str or not status or len(status) > 15):
        raise InvalidPortValueError("status must be None or a nonempty string of at most 15 characters")
    buf = _secondary_canvas(_PANEL)
    _border(buf, _BLUE)
    _line(buf, 1, 8, 62, 8, _MUTED)
    _line(buf, 1, 22, 62, 22, _MUTED)
    _text(buf, f"10P F{frame_number}", 4, 2, _BLACK)
    _text(buf, f"P{player_number}", 5, 11, _PLAYER_COLORS[player_color], scale=2)
    score = min(999, max(0, bowling.confirmed_score))
    _text(buf, f"{score:03d}", 35, 11, _PLAYER_COLORS[player_color], scale=2)
    lower = status if status is not None else f"BALL {roll_number}"
    _center(buf, lower, 25, _BLACK)
    return bytes(buf)


_PIN_POSITIONS = {
    7: (20, 5), 8: (28, 5), 9: (36, 5), 10: (44, 5),
    4: (24, 7), 5: (32, 7), 6: (40, 7),
    2: (28, 9), 3: (36, 9),
    1: (32, 11),
}


def _draw_pin(buf: bytearray, x: int, y: int, *, falling: bool = False) -> None:
    if falling:
        _line(buf, x - 2, y, x + 2, y + 1, _WHITE)
        _pixel(buf, x, y, _RED)
        return
    _pixel(buf, x, y - 1, _WHITE)
    _rect(buf, x - 1, y, 3, 2, _WHITE)
    _line(buf, x - 1, y, x + 1, y, _RED)


def _draw_action_lane(buf: bytearray) -> None:
    _rect(buf, 0, 0, 64, 32, (4, 10, 24))
    _rect(buf, 20, 2, 25, 11, (5, 6, 10))
    _line(buf, 19, 3, 2, 31, _BLUE)
    _line(buf, 45, 3, 61, 31, _BLUE)
    _line(buf, 20, 13, 44, 13, _YELLOW)
    for y in range(14, 32, 4):
        _line(buf, max(3, 18 - (y - 14) // 2), y, min(60, 46 + (y - 14) // 2), y, (28, 50, 68))


def render_secondary_ball_roll_rgb888(
    sample: BallTrajectorySample,
    standing_pins: tuple[int, ...] = FULL_RACK,
    *,
    player_color: PlayerColor = PlayerColor.BLUE,
) -> bytes:
    if type(sample) is not BallTrajectorySample:
        raise InvalidPortValueError("sample must be exact BallTrajectorySample")
    if type(standing_pins) is not tuple or any(pin not in FULL_RACK for pin in standing_pins):
        raise InvalidPortValueError("standing_pins must be a valid tuple")
    if type(player_color) is not PlayerColor:
        raise InvalidPortValueError("player_color must be exact PlayerColor")
    buf = _secondary_canvas()
    _draw_action_lane(buf)
    for pin in standing_pins:
        x, y = _PIN_POSITIONS[pin]
        _draw_pin(buf, x, y)
    ball_x = max(8, min(55, 32 + round((sample.x - 64) * 0.22)))
    ball_y = max(14, min(28, 28 - round(sample.progress * 14)))
    color = _PLAYER_COLORS[player_color]
    _rect(buf, ball_x - 2, ball_y - 2, 5, 5, color)
    _pixel(buf, ball_x - 1, ball_y - 1, _DARK)
    _pixel(buf, ball_x + 1, ball_y - 1, _DARK)
    return bytes(buf)


def render_secondary_pinfall_rgb888(
    sample: BallTrajectorySample,
    resolution: PinfallResolution,
    elapsed_seconds: Real,
    *,
    player_color: PlayerColor = PlayerColor.BLUE,
) -> bytes:
    if type(sample) is not BallTrajectorySample or type(resolution) is not PinfallResolution:
        raise InvalidPortValueError("sample and resolution must be exact")
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, Real):
        raise InvalidPortValueError("elapsed_seconds must be a finite nonnegative real")
    elapsed = float(elapsed_seconds)
    if not isfinite(elapsed) or elapsed < 0:
        raise InvalidPortValueError("elapsed_seconds must be a finite nonnegative real")
    if type(player_color) is not PlayerColor:
        raise InvalidPortValueError("player_color must be exact PlayerColor")
    buf = bytearray(render_secondary_ball_roll_rgb888(sample, resolution.standing_before, player_color=player_color))
    progress = min(1.0, elapsed / 0.8)
    for pin in resolution.knocked_down:
        x, y = _PIN_POSITIONS[pin]
        _rect(buf, x - 2, y - 2, 5, 5, (4, 10, 24))
        _draw_pin(buf, x + round((pin % 3 - 1) * 3 * progress), y + round(4 * progress), falling=True)
    if resolution.knocked_down:
        for dx, dy in ((-4, -2), (4, -2), (-5, 2), (5, 2)):
            _pixel(buf, 32 + dx, 12 + dy, _YELLOW)
    return bytes(buf)


def render_secondary_result_rgb888(
    label: str,
    bowling: BowlingSnapshot,
    frame_number: int,
    roll_number: int,
    *,
    player_number: int = 1,
    player_color: PlayerColor = PlayerColor.BLUE,
) -> bytes:
    _validate_score_inputs(bowling, frame_number, roll_number, player_number)
    if type(label) is not str or not label or len(label) > 15:
        raise InvalidPortValueError("label must be a nonempty string of at most 15 characters")
    if type(player_color) is not PlayerColor:
        raise InvalidPortValueError("player_color must be exact PlayerColor")
    buf = _secondary_canvas()
    color = _YELLOW if label in ("STRIKE", "SPARE", "TURKEY") else _CYAN
    _border(buf, color)
    _text(buf, f"10P F{frame_number}", 3, 2, _CYAN)
    large = label if len(label) <= 7 else label[:7]
    _center(buf, large, 10, color, scale=2 if len(large) <= 7 else 1)
    _center(buf, f"P{player_number} {bowling.confirmed_score:03d}", 25, _PLAYER_COLORS[player_color])
    return bytes(buf)


def render_secondary_game_over_rgb888(
    bowling: BowlingSnapshot,
    *,
    player_number: int = 1,
    player_color: PlayerColor = PlayerColor.BLUE,
) -> bytes:
    if type(bowling) is not BowlingSnapshot or not bowling.complete:
        raise InvalidPortValueError("bowling must be a complete exact BowlingSnapshot")
    if type(player_number) is not int or not 1 <= player_number <= 4 or type(player_color) is not PlayerColor:
        raise InvalidPortValueError("player identity is invalid")
    buf = _secondary_canvas()
    _border(buf, _YELLOW)
    _center(buf, "GAMEOVER", 3, _CYAN)
    _center(buf, "WINNER", 11, _YELLOW, scale=2)
    _center(buf, f"P{player_number} {bowling.confirmed_score:03d}", 25, _PLAYER_COLORS[player_color])
    return bytes(buf)


__all__ = (
    "MAIN_WIDTH", "MAIN_HEIGHT", "MAIN_RGB888_BYTE_LENGTH",
    "SECONDARY_WIDTH", "SECONDARY_HEIGHT", "SECONDARY_RGB888_BYTE_LENGTH",
    "FULL_FRAME_WIDTH", "FULL_FRAME_HEIGHT", "FULL_FRAME_RGB888_BYTE_LENGTH",
    "compose_dartsnut_full_frame", "render_secondary_waiting_rgb888",
    "render_secondary_scoreboard_rgb888", "render_secondary_ball_roll_rgb888",
    "render_secondary_pinfall_rgb888", "render_secondary_result_rgb888",
    "render_secondary_game_over_rgb888",
)
