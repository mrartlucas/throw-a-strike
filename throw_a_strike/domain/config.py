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


class ControlStyle(str, Enum):
    QUICK = "quick"
    ADVANCED = "advanced"


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
    control_style: ControlStyle = ControlStyle.QUICK

    SCHEMA_VERSION = 2
    _V1_PAYLOAD_FIELDS = frozenset(
        {"schema_version", "mode", "theme", "player_count", "frame_count", "seed"}
    )
    _PAYLOAD_FIELDS = _V1_PAYLOAD_FIELDS | {"control_style"}

    def __post_init__(self) -> None:
        if type(self.mode) is not Mode:
            raise InvalidMatchConfigError("mode must be a Mode member")
        if type(self.theme) is not Theme:
            raise InvalidMatchConfigError("theme must be a Theme member")
        if type(self.control_style) is not ControlStyle:
            raise InvalidMatchConfigError("control_style must be a ControlStyle member")
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
            "control_style": self.control_style.value,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "MatchConfig":
        if not isinstance(payload, Mapping):
            raise InvalidMatchConfigError("configuration payload fields are invalid")
        version = payload.get("schema_version")
        if type(version) is not int or version not in (1, cls.SCHEMA_VERSION):
            raise InvalidMatchConfigError("unsupported configuration schema version")
        expected = cls._V1_PAYLOAD_FIELDS if version == 1 else cls._PAYLOAD_FIELDS
        if set(payload) != expected:
            raise InvalidMatchConfigError("configuration payload fields are invalid")
        string_keys = ("mode", "theme") if version == 1 else ("mode", "theme", "control_style")
        if any(type(payload[key]) is not str for key in string_keys):
            raise InvalidMatchConfigError("serialized enum values must be strings")
        try:
            mode = Mode(payload["mode"])
            theme = Theme(payload["theme"])
            control_style = ControlStyle.QUICK if version == 1 else ControlStyle(payload["control_style"])
        except (TypeError, ValueError) as exc:
            raise InvalidMatchConfigError("payload contains an invalid mode or theme") from exc
        return cls(
            mode=mode,
            theme=theme,
            player_count=payload["player_count"],  # type: ignore[arg-type]
            frame_count=payload["frame_count"],  # type: ignore[arg-type]
            seed=payload["seed"],  # type: ignore[arg-type]
            control_style=control_style,
        )
