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


class PinContactBand(str, Enum):
    LEFT_CONTACT = "left_contact"
    NEAR_LEFT_POCKET = "near_left_pocket"
    CENTER_CONTACT = "center_contact"
    NEAR_RIGHT_POCKET = "near_right_pocket"
    RIGHT_CONTACT = "right_contact"


CONTACT_BAND_LEFT_MAX = -3.25
CONTACT_BAND_NEAR_LEFT_MAX = -1.00
CONTACT_BAND_CENTER_MAX = 1.00
CONTACT_BAND_NEAR_RIGHT_MAX = 3.25
ARCADE_CONTACT_RADIUS_PIXELS = BALL_PIN_CONTACT_RADIUS_PIXELS
TRANSFER_ADJACENCY_PIXELS = 23


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
        before = _pins(self.standing_before, "standing_before")
        knocked = _pins(self.knocked_down, "knocked_down")
        after = _pins(self.standing_after, "standing_after")
        if self.direct_hit_pin is not None and type(self.direct_hit_pin) is not int:
            raise InvalidPinfallValueError("direct_hit_pin must be an exact int or None")
        for value, name in ((self.contact_progress, "contact_progress"),
                            (self.impact_dx, "impact_dx"), (self.impact_dy, "impact_dy")):
            if type(value) is not float or not isfinite(value):
                raise InvalidPinfallValueError(f"{name} must be finite float")
        if not 0.0 <= self.contact_progress <= 1.0:
            raise InvalidPinfallValueError("contact_progress out of range")
        if type(self.contact_x) is not int or type(self.contact_y) is not int:
            raise InvalidPinfallValueError("contact point must be exact ints")
        if not 0 <= self.contact_x <= 127 or not 0 <= self.contact_y <= 127:
            raise InvalidPinfallValueError("contact point must be inside the framebuffer")
        if type(self.impact_bias) is not PinImpactBias:
            raise InvalidPinfallValueError("impact_bias must be exact")
        if type(self.fall_waves) is not tuple:
            raise InvalidPinfallValueError("fall_waves must be an exact tuple")

        seen = set()
        flattened = []
        for wave in self.fall_waves:
            if type(wave) is not tuple:
                raise InvalidPinfallValueError("each fall wave must be an exact tuple")
            _pins(wave, "fall_wave")
            if not wave:
                raise InvalidPinfallValueError("fall waves must be non-empty")
            for pin in wave:
                if pin in seen:
                    raise InvalidPinfallValueError("a pin may appear in only one fall wave")
                seen.add(pin)
                flattened.append(pin)
        flattened = tuple(flattened)
        if tuple(sorted(flattened)) != knocked:
            raise InvalidPinfallValueError("fall_waves must cover knocked_down exactly")
        if any(pin not in before for pin in knocked):
            raise InvalidPinfallValueError("knocked pins must have been standing")
        if after != tuple(pin for pin in before if pin not in knocked):
            raise InvalidPinfallValueError("standing_after mismatch")

        if self.result_kind is BowlingThrowResultKind.PIN_HIT:
            if self.direct_hit_pin not in before:
                raise InvalidPinfallValueError("PIN_HIT direct_hit_pin must be standing")
            if not self.fall_waves:
                raise InvalidPinfallValueError("PIN_HIT requires fall waves")
            if self.fall_waves[0] != (self.direct_hit_pin,):
                raise InvalidPinfallValueError("PIN_HIT first wave must be the direct hit pin")
            if self.direct_hit_pin not in knocked or not knocked:
                raise InvalidPinfallValueError("PIN_HIT requires knocked direct hit pin")
        elif self.result_kind in (BowlingThrowResultKind.MISS, BowlingThrowResultKind.GUTTER):
            if self.direct_hit_pin is not None:
                raise InvalidPinfallValueError("no-hit direct_hit_pin must be None")
            if self.contact_progress != 1.0:
                raise InvalidPinfallValueError("no-hit contact_progress must be exactly one")
            if self.fall_waves != () or knocked != () or after != before:
                raise InvalidPinfallValueError("no-hit results must preserve the rack")
        else:
            raise InvalidPinfallValueError("unsupported pinfall result kind")

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

def classify_pin_contact_band(pin: int, contact_x: Real) -> PinContactBand:
    if type(pin) is not int or pin not in PIN_CENTERS:
        raise InvalidPinfallValueError("pin must be an exact pin number")
    if isinstance(contact_x, bool) or not isinstance(contact_x, Real):
        raise InvalidPinfallValueError("contact_x must be a finite real")
    offset = float(contact_x) - PIN_CENTERS[pin][0]
    if not isfinite(offset):
        raise InvalidPinfallValueError("contact_x must be finite")
    if offset <= CONTACT_BAND_LEFT_MAX:
        return PinContactBand.LEFT_CONTACT
    if offset <= CONTACT_BAND_NEAR_LEFT_MAX:
        return PinContactBand.NEAR_LEFT_POCKET
    if offset <= CONTACT_BAND_CENTER_MAX:
        return PinContactBand.CENTER_CONTACT
    if offset <= CONTACT_BAND_NEAR_RIGHT_MAX:
        return PinContactBand.NEAR_RIGHT_POCKET
    return PinContactBand.RIGHT_CONTACT


