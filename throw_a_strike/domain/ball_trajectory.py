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

    def __post_init__(self) -> None:
        integer_fields = {
            "raw_aim_x": self.raw_aim_x, "raw_aim_y": self.raw_aim_y,
            "target_x": self.target_x, "target_y": self.target_y,
            "start_x": self.start_x, "start_y": self.start_y,
            "power_percent": self.power_percent,
        }
        if any(type(value) is not int for value in integer_fields.values()):
            raise InvalidBallTrajectoryValueError("trajectory integer fields must be exact ints")
        if not 0 <= self.raw_aim_x <= 127 or not 0 <= self.raw_aim_y <= 127:
            raise InvalidBallTrajectoryValueError("raw aim must be within the emulator input range")
        if (self.start_x, self.start_y) != (BALL_START_X, BALL_START_Y):
            raise InvalidBallTrajectoryValueError("trajectory start must be the exact ball start")
        if not BALL_MIN_X <= self.target_x <= BALL_MAX_X or not BALL_MIN_Y <= self.target_y <= BALL_MAX_Y:
            raise InvalidBallTrajectoryValueError("trajectory target must be within display bounds")
        if type(self.curve_level) is not CurveLevel:
            raise InvalidBallTrajectoryValueError("curve_level must be exact")
        float_fields = (self.control_x, self.control_y, self.curve_strength,
                        self.duration_seconds, self.arrival_dx, self.arrival_dy)
        if any(type(value) is not float or not isfinite(value) for value in float_fields):
            raise InvalidBallTrajectoryValueError("trajectory numeric metadata must be finite floats")
        if not BALL_MIN_X <= self.control_x <= BALL_MAX_X or not BALL_MIN_Y <= self.control_y <= BALL_MAX_Y:
            raise InvalidBallTrajectoryValueError("control point must be within display bounds")
        if self.curve_strength != self.curve_level.strength:
            raise InvalidBallTrajectoryValueError("curve strength must match curve level")
        if self.power_percent not in _DURATIONS or self.duration_seconds != _DURATIONS[self.power_percent]:
            raise InvalidBallTrajectoryValueError("duration must match power")


@dataclass(frozen=True)
class BallTrajectorySample:
    progress: float
    x: int
    y: int

    def __post_init__(self) -> None:
        if type(self.progress) is not float or not isfinite(self.progress) or not 0.0 <= self.progress <= 1.0:
            raise InvalidBallTrajectoryValueError("progress must be a finite float from zero through one")
        if type(self.x) is not int or type(self.y) is not int:
            raise InvalidBallTrajectoryValueError("sample pixels must be exact ints")
        if not 0 <= self.x < 128 or not 0 <= self.y < 128:
            raise InvalidBallTrajectoryValueError("sample pixels must be within the framebuffer")


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


def sample_ball_trajectory_progress(trajectory: BallTrajectory, progress: Real) -> BallTrajectorySample:
    """Sample by normalized trajectory progress, using half-up nonnegative rounding."""
    if type(trajectory) is not BallTrajectory:
        raise InvalidBallTrajectoryValueError("trajectory must be exact")
    if isinstance(progress, bool) or not isinstance(progress, Real):
        raise InvalidBallTrajectoryValueError("progress must be a finite real")
    progress = min(1.0, max(0.0, float(progress)))
    if not isfinite(progress):
        raise InvalidBallTrajectoryValueError("progress must be a finite real")
    if progress == 0.0:
        return BallTrajectorySample(0.0, trajectory.start_x, trajectory.start_y)
    if progress == 1.0:
        return BallTrajectorySample(1.0, trajectory.target_x, trajectory.target_y)
    inverse = 1.0 - progress
    x = inverse * inverse * trajectory.start_x + 2 * inverse * progress * trajectory.control_x + progress * progress * trajectory.target_x
    y = inverse * inverse * trajectory.start_y + 2 * inverse * progress * trajectory.control_y + progress * progress * trajectory.target_y
    return BallTrajectorySample(progress, _pixel(x), _pixel(y))


def sample_ball_trajectory(trajectory: BallTrajectory, elapsed_seconds: Real) -> BallTrajectorySample:
    """Sample by elapsed time, retaining the Phase 0T timing contract."""
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, Real):
        raise InvalidBallTrajectoryValueError("elapsed_seconds must be a finite real")
    elapsed = float(elapsed_seconds)
    if not isfinite(elapsed):
        raise InvalidBallTrajectoryValueError("elapsed_seconds must be a finite real")
    if type(trajectory) is not BallTrajectory:
        raise InvalidBallTrajectoryValueError("trajectory must be exact")
    return sample_ball_trajectory_progress(trajectory, elapsed / trajectory.duration_seconds)
