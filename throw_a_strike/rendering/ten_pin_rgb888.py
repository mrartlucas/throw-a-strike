"""RGB888 scoring HUD renderers for the single-player ten-pin emulator."""
from throw_a_strike.application import ThrowControlPresentation
from throw_a_strike.domain import BowlingSnapshot, PlayerColor, ThrowSetup
from throw_a_strike.domain.pinfall import PinfallResolution
from throw_a_strike.domain.ball_trajectory import BallTrajectorySample
from throw_a_strike.domain.bowling_round import FULL_RACK
from .throw_control_rgb888 import (_canvas, _deck, _rect, _line, _text, _center, _arrow, _power_bar,
    _HUD, _CYAN, _YELLOW, _RED, _WHITE, _MUTED, EMULATOR_RGB888_BYTE_LENGTH, render_wrong_color_rgb888)
from .ball_animation_rgb888 import _draw_ball
from .pinfall_animation_rgb888 import _standing_during, _draw_falling_pin
from throw_a_strike.domain.pinfall import PIN_CENTERS


def _hud_base(standing_pins=FULL_RACK):
    buf=_canvas(); _deck(buf, standing_pins); _rect(buf,0,88,128,40,_HUD); _line(buf,0,88,127,88,_CYAN); return buf

def _frame_text(frame):
    marks="".join(frame.marks) or "_"
    score="..." if frame.cumulative_score is None else str(frame.cumulative_score)
    return f"F{frame.number}{marks}{score}"

def _strip(buf, bowling):
    if bowling is None: return
    started=[f for f in bowling.frames if f.rolls or f.number==bowling.current_frame]
    for i,frame in enumerate(started[-3:]): _text(buf,_frame_text(frame)[:10],2+i*42,81,_WHITE)

def _status(buf, presentation, bowling, label=None):
    frame=bowling.current_frame if bowling else 1; roll=bowling.current_roll or 0 if bowling else 1; score=bowling.confirmed_score if bowling else 0
    _text(buf,f"F{frame} R{roll}",2,90,_CYAN); _text(buf,f"S{score}",92,90,_CYAN)
    if label: _center(buf,label,97,_YELLOW)
    else:
        p=presentation.primary_prompt
        if p is not None: _center(buf,p.label,97,_YELLOW)
        if presentation.secondary_prompt is not None: _center(buf,presentation.secondary_prompt.label,103,_RED)
    _arrow(buf,presentation.curve_icon,5,111); _text(buf,presentation.curve_label,19,111,_WHITE)
    _text(buf,f"{presentation.power_percent}%",73,111,_WHITE); _power_bar(buf,presentation.power_percent)
    _text(buf,presentation.power_feedback_label,72,121,_MUTED)

def render_ten_pin_attempt_rgb888(presentation: ThrowControlPresentation, bowling: BowlingSnapshot, standing_pins=FULL_RACK, blink_on: bool=True) -> bytes:
    buf=_hud_base(standing_pins); _strip(buf,bowling); _status(buf,presentation,bowling if blink_on else bowling); return bytes(buf)

def render_ten_pin_ball_roll_rgb888(presentation, bowling, standing_pins, sample: BallTrajectorySample, player_color: PlayerColor) -> bytes:
    return _draw_ball(render_ten_pin_attempt_rgb888(presentation,bowling,standing_pins),sample,player_color)

def render_ten_pin_pinfall_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup, player_color: PlayerColor, sample: BallTrajectorySample, resolution: PinfallResolution, elapsed_seconds: float, bowling: BowlingSnapshot) -> bytes:
    standing, falling = _standing_during(resolution, max(0.0,float(elapsed_seconds)))
    buf=bytearray(render_ten_pin_attempt_rgb888(presentation,bowling,standing))
    for pin, progress in falling:
        x,y=PIN_CENTERS[pin]; _draw_falling_pin(buf,x,y,resolution.impact_bias,progress)
    return _draw_ball(bytes(buf),sample,player_color)

def render_ten_pin_result_rgb888(presentation: ThrowControlPresentation, setup: ThrowSetup, player_color: PlayerColor, sample: BallTrajectorySample, resolution: PinfallResolution, bowling: BowlingSnapshot, result_label: str) -> bytes:
    standing = resolution.standing_after if result_label not in ("MISS","GUTTER") else resolution.standing_before
    buf=_hud_base(standing); _strip(buf,bowling); _status(buf,presentation,bowling,result_label)
    diag=f"D{setup.dart_index} X{setup.aim_x} Y{setup.aim_y}"; _center(buf,diag,104,_RED)
    return _draw_ball(bytes(buf),sample,player_color)

def render_ten_pin_wrong_color_rgb888(presentation: ThrowControlPresentation, bowling: BowlingSnapshot, standing_pins=FULL_RACK) -> bytes:
    buf=bytearray(render_ten_pin_attempt_rgb888(presentation,bowling,standing_pins)); _rect(buf,0,94,128,14,_HUD); _center(buf,"WRONG COLOR",94,_YELLOW); _center(buf,"USE BLUE DART",102,_RED); return bytes(buf)

def render_ten_pin_foul_rgb888(presentation: ThrowControlPresentation, bowling: BowlingSnapshot, standing_pins=FULL_RACK) -> bytes:
    buf=_hud_base(standing_pins); _strip(buf,bowling); _status(buf,presentation,bowling,"FOUL"); return bytes(buf)

def render_ten_pin_game_over_rgb888(bowling: BowlingSnapshot) -> bytes:
    buf=_canvas(); _center(buf,"THROW A STRIKE",5,_CYAN); _center(buf,"GAME OVER",18,_YELLOW); _center(buf,f"FINAL {bowling.confirmed_score}",31,_WHITE)
    for index,frame in enumerate(bowling.frames):
        x=2+(index%5)*25; y=50 if index<5 else 83
        _text(buf,f"F{frame.number}",x,y,_CYAN); _text(buf,"".join(frame.marks) or "-",x,y+8,_YELLOW); _text(buf,"" if frame.cumulative_score is None else str(frame.cumulative_score),x,y+16,_WHITE)
    return bytes(buf)
