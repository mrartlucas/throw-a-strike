"""Pure regulation ten-pin bowling scoring and rack state.

``BowlingGame.roll`` is the only state-changing operation.  All public views are
immutable tuples and frozen dataclasses so display and multiplayer code can retain
a snapshot without observing later mutations.
"""

from __future__ import annotations

from dataclasses import dataclass


class IllegalRollError(ValueError):
    """Raised when a roll is impossible in the current game/rack state."""


@dataclass(frozen=True)
class RollSnapshot:
    """One recorded roll, including its rack transition."""

    pins: int
    standing_before: int
    standing_after: int


@dataclass(frozen=True)
class FrameSnapshot:
    """Immutable scoring view of one of the ten frames."""

    number: int
    rolls: tuple[int, ...]
    marks: tuple[str, ...]
    score: int | None
    cumulative_score: int | None
    complete: bool


@dataclass(frozen=True)
class BowlingSnapshot:
    """Complete read-only view suitable for a future scoreboard."""

    current_frame: int
    current_roll: int | None
    pins_standing: int
    frames: tuple[FrameSnapshot, ...]
    roll_history: tuple[tuple[RollSnapshot, ...], ...]
    complete: bool
    confirmed_score: int


class BowlingGame:
    """Mutable state machine for one regulation ten-pin bowling game."""

    FRAME_COUNT = 10
    PINS_PER_RACK = 10

    def __init__(self) -> None:
        self._rolls: list[list[int]] = [[] for _ in range(self.FRAME_COUNT)]
        self._history: list[list[RollSnapshot]] = [
            [] for _ in range(self.FRAME_COUNT)
        ]
        self._frame_index = 0
        self._pins_standing = self.PINS_PER_RACK
        self._complete = False

    @property
    def current_frame(self) -> int:
        """One-based current frame (10 after the game is complete)."""
        return self._frame_index + 1

    @property
    def current_roll(self) -> int | None:
        """One-based next roll within the frame, or ``None`` when complete."""
        if self._complete:
            return None
        return len(self._rolls[self._frame_index]) + 1

    @property
    def pins_standing(self) -> int:
        return self._pins_standing

    @property
    def rolls_by_frame(self) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(frame) for frame in self._rolls)

    @property
    def is_complete(self) -> bool:
        return self._complete

    @property
    def frames(self) -> tuple[FrameSnapshot, ...]:
        return self.snapshot().frames

    @property
    def confirmed_score(self) -> int:
        """Sum of consecutive frames whose bonuses are fully known."""
        return self.snapshot().confirmed_score

    def roll(self, pins: int) -> RollSnapshot:
        """Record ``pins`` knocked down and return the rack transition.

        Raises :class:`IllegalRollError` after completion or when the count is
        negative, non-integral, or exceeds the currently standing rack.
        """
        if self._complete:
            raise IllegalRollError("the game is already complete")
        if isinstance(pins, bool) or not isinstance(pins, int):
            raise IllegalRollError("pins must be an integer")
        if pins < 0:
            raise IllegalRollError("pins cannot be negative")
        if pins > self._pins_standing:
            raise IllegalRollError(
                f"cannot knock down {pins} pins with {self._pins_standing} standing"
            )

        before = self._pins_standing
        self._pins_standing -= pins
        transition = RollSnapshot(pins, before, self._pins_standing)
        self._rolls[self._frame_index].append(pins)
        self._history[self._frame_index].append(transition)

        if self._frame_index < 9:
            self._advance_ordinary_frame(pins)
        else:
            self._advance_tenth_frame()
        return transition

    def snapshot(self) -> BowlingSnapshot:
        """Return an immutable view of the current game."""
        scores = self._frame_scores()
        running = 0
        cumulative: list[int | None] = []
        still_confirmed = True
        for score in scores:
            if still_confirmed and score is not None:
                running += score
                cumulative.append(running)
            else:
                still_confirmed = False
                cumulative.append(None)

        frames = tuple(
            FrameSnapshot(
                number=index + 1,
                rolls=tuple(rolls),
                marks=self._marks(index, rolls),
                score=scores[index],
                cumulative_score=cumulative[index],
                complete=self._frame_complete(index),
            )
            for index, rolls in enumerate(self._rolls)
        )
        return BowlingSnapshot(
            current_frame=self.current_frame,
            current_roll=self.current_roll,
            pins_standing=self._pins_standing,
            frames=frames,
            roll_history=tuple(tuple(frame) for frame in self._history),
            complete=self._complete,
            confirmed_score=running,
        )

    def _advance_ordinary_frame(self, pins: int) -> None:
        frame = self._rolls[self._frame_index]
        if pins == 10 or len(frame) == 2:
            self._frame_index += 1
            self._pins_standing = 10

    def _advance_tenth_frame(self) -> None:
        frame = self._rolls[9]
        if len(frame) == 1:
            if frame[0] == 10:
                self._pins_standing = 10
            return
        if len(frame) == 2:
            first, second = frame
            if first == 10:
                if second == 10:
                    self._pins_standing = 10
                # Otherwise the third ball keeps the remainder of rack two.
            elif first + second == 10:
                self._pins_standing = 10
            else:
                self._complete = True
            return
        self._complete = True

    def _frame_complete(self, index: int) -> bool:
        rolls = self._rolls[index]
        if index < 9:
            return bool(rolls) and (rolls[0] == 10 or len(rolls) == 2)
        if len(rolls) < 2:
            return False
        bonus = rolls[0] == 10 or rolls[0] + rolls[1] == 10
        return len(rolls) == 3 if bonus else True

    def _frame_scores(self) -> list[int | None]:
        flat: list[int] = []
        starts: list[int] = []
        for frame in self._rolls:
            starts.append(len(flat))
            flat.extend(frame)
        scores: list[int | None] = []
        for index, frame in enumerate(self._rolls):
            if index == 9:
                scores.append(sum(frame) if self._frame_complete(index) else None)
            elif not self._frame_complete(index):
                scores.append(None)
            elif frame[0] == 10:
                following = flat[starts[index] + 1 : starts[index] + 3]
                scores.append(10 + sum(following) if len(following) == 2 else None)
            elif sum(frame) == 10:
                following = flat[starts[index] + 2 : starts[index] + 3]
                scores.append(10 + following[0] if following else None)
            else:
                scores.append(sum(frame))
        return scores

    @staticmethod
    def _marks(index: int, rolls: list[int]) -> tuple[str, ...]:
        if index == 9:
            return BowlingGame._tenth_frame_marks(rolls)

        marks: list[str] = []
        for roll_index, pins in enumerate(rolls):
            if pins == 0:
                mark = "-"
            elif roll_index > 0 and sum(rolls[:2]) == 10:
                mark = "/"
            elif roll_index == 0 and pins == 10:
                mark = "X"
            else:
                mark = str(pins)
            marks.append(mark)
        return tuple(marks)

    @staticmethod
    def _tenth_frame_marks(rolls: list[int]) -> tuple[str, ...]:
        """Format tenth-frame rolls according to the rack each ball used."""
        marks: list[str] = []
        for roll_index, pins in enumerate(rolls):
            if roll_index == 0:
                mark = "X" if pins == 10 else BowlingGame._pin_mark(pins)
            elif roll_index == 1:
                if rolls[0] == 10:
                    mark = "X" if pins == 10 else BowlingGame._pin_mark(pins)
                else:
                    mark = "/" if rolls[0] + pins == 10 else BowlingGame._pin_mark(pins)
            elif rolls[0] == 10 and rolls[1] < 10:
                mark = "/" if rolls[1] + pins == 10 else BowlingGame._pin_mark(pins)
            else:
                mark = "X" if pins == 10 else BowlingGame._pin_mark(pins)
            marks.append(mark)
        return tuple(marks)

    @staticmethod
    def _pin_mark(pins: int) -> str:
        return "-" if pins == 0 else str(pins)
