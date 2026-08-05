import unittest
from dataclasses import FrozenInstanceError
from fractions import Fraction

from throw_a_strike.domain import (
    ControlStyle, CurveLevel, InvalidThrowControlError, LaneArrow, PowerFeedback,
    ThrowControlCommand, ThrowControlCommandKind as Kind, ThrowControlMachine,
    ThrowControlOutcome, ThrowControlOutcomeKind, ThrowControlPhase as Phase,
    ThrowControlSnapshot, ThrowSetup, THROW_FOUL_SECONDS, THROW_WARNING_SECONDS,
)


def command(kind, timestamp, **values):
    return ThrowControlCommand(kind, timestamp, **values)


def enter_power(machine, timestamp=0):
    machine.apply(command(Kind.CONFIRM, timestamp))
    machine.apply(command(Kind.CONFIRM, timestamp))



class ValueTests(unittest.TestCase):
    def test_public_throw_deadlines(self):
        self.assertEqual(THROW_WARNING_SECONDS, 20.0)
        self.assertEqual(THROW_FOUL_SECONDS, 30.0)

    def test_curve_order_labels_and_strengths(self):
        self.assertEqual([x.name for x in CurveLevel], ["LEFT_3", "LEFT_2", "LEFT_1", "STRAIGHT", "RIGHT_1", "RIGHT_2", "RIGHT_3"])
        self.assertEqual([x.label for x in CurveLevel], ["L3", "L2", "L1", "STR", "R1", "R2", "R3"])
        self.assertEqual([x.strength for x in CurveLevel], [-1, -.66, -.33, 0, .33, .66, 1])

    def test_feedback_values_and_setup_derivations(self):
        expected = [PowerFeedback.WEAK, PowerFeedback.WEAK, PowerFeedback.GOOD, PowerFeedback.PERFECT,
                    PowerFeedback.GOOD, PowerFeedback.POWER, PowerFeedback.OVERDRIVE]
        for power, feedback in zip((40, 50, 60, 70, 80, 90, 100), expected):
            setup = ThrowSetup(ControlStyle.ADVANCED, 0, 1, 2, CurveLevel.LEFT_1, power)
            self.assertIs(setup.power_feedback, feedback)
            self.assertEqual(setup.curve_strength, -.33)

    def test_commands_validate_and_normalize(self):
        hit = command(Kind.DART_HIT, 2, dart_index=0, x=0, y=127)
        self.assertIs(type(hit.timestamp), float)
        command(Kind.DART_HIT, 2, dart_index=11, x=127, y=0)
        for kwargs in ({}, {"dart_index": -1, "x": 0, "y": 0}, {"dart_index": 12, "x": 0, "y": 0},
                       {"dart_index": 0, "x": -1, "y": 0}, {"dart_index": 0, "x": 0, "y": 128}):
            with self.assertRaises(InvalidThrowControlError): command(Kind.DART_HIT, 0, **kwargs)
        with self.assertRaises(InvalidThrowControlError): command(Kind.LEFT, 0, x=1)
        for timestamp in (-1, True, float("inf"), float("nan")):
            with self.assertRaises(InvalidThrowControlError): command(Kind.TICK, timestamp)

    def test_timestamp_float_conversion_overflow_is_normalized(self):
        with self.assertRaises(InvalidThrowControlError):
            command(Kind.TICK, Fraction(10 ** 10000, 1))

    def test_exact_types_and_frozen_values(self):
        class IntSubclass(int): pass
        with self.assertRaises(InvalidThrowControlError):
            ThrowSetup(ControlStyle.QUICK, IntSubclass(1), 0, 0, CurveLevel.STRAIGHT, 70)
        with self.assertRaises(InvalidThrowControlError): ThrowControlMachine("quick")
        value = ThrowSetup(ControlStyle.QUICK, 0, 0, 0, CurveLevel.STRAIGHT, 70)
        with self.assertRaises(FrozenInstanceError): value.aim_x = 2
        outcome = ThrowControlOutcome(ThrowControlOutcomeKind.THROW, value)
        with self.assertRaises(FrozenInstanceError): outcome.setup = None
        with self.assertRaises(InvalidThrowControlError): ThrowControlOutcome(ThrowControlOutcomeKind.THROW)
        with self.assertRaises(InvalidThrowControlError): ThrowControlOutcome(ThrowControlOutcomeKind.FOUL, value)


