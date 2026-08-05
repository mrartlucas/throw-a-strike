"""Deterministic packed RGB888 artwork for the observed emulator main canvas."""

from throw_a_strike.application.throw_control_presentation import (
    ThrowControlCurveIcon, ThrowControlPresentation, ThrowControlPrompt,
)
from throw_a_strike.application.throw_control_style_selection import ThrowControlStyleSelectionSnapshot
from throw_a_strike.domain import ControlStyle, LaneArrow, PlayerColor, ThrowControlPhase
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.domain.pinfall import PIN_CENTERS

EMULATOR_MAIN_WIDTH = 128
EMULATOR_MAIN_HEIGHT = 128
EMULATOR_RGB888_BYTE_LENGTH = 49152

_FONT = {
 "A":("010","101","111","101","101"),"B":("110","101","110","101","110"),
 "C":("011","100","100","100","011"),"D":("110","101","101","101","110"),
 "E":("111","100","110","100","111"),"F":("111","100","110","100","100"),
 "G":("011","100","101","101","011"),"H":("101","101","111","101","101"),
 "I":("111","010","010","010","111"),"J":("001","001","001","101","010"),
 "K":("101","101","110","101","101"),"L":("100","100","100","100","111"),
 "M":("101","111","111","101","101"),"N":("101","111","111","111","101"),
 "O":("010","101","101","101","010"),"P":("110","101","110","100","100"),
 "Q":("010","101","101","111","011"),"R":("110","101","110","101","101"),
 "S":("011","100","010","001","110"),"T":("111","010","010","010","010"),
 "U":("101","101","101","101","111"),"V":("101","101","101","101","010"),
 "W":("101","101","111","111","101"),"X":("101","101","010","101","101"),
 "Y":("101","101","010","010","010"),"Z":("111","001","010","100","111"),
 "0":("111","101","101","101","111"),"1":("010","110","010","010","111"),
 "2":("110","001","010","100","111"),"3":("110","001","010","001","110"),
 "4":("101","101","111","001","001"),"5":("111","100","110","001","110"),
 "6":("011","100","110","101","010"),"7":("111","001","010","010","010"),
 "8":("010","101","010","101","010"),"9":("010","101","011","001","110"),
 "%":("101","001","010","100","101"),"/":("001","001","010","100","100"),"-":("000","000","111","000","000"),
 "<":("001","010","100","010","001"),">":("100","010","001","010","100"),
}
_BG=(8,12,20); _LANE=(52,70,79); _HUD=(12,19,30); _WHITE=(238,244,236)
_RED=(225,55,65); _CYAN=(55,220,225); _YELLOW=(250,210,55); _MUTED=(115,140,150)
_BLUE=(70,135,255)

def _canvas(): return bytearray(_BG * (EMULATOR_MAIN_WIDTH * EMULATOR_MAIN_HEIGHT))
def _pixel(buf,x,y,c):
    if 0 <= x < 128 and 0 <= y < 128:
        i=(y*128+x)*3; buf[i:i+3]=bytes(c)
def _rect(buf,x,y,w,h,c):
    for yy in range(y,y+h):
        for xx in range(x,x+w): _pixel(buf,xx,yy,c)
def _line(buf,x0,y0,x1,y1,c):
    dx=abs(x1-x0); sx=1 if x0<x1 else -1; dy=-abs(y1-y0); sy=1 if y0<y1 else -1; err=dx+dy
    while True:
        _pixel(buf,x0,y0,c)
        if x0==x1 and y0==y1: break
        e=2*err
        if e>=dy: err+=dy; x0+=sx
        if e<=dx: err+=dx; y0+=sy
def _text(buf,text,x,y,c,scale=1):
    for char in text.upper():
        glyph=_FONT.get(char)
        if glyph:
            for gy,row in enumerate(glyph):
                for gx,on in enumerate(row):
                    if on=="1": _rect(buf,x+gx*scale,y+gy*scale,scale,scale,c)
        x += 4*scale
