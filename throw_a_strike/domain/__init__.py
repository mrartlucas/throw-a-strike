"""Hardware-independent game rules."""

from .bowling import (
    BowlingGame,
    BowlingSnapshot,
    FrameSnapshot,
    IllegalRollError,
    RollSnapshot,
)
from .cumulative import (
    CumulativeFrameSnapshot,
    CumulativeGame,
    CumulativeRollSnapshot,
    CumulativeSnapshot,
    IllegalCumulativeRollError,
    InvalidCumulativeConfigurationError,
)
from .match import (
    BowlingMatch,
    InvalidMatchConfigurationError,
    MatchCompleteError,
    MatchRollResult,
    MatchSnapshot,
    PlayerColor,
    PlayerSnapshot,
    StandingSnapshot,
)

__all__ = [
    "BowlingGame",
    "BowlingSnapshot",
    "FrameSnapshot",
    "IllegalRollError",
    "RollSnapshot",
    "CumulativeFrameSnapshot",
    "CumulativeGame",
    "CumulativeRollSnapshot",
    "CumulativeSnapshot",
    "IllegalCumulativeRollError",
    "InvalidCumulativeConfigurationError",
    "BowlingMatch",
    "InvalidMatchConfigurationError",
    "MatchCompleteError",
    "MatchRollResult",
    "MatchSnapshot",
    "PlayerColor",
    "PlayerSnapshot",
    "StandingSnapshot",
]