class MachineTests(unittest.TestCase):
    def test_initial_states(self):
        quick = ThrowControlMachine(ControlStyle.QUICK).snapshot
        self.assertEqual((quick.phase, quick.curve_level, quick.displayed_power_percent, quick.locked_power_percent),
                         (Phase.THROW_READY, CurveLevel.STRAIGHT, 70, 70))
        advanced = ThrowControlMachine(ControlStyle.ADVANCED).snapshot
        self.assertEqual((advanced.phase, advanced.curve_level, advanced.displayed_power_percent, advanced.locked_power_percent),
                         (Phase.SET_CURVE, CurveLevel.STRAIGHT, 70, None))

    def test_curve_movement_clamps_back_and_confirm(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        for n in range(5): machine.apply(command(Kind.LEFT, 0))
        self.assertIs(machine.snapshot.curve_level, CurveLevel.LEFT_3)
        for n in range(7): machine.apply(command(Kind.RIGHT, 0))
        self.assertIs(machine.snapshot.curve_level, CurveLevel.RIGHT_3)
        # A fresh machine isolates BACK's timer behavior.
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.LEFT, 1)); machine.apply(command(Kind.BACK, 7.9))
        self.assertIs(machine.snapshot.curve_level, CurveLevel.STRAIGHT)
        machine.apply(command(Kind.TICK, 600))
        self.assertIs(machine.snapshot.phase, Phase.SET_CURVE)

    def test_curve_confirm_preserves_selection(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 1)); machine.apply(command(Kind.CONFIRM, 2))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level), (Phase.SET_LANE_ARROW, CurveLevel.RIGHT_1))

    def test_curve_has_no_timeout(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.LEFT, 1)); machine.apply(command(Kind.TICK, 600))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level), (Phase.SET_CURVE, CurveLevel.LEFT_1))

    def test_exact_meter_sequence_and_cycle(self):
        values = (40, 50, 60, 70, 80, 90, 100, 90, 80, 70, 60, 50, 40)
        for step, expected in enumerate(values):
            machine = ThrowControlMachine(ControlStyle.ADVANCED)
            enter_power(machine, 0)
            machine.apply(command(Kind.TICK, step * .2))
            self.assertEqual(machine.snapshot.displayed_power_percent, expected)

    def test_every_meter_transition_uses_strict_half_open_intervals(self):
        sequence = (40, 50, 60, 70, 80, 90, 100, 90, 80, 70, 60, 50, 40)
        nanosecond = 0.000000001
        for step in range(1, len(sequence)):
            boundary = step * 0.200
            with self.subTest(step=step, position="before"):
                machine = ThrowControlMachine(ControlStyle.ADVANCED)
                enter_power(machine, 0)
                machine.apply(command(Kind.TICK, boundary - nanosecond))
                self.assertEqual(machine.snapshot.displayed_power_percent, sequence[step - 1])
            with self.subTest(step=step, position="exact"):
                machine = ThrowControlMachine(ControlStyle.ADVANCED)
                enter_power(machine, 0)
                machine.apply(command(Kind.TICK, boundary))
                self.assertEqual(machine.snapshot.displayed_power_percent, sequence[step])
            with self.subTest(step=step, position="after"):
                machine = ThrowControlMachine(ControlStyle.ADVANCED)
                enter_power(machine, 0)
                machine.apply(command(Kind.TICK, boundary + nanosecond))
                self.assertEqual(machine.snapshot.displayed_power_percent, sequence[step])

        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        enter_power(machine, 0)
        machine.apply(command(Kind.TICK, 2.399999999))
        self.assertEqual(machine.snapshot.displayed_power_percent, 50)
        machine.apply(command(Kind.TICK, 2.400))
        self.assertEqual(machine.snapshot.displayed_power_percent, 40)

        # The same strict boundary behavior repeats in a later cycle.
        for timestamp, expected in ((3.199999999, 70), (3.200, 80), (3.200000001, 80)):
            with self.subTest(timestamp=timestamp):
                later = ThrowControlMachine(ControlStyle.ADVANCED)
                enter_power(later, 0)
                later.apply(command(Kind.TICK, timestamp))
                self.assertEqual(later.snapshot.displayed_power_percent, expected)

    def test_confirm_observes_strict_first_meter_boundary(self):
        before = ThrowControlMachine(ControlStyle.ADVANCED)
        enter_power(before, 0)
        before.apply(command(Kind.CONFIRM, 0.799999999))
        self.assertEqual(before.snapshot.locked_power_percent, 70)

        exact = ThrowControlMachine(ControlStyle.ADVANCED)
        enter_power(exact, 0)
        exact.apply(command(Kind.CONFIRM, 0.800))
        self.assertEqual(exact.snapshot.locked_power_percent, 80)
        self.assertIs(exact.snapshot.power_feedback, PowerFeedback.GOOD)

    def test_meter_uses_elapsed_time_and_confirm_locks(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        enter_power(machine, 0)
        machine.apply(command(Kind.TICK, 0.01)); machine.apply(command(Kind.CONFIRM, 0.80))
        self.assertEqual(machine.snapshot.locked_power_percent, 80)
        self.assertIs(machine.snapshot.power_feedback, PowerFeedback.GOOD)

    def test_power_back_and_no_timeout(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 0)); enter_power(machine, 0); machine.apply(command(Kind.TICK, .45))
        machine.apply(command(Kind.BACK, 1))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level, machine.snapshot.locked_power_percent), (Phase.SET_LANE_ARROW, CurveLevel.RIGHT_1, None))
        machine.apply(command(Kind.CONFIRM, 2)); self.assertEqual(machine.snapshot.displayed_power_percent, 40)
        machine.apply(command(Kind.TICK, 602))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.locked_power_percent), (Phase.SET_POWER, None))

    def test_quick_throw_preserves_raw_values_and_is_terminal(self):
        machine = ThrowControlMachine(ControlStyle.QUICK)
        machine.apply(command(Kind.BACK, 1))
        result = machine.apply(command(Kind.DART_HIT, 2, dart_index=11, x=3, y=124))
        setup = result.outcome.setup
        self.assertEqual((setup.dart_index, setup.aim_x, setup.aim_y, setup.curve_level, setup.power_percent),
                         (11, 3, 124, CurveLevel.STRAIGHT, 70))
        first = result.outcome
        machine.apply(command(Kind.DART_HIT, 3, dart_index=1, x=9, y=8))
        self.assertIs(machine.snapshot.outcome, first)

    def test_advanced_success_preserves_controls_and_raw_aim(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.LEFT, 0))
        enter_power(machine, 0)
        machine.apply(command(Kind.CONFIRM, 0.800))
        result = machine.apply(
            command(Kind.DART_HIT, 1, dart_index=9, x=17, y=113)
        )
        self.assertIs(result.phase, Phase.COMPLETE)
        self.assertIs(result.outcome.kind, ThrowControlOutcomeKind.THROW)
        setup = result.outcome.setup
        self.assertEqual(
            (setup.curve_level, setup.power_percent, setup.lane_arrow),
            (CurveLevel.LEFT_1, 80, LaneArrow.CENTER),
        )
        self.assertEqual((setup.dart_index, setup.aim_x, setup.aim_y), (9, 17, 113))
        first = result.outcome
        machine.apply(command(Kind.DART_HIT, 2, dart_index=1, x=113, y=17))
        self.assertIs(machine.snapshot.outcome, first)

    def test_advanced_ready_back_warning_and_foul(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 0)); enter_power(machine, 0); machine.apply(command(Kind.CONFIRM, .80))
        self.assertEqual((machine.snapshot.curve_level, machine.snapshot.locked_power_percent), (CurveLevel.RIGHT_1, 80))
        machine.apply(command(Kind.TICK, 20.149)); self.assertFalse(machine.snapshot.warning_active)
        machine.apply(command(Kind.TICK, 20.80)); self.assertTrue(machine.snapshot.warning_active)
        machine.apply(command(Kind.TICK, 30.80)); self.assertIs(machine.snapshot.phase, Phase.FOUL)
        self.assertIs(machine.snapshot.outcome.kind, ThrowControlOutcomeKind.FOUL)
        self.assertIsNone(machine.snapshot.outcome.setup)

    def test_ready_back_restarts_power(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        enter_power(machine, 0); machine.apply(command(Kind.CONFIRM, .45)); machine.apply(command(Kind.BACK, 1))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.displayed_power_percent, machine.snapshot.locked_power_percent), (Phase.SET_POWER, 40, None))

    def test_early_curve_recovery_preserves_and_restarts(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.LEFT, 1)); machine.apply(command(Kind.DART_HIT, 2, dart_index=0, x=1, y=2))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level, machine.snapshot.outcome), (Phase.SET_CURVE, CurveLevel.LEFT_1, None))
        machine.apply(command(Kind.TICK, 100)); self.assertIs(machine.snapshot.phase, Phase.SET_CURVE)
        machine.apply(command(Kind.REARMED, 101)); machine.apply(command(Kind.TICK, 108.9))
        self.assertIs(machine.snapshot.phase, Phase.SET_CURVE)
        machine.apply(command(Kind.TICK, 600)); self.assertIs(machine.snapshot.phase, Phase.SET_CURVE)

    def test_early_power_recovery_restarts_meter(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 0)); enter_power(machine, 0); machine.apply(command(Kind.DART_HIT, 1, dart_index=0, x=0, y=0))
        machine.apply(command(Kind.DART_HIT, 50, dart_index=1, x=1, y=1)); machine.apply(command(Kind.REARMED, 51))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level, machine.snapshot.displayed_power_percent), (Phase.SET_POWER, CurveLevel.RIGHT_1, 70))

    def test_monotonic_rejection_is_atomic_and_equal_allowed(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED, 5)
        machine.apply(command(Kind.LEFT, 5)); before = machine.snapshot
        with self.assertRaises(InvalidThrowControlError): machine.apply(command(Kind.RIGHT, 4))
        self.assertEqual(machine.snapshot, before)
        machine.apply(command(Kind.RIGHT, 5))

    def test_sparse_tick_does_not_cross_setup(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.TICK, 600))
        self.assertIs(machine.snapshot.phase, Phase.SET_CURVE)

    def test_quick_warning_and_foul_exact_boundaries(self):
        machine = ThrowControlMachine(ControlStyle.QUICK)
        machine.apply(command(Kind.TICK, 19.999)); self.assertFalse(machine.snapshot.warning_active)
        machine.apply(command(Kind.TICK, 20.0)); self.assertTrue(machine.snapshot.warning_active)
        machine.apply(command(Kind.TICK, 29.999))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.warning_active), (Phase.THROW_READY, True))
        result = machine.apply(command(Kind.TICK, 30.0))
        self.assertEqual((result.phase, result.warning_active), (Phase.FOUL, False))
        self.assertIs(result.outcome.kind, ThrowControlOutcomeKind.FOUL)
        self.assertIsNone(result.outcome.setup)

    def test_dart_deadline_precedence(self):
        before = ThrowControlMachine(ControlStyle.QUICK)
        self.assertIs(before.apply(command(Kind.DART_HIT, 29.999, dart_index=0, x=1, y=2)).phase, Phase.COMPLETE)
        for timestamp in (30.0, 30.001):
            with self.subTest(timestamp=timestamp):
                machine = ThrowControlMachine(ControlStyle.QUICK)
                result = machine.apply(command(Kind.DART_HIT, timestamp, dart_index=0, x=1, y=2))
                self.assertIs(result.phase, Phase.FOUL)
                self.assertIsNone(result.outcome.setup)

    def test_sparse_quick_ticks_at_and_beyond_foul(self):
        for timestamp in (30.0, 300.0):
            machine = ThrowControlMachine(ControlStyle.QUICK)
            self.assertIs(machine.apply(command(Kind.TICK, timestamp)).phase, Phase.FOUL)

    def test_no_public_reset(self):
        self.assertFalse(hasattr(ThrowControlMachine(ControlStyle.QUICK), "reset"))


if __name__ == "__main__": unittest.main()
