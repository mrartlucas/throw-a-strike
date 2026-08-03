"""Immutable, serializable match configuration and locked product identity."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class InvalidMatchConfigError(ValueError):
    """Raised when a match configuration or its payload is invalid."""


class Mode(str, Enum):
    TEN_PIN = "ten_pin"
    HUNDRED_PIN = "hundred_pin"
    REMIX = "remix"
    PARTY = "party"


class Theme(str, Enum):
    REGULAR = "regular"
    BLACKLIGHT = "blacklight"


@dataclass(frozen=True)
class BrandingSnapshot:
    presenter: str
    game_title: str
    title_treatment: str


LOCKED_BRANDING = BrandingSnapshot(
    presenter="Throw A Way Games",
    game_title="Throw a Strike",
    title_treatment="Throw A Way Games presents\nThrow a Strike",
)


@dataclass(frozen=True)
class MatchConfig:
    """The complete immutable configuration required to reproduce a match."""

    mode: Mode
    theme: Theme
    player_count: int
    frame_count: int
    seed: int

    SCHEMA_VERSION = 1
    _PAYLOAD_FIELDS = frozenset(
        {"schema_version", "mode", "theme", "player_count", "frame_count", "seed"}
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, Mode):
            raise InvalidMatchConfigError("mode must be a Mode member")
        if not isinstance(self.theme, Theme):
            raise InvalidMatchConfigError("theme must be a Theme member")
        if type(self.player_count) is not int or not 1 <= self.player_count <= 4:
            raise InvalidMatchConfigError("player_count must be an integer from 1 to 4")
        valid_frames = (10,) if self.mode is Mode.TEN_PIN else (3, 5, 10)
        if type(self.frame_count) is not int or self.frame_count not in valid_frames:
            raise InvalidMatchConfigError(
                f"frame_count must be one of {valid_frames} for {self.mode.value}"
            )
        if type(self.seed) is not int or not 0 <= self.seed <= (1 << 64) - 1:
            raise InvalidMatchConfigError("seed must be an unsigned 64-bit integer")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "mode": self.mode.value,
            "theme": self.theme.value,
            "player_count": self.player_count,
            "frame_count": self.frame_count,
            "seed": self.seed,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "MatchConfig":
        if not isinstance(payload, Mapping) or set(payload) != cls._PAYLOAD_FIELDS:
            raise InvalidMatchConfigError("configuration payload fields are invalid")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise InvalidMatchConfigError("unsupported configuration schema version")
        try:
            mode = Mode(payload["mode"])
            theme = Theme(payload["theme"])
        except (TypeError, ValueError) as exc:
            raise InvalidMatchConfigError("payload contains an invalid mode or theme") from exc
        return cls(
            mode=mode,
            theme=theme,
            player_count=payload["player_count"],  # type: ignore[arg-type]
            frame_count=payload["frame_count"],  # type: ignore[arg-type]
            seed=payload["seed"],  # type: ignore[arg-type]
        )
