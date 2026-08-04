"""Pure deterministic swept ball-to-pin collision and authored pinfall."""
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from math import isfinite, sqrt
from numbers import Real

from .ball_trajectory import (BallTrajectory, BallTrajectorySample, ball_trajectory_derivative_at_progress,
    ball_trajectory_point_at_progress, sample_ball_trajectory_progress)
from .bowling_round import BowlingThrowResultKind, FULL_RACK

PIN_RADIUS_PIXELS = 3
BALL_PIN_CONTACT_RADIUS_PIXELS = 6
COLLISION_SUBDIVISIONS = 256
PINFALL_DURATION_SECONDS = 0.750
PINFALL_WAVE_DELAY_SECONDS = 0.120
PINFALL_PIN_DURATION_SECONDS = 0.300
_PIN_CENTERS = {
    1: (64, 72), 2: (54, 56), 3: (74, 56), 4: (44, 40), 5: (64, 40),
    6: (84, 40), 7: (34, 23), 8: (54, 23), 9: (74, 23), 10: (94, 23),
}
_PIN_CHILDREN = {1: (2, 3), 2: (4, 5), 3: (5, 6), 4: (7, 8), 5: (8, 9),
                 6: (9, 10), 7: (), 8: (), 9: (), 10: ()}
PIN_CENTERS = MappingProxyType(_PIN_CENTERS)
PIN_CHILDREN = MappingProxyType(_PIN_CHILDREN)

class InvalidPinfallValueError(ValueError):
    """Raised when pinfall values violate the exact contract."""