def _center(buf,text,y,c,scale=1): _text(buf,text,(128-(len(text)*4-1)*scale)//2,y,c,scale)
def _draw_upright_pin(buf, x, y):
    _rect(buf,x-3,y-3,7,7,_WHITE); _pixel(buf,x-3,y-3,_LANE); _pixel(buf,x+3,y-3,_LANE)
    _line(buf,x-2,y-1,x+2,y-1,_RED)

def _deck(buf, standing_pins=FULL_RACK):
    _rect(buf,8,0,112,88,_LANE); _line(buf,8,0,8,87,_MUTED); _line(buf,119,0,119,87,_MUTED)
    if type(standing_pins) is not tuple:
        raise TypeError("standing_pins must be a tuple")
    for pin in standing_pins:
        x,y = PIN_CENTERS[pin]
        _draw_upright_pin(buf,x,y)
def _arrow(buf,icon,x,y):
    if icon is ThrowControlCurveIcon.STRAIGHT:
        _line(buf,x+5,y+10,x+5,y+2,_CYAN); _line(buf,x+2,y+5,x+5,y+2,_CYAN); _line(buf,x+8,y+5,x+5,y+2,_CYAN)
    elif icon is ThrowControlCurveIcon.LEFT:
        _line(buf,x+10,y+9,x+5,y+9,_CYAN); _line(buf,x+5,y+9,x+1,y+4,_CYAN); _line(buf,x+1,y+4,x+1,y+8,_CYAN); _line(buf,x+1,y+4,x+5,y+4,_CYAN)
    else:
        _line(buf,x,y+9,x+5,y+9,_CYAN); _line(buf,x+5,y+9,x+9,y+4,_CYAN); _line(buf,x+9,y+4,x+9,y+8,_CYAN); _line(buf,x+9,y+4,x+5,y+4,_CYAN)

def _lane_arrow_hud(buf, selected: LaneArrow, x=45, y=112):
    arrows = list(LaneArrow)
    for i, arrow in enumerate(arrows):
        c = _YELLOW if arrow is selected else _MUTED
        ax = x + i * 5
        _line(buf, ax+2, y, ax, y+4, c); _line(buf, ax+2, y, ax+4, y+4, c); _line(buf, ax+2, y, ax+2, y+7, c)

def _lane_arrow_selector(buf, selected: LaneArrow):
    arrows = list(LaneArrow)
    for i, arrow in enumerate(arrows):
        x = 22 + i * 21; c = _YELLOW if arrow is selected else _MUTED
        if arrow is selected: _rect(buf, x-3, 101, 13, 14, _CYAN)
        _line(buf, x+3, 103, x-1, 111, c); _line(buf, x+3, 103, x+7, 111, c); _line(buf, x+3, 103, x+3, 116, c)

def _power_bar(buf,power,*,y=118):
    """Render seven fixed segments derived only from the displayed percentage."""
    active=(power-30)//10
    for index in range(7):
        _rect(buf,72+index*6,y,4,2,_CYAN if index < active else _MUTED)

def render_throw_control_rgb888(presentation: ThrowControlPresentation, blink_on: bool=True, *, standing_pins=FULL_RACK) -> bytes:
    if type(presentation) is not ThrowControlPresentation or type(blink_on) is not bool: raise TypeError("invalid renderer argument")
    buf=_canvas(); _deck(buf, standing_pins); _rect(buf,0,88,128,40,_HUD); _line(buf,0,88,127,88,_CYAN)
    primary=presentation.primary_prompt
    if primary is ThrowControlPrompt.THROW_READY and not presentation.ready_cue_visible:
        primary = None
    if primary is not None:
        _center(buf,primary.label,91,_YELLOW)
    if presentation.secondary_prompt is not None: _center(buf,presentation.secondary_prompt.label,98,_RED)
    if presentation.phase is ThrowControlPhase.SET_LANE_ARROW:
        _lane_arrow_selector(buf, presentation.lane_arrow)
    _arrow(buf,presentation.curve_icon,5,111)
    _text(buf,presentation.curve_label,19,111,_WHITE)
    _lane_arrow_hud(buf, presentation.lane_arrow)
    power=f"{presentation.power_percent}%"; _text(buf,power,73,111,_WHITE)
    _power_bar(buf,presentation.power_percent)
    _text(buf,presentation.power_feedback_label,72,121,_MUTED)
    _text(buf,"Q" if presentation.control_style is ControlStyle.QUICK else "A",120,111,_CYAN)
    return bytes(buf)

def render_dart_accepted_rgb888(
    presentation: ThrowControlPresentation, dart_index: int, x: int, y: int,
    *, standing_pins=FULL_RACK, result_label: str="DART ACCEPTED"
) -> bytes:
    """Render a completed throw with its unchanged input diagnostics."""
    if type(presentation) is not ThrowControlPresentation:
        raise TypeError("presentation must be exact ThrowControlPresentation")
    if not presentation.terminal or presentation.phase is not ThrowControlPhase.COMPLETE:
        raise ValueError("presentation must describe a completed throw")
    if type(dart_index) is not int or dart_index < 0:
        raise TypeError("dart_index must be an exact nonnegative integer")
    if type(x) is not int or type(y) is not int:
        raise TypeError("x and y must be exact integers")
    diagnostic=f"D{dart_index} X{x} Y{y}"
    if (len(diagnostic)*4-1) > EMULATOR_MAIN_WIDTH:
        raise ValueError("diagnostic text must fit the framebuffer")
    buf=_canvas(); _deck(buf, standing_pins); _rect(buf,0,88,128,40,_HUD); _line(buf,0,88,127,88,_CYAN)
    _center(buf,result_label,91,_YELLOW)
    _center(buf,diagnostic,98,_RED)
    if presentation.phase is ThrowControlPhase.SET_LANE_ARROW:
        _lane_arrow_selector(buf, presentation.lane_arrow)
    _arrow(buf,presentation.curve_icon,5,111)
    _text(buf,presentation.curve_label,19,111,_WHITE)
    _lane_arrow_hud(buf, presentation.lane_arrow)
    _text(buf,f"{presentation.power_percent}%",73,111,_WHITE)
    _power_bar(buf,presentation.power_percent)
    _text(buf,presentation.power_feedback_label,72,121,_MUTED)
    _text(buf,"Q" if presentation.control_style is ControlStyle.QUICK else "A",120,111,_CYAN)
    return bytes(buf)

def render_round_throw_rgb888(presentation: ThrowControlPresentation, throw_number: int,
                              player_number: int, player_color: PlayerColor,
                              blink_on: bool=True, *, standing_pins=FULL_RACK) -> bytes:
    """Render the active round throw with its player and color identity."""
    if type(throw_number) is not int or throw_number not in (1,2): raise TypeError("invalid throw number")
    if type(player_number) is not int or not 1 <= player_number <= 4: raise TypeError("invalid player number")
    if type(player_color) is not PlayerColor: raise TypeError("invalid player color")
    if type(presentation) is not ThrowControlPresentation or type(blink_on) is not bool:
        raise TypeError("invalid renderer argument")
    buf=_canvas(); _deck(buf, standing_pins); _rect(buf,0,88,128,40,_HUD); _line(buf,0,88,127,88,_CYAN)
    _text(buf,f"THROW {throw_number}",2,90,_CYAN)
    color=_BLUE if player_color is PlayerColor.BLUE else _CYAN
    _text(buf,f"P{player_number} {player_color.value.upper()}",99,90,color)
    primary=presentation.primary_prompt
    if primary is ThrowControlPrompt.THROW_READY and not presentation.ready_cue_visible:
        primary = None
    if primary is not None:
        _center(buf,primary.label,96,_YELLOW)
    if presentation.early_warning_active:
        _center(buf,"TOO SOON",96,_YELLOW); _center(buf,"REMOVE DART",102,_RED)
    elif presentation.secondary_prompt is not None:
        _center(buf,presentation.secondary_prompt.label,102,_RED)
    if presentation.phase is ThrowControlPhase.SET_LANE_ARROW:
        _lane_arrow_selector(buf, presentation.lane_arrow)
    _arrow(buf,presentation.curve_icon,5,111)
    _text(buf,presentation.curve_label,19,111,_WHITE)
    _lane_arrow_hud(buf, presentation.lane_arrow)
    _text(buf,f"{presentation.power_percent}%",73,111,_WHITE)
    _power_bar(buf,presentation.power_percent)
    _text(buf,presentation.power_feedback_label,72,121,_MUTED)
    _text(buf,"Q" if presentation.control_style is ControlStyle.QUICK else "A",120,111,_CYAN)
    return bytes(buf)

def render_wrong_color_rgb888(presentation: ThrowControlPresentation, throw_number: int,
                              player_number: int, player_color: PlayerColor,
                              *, standing_pins=FULL_RACK) -> bytes:
    buf=bytearray(render_round_throw_rgb888(
        presentation,throw_number,player_number,player_color, standing_pins=standing_pins))
    _rect(buf,0,89,128,19,_HUD); _center(buf,"WRONG COLOR",91,_YELLOW)
    _center(buf,f"USE {player_color.value.upper()} DART",99,_RED)
    return bytes(buf)

def render_round_complete_rgb888(presentation: ThrowControlPresentation, *, standing_pins=FULL_RACK) -> bytes:
    if type(presentation) is not ThrowControlPresentation: raise TypeError("presentation must be exact")
    buf=_canvas(); _deck(buf, standing_pins); _rect(buf,0,88,128,40,_HUD); _line(buf,0,88,127,88,_CYAN)
    _center(buf,"ROUND COMPLETE",94,_YELLOW)
    return bytes(buf)

def render_style_selection_rgb888(selection: ThrowControlStyleSelectionSnapshot, blink_on: bool=True) -> bytes:
    if type(selection) is not ThrowControlStyleSelectionSnapshot or type(blink_on) is not bool: raise TypeError("invalid renderer argument")
    buf=_canvas(); _center(buf,"THROW A STRIKE",12,_CYAN); _center(buf,"CONTROL STYLE",37,_WHITE)
    label="QUICK PLAY" if selection.selected_style is ControlStyle.QUICK else "ADVANCED PLAY"
    _center(buf,label,62,_YELLOW,1); _text(buf,"<",12,62,_CYAN); _text(buf,">",112,62,_CYAN)
    if blink_on: _center(buf,"A SELECT",91,_WHITE)
    return bytes(buf)
