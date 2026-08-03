"""Black-box tests for cumulative multiplayer coordination."""

import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain import (
    CumulativeMatch,
    CumulativeMatchCompleteError,
    IllegalCumulativeRollError,
    InvalidCumulativeConfigurationError,
    InvalidCumulativeMatchConfigurationError,
    PlayerColor,
)


class CumulativeMatchConfigurationTests(unittest.TestCase):
    def test_fixed_player_colors_for_every_supported_count(self) -> None:
        colors = tuple(PlayerColor)
        for count in range(1, 5):
            with self.subTest(count=count):
                snapshot = CumulativeMatch(count, (10,) * 3).snapshot()
                self.assertEqual(snapshot.active_player_count, count)
                self.assertEqual(
                    tuple(player.color for player in snapshot.players), colors[:count]
                )

    def test_invalid_player_counts_are_rejected(self) -> None:
        for count in (0, -1, 5, True, False, 1.0, "1"):
            with self.subTest(count=count):
                with self.assertRaises(InvalidCumulativeMatchConfigurationError):
                    CumulativeMatch(count, (10,) * 3)  # type: ignore[arg-type]

    def test_cumulative_game_validates_frame_configuration(self) -> None:
        invalid = ((), (10,), (10,) * 4, (10, 10, 0), [10, 10, 10])
        for maximums in invalid:
            with self.subTest(maximums=maximums):
                with self.assertRaises(InvalidCumulativeConfigurationError):
                    CumulativeMatch(2, maximums)  # type: ignore[arg-type]

    def test_three_five_and_ten_frame_configurations_work(self) -> None:
        for count in (3, 5, 10):
            snapshot = CumulativeMatch(1, (10,) * count).snapshot()
            self.assertEqual(snapshot.frame_count, count)
            self.assertEqual(len(snapshot.players[0].cumulative.frames), count)

    def test_every_player_receives_identical_variable_maximums(self) -> None:
        maximums = (75, 120, 90)
        snapshot = CumulativeMatch(4, maximums).snapshot()
        self.assertEqual(snapshot.frame_max_scores, maximums)
        for player in snapshot.players:
            self.assertEqual(
                tuple(frame.maximum_score for frame in player.cumulative.frames),
                maximums,
            )

    def test_no_public_games_collection_exists(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        self.assertFalse(hasattr(match, "games"))


class CumulativeMatchIndependenceTests(unittest.TestCase):
    def test_first_players_state_does_not_mutate_second_player(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        match.roll(6)
        snapshot = match.snapshot()
        first, second = snapshot.players
        self.assertEqual(first.total_score, 6)
        self.assertEqual(first.cumulative.frames[0].rolls[0].points, 6)
        self.assertEqual(first.cumulative.remaining_capacity, 4)
        self.assertEqual(second.total_score, 0)
        self.assertEqual(second.cumulative.frames[0].rolls, ())
        self.assertEqual(second.cumulative.remaining_capacity, 10)

    def test_player_roll_histories_remain_separate_after_rotation(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        for points in (4, 3, 8):
            match.roll(points)
        first, second = match.snapshot().players
        self.assertEqual(
            tuple(roll.points for roll in first.cumulative.frames[0].rolls), (4, 3)
        )
        self.assertEqual(
            tuple(roll.points for roll in second.cumulative.frames[0].rolls), (8,)
        )


class CumulativeMatchTurnTests(unittest.TestCase):
    def test_first_roll_keeps_player_and_selects_roll_two(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        result = match.roll(4)
        self.assertFalse(result.turn_ended)
        self.assertFalse(result.global_frame_ended)
        self.assertEqual(result.next_player_number, 1)
        self.assertEqual(result.match.current_roll_number, 2)
        self.assertEqual(result.match.current_remaining_capacity, 6)

    def test_second_roll_advances_to_next_player(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        match.roll(4)
        result = match.roll(3)
        self.assertTrue(result.turn_ended)
        self.assertFalse(result.global_frame_ended)
        self.assertEqual(result.player_number, 1)
        self.assertEqual(result.next_player_number, 2)
        self.assertEqual(result.next_player_color, PlayerColor.RED)
        self.assertEqual(result.match.current_global_frame_number, 1)

    def test_last_players_second_roll_ends_frame_and_returns_to_blue(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        for points in (1, 2, 3):
            match.roll(points)
        result = match.roll(4)
        self.assertTrue(result.global_frame_ended)
        self.assertEqual(result.next_player_number, 1)
        self.assertEqual(result.next_player_color, PlayerColor.BLUE)
        self.assertEqual(result.match.current_global_frame_number, 2)

    def test_global_frame_waits_for_every_player(self) -> None:
        match = CumulativeMatch(3, (10,) * 3)
        for _ in range(5):
            result = match.roll(0)
            self.assertEqual(result.match.current_global_frame_number, 1)
        result = match.roll(0)
        self.assertEqual(result.match.current_global_frame_number, 2)

    def test_player_game_may_advance_while_global_frame_does_not(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        match.roll(1)
        match.roll(2)
        snapshot = match.snapshot()
        self.assertEqual(snapshot.players[0].cumulative.current_frame_number, 2)
        self.assertEqual(snapshot.current_global_frame_number, 1)

    def test_full_capacity_first_roll_requires_zero_before_rotation(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        result = match.roll(10)
        self.assertFalse(result.turn_ended)
        self.assertEqual(result.match.current_player_number, 1)
        self.assertEqual(result.match.current_remaining_capacity, 0)
        before = match.snapshot()
        with self.assertRaises(IllegalCumulativeRollError):
            match.roll(1)
        self.assertEqual(match.snapshot(), before)
        result = match.roll(0)
        self.assertTrue(result.turn_ended)
        self.assertEqual(result.next_player_number, 2)

    def test_rejected_rolls_leave_entire_match_unchanged(self) -> None:
        for points in (-1, 11, True, False, 1.0, "1"):
            match = CumulativeMatch(2, (10,) * 3)
            before = match.snapshot()
            with self.subTest(points=points):
                with self.assertRaises(IllegalCumulativeRollError):
                    match.roll(points)  # type: ignore[arg-type]
                self.assertEqual(match.snapshot(), before)

    def test_variable_maximum_resets_for_each_player_and_frame(self) -> None:
        match = CumulativeMatch(2, (75, 120, 90))
        for points in (75, 0, 60, 10):
            match.roll(points)
        snapshot = match.snapshot()
        self.assertEqual(snapshot.current_global_frame_number, 2)
        self.assertEqual(snapshot.current_frame_maximum, 120)
        self.assertEqual(snapshot.current_remaining_capacity, 120)
        self.assertEqual(snapshot.players[1].cumulative.frames[0].score, 70)


class CumulativeMatchCompletionTests(unittest.TestCase):
    def test_exact_roll_count_completes_each_match_shape(self) -> None:
        for players, frames in ((1, 3), (2, 3), (4, 5)):
            match = CumulativeMatch(players, (10,) * frames)
            expected = players * frames * 2
            for _ in range(expected - 1):
                match.roll(0)
                self.assertFalse(match.is_complete)
            match.roll(0)
            self.assertTrue(match.is_complete)

    def test_match_waits_for_last_player_in_final_frame(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        for _ in range(11):
            match.roll(0)
        self.assertTrue(match.snapshot().players[0].complete)
        self.assertFalse(match.snapshot().complete)
        result = match.roll(0)
        self.assertTrue(result.global_frame_ended)
        self.assertTrue(result.match.complete)

    def test_completed_current_fields_are_none(self) -> None:
        match = CumulativeMatch(1, (10,) * 3)
        for _ in range(6):
            match.roll(0)
        snapshot = match.snapshot()
        self.assertIsNone(snapshot.current_global_frame_number)
        self.assertIsNone(snapshot.current_player_number)
        self.assertIsNone(snapshot.current_player_color)
        self.assertIsNone(snapshot.current_roll_number)
        self.assertIsNone(snapshot.current_frame_maximum)
        self.assertIsNone(snapshot.current_remaining_capacity)

    def test_roll_after_completion_raises_match_specific_error(self) -> None:
        match = CumulativeMatch(1, (10,) * 3)
        for _ in range(6):
            match.roll(0)
        before = match.snapshot()
        with self.assertRaises(CumulativeMatchCompleteError):
            match.roll(0)
        self.assertEqual(match.snapshot(), before)


class CumulativeMatchStandingTests(unittest.TestCase):
    @staticmethod
    def _complete_with_frame_scores(scores: tuple[int, ...]) -> CumulativeMatch:
        match = CumulativeMatch(len(scores), (100,) * 3)
        for _ in range(3):
            for score in scores:
                match.roll(score)
                match.roll(0)
        return match

    def test_provisional_standings_sort_scores_and_use_competition_ranks(self) -> None:
        match = CumulativeMatch(4, (100,) * 3)
        for score in (100, 100, 80, 60):
            match.roll(score)
            match.roll(0)
        standings = match.snapshot().standings
        self.assertEqual(tuple(row.player_number for row in standings), (1, 2, 3, 4))
        self.assertEqual(tuple(row.rank for row in standings), (1, 1, 3, 4))
        self.assertTrue(all(row.provisional for row in standings))
        self.assertEqual(match.snapshot().winners, ())

    def test_standings_sort_by_score_then_player_number(self) -> None:
        match = CumulativeMatch(3, (100,) * 3)
        for score in (20, 50, 50):
            match.roll(score)
            match.roll(0)
        self.assertEqual(
            tuple(row.player_number for row in match.snapshot().standings), (2, 3, 1)
        )

    def test_final_standings_and_all_tied_winners(self) -> None:
        snapshot = self._complete_with_frame_scores((100, 100, 80, 60)).snapshot()
        self.assertFalse(any(row.provisional for row in snapshot.standings))
        self.assertEqual(tuple(row.rank for row in snapshot.standings), (1, 1, 3, 4))
        self.assertEqual(tuple(player.player_number for player in snapshot.winners), (1, 2))


class CumulativeMatchSnapshotTests(unittest.TestCase):
    def test_snapshots_and_nested_records_are_frozen(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        match.roll(1)
        snapshot = match.snapshot()
        with self.assertRaises(FrozenInstanceError):
            snapshot.complete = True  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            snapshot.players[0].total_score = 9  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            snapshot.standings[0].rank = 9  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            snapshot.players[0].cumulative.frames[0].score = 9  # type: ignore[misc]

    def test_all_public_collections_are_tuples(self) -> None:
        snapshot = CumulativeMatch(2, (10,) * 3).snapshot()
        self.assertIsInstance(snapshot.frame_max_scores, tuple)
        self.assertIsInstance(snapshot.players, tuple)
        self.assertIsInstance(snapshot.standings, tuple)
        self.assertIsInstance(snapshot.winners, tuple)
        self.assertIsInstance(snapshot.players[0].cumulative.frames, tuple)

    def test_retained_snapshot_does_not_change(self) -> None:
        match = CumulativeMatch(2, (10,) * 3)
        retained = match.snapshot()
        match.roll(7)
        match.roll(1)
        self.assertEqual(retained.players[0].total_score, 0)
        self.assertEqual(retained.players[0].cumulative.frames[0].rolls, ())
        self.assertEqual(retained.current_player_number, 1)


if __name__ == "__main__":
    unittest.main()