class PinImpactBias(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


def _pins(value, name):
    if type(value) is not tuple or any(type(pin) is not int for pin in value):
        raise InvalidPinfallValueError(f"{name} must be an exact tuple of exact ints")
    if value != tuple(sorted(value)) or len(set(value)) != len(value) or any(pin not in PIN_CENTERS for pin in value):
        raise InvalidPinfallValueError(f"{name} must contain unique ascending pin numbers")
    return value

@dataclass(frozen=True)
class PinfallResolution:
    result_kind: BowlingThrowResultKind
    standing_before: tuple[int, ...]
    direct_hit_pin: int | None
    contact_progress: float
    contact_x: int
    contact_y: int
    impact_dx: float
    impact_dy: float
    impact_bias: PinImpactBias
    fall_waves: tuple[tuple[int, ...], ...]
    knocked_down: tuple[int, ...]
    standing_after: tuple[int, ...]
    def __post_init__(self):
        if type(self.result_kind) is not BowlingThrowResultKind:
            raise InvalidPinfallValueError("result_kind must be exact")
        before=_pins(self.standing_before,"standing_before"); knocked=_pins(self.knocked_down,"knocked_down"); after=_pins(self.standing_after,"standing_after")
        if self.direct_hit_pin is not None and (type(self.direct_hit_pin) is not int or self.direct_hit_pin not in before):
            raise InvalidPinfallValueError("direct_hit_pin must be standing or None")
        for value,name in ((self.contact_progress,"contact_progress"),(self.impact_dx,"impact_dx"),(self.impact_dy,"impact_dy")):
            if type(value) is not float or not isfinite(value): raise InvalidPinfallValueError(f"{name} must be finite float")
        if not 0.0 <= self.contact_progress <= 1.0: raise InvalidPinfallValueError("contact_progress out of range")
        if type(self.contact_x) is not int or type(self.contact_y) is not int: raise InvalidPinfallValueError("contact point must be ints")
        if type(self.impact_bias) is not PinImpactBias: raise InvalidPinfallValueError("impact_bias must be exact")
        if type(self.fall_waves) is not tuple or any(type(w) is not tuple for w in self.fall_waves): raise InvalidPinfallValueError("fall_waves must be tuple of tuples")
        flattened=tuple(pin for wave in self.fall_waves for pin in wave)
        if any(_pins(w,"fall_wave") != w for w in self.fall_waves): pass
        if flattened != knocked: raise InvalidPinfallValueError("fall_waves must flatten to knocked_down")
        if any(pin not in before for pin in knocked): raise InvalidPinfallValueError("knocked pins must have been standing")
        if after != tuple(pin for pin in before if pin not in knocked): raise InvalidPinfallValueError("standing_after mismatch")
        if self.result_kind is BowlingThrowResultKind.PIN_HIT:
            if self.direct_hit_pin is None or not knocked: raise InvalidPinfallValueError("PIN_HIT requires knocked pins")
        elif self.result_kind in (BowlingThrowResultKind.MISS, BowlingThrowResultKind.GUTTER):
            if self.direct_hit_pin is not None or knocked or after != before or self.fall_waves != (): raise InvalidPinfallValueError("no-hit must preserve rack")
        else: raise InvalidPinfallValueError("unsupported pinfall result kind")

def _point(trajectory, t):
    return ball_trajectory_point_at_progress(trajectory, t)

def _segment_circle_t(x1,y1,x2,y2,cx,cy,r):
    dx=x2-x1; dy=y2-y1; fx=x1-cx; fy=y1-cy
    a=dx*dx+dy*dy; b=2*(fx*dx+fy*dy); c=fx*fx+fy*fy-r*r
    if a == 0: return 0.0 if c <= 0 else None
    disc=b*b-4*a*c
    if disc < 0: return None
    root=sqrt(disc)
    vals=[(-b-root)/(2*a),(-b+root)/(2*a)]
    hits=[v for v in vals if 0.0 <= v <= 1.0]
    return min(hits) if hits else None

def _bias(trajectory, dx):
    if trajectory.curve_strength < 0: return PinImpactBias.LEFT
    if trajectory.curve_strength > 0: return PinImpactBias.RIGHT
    if dx < -0.25: return PinImpactBias.LEFT
    if dx > 0.25: return PinImpactBias.RIGHT
    return PinImpactBias.CENTER

def _costs(bias):
    return {PinImpactBias.CENTER:(3,3), PinImpactBias.LEFT:(2,4), PinImpactBias.RIGHT:(4,2)}[bias]

def _waves(direct, standing, energy, bias):
    standing=set(standing); knocked={direct: energy}; waves=[(direct,)]; frontier={direct: energy}; lc,rc=_costs(bias)
    while frontier:
        received={}
        for pin,e in frontier.items():
            for child,cost in zip(PIN_CHILDREN[pin], (lc, rc)):
                ne=e-cost
                if child in standing and child not in knocked and ne >= 1:
                    received[child]=max(received.get(child,0), ne)
        if not received: break
        wave=tuple(sorted(received))
        waves.append(wave); knocked.update(received); frontier={pin: received[pin] for pin in wave}
    return tuple(waves), tuple(pin for wave in waves for pin in wave)

def resolve_ball_pinfall(trajectory: BallTrajectory, standing_before: tuple[int,...]=FULL_RACK) -> PinfallResolution:
    if type(trajectory) is not BallTrajectory: raise InvalidPinfallValueError("trajectory must be exact")
    standing=_pins(standing_before,"standing_before")
    best=None
    for i in range(COLLISION_SUBDIVISIONS):
        p0=i/COLLISION_SUBDIVISIONS; p1=(i+1)/COLLISION_SUBDIVISIONS
        x1,y1=_point(trajectory,p0); x2,y2=_point(trajectory,p1)
        for pin in standing:
            cx,cy=PIN_CENTERS[pin]
            local=_segment_circle_t(x1,y1,x2,y2,cx,cy,BALL_PIN_CONTACT_RADIUS_PIXELS)
            if local is None: continue
            progress=p0+(p1-p0)*local
            dx, dy = ball_trajectory_derivative_at_progress(trajectory, progress)
            candidate=(progress,pin,x1+(x2-x1)*local,y1+(y2-y1)*local,dx,dy)
            if best is None or (candidate[0], candidate[1]) < (best[0], best[1]): best=candidate
    if best is None:
        kind = BowlingThrowResultKind.GUTTER if trajectory.target_x <= 19 or trajectory.target_x >= 108 else BowlingThrowResultKind.MISS
        end=sample_ball_trajectory_progress(trajectory,1.0)
        return PinfallResolution(kind, standing, None, 1.0, end.x, end.y, trajectory.arrival_dx, trajectory.arrival_dy, PinImpactBias.CENTER, (), (), standing)
    progress,pin,cx,cy,dx,dy=best; bias=_bias(trajectory,dx); fall_waves, knocked=_waves(pin,standing,trajectory.power_percent//10,bias)
    after=tuple(p for p in standing if p not in knocked)
    return PinfallResolution(BowlingThrowResultKind.PIN_HIT, standing, pin, float(progress), int(cx+0.5), int(cy+0.5), float(dx), float(dy), bias, fall_waves, knocked, after)

def sample_ball_roll(trajectory: BallTrajectory, resolution: PinfallResolution, elapsed_seconds: Real) -> BallTrajectorySample:
    if type(resolution) is not PinfallResolution: raise InvalidPinfallValueError("resolution must be exact")
    if isinstance(elapsed_seconds,bool) or not isinstance(elapsed_seconds,Real): raise InvalidPinfallValueError("elapsed_seconds must be real")
    elapsed=float(elapsed_seconds)
    if not isfinite(elapsed): raise InvalidPinfallValueError("elapsed_seconds finite")
    terminal=resolution.contact_progress if resolution.result_kind is BowlingThrowResultKind.PIN_HIT else 1.0
    progress=max(0.0,min(1.0,elapsed/trajectory.duration_seconds))*terminal
    return sample_ball_trajectory_progress(trajectory,progress)