def _bias(trajectory, direct, contact_x, dx):
    offset = contact_x - PIN_CENTERS[direct][0]
    # Positive transfer points toward larger-x pins. A left-side hit therefore
    # sends energy right; a right-side hit sends it left. Curve and entry angle
    # can help or hurt that authored contact-side tendency.
    transfer = (-offset / ARCADE_CONTACT_RADIUS_PIXELS) * 1.40 + trajectory.curve_strength * 0.55 + (dx / 32.0) * 0.35
    if transfer < -0.30:
        return PinImpactBias.LEFT
    if transfer > 0.30:
        return PinImpactBias.RIGHT
    return PinImpactBias.CENTER


def _initial_energy(trajectory, direct, contact_x, dx):
    band = classify_pin_contact_band(direct, contact_x)
    band_bonus = {
        PinContactBand.LEFT_CONTACT: 0.15,
        PinContactBand.NEAR_LEFT_POCKET: 0.85,
        PinContactBand.CENTER_CONTACT: 1.15,
        PinContactBand.NEAR_RIGHT_POCKET: 0.85,
        PinContactBand.RIGHT_CONTACT: 0.15,
    }[band]
    entry_bonus = max(0.0, 0.65 - abs(dx) / 20.0)
    curve_bonus = min(0.65, abs(trajectory.curve_strength) * 0.45)
    return trajectory.power_percent / 10.0 - 1.10 + band_bonus + entry_bonus + curve_bonus


def _neighbor_pins(pin, standing):
    x, y = PIN_CENTERS[pin]
    neighbors = []
    for other in standing:
        if other == pin:
            continue
        ox, oy = PIN_CENTERS[other]
        distance = sqrt((ox - x) ** 2 + (oy - y) ** 2)
        if distance <= TRANSFER_ADJACENCY_PIXELS:
            neighbors.append((other, ox - x, oy - y, distance))
    return neighbors


def _transfer_cost(dx, dy, distance, bias):
    # Rearward transfers are easier than flat side-to-side nudges, while the
    # selected contact bias discounts the matching side of the rack.
    rear_discount = max(0.0, -dy) / 28.0
    side_penalty = abs(dx) / 34.0
    if bias is PinImpactBias.RIGHT:
        bias_adjust = -0.65 if dx > 0 else (0.55 if dx < 0 else 0.0)
    elif bias is PinImpactBias.LEFT:
        bias_adjust = -0.65 if dx < 0 else (0.55 if dx > 0 else 0.0)
    else:
        bias_adjust = -0.20 if abs(dx) <= 2 else 0.0
    return 1.70 + distance / 24.0 + side_penalty - rear_discount + bias_adjust


def _waves(direct, standing, energy, bias):
    standing=set(standing); knocked={direct: energy}; waves=[(direct,)]; frontier={direct: energy}
    while frontier:
        received={}
        for pin,e in frontier.items():
            for child, dx, dy, distance in _neighbor_pins(pin, standing):
                if child in knocked:
                    continue
                ne=e-_transfer_cost(dx, dy, distance, bias)
                if ne >= 0.70:
                    received[child]=max(received.get(child,0.0), ne)
        if not received: break
        wave=tuple(sorted(received))
        waves.append(wave); knocked.update(received); frontier={pin: received[pin] for pin in wave}
    return tuple(waves), tuple(sorted(pin for wave in waves for pin in wave))

def resolve_ball_pinfall(trajectory: BallTrajectory, standing_before: tuple[int,...]=FULL_RACK) -> PinfallResolution:
    if type(trajectory) is not BallTrajectory: raise InvalidPinfallValueError("trajectory must be exact")
    standing=_pins(standing_before,"standing_before")
    best=None
    for i in range(COLLISION_SUBDIVISIONS):
        p0=i/COLLISION_SUBDIVISIONS; p1=(i+1)/COLLISION_SUBDIVISIONS
        x1,y1=_point(trajectory,p0); x2,y2=_point(trajectory,p1)
        for pin in standing:
            cx,cy=PIN_CENTERS[pin]
            local=_segment_circle_t(x1,y1,x2,y2,cx,cy,ARCADE_CONTACT_RADIUS_PIXELS)
            if local is None: continue
            progress=p0+(p1-p0)*local
            dx, dy = ball_trajectory_derivative_at_progress(trajectory, progress)
            candidate=(progress,pin,x1+(x2-x1)*local,y1+(y2-y1)*local,dx,dy)
            if best is None or (candidate[0], candidate[1]) < (best[0], best[1]): best=candidate
    if best is None:
        kind = BowlingThrowResultKind.GUTTER if trajectory.target_x <= 19 or trajectory.target_x >= 108 else BowlingThrowResultKind.MISS
        end=sample_ball_trajectory_progress(trajectory,1.0)
        return PinfallResolution(kind, standing, None, 1.0, end.x, end.y, trajectory.arrival_dx, trajectory.arrival_dy, PinImpactBias.CENTER, (), (), standing)
    progress,pin,cx,cy,dx,dy=best; bias=_bias(trajectory,pin,cx,dx); fall_waves, knocked=_waves(pin,standing,_initial_energy(trajectory,pin,cx,dx),bias)
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
