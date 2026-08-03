"""Tests for the pure two-roll cumulative scoring state machine."""

import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain.cumulative import (
    CumulativeGame,
    IllegalCumulativeRollError,
    InvalidCumulativeConfigurationError,
)


class CumulativeConfigurationTests(unittest.TestCase):
    def test_allowed_frame_counts(self) -> None:
        for count in (3, 5, 10):
            with self.subTest(count=count):
                game = CumulativeGame((10,) * count)
                self.assertEqual(game.snapshot().frame_count, count)

    def test_disallowed_frame_counts(self) -> None:
        for count in (0, 1, 2, 4, 6, 11):
            with self.subTest(count=count):
                with self.assertRaises(InvalidCumulativeConfigurationError):
                    CumulativeGame((10,) * count)

    def test_configuration_must_be_an_immutable_tuple(self) -> None:
        with self.assertRaises(InvalidCumulativeConfigurationError):
            CumulativeGame([10, 10, 10])  # type: ignore[arg-type]

    def test_frame_maximums_must_be_non_boolean_integers(self) -> None:
        for value in (True, False, 1.5, "10"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidCumulativeConfigurationError):
                    CumulativeGame((10, 10, value))  # type: ignore[arg-type]

    def test_frame_maximums_must_be_positive(self) -> None:
        for value in (0, -1):
            with self.subTest(value=value):
                with self.assertRaises(InvalidCumulativeConfigurationError):
                    CumulativeGame((10, 10, value))

    def test_standard_mode_configurations(self) -> None:
        hundred_pin = CumulativeGame((100, 100, 100)).snapshot()
        remix = CumulativeGame((10,) * 5).snapshot()
        self.assertEqual(tuple(f.maximum_score for f in hundred_pin.frames), (100,) * 3)
        self.assertEqual(tuple(f.maximum_score for f in remix.frames), (10,) * 5)

    def test_variable_party_configuration(self) -> None:
        snapshot = CumulativeGame((75, 120, 90)).snapshot()
        self.assertEqual(
            tuple(frame.maximum_score for frame in snapshot.frames), (75, 120, 90)
        )


class CumulativeRollTests(unittest.TestCase):
    def test_first_roll_keeps_frame_active_and_selects_roll_two(self) -> None:
        game = CumulativeGame((10, 10, 10))
        game.roll(4)
        snapshot = game.snapshot()
        self.assertEqual(snapshot.current_frame_number, 1)
        self.assertEqual(snapshot.current_roll_number, 2)
        self.assertFalse(snapshot.frames[0].complete)

    def test_second_roll_completes_frame_and_advances(self) -> None:
        game = CumulativeGame((10, 20, 30))
        game.roll(4)
        game.roll(3)
        snapshot = game.snapshot()
        self.assertTrue(snapshot.frames[0].complete)
        self.assertEqual(snapshot.current_frame_number, 2)
        self.assertEqual(snapshot.current_roll_number, 1)
        self.assertEqual(snapshot.current_frame_maximum, 20)
        self.assertEqual(snapshot.remaining_capacity, 20)

    def test_full_capacity_first_roll_still_requires_zero(self) -> None:
        game = CumulativeGame((100, 100, 100))
        game.roll(100)
        snapshot = game.snapshot()
        self.assertEqual(snapshot.current_roll_number, 2)
        self.assertEqual(snapshot.remaining_capacity, 0)
        self.assertFalse(snapshot.frames[0].complete)
        game.roll(0)
        self.assertEqual(game.snapshot().current_frame_number, 2)

    def test_nonzero_roll_after_full_capacity_is_rejected(self) -> None:
        game = CumulativeGame((10, 10, 10))
        game.roll(10)
        before = game.snapshot()
        with self.assertRaises(IllegalCumulativeRollError):
            game.roll(1)
        self.assertEqual(game.snapshot(), before)

    def test_roll_above_remaining_capacity_is_atomic(self) -> None:
        game = CumulativeGame((10, 10, 10))
        game.roll(7)
        before = game.snapshot()
        with self.assertRaises(IllegalCumulativeRollError):
            game.roll(4)
        self.assertEqual(game.snapshot(), before)

    def test_negative_roll_is_atomic(self) -> None:
        game = CumulativeGame((10, 10, 10))
        before = game.snapshot()
        with self.assertRaises(IllegalCumulativeRollError):
            game.roll(-1)
        self.assertEqual(game.snapshot(), before)

    def test_non_integer_rolls_are_rejected(self) -> None:
        for points in (True, False, 1.0, "1"):
            game = CumulativeGame((10, 10, 10))
            before = game.snapshot()
            with self.subTest(points=points):
                with self.assertRaises(IllegalCumulativeRollError):
                    game.roll(points)  # type: ignore[arg-type]
                self.assertEqual(game.snapshot(), before)

    def test_zero_point_rolls_are_legal(self) -> None:
        game = CumulativeGame((10, 10, 10))
        first = game.roll(0)
        second = game.roll(0)
        self.assertEqual((first.points, second.points), (0, 0))
        self.assertEqual(game.snapshot().frames[0].score, 0)

    def test_roll_snapshot_records_capacity_transition(self) -> None:
        roll = CumulativeGame((75, 120, 90)).roll(25)
        self.assertEqual(roll.frame_number, 1)
        self.assertEqual(roll.roll_number, 1)
        self.assertEqual(roll.points, 25)
        self.assertEqual(roll.remaining_before, 75)
        self.assertEqual(roll.remaining_after, 50)

    def test_frame_maximums_apply_independently(self) -> None:
        game = CumulativeGame((75, 120, 90))
        for points in (70, 5, 100, 20, 80, 10):
            game.roll(points)
        snapshot = game.snapshot()
        self.assertEqual(tuple(frame.score for frame in snapshot.frames), (75, 120, 90))
        self.assertEqual(snapshot.total_score, 285)

    def test_frame_and_total_scores_are_direct_sums(self) -> None:
        game = CumulativeGame((10, 10, 10))
        for points in (5, 5, 10, 0, 7, 3):
            game.roll(points)
        snapshot = game.snapshot()
        self.assertEqual(tuple(frame.score for frame in snapshot.frames), (10, 10, 10))
        self.assertEqual(snapshot.total_score, 30)

    def test_no_strike_or_spare_bonus_is_applied(self) -> None:
        game = CumulativeGame((10, 10, 10))
        for points in (10, 0, 5, 5, 10, 0):
            game.roll(points)
        self.assertEqual(game.snapshot().total_score, 30)

    def test_frame_score_cannot_exceed_its_maximum(self) -> None:
        for maximum in (10, 100):
            with self.subTest(maximum=maximum):
                game = CumulativeGame((maximum,) * 3)
                game.roll(maximum - 1)
                before = game.snapshot()
                with self.assertRaises(IllegalCumulativeRollError):
                    game.roll(2)
                self.assertEqual(game.snapshot(), before)


