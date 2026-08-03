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
from .cumulative_match import (
    CumulativeMatch,
    CumulativeMatchCompleteError,
    CumulativeMatchPlayerSnapshot,
    CumulativeMatchRollResult,
    CumulativeMatchSnapshot,
    CumulativeStandingSnapshot,
    InvalidCumulativeMatchConfigurationError,
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
    "CumulativeMatch",
    "CumulativeMatchCompleteError",
    "CumulativeMatchPlayerSnapshot",
    "CumulativeMatchRollResult",
    "CumulativeMatchSnapshot",
    "CumulativeStandingSnapshot",
    "InvalidCumulativeMatchConfigurationError",
]
