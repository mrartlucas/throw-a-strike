import unittest

from throw_a_strike.domain.bowling import BowlingGame, IllegalRollError


class BowlingGameTests(unittest.TestCase):
    def game(self, rolls):
        game = BowlingGame()
        for pins in rolls:
            game.roll(pins)
        return game

    def assert_total(self, rolls, total):
        game = self.game(rolls)
        self.assertTrue(game.is_complete)
        self.assertEqual(total, game.confirmed_score)

    def test_perfect_game(self):
        game = self.game([10] * 12)
        self.assertEqual(300, game.confirmed_score)
        self.assertEqual((10, 10, 10), game.rolls_by_frame[9])

    def test_all_gutters(self):
        self.assert_total([0, 0] * 10, 0)

    def test_all_nine_then_miss(self):
        self.assert_total([9, 0] * 10, 90)

    def test_all_five_spares(self):
        self.assert_total([5, 5] * 10 + [5], 150)

    def test_consecutive_strikes(self):
        game = self.game([10, 10, 3, 4])
        self.assertEqual([23, 17], [f.score for f in game.frames[:2]])
        self.assertEqual(47, game.confirmed_score)

    def test_strike_followed_by_open(self):
        game = self.game([10, 3, 4])
        self.assertEqual([17, 7], [f.score for f in game.frames[:2]])

    def test_spare_followed_by_open(self):
        game = self.game([6, 4, 3, 4])
        self.assertEqual([13, 7], [f.score for f in game.frames[:2]])

    def test_ordinary_gutter_ten_marks_spare(self):
        game = self.game([0, 10])
        self.assertEqual(("-", "/"), game.frames[0].marks)

    def test_ordinary_first_roll_strike_mark(self):
        game = self.game([10])
        self.assertEqual(("X",), game.frames[0].marks)

    def test_ordinary_five_spare_marks(self):
        game = self.game([5, 5])
        self.assertEqual(("5", "/"), game.frames[0].marks)

    def test_ordinary_nine_miss_marks(self):
        game = self.game([9, 0])
        self.assertEqual(("9", "-"), game.frames[0].marks)

    def test_known_mixed_game(self):
        # Canonical example: X 7/ 9- X -8 8/ -6 X X X81 = 167.
        self.assert_total([10, 7, 3, 9, 0, 10, 0, 8, 8, 2, 0, 6, 10, 10, 10, 8, 1], 167)

    def test_tenth_strike_strike_strike(self):
        self.assert_total([0, 0] * 9 + [10, 10, 10], 30)

    def test_tenth_strike_seven_spare(self):
        self.assert_total([0, 0] * 9 + [10, 7, 3], 20)

    def test_tenth_strike_seven_two(self):
        self.assert_total([0, 0] * 9 + [10, 7, 2], 19)

    def test_tenth_seven_spare_strike(self):
        self.assert_total([0, 0] * 9 + [7, 3, 10], 20)

    def test_tenth_gutter_spare_strike(self):
        game = self.game([0, 0] * 9 + [0, 10, 10])
        self.assertEqual(("-", "/", "X"), game.frames[9].marks)
        self.assertEqual(20, game.confirmed_score)

    def test_tenth_strike_gutter_spare_marks(self):
        game = self.game([0, 0] * 9 + [10, 0, 10])
        self.assertEqual(("X", "-", "/"), game.frames[9].marks)

    def test_tenth_three_strikes_marks(self):
        game = self.game([0, 0] * 9 + [10, 10, 10])
        self.assertEqual(("X", "X", "X"), game.frames[9].marks)

    def test_tenth_strike_seven_spare_marks(self):
        game = self.game([0, 0] * 9 + [10, 7, 3])
        self.assertEqual(("X", "7", "/"), game.frames[9].marks)

    def test_open_tenth_ends_after_two(self):
        game = self.game([0, 0] * 9 + [7, 2])
        self.assertTrue(game.is_complete)
        self.assertIsNone(game.current_roll)
        self.assertIsNone(game.snapshot().current_roll)
        with self.assertRaises(IllegalRollError):
            game.roll(0)

    def test_current_roll_is_none_after_completed_bonus_tenth(self):
        strike = self.game([0, 0] * 9 + [10, 10, 10])
        spare = self.game([0, 0] * 9 + [7, 3, 10])
        self.assertIsNone(strike.current_roll)
        self.assertIsNone(strike.snapshot().current_roll)
        self.assertIsNone(spare.current_roll)
        self.assertIsNone(spare.snapshot().current_roll)

    def test_active_current_roll_is_one_based(self):
        game = BowlingGame()
        self.assertEqual(1, game.current_roll)
        game.roll(4)
        self.assertEqual(2, game.current_roll)
        game.roll(3)
        self.assertEqual(1, game.current_roll)
        self.assertEqual(1, game.snapshot().current_roll)

    def test_roll_greater_than_standing_is_rejected_without_mutation(self):
        game = self.game([7])
        with self.assertRaises(IllegalRollError):
            game.roll(4)
        self.assertEqual((7,), game.rolls_by_frame[0])
        self.assertEqual(3, game.pins_standing)

    def test_negative_roll_is_rejected(self):
        with self.assertRaises(IllegalRollError):
            BowlingGame().roll(-1)

    def test_roll_after_completion_is_rejected(self):
        game = self.game([0, 0] * 10)
        with self.assertRaises(IllegalRollError):
            game.roll(0)

    def test_second_roll_uses_remaining_rack(self):
        game = BowlingGame()
        first = game.roll(6)
        second = game.roll(4)
        self.assertEqual((10, 4), (first.standing_before, first.standing_after))
        self.assertEqual((4, 0), (second.standing_before, second.standing_after))
        self.assertEqual(10, game.pins_standing)

    def test_tenth_rack_reset_rules_and_audit_regressions(self):
        game = self.game([0, 0] * 9)
        one = game.roll(10)
        two = game.roll(4)
        three = game.roll(6)
        self.assertEqual([(10, 0), (10, 6), (6, 0)], [
            (r.standing_before, r.standing_after) for r in (one, two, three)
        ])
        self.assertEqual(20, game.frames[9].score)

        double = self.game([0, 0] * 9 + [10, 10])
        self.assertEqual(10, double.pins_standing)
        self.assertEqual((10, 3), (double.roll(7).standing_before, double.pins_standing))

        spare = self.game([0, 0] * 9 + [7, 3])
        self.assertEqual(10, spare.pins_standing)

    def test_incomplete_bonuses_are_unresolved(self):
        strike = self.game([10])
        self.assertIsNone(strike.frames[0].score)
        self.assertEqual(0, strike.confirmed_score)
        strike.roll(3)
        self.assertIsNone(strike.frames[0].score)

        spare = self.game([5, 5])
        self.assertIsNone(spare.frames[0].score)
        self.assertIsNone(spare.frames[0].cumulative_score)
        self.assertEqual(0, spare.confirmed_score)

    def test_snapshot_is_read_only_and_contains_ten_frames(self):
        snapshot = BowlingGame().snapshot()
        self.assertEqual(10, len(snapshot.frames))
        self.assertEqual(1, snapshot.current_frame)
        self.assertEqual(1, snapshot.current_roll)
        with self.assertRaises(Exception):
            snapshot.pins_standing = 4

    def test_invalid_types_are_rejected(self):
        for value in (True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(IllegalRollError):
                BowlingGame().roll(value)


if __name__ == "__main__":
    unittest.main()
