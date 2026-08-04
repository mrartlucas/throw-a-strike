"""Pure, deterministic emulator ball trajectory geometry."""

from dataclasses import dataclass
from math import floor, isfinite
from numbers import Real

from .throw_controls import CurveLevel, ThrowSetup

BALL_RADIUS_PIXELS = 3
BALL_START_X = 64
BALL_START_Y = 84
BALL_MIN_X = 12
BALL_MAX_X = 115
BALL_MIN_Y = 4
BALL_MAX_Y = 84
MAX_CURVE_OFFSET_PIXELS = 18

_DURATIONS = {40: 1.20, 50: 1.10, 60: 1.00, 70: 0.90,
              80: 0.80, 90: 0.70, 100: 0.60}


class InvalidBallTrajectoryValueError(ValueError):
    """Raised when a ball trajectory argument is not an exact valid value."""


@dataclass(frozen=True)
class BallTrajectory:
    raw_aim_x: int
    raw_aim_y: int
    target_x: int
    target_y: int
    start_x: int
    start_y: int
    control_x: float
    control_y: float
    curve_level: CurveLevel
    curve_strength: float
    power_percent: int
    duration_seconds: float
    arrival_dx: float
    arrival_dy: float


@dataclass(frozen=True)
class BallTrajectorySample:
    progress: float
    x: int
    y: int


def build_ball_trajectory(setup: ThrowSetup) -> BallTrajectory:
    """Build the display-local path without changing the setup's raw aim."""
    if type(setup) is not ThrowSetup:
        raise InvalidBallTrajectoryValueError("setup must be an exact ThrowSetup")
    target_x = min(BALL_MAX_X, max(BALL_MIN_X, setup.aim_x))
    target_y = min(BALL_MAX_Y, max(BALL_MIN_Y, setup.aim_y))
    mid_x = (BALL_START_X + target_x) / 2
    mid_y = (BALL_START_Y + target_y) / 2
    control_x = min(BALL_MAX_X, max(BALL_MIN_X,
                    mid_x + setup.curve_strength * MAX_CURVE_OFFSET_PIXELS))
    return BallTrajectory(
        setup.aim_x, setup.aim_y, target_x, target_y,
        BALL_START_X, BALL_START_Y, control_x, mid_y,
        setup.curve_level, setup.curve_strength, setup.power_percent,
        _DURATIONS[setup.power_percent],
        2 * (target_x - control_x), 2 * (target_y - mid_y),
    )


def _pixel(value: float) -> int:
    return floor(value + 0.5)


def sample_ball_trajectory(trajectory: BallTrajectory, elapsed_seconds: Real) -> BallTrajectorySample:
    """Sample by elapsed time, using explicit half-up nonnegative rounding."""
    if type(trajectory) is not BallTrajectory:
        raise InvalidBallTrajectoryValueError("trajectory must be exact")
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, Real):
        raise InvalidBallTrajectoryValueError("elapsed_seconds must be a finite real")
    elapsed = float(elapsed_seconds)
    if not isfinite(elapsed):
        raise InvalidBallTrajectoryValueError("elapsed_seconds must be a finite real")
    progress = min(1.0, max(0.0, elapsed / trajectory.duration_seconds))
    if progress == 0.0:
        return BallTrajectorySample(0.0, trajectory.start_x, trajectory.start_y)
    if progress == 1.0:
        return BallTrajectorySample(1.0, trajectory.target_x, trajectory.target_y)
    inverse = 1.0 - progress
    x = inverse * inverse * trajectory.start_x + 2 * inverse * progress * trajectory.control_x + progress * progress * trajectory.target_x
    y = inverse * inverse * trajectory.start_y + 2 * inverse * progress * trajectory.control_y + progress * progress * trajectory.target_y
    return BallTrajectorySample(progress, _pixel(x), _pixel(y))

