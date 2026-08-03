"""Deterministic, match-level Remix and Party schedules.

Derivations hash ``throw-a-strike|schedule|v1|SEED|PART...`` with SHA-256 and
interpret the first eight digest bytes as an unsigned big-endian integer.  This
contract is independent of Python's process state and pseudo-random generator.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping

from .config import InvalidMatchConfigError, MatchConfig, Mode


class InvalidScheduleConfigurationError(ValueError):
    """Raised for an invalid catalog, schedule, or serialized payload."""


class ScheduleModeError(InvalidScheduleConfigurationError):
    """Raised when a schedule builder receives the wrong match mode."""


class RemixObject(str, Enum):
    TENNIS_BALL = "tennis_ball"
    BASEBALL = "baseball"
    BASKETBALL = "basketball"
    BEACH_BALL = "beach_ball"
    FOOTBALL = "football"
    SOCCER_BALL = "soccer_ball"
    GOLF_BALL = "golf_ball"
    MEDICINE_BALL = "medicine_ball"
    RUBBER_BALL = "rubber_ball"


def _derive_u64(seed: int, *parts: object) -> int:
    fields = ("throw-a-strike", "schedule", "v1", str(seed), *(str(p) for p in parts))
    digest = hashlib.sha256("|".join(fields).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidScheduleConfigurationError(f"{name} must be a nonempty stripped string")
    return value


def _identifiers(value: object, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple) or (nonempty and not value):
        qualifier = "nonempty " if nonempty else ""
        raise InvalidScheduleConfigurationError(f"{name} must be a {qualifier}tuple")
    for item in value:
        _identifier(item, name)
    if len(set(value)) != len(value):
        raise InvalidScheduleConfigurationError(f"{name} values must be unique")
    return value


@dataclass(frozen=True)
class RemixFrameSchedule:
    frame_number: int
    objects: tuple[RemixObject, RemixObject]

    def __post_init__(self) -> None:
        if type(self.frame_number) is not int or self.frame_number < 1:
            raise InvalidScheduleConfigurationError("frame_number must be a positive integer")
        if not isinstance(self.objects, tuple) or len(self.objects) != 2:
            raise InvalidScheduleConfigurationError("a Remix frame requires exactly two objects")
        if any(not isinstance(item, RemixObject) for item in self.objects):
            raise InvalidScheduleConfigurationError("objects must be RemixObject members")


@dataclass(frozen=True)
class RemixSchedule:
    config: MatchConfig
    frames: tuple[RemixFrameSchedule, ...]
    frame_max_scores: tuple[int, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.config, MatchConfig) or self.config.mode is not Mode.REMIX:
            raise ScheduleModeError("Remix schedules require Remix configuration")
        if not isinstance(self.frames, tuple):
            raise InvalidScheduleConfigurationError("frames must be a tuple")
        if not isinstance(self.frame_max_scores, tuple):
            raise InvalidScheduleConfigurationError("frame_max_scores must be a tuple")
        if any(not isinstance(frame, RemixFrameSchedule) for frame in self.frames):
            raise InvalidScheduleConfigurationError("frames must be RemixFrameSchedule values")
        if len(self.frames) != self.config.frame_count:
            raise InvalidScheduleConfigurationError("Remix frame count does not match configuration")
        if tuple(frame.frame_number for frame in self.frames) != tuple(range(1, len(self.frames) + 1)):
            raise InvalidScheduleConfigurationError("Remix frame numbering must be contiguous")
        if any(type(maximum) is not int for maximum in self.frame_max_scores):
            raise InvalidScheduleConfigurationError(
                "Remix frame maximums must be non-boolean integers"
            )
        if any(maximum != 10 for maximum in self.frame_max_scores):
            raise InvalidScheduleConfigurationError("Remix frame maximums must all be 10")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "config": self.config.to_payload(),
            "frames": [
                {"frame_number": frame.frame_number, "objects": [o.value for o in frame.objects]}
                for frame in self.frames
            ],
            "frame_max_scores": list(self.frame_max_scores),
        }

    @classmethod
    def from_payload(cls, payload: object) -> "RemixSchedule":
        try:
            if not isinstance(payload, Mapping) or set(payload) != {
                "schema_version", "config", "frames", "frame_max_scores"
            }:
                raise InvalidScheduleConfigurationError("Remix payload fields are invalid")
            if type(payload["schema_version"]) is not int or payload["schema_version"] != cls.SCHEMA_VERSION:
                raise InvalidScheduleConfigurationError("unsupported Remix schema version")
            raw_frames = payload["frames"]
            raw_maximums = payload["frame_max_scores"]
            if not isinstance(raw_frames, list) or not isinstance(raw_maximums, list):
                raise InvalidScheduleConfigurationError("serialized collections must be lists")
            frames = []
            for raw in raw_frames:
                if not isinstance(raw, Mapping) or set(raw) != {"frame_number", "objects"}:
                    raise InvalidScheduleConfigurationError("Remix frame fields are invalid")
                objects = raw["objects"]
                if not isinstance(objects, list):
                    raise InvalidScheduleConfigurationError("serialized objects must be a list")
                frames.append(RemixFrameSchedule(raw["frame_number"], tuple(RemixObject(o) for o in objects)))  # type: ignore[arg-type]
            return cls(MatchConfig.from_payload(payload["config"]), tuple(frames), tuple(raw_maximums))  # type: ignore[arg-type]
        except InvalidScheduleConfigurationError:
            raise
        except (InvalidMatchConfigError, TypeError, ValueError, KeyError) as exc:
            raise InvalidScheduleConfigurationError("invalid Remix schedule payload") from exc


@dataclass(frozen=True)
class PartySetupDefinition:
    setup_id: str
    formation_id: str
    target_type_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    mystery_outcome_ids: tuple[str, ...]
    maximum_score: int

    def __post_init__(self) -> None:
        _identifier(self.setup_id, "setup_id")
        _identifier(self.formation_id, "formation_id")
        _identifiers(self.target_type_ids, "target_type_ids", nonempty=True)
        _identifiers(self.reaction_ids, "reaction_ids")
        _identifiers(self.mystery_outcome_ids, "mystery_outcome_ids")
        if type(self.maximum_score) is not int or self.maximum_score <= 0:
            raise InvalidScheduleConfigurationError("maximum_score must be a positive integer")


@dataclass(frozen=True)
class PartyFrameSchedule:
    frame_number: int
    setup_id: str
    formation_id: str
    target_type_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    mystery_outcome_ids: tuple[str, ...]
    maximum_score: int
    frame_seed: int

    def __post_init__(self) -> None:
        if type(self.frame_number) is not int or self.frame_number < 1:
            raise InvalidScheduleConfigurationError("frame_number must be a positive integer")
        _identifier(self.setup_id, "setup_id")
        _identifier(self.formation_id, "formation_id")
        _identifiers(self.target_type_ids, "target_type_ids", nonempty=True)
        _identifiers(self.reaction_ids, "reaction_ids")
        _identifiers(self.mystery_outcome_ids, "mystery_outcome_ids")
        if type(self.maximum_score) is not int or self.maximum_score <= 0:
            raise InvalidScheduleConfigurationError("maximum_score must be a positive integer")
        if type(self.frame_seed) is not int or not 0 <= self.frame_seed <= (1 << 64) - 1:
            raise InvalidScheduleConfigurationError("frame_seed must be an unsigned 64-bit integer")


@dataclass(frozen=True)
class PartySchedule:
    config: MatchConfig
    catalog_fingerprint: str
    frames: tuple[PartyFrameSchedule, ...]
    frame_max_scores: tuple[int, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.config, MatchConfig) or self.config.mode is not Mode.PARTY:
            raise ScheduleModeError("Party schedules require Party configuration")
        if (not isinstance(self.catalog_fingerprint, str) or len(self.catalog_fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in self.catalog_fingerprint)):
            raise InvalidScheduleConfigurationError("catalog_fingerprint must be SHA-256 hex")
        if not isinstance(self.frames, tuple):
            raise InvalidScheduleConfigurationError("frames must be a tuple")
        if not isinstance(self.frame_max_scores, tuple):
            raise InvalidScheduleConfigurationError("frame_max_scores must be a tuple")
        if any(not isinstance(frame, PartyFrameSchedule) for frame in self.frames):
            raise InvalidScheduleConfigurationError("frames must be PartyFrameSchedule values")
        if len(self.frames) != self.config.frame_count:
            raise InvalidScheduleConfigurationError("Party frame count does not match configuration")
        if tuple(frame.frame_number for frame in self.frames) != tuple(range(1, len(self.frames) + 1)):
            raise InvalidScheduleConfigurationError("Party frame numbering must be contiguous")
        if any(
            type(maximum) is not int or maximum <= 0
            for maximum in self.frame_max_scores
        ):
            raise InvalidScheduleConfigurationError(
                "Party frame maximums must be positive non-boolean integers"
            )
        if self.frame_max_scores != tuple(frame.maximum_score for frame in self.frames):
            raise InvalidScheduleConfigurationError("Party frame maximums do not match frames")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "config": self.config.to_payload(),
            "catalog_fingerprint": self.catalog_fingerprint,
            "frames": [
                {
                    "frame_number": f.frame_number, "setup_id": f.setup_id,
                    "formation_id": f.formation_id, "target_type_ids": list(f.target_type_ids),
                    "reaction_ids": list(f.reaction_ids),
                    "mystery_outcome_ids": list(f.mystery_outcome_ids),
                    "maximum_score": f.maximum_score, "frame_seed": f.frame_seed,
                } for f in self.frames
            ],
            "frame_max_scores": list(self.frame_max_scores),
        }

    @classmethod
    def from_payload(cls, payload: object) -> "PartySchedule":
        keys = {"schema_version", "config", "catalog_fingerprint", "frames", "frame_max_scores"}
        frame_keys = {"frame_number", "setup_id", "formation_id", "target_type_ids", "reaction_ids", "mystery_outcome_ids", "maximum_score", "frame_seed"}
        try:
            if not isinstance(payload, Mapping) or set(payload) != keys:
                raise InvalidScheduleConfigurationError("Party payload fields are invalid")
            if type(payload["schema_version"]) is not int or payload["schema_version"] != cls.SCHEMA_VERSION:
                raise InvalidScheduleConfigurationError("unsupported Party schema version")
            raw_frames, raw_maximums = payload["frames"], payload["frame_max_scores"]
            if not isinstance(raw_frames, list) or not isinstance(raw_maximums, list):
                raise InvalidScheduleConfigurationError("serialized collections must be lists")
            frames = []
            for raw in raw_frames:
                if not isinstance(raw, Mapping) or set(raw) != frame_keys:
                    raise InvalidScheduleConfigurationError("Party frame fields are invalid")
                tuple_fields = ("target_type_ids", "reaction_ids", "mystery_outcome_ids")
                if any(not isinstance(raw[name], list) for name in tuple_fields):
                    raise InvalidScheduleConfigurationError("serialized metadata must use lists")
                frames.append(PartyFrameSchedule(
                    raw["frame_number"], raw["setup_id"], raw["formation_id"],
                    tuple(raw["target_type_ids"]), tuple(raw["reaction_ids"]),
                    tuple(raw["mystery_outcome_ids"]), raw["maximum_score"], raw["frame_seed"],
                ))  # type: ignore[arg-type]
            return cls(MatchConfig.from_payload(payload["config"]), payload["catalog_fingerprint"], tuple(frames), tuple(raw_maximums))  # type: ignore[arg-type]
        except InvalidScheduleConfigurationError:
            raise
        except (InvalidMatchConfigError, TypeError, ValueError, KeyError) as exc:
            raise InvalidScheduleConfigurationError("invalid Party schedule payload") from exc


def build_remix_schedule(config: MatchConfig) -> RemixSchedule:
    if not isinstance(config, MatchConfig) or config.mode is not Mode.REMIX:
        raise ScheduleModeError("build_remix_schedule requires Remix mode")
    catalog = tuple(RemixObject)
    frames = tuple(
        RemixFrameSchedule(
            frame,
            tuple(catalog[_derive_u64(config.seed, "remix_object", frame, roll) % len(catalog)] for roll in (1, 2)),  # type: ignore[arg-type]
        )
        for frame in range(1, config.frame_count + 1)
    )
    return RemixSchedule(config, frames, (10,) * config.frame_count)


def _catalog_fingerprint(catalog: tuple[PartySetupDefinition, ...]) -> str:
    value = {
        "schema_version": 1,
        "setups": [
            {
                "setup_id": item.setup_id, "formation_id": item.formation_id,
                "target_type_ids": list(item.target_type_ids), "reaction_ids": list(item.reaction_ids),
                "mystery_outcome_ids": list(item.mystery_outcome_ids), "maximum_score": item.maximum_score,
            } for item in catalog
        ],
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_party_schedule(config: MatchConfig, catalog: tuple[PartySetupDefinition, ...]) -> PartySchedule:
    if not isinstance(config, MatchConfig) or config.mode is not Mode.PARTY:
        raise ScheduleModeError("build_party_schedule requires Party mode")
    if not isinstance(catalog, tuple) or not catalog:
        raise InvalidScheduleConfigurationError("Party catalog must be a nonempty tuple")
    if any(not isinstance(item, PartySetupDefinition) for item in catalog):
        raise InvalidScheduleConfigurationError("Party catalog entries must be definitions")
    if len({item.setup_id for item in catalog}) != len(catalog):
        raise InvalidScheduleConfigurationError("Party setup IDs must be unique")
    fingerprint = _catalog_fingerprint(catalog)
    frames = []
    for frame_number in range(1, config.frame_count + 1):
        selected = catalog[_derive_u64(config.seed, "party_setup", fingerprint, frame_number) % len(catalog)]
        mysteries = tuple(sorted(
            selected.mystery_outcome_ids,
            key=lambda outcome: (_derive_u64(config.seed, "party_mystery_outcome", fingerprint, frame_number, outcome), outcome),
        ))
        frames.append(PartyFrameSchedule(
            frame_number, selected.setup_id, selected.formation_id, selected.target_type_ids,
            selected.reaction_ids, mysteries, selected.maximum_score,
            _derive_u64(config.seed, "party_frame_seed", fingerprint, frame_number),
        ))
    result = tuple(frames)
    return PartySchedule(config, fingerprint, result, tuple(f.maximum_score for f in result))
