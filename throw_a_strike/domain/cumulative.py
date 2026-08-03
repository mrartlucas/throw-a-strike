"""Pure cumulative scoring for games with exactly two rolls per frame.

This module deliberately models only one player's score state.  It has no
knowledge of bowling bonuses, players, physical targets, or presentation.
"""

from __future__ import annotations

from dataclasses import dataclass


class InvalidCumulativeConfigurationError(ValueError):
    """Raised when the frame maximums cannot define a cumulative game."""


class IllegalCumulativeRollError(ValueError):
    """Raised when points cannot be accepted in the current score state."""


@dataclass(frozen=True)
class CumulativeRollSnapshot:
    """An accepted roll and its score-capacity transition."""

    frame_number: int
    roll_number: int
    points: int
    remaining_before: int
    remaining_after: int


@dataclass(frozen=True)
class CumulativeFrameSnapshot:
    """Immutable scoring state for one configured frame."""

    frame_number: int
    maximum_score: int
    rolls: tuple[CumulativeRollSnapshot, ...]
    score: int
    remaining_capacity: int
    complete: bool


@dataclass(frozen=True)
class CumulativeSnapshot:
    """Complete immutable view of one player's cumulative game."""

    frame_count: int
    frames: tuple[CumulativeFrameSnapshot, ...]
    current_frame_number: int | None
    current_roll_number: int | None
    current_frame_maximum: int | None
    remaining_capacity: int | None
    total_score: int
    complete: bool


class CumulativeGame:
    """One-player, direct-scoring state machine with two rolls per frame."""

    VALID_FRAME_COUNTS = frozenset((3, 5, 10))

    def __init__(self, frame_max_scores: tuple[int, ...]) -> None:
        if not isinstance(frame_max_scores, tuple):
            raise InvalidCumulativeConfigurationError(
                "frame_max_scores must be an immutable tuple"
            )
        if len(frame_max_scores) not in self.VALID_FRAME_COUNTS:
            raise InvalidCumulativeConfigurationError(
                "a cumulative game must contain exactly 3, 5, or 10 frames"
            )
        if any(
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum <= 0
            for maximum in frame_max_scores
        ):
            raise InvalidCumulativeConfigurationError(
                "every frame maximum must be a positive integer"
            )

        self._frame_max_scores = frame_max_scores
        self._rolls: list[list[CumulativeRollSnapshot]] = [
            [] for _ in frame_max_scores
        ]
        self._frame_index = 0
        self._remaining_capacity = frame_max_scores[0]
        self._complete = False

    def roll(self, points: int) -> CumulativeRollSnapshot:
        """Accept one point result and return its immutable recorded value.

        A rejected value, including any value submitted after completion, is
        detected before state mutation and raises
        :class:`IllegalCumulativeRollError`.
        """
        if self._complete:
            raise IllegalCumulativeRollError("the cumulative game is complete")
        if isinstance(points, bool) or not isinstance(points, int):
            raise IllegalCumulativeRollError("points must be an integer")
        if points < 0:
            raise IllegalCumulativeRollError("points cannot be negative")
        if points > self._remaining_capacity:
            raise IllegalCumulativeRollError(
                f"cannot score {points} with {self._remaining_capacity} remaining"
            )

        frame_rolls = self._rolls[self._frame_index]
        accepted = CumulativeRollSnapshot(
            frame_number=self._frame_index + 1,
            roll_number=len(frame_rolls) + 1,
            points=points,
            remaining_before=self._remaining_capacity,
            remaining_after=self._remaining_capacity - points,
        )
        frame_rolls.append(accepted)
        self._remaining_capacity = accepted.remaining_after

        if len(frame_rolls) == 2:
            if self._frame_index == len(self._frame_max_scores) - 1:
                self._complete = True
            else:
                self._frame_index += 1
                self._remaining_capacity = self._frame_max_scores[self._frame_index]
        return accepted

    def snapshot(self) -> CumulativeSnapshot:
        """Return a detached, deeply immutable view of the score state."""
        frames = tuple(
            CumulativeFrameSnapshot(
                frame_number=index + 1,
                maximum_score=maximum,
                rolls=tuple(self._rolls[index]),
                score=sum(roll.points for roll in self._rolls[index]),
                remaining_capacity=(
                    maximum - sum(roll.points for roll in self._rolls[index])
                ),
                complete=len(self._rolls[index]) == 2,
            )
            for index, maximum in enumerate(self._frame_max_scores)
        )
        if self._complete:
            current_frame_number = None
            current_roll_number = None
            current_frame_maximum = None
            remaining_capacity = None
        else:
            current_frame_number = self._frame_index + 1
            current_roll_number = len(self._rolls[self._frame_index]) + 1
            current_frame_maximum = self._frame_max_scores[self._frame_index]
            remaining_capacity = self._remaining_capacity

        return CumulativeSnapshot(
            frame_count=len(self._frame_max_scores),
            frames=frames,
            current_frame_number=current_frame_number,
            current_roll_number=current_roll_number,
            current_frame_maximum=current_frame_maximum,
            remaining_capacity=remaining_capacity,
            total_score=sum(frame.score for frame in frames),
            complete=self._complete,
        )
