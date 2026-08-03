"""Pure multiplayer turn order for regulation ten-pin bowling.

This module deliberately knows nothing about input devices or presentation.  It
coordinates one independent :class:`BowlingGame` per active player and exposes
only immutable views of match state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .bowling import BowlingGame, BowlingSnapshot, RollSnapshot


class InvalidMatchConfigurationError(ValueError):
    """Raised when a match is not configured for one through four players."""


class MatchCompleteError(RuntimeError):
    """Raised when a roll is attempted after every player has finished."""


class PlayerColor(Enum):
    """The fixed display colors, in locked player order."""

    BLUE = "Blue"
    RED = "Red"
    GREEN = "Green"
    YELLOW = "Yellow"


@dataclass(frozen=True)
class PlayerSnapshot:
    """Read-only state for one active player."""

    player_number: int
    color: PlayerColor
    bowling: BowlingSnapshot
    confirmed_score: int
    complete: bool


@dataclass(frozen=True)
class StandingSnapshot:
    """One provisional or final row in competition-ranked standings."""

    rank: int
    player_number: int
    color: PlayerColor
    confirmed_score: int
    provisional: bool


@dataclass(frozen=True)
class MatchSnapshot:
    """Complete immutable view for future presenters."""

    active_player_count: int
    players: tuple[PlayerSnapshot, ...]
    current_frame: int | None
    current_player_number: int | None
    current_player_color: PlayerColor | None
    current_roll: int | None
    pins_standing: int | None
    complete: bool
    standings: tuple[StandingSnapshot, ...]
    winners: tuple[PlayerSnapshot, ...]


@dataclass(frozen=True)
class MatchRollResult:
    """The accepted roll's rack transition and resulting turn transition."""

    player_number: int
    player_color: PlayerColor
    rack: RollSnapshot
    turn_ended: bool
    global_frame_ended: bool
    next_player_number: int | None
    next_player_color: PlayerColor | None
    match: MatchSnapshot


class BowlingMatch:
    """A regulation match for one to four fixed-color players."""

    _COLORS = tuple(PlayerColor)

    def __init__(self, player_count: int) -> None:
        if (
            isinstance(player_count, bool)
            or not isinstance(player_count, int)
            or not 1 <= player_count <= 4
        ):
            raise InvalidMatchConfigurationError(
                "player_count must be an integer from 1 through 4"
            )
        self._games = tuple(BowlingGame() for _ in range(player_count))
        self._player_index = 0
        self._global_frame = 1
        self._complete = False

    @property
    def games(self) -> tuple[BowlingGame, ...]:
        """The distinct games owned by active players.

        This tuple is immutable, while each game is intentionally the player's
        mutable scoring engine.  Callers should use :meth:`snapshot` for views.
        """
        return self._games

    @property
    def is_complete(self) -> bool:
        return self._complete

    def roll(self, pins: int) -> MatchRollResult:
        """Apply one roll to the current player and rotate only when appropriate.

        Validation is delegated to :class:`BowlingGame`; if it rejects a roll,
        no match turn or frame state has been changed.
        """
        if self._complete:
            raise MatchCompleteError("the match is already complete")

        player_index = self._player_index
        game = self._games[player_index]
        frame_before = game.current_frame
        rack = game.roll(pins)
        turn_ended = game.is_complete or game.current_frame != frame_before
        global_frame_ended = False

        if turn_ended:
            if player_index + 1 < len(self._games):
                self._player_index += 1
            else:
                global_frame_ended = True
                if self._global_frame == BowlingGame.FRAME_COUNT:
                    self._complete = True
                else:
                    self._global_frame += 1
                    self._player_index = 0

        snapshot = self.snapshot()
        return MatchRollResult(
            player_number=player_index + 1,
            player_color=self._COLORS[player_index],
            rack=rack,
            turn_ended=turn_ended,
            global_frame_ended=global_frame_ended,
            next_player_number=snapshot.current_player_number,
            next_player_color=snapshot.current_player_color,
            match=snapshot,
        )

    def snapshot(self) -> MatchSnapshot:
        """Build an immutable match, player, standings, and winners view."""
        players = tuple(
            self._player_snapshot(index, game)
            for index, game in enumerate(self._games)
        )
        ordered = sorted(
            players, key=lambda player: (-player.confirmed_score, player.player_number)
        )
        standings: list[StandingSnapshot] = []
        previous_score: int | None = None
        previous_rank = 0
        for position, player in enumerate(ordered, start=1):
            rank = previous_rank if player.confirmed_score == previous_score else position
            standings.append(
                StandingSnapshot(
                    rank=rank,
                    player_number=player.player_number,
                    color=player.color,
                    confirmed_score=player.confirmed_score,
                    provisional=not self._complete,
                )
            )
            previous_score = player.confirmed_score
            previous_rank = rank

        winners: tuple[PlayerSnapshot, ...] = ()
        if self._complete:
            winning_score = ordered[0].confirmed_score
            winners = tuple(
                player for player in ordered if player.confirmed_score == winning_score
            )

        if self._complete:
            current_frame = current_number = current_color = current_roll = standing = None
        else:
            current_game = self._games[self._player_index]
            current_frame = self._global_frame
            current_number = self._player_index + 1
            current_color = self._COLORS[self._player_index]
            current_roll = current_game.current_roll
            standing = current_game.pins_standing

        return MatchSnapshot(
            active_player_count=len(players),
            players=players,
            current_frame=current_frame,
            current_player_number=current_number,
            current_player_color=current_color,
            current_roll=current_roll,
            pins_standing=standing,
            complete=self._complete,
            standings=tuple(standings),
            winners=winners,
        )

    def _player_snapshot(self, index: int, game: BowlingGame) -> PlayerSnapshot:
        bowling = game.snapshot()
        return PlayerSnapshot(
            player_number=index + 1,
            color=self._COLORS[index],
            bowling=bowling,
            confirmed_score=bowling.confirmed_score,
            complete=bowling.complete,
        )