class CumulativeCompletionTests(unittest.TestCase):
    def test_games_complete_after_exactly_two_rolls_per_frame(self) -> None:
        for frame_count in (3, 5, 10):
            with self.subTest(frame_count=frame_count):
                game = CumulativeGame((10,) * frame_count)
                for roll_index in range(frame_count * 2 - 1):
                    game.roll(0)
                    self.assertFalse(game.snapshot().complete, roll_index)
                game.roll(0)
                self.assertTrue(game.snapshot().complete)

    def test_completed_current_state_fields_are_none(self) -> None:
        game = CumulativeGame((10, 10, 10))
        for _ in range(6):
            game.roll(0)
        snapshot = game.snapshot()
        self.assertIsNone(snapshot.current_frame_number)
        self.assertIsNone(snapshot.current_roll_number)
        self.assertIsNone(snapshot.current_frame_maximum)
        self.assertIsNone(snapshot.remaining_capacity)

    def test_roll_after_completion_is_rejected_without_mutation(self) -> None:
        game = CumulativeGame((10, 10, 10))
        for _ in range(6):
            game.roll(0)
        before = game.snapshot()
        with self.assertRaises(IllegalCumulativeRollError):
            game.roll(0)
        self.assertEqual(game.snapshot(), before)


class CumulativeSnapshotTests(unittest.TestCase):
    def test_snapshots_and_nested_records_are_frozen(self) -> None:
        game = CumulativeGame((10, 10, 10))
        game.roll(1)
        snapshot = game.snapshot()
        with self.assertRaises(FrozenInstanceError):
            snapshot.total_score = 99  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            snapshot.frames[0].score = 99  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            snapshot.frames[0].rolls[0].points = 99  # type: ignore[misc]

    def test_frame_and_roll_histories_are_tuples(self) -> None:
        game = CumulativeGame((10, 10, 10))
        game.roll(1)
        snapshot = game.snapshot()
        self.assertIsInstance(snapshot.frames, tuple)
        self.assertIsInstance(snapshot.frames[0].rolls, tuple)

    def test_retained_snapshot_does_not_change(self) -> None:
        game = CumulativeGame((10, 10, 10))
        retained = game.snapshot()
        game.roll(4)
        game.roll(5)
        self.assertEqual(retained.total_score, 0)
        self.assertEqual(retained.frames[0].rolls, ())
        self.assertEqual(retained.current_roll_number, 1)


if __name__ == "__main__":
    unittest.main()
