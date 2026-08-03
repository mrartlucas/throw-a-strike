import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain.bowling import IllegalRollError
from throw_a_strike.domain.match import (
    BowlingMatch,
    InvalidMatchConfigurationError,
    MatchCompleteError,
    PlayerColor,
)


class BowlingMatchTests(unittest.TestCase):
    def finish_open_frame(self, match, first=0, second=0):
        match.roll(first)
        return match.roll(second)

    def finish_gutter_match(self, match):
        while not match.is_complete:
            match.roll(0)

    def test_fixed_player_counts_and_colors(self):
        expected = [
            PlayerColor.BLUE,
            PlayerColor.RED,
            PlayerColor.GREEN,
            PlayerColor.YELLOW,
        ]
        for count in range(1, 5):
            with self.subTest(count=count):
                snapshot = BowlingMatch(count).snapshot()
                self.assertEqual(count, snapshot.active_player_count)
                self.assertEqual(expected[:count], [p.color for p in snapshot.players])
                self.assertEqual(list(range(1, count + 1)), [p.player_number for p in snapshot.players])

    def test_invalid_player_counts_are_rejected(self):
        for count in (0, 5, -1, True, 2.0):
            with self.subTest(count=count), self.assertRaises(InvalidMatchConfigurationError):
                BowlingMatch(count)

    def test_non_strike_keeps_player_then_second_roll_advances(self):
        match = BowlingMatch(2)
        first = match.roll(4)
        self.assertFalse(first.turn_ended)
        self.assertEqual((1, PlayerColor.BLUE, 2, 6), (
            first.next_player_number, first.next_player_color,
            first.match.current_roll, first.match.pins_standing,
        ))
        second = match.roll(3)
        self.assertTrue(second.turn_ended)
        self.assertFalse(second.global_frame_ended)
        self.assertEqual((2, PlayerColor.RED), (
            second.next_player_number, second.next_player_color,
        ))

    def test_ordinary_strike_advances_immediately(self):
        result = BowlingMatch(2).roll(10)
        self.assertTrue(result.turn_ended)
        self.assertEqual(2, result.next_player_number)

    def test_final_player_ends_global_frame_and_returns_to_player_one(self):
        match = BowlingMatch(2)
        self.finish_open_frame(match)
        result = self.finish_open_frame(match)
        self.assertTrue(result.global_frame_ended)
        self.assertEqual((2, 1), (result.match.current_frame, result.next_player_number))

    def test_global_frame_waits_for_every_player(self):
        match = BowlingMatch(3)
        self.finish_open_frame(match)
        self.assertEqual(1, match.snapshot().current_frame)
        self.finish_open_frame(match)
        self.assertEqual(1, match.snapshot().current_frame)
        self.finish_open_frame(match)
        self.assertEqual(2, match.snapshot().current_frame)

    def test_games_and_racks_are_independent(self):
        match = BowlingMatch(2)
        self.assertIsNot(match.games[0], match.games[1])
        match.roll(7)
        snapshot = match.snapshot()
        self.assertEqual(3, snapshot.players[0].bowling.pins_standing)
        self.assertEqual(10, snapshot.players[1].bowling.pins_standing)

    def test_one_players_score_does_not_mutate_another(self):
        match = BowlingMatch(2)
        self.finish_open_frame(match, 4, 3)
        snapshot = match.snapshot()
        self.assertEqual(7, snapshot.players[0].confirmed_score)
        self.assertEqual(0, snapshot.players[1].confirmed_score)

    def test_illegal_roll_does_not_rotate(self):
        match = BowlingMatch(2)
        match.roll(8)
        before = match.snapshot()
        with self.assertRaises(IllegalRollError):
            match.roll(3)
        after = match.snapshot()
        self.assertEqual(before, after)
        self.assertEqual(1, after.current_player_number)

    def test_tenth_strike_fill_balls_keep_player(self):
        match = BowlingMatch(2)
        for _ in range(9):
            self.finish_open_frame(match)
            self.finish_open_frame(match)
        one = match.roll(10)
        two = match.roll(10)
        self.assertFalse(one.turn_ended)
        self.assertFalse(two.turn_ended)
        self.assertEqual(1, two.next_player_number)
        three = match.roll(10)
        self.assertTrue(three.turn_ended)
        self.assertEqual(2, three.next_player_number)

    def test_tenth_spare_fill_ball_keeps_player(self):
        match = BowlingMatch(1)
        for _ in range(9):
            self.finish_open_frame(match)
        match.roll(6)
        spare = match.roll(4)
        self.assertFalse(spare.turn_ended)
        self.assertEqual(3, spare.match.current_roll)
        final = match.roll(5)
        self.assertTrue(final.turn_ended)
        self.assertTrue(final.match.complete)

    def test_open_tenth_advances_after_two_rolls(self):
        match = BowlingMatch(2)
        for _ in range(9):
            self.finish_open_frame(match)
            self.finish_open_frame(match)
        match.roll(7)
        result = match.roll(2)
        self.assertTrue(result.turn_ended)
        self.assertFalse(result.match.complete)
        self.assertEqual(2, result.next_player_number)

    def test_match_completes_only_after_every_tenth_frame(self):
        match = BowlingMatch(2)
        for _ in range(9):
            self.finish_open_frame(match)
            self.finish_open_frame(match)
        self.finish_open_frame(match)
        self.assertFalse(match.is_complete)
        self.finish_open_frame(match)
        self.assertTrue(match.is_complete)

    def test_completed_match_rejects_roll_and_clears_current_fields(self):
        match = BowlingMatch(1)
        self.finish_gutter_match(match)
        snapshot = match.snapshot()
        self.assertEqual((None, None, None, None, None), (
            snapshot.current_player_number, snapshot.current_player_color,
            snapshot.current_frame, snapshot.current_roll, snapshot.pins_standing,
        ))
        with self.assertRaises(MatchCompleteError):
            match.roll(0)

    def test_standings_sort_scores_and_use_competition_ranks(self):
        match = BowlingMatch(4)
        # One confirmed open frame per player: 7, 7, 4, 2.
        for first in (7, 7, 4, 2):
            self.finish_open_frame(match, first, 0)
        standings = match.snapshot().standings
        self.assertEqual([1, 2, 3, 4], [s.player_number for s in standings])
        self.assertEqual([1, 1, 3, 4], [s.rank for s in standings])
        self.assertTrue(all(s.provisional for s in standings))

    def test_tied_final_winners_are_all_preserved(self):
        match = BowlingMatch(3)
        self.finish_gutter_match(match)
        snapshot = match.snapshot()
        self.assertEqual([1, 2, 3], [p.player_number for p in snapshot.winners])
        self.assertEqual([1, 1, 1], [s.rank for s in snapshot.standings])
        self.assertTrue(all(not s.provisional for s in snapshot.standings))

    def test_snapshots_are_immutable_and_retained_snapshots_do_not_change(self):
        match = BowlingMatch(1)
        old = match.snapshot()
        with self.assertRaises(FrozenInstanceError):
            old.current_frame = 2
        with self.assertRaises(FrozenInstanceError):
            old.players[0].confirmed_score = 4
        match.roll(4)
        self.assertEqual(10, old.pins_standing)

    def test_single_player_progresses_all_ten_frames(self):
        match = BowlingMatch(1)
        for frame in range(1, 10):
            result = self.finish_open_frame(match, 9, 0)
            self.assertEqual(frame + 1, result.match.current_frame)
            self.assertEqual(1, result.next_player_number)
        self.finish_open_frame(match, 9, 0)
        self.assertEqual(90, match.snapshot().players[0].confirmed_score)
        self.assertTrue(match.is_complete)

    def test_multiplayer_perfect_games_produce_correct_tied_winners(self):
        match = BowlingMatch(2)
        for _ in range(9):
            match.roll(10)
            match.roll(10)
        for _ in range(3):
            match.roll(10)
        for _ in range(3):
            match.roll(10)
        snapshot = match.snapshot()
        self.assertEqual([300, 300], [p.confirmed_score for p in snapshot.players])
        self.assertEqual([1, 2], [p.player_number for p in snapshot.winners])


if __name__ == "__main__":
    unittest.main()
