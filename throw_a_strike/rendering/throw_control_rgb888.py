"""Deterministic packed RGB888 artwork for the observed emulator main canvas."""

from throw_a_strike.application.throw_control_presentation import (
    ThrowControlCurveIcon, ThrowControlPresentation, ThrowControlPrompt,
)
from throw_a_strike.application.throw_control_style_selection import ThrowControlStyleSelectionSnapshot
from throw_a_strike.domain import ControlStyle

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
 "%":("101","001","010","100","101"),"-":("000","000","111","000","000"),
 "<":("001","010","100","010","001"),">":("100","010","001","010","100"),
}
_BG=(8,12,20); _LANE=(52,70,79); _HUD=(12,19,30); _WHITE=(238,244,236)
_RED=(225,55,65); _CYAN=(55,220,225); _YELLOW=(250,210,55); _MUTED=(115,140,150)

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
def _deck(buf):
    _rect(buf,8,0,112,88,_LANE); _line(buf,8,0,8,87,_MUTED); _line(buf,119,0,119,87,_MUTED)
    positions=((64,72),(54,56),(74,56),(44,40),(64,40),(84,40),(34,23),(54,23),(74,23),(94,23))
    for x,y in positions:
        _rect(buf,x-3,y-3,7,7,_WHITE); _pixel(buf,x-3,y-3,_LANE); _pixel(buf,x+3,y-3,_LANE)
        _line(buf,x-2,y-1,x+2,y-1,_RED)
def _arrow(buf,icon,x,y):
    if icon is ThrowControlCurveIcon.STRAIGHT:
        _line(buf,x,y+6,x+10,y+6,_CYAN); _line(buf,x+7,y+3,x+10,y+6,_CYAN); _line(buf,x+7,y+9,x+10,y+6,_CYAN)
    elif icon is ThrowControlCurveIcon.LEFT:
        _line(buf,x+10,y+9,x+5,y+9,_CYAN); _line(buf,x+5,y+9,x+1,y+4,_CYAN); _line(buf,x+1,y+4,x+1,y+8,_CYAN); _line(buf,x+1,y+4,x+5,y+4,_CYAN)
    else:
        _line(buf,x,y+9,x+5,y+9,_CYAN); _line(buf,x+5,y+9,x+9,y+4,_CYAN); _line(buf,x+9,y+4,x+9,y+8,_CYAN); _line(buf,x+9,y+4,x+5,y+4,_CYAN)

def render_throw_control_rgb888(presentation: ThrowControlPresentation, blink_on: bool=True) -> bytes:
    if type(presentation) is not ThrowControlPresentation or type(blink_on) is not bool: raise TypeError("invalid renderer argument")
    buf=_canvas(); _deck(buf); _rect(buf,0,88,128,40,_HUD); _line(buf,0,88,127,88,_CYAN)
    primary=presentation.primary_prompt
    if primary is not None and not (primary is ThrowControlPrompt.THROW_READY and not blink_on):
        _center(buf,primary.label,91,_YELLOW)
    if presentation.secondary_prompt is not None: _center(buf,presentation.secondary_prompt.label,98,_RED)
    _arrow(buf,presentation.curve_icon,5,111)
    _text(buf,presentation.curve_label,19,111,_WHITE)
    power=f"{presentation.power_percent}%"; _text(buf,power,73,111,_WHITE)
    _text(buf,presentation.power_feedback_label,72,121,_MUTED)
    _text(buf,"Q" if presentation.control_style is ControlStyle.QUICK else "A",120,111,_CYAN)
    return bytes(buf)

def render_style_selection_rgb888(selection: ThrowControlStyleSelectionSnapshot, blink_on: bool=True) -> bytes:
    if type(selection) is not ThrowControlStyleSelectionSnapshot or type(blink_on) is not bool: raise TypeError("invalid renderer argument")
    buf=_canvas(); _center(buf,"THROW A STRIKE",12,_CYAN); _center(buf,"CONTROL STYLE",37,_WHITE)
    label="QUICK PLAY" if selection.selected_style is ControlStyle.QUICK else "ADVANCED PLAY"
    _center(buf,label,62,_YELLOW,1); _text(buf,"<",12,62,_CYAN); _text(buf,">",112,62,_CYAN)
    if blink_on: _center(buf,"A SELECT",91,_WHITE)
    return bytes(buf)
