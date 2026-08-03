"""Pure multiplayer coordination for two-roll cumulative games."""

from __future__ import annotations

from dataclasses import dataclass

from .cumulative import CumulativeGame, CumulativeRollSnapshot, CumulativeSnapshot
from .match import PlayerColor


class InvalidCumulativeMatchConfigurationError(ValueError):
    """Raised when a cumulative match has an invalid player count."""


class CumulativeMatchCompleteError(RuntimeError):
    """Raised when a roll is attempted after the match has finished."""


@dataclass(frozen=True)
class CumulativeMatchPlayerSnapshot:
    """Immutable score state for one active player."""

    player_number: int
    color: PlayerColor
    cumulative: CumulativeSnapshot
    total_score: int
    complete: bool


@dataclass(frozen=True)
class CumulativeStandingSnapshot:
    """One competition-ranked provisional or final standing."""

    rank: int
    player_number: int
    color: PlayerColor
    total_score: int
    provisional: bool


@dataclass(frozen=True)
class CumulativeMatchSnapshot:
    """Detached, deeply immutable view of a cumulative match."""

    active_player_count: int
    frame_count: int
    frame_max_scores: tuple[int, ...]
    players: tuple[CumulativeMatchPlayerSnapshot, ...]
    current_global_frame_number: int | None
    current_player_number: int | None
    current_player_color: PlayerColor | None
    current_roll_number: int | None
    current_frame_maximum: int | None
    current_remaining_capacity: int | None
    complete: bool
    standings: tuple[CumulativeStandingSnapshot, ...]
    winners: tuple[CumulativeMatchPlayerSnapshot, ...]


@dataclass(frozen=True)
class CumulativeMatchRollResult:
    """An accepted roll together with its match-level transition."""

    player_number: int
    player_color: PlayerColor
    roll: CumulativeRollSnapshot
    turn_ended: bool
    global_frame_ended: bool
    next_player_number: int | None
    next_player_color: PlayerColor | None
    match: CumulativeMatchSnapshot


class CumulativeMatch:
    """Coordinate independent cumulative games in fixed player order."""

    _COLORS = tuple(PlayerColor)

    def __init__(
        self, player_count: int, frame_max_scores: tuple[int, ...]
    ) -> None:
        if (
            isinstance(player_count, bool)
            or not isinstance(player_count, int)
            or not 1 <= player_count <= 4
        ):
            raise InvalidCumulativeMatchConfigurationError(
                "player_count must be an integer from 1 through 4"
            )

        # CumulativeGame remains the sole authority for frame configuration.
        # Constructing each game separately also guarantees independent state.
        self._games = tuple(
            CumulativeGame(frame_max_scores) for _ in range(player_count)
        )
        self._frame_max_scores = frame_max_scores
        self._player_index = 0
        self._global_frame = 1
        self._complete = False

    @property
    def is_complete(self) -> bool:
        return self._complete

    def roll(self, points: int) -> CumulativeMatchRollResult:
        """Apply points to only the active player and coordinate rotation."""
        if self._complete:
            raise CumulativeMatchCompleteError("the cumulative match is complete")

        player_index = self._player_index
        game = self._games[player_index]
        accepted = game.roll(points)
        turn_ended = accepted.roll_number == 2
        global_frame_ended = False

        if turn_ended:
            if player_index + 1 < len(self._games):
                self._player_index += 1
            else:
                global_frame_ended = True
                if self._global_frame == len(self._frame_max_scores):
                    self._complete = True
                else:
                    self._global_frame += 1
                    self._player_index = 0

        snapshot = self.snapshot()
        return CumulativeMatchRollResult(
            player_number=player_index + 1,
            player_color=self._COLORS[player_index],
            roll=accepted,
            turn_ended=turn_ended,
            global_frame_ended=global_frame_ended,
            next_player_number=snapshot.current_player_number,
            next_player_color=snapshot.current_player_color,
            match=snapshot,
        )

    def snapshot(self) -> CumulativeMatchSnapshot:
        """Build immutable player, standings, winner, and turn state."""
        players = tuple(
            self._player_snapshot(index, game)
            for index, game in enumerate(self._games)
        )
        ordered = sorted(
            players, key=lambda player: (-player.total_score, player.player_number)
        )
        standings: list[CumulativeStandingSnapshot] = []
        previous_score: int | None = None
        previous_rank = 0
        for position, player in enumerate(ordered, start=1):
            rank = previous_rank if player.total_score == previous_score else position
            standings.append(
                CumulativeStandingSnapshot(
                    rank=rank,
                    player_number=player.player_number,
                    color=player.color,
                    total_score=player.total_score,
                    provisional=not self._complete,
                )
            )
            previous_score = player.total_score
            previous_rank = rank

        winners: tuple[CumulativeMatchPlayerSnapshot, ...] = ()
        if self._complete:
            winning_score = ordered[0].total_score
            winners = tuple(
                player for player in ordered if player.total_score == winning_score
            )

        if self._complete:
            global_frame = None
            player_number = None
            color = None
            roll_number = None
            maximum = None
            remaining = None
        else:
            current = players[self._player_index].cumulative
            global_frame = self._global_frame
            player_number = self._player_index + 1
            color = self._COLORS[self._player_index]
            roll_number = current.current_roll_number
            maximum = current.current_frame_maximum
            remaining = current.remaining_capacity

        return CumulativeMatchSnapshot(
            active_player_count=len(players),
            frame_count=len(self._frame_max_scores),
            frame_max_scores=self._frame_max_scores,
            players=players,
            current_global_frame_number=global_frame,
            current_player_number=player_number,
            current_player_color=color,
            current_roll_number=roll_number,
            current_frame_maximum=maximum,
            current_remaining_capacity=remaining,
            complete=self._complete,
            standings=tuple(standings),
            winners=winners,
        )

    def _player_snapshot(
        self, index: int, game: CumulativeGame
    ) -> CumulativeMatchPlayerSnapshot:
        cumulative = game.snapshot()
        return CumulativeMatchPlayerSnapshot(
            player_number=index + 1,
            color=self._COLORS[index],
            cumulative=cumulative,
            total_score=cumulative.total_score,
            complete=cumulative.complete,
        )
