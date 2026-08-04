import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain import (
    ControlStyle, CurveLevel, InvalidThrowControlError, PowerFeedback,
    ThrowControlCommand, ThrowControlCommandKind as Kind, ThrowControlMachine,
    ThrowControlOutcome, ThrowControlOutcomeKind, ThrowControlPhase as Phase,
    ThrowControlSnapshot, ThrowSetup,
)


def command(kind, timestamp, **values):
    return ThrowControlCommand(kind, timestamp, **values)


class ValueTests(unittest.TestCase):
    def test_curve_order_labels_and_strengths(self):
        self.assertEqual([x.name for x in CurveLevel], ["LEFT_3", "LEFT_2", "LEFT_1", "STRAIGHT", "RIGHT_1", "RIGHT_2", "RIGHT_3"])
        self.assertEqual([x.label for x in CurveLevel], ["L3", "L2", "L1", "STR", "R1", "R2", "R3"])
        self.assertEqual([x.strength for x in CurveLevel], [-1, -.66, -.33, 0, .33, .66, 1])

    def test_feedback_values_and_setup_derivations(self):
        expected = [PowerFeedback.WEAK, PowerFeedback.WEAK, PowerFeedback.GOOD, PowerFeedback.GOOD,
                    PowerFeedback.PERFECT, PowerFeedback.POWER, PowerFeedback.OVERDRIVE]
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
        machine.apply(command(Kind.TICK, 8))
        self.assertIs(machine.snapshot.phase, Phase.SET_POWER)

    def test_curve_confirm_preserves_selection(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 1)); machine.apply(command(Kind.CONFIRM, 2))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level), (Phase.SET_POWER, CurveLevel.RIGHT_1))

    def test_curve_timeout_defaults_straight(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.LEFT, 1)); machine.apply(command(Kind.TICK, 8))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level), (Phase.SET_POWER, CurveLevel.STRAIGHT))

    def test_exact_meter_sequence_and_cycle(self):
        values = (70, 80, 90, 100, 90, 80, 70, 60, 50, 40, 50, 60, 70)
        for step, expected in enumerate(values):
            machine = ThrowControlMachine(ControlStyle.ADVANCED)
            machine.apply(command(Kind.CONFIRM, 0))
            machine.apply(command(Kind.TICK, step * .15))
            self.assertEqual(machine.snapshot.displayed_power_percent, expected)

    def test_meter_uses_elapsed_time_and_confirm_locks(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.CONFIRM, 1))
        machine.apply(command(Kind.TICK, 1.01)); machine.apply(command(Kind.CONFIRM, 1.15))
        self.assertEqual(machine.snapshot.locked_power_percent, 80)
        self.assertIs(machine.snapshot.power_feedback, PowerFeedback.PERFECT)

    def test_power_back_and_timeout(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 0)); machine.apply(command(Kind.CONFIRM, 0)); machine.apply(command(Kind.TICK, .45))
        machine.apply(command(Kind.BACK, 1))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level, machine.snapshot.locked_power_percent), (Phase.SET_CURVE, CurveLevel.RIGHT_1, None))
        machine.apply(command(Kind.CONFIRM, 2)); self.assertEqual(machine.snapshot.displayed_power_percent, 70)
        machine.apply(command(Kind.TICK, 10))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.locked_power_percent), (Phase.THROW_READY, 70))

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

    def test_advanced_ready_back_warning_and_foul(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 0)); machine.apply(command(Kind.CONFIRM, 0)); machine.apply(command(Kind.CONFIRM, .15))
        self.assertEqual((machine.snapshot.curve_level, machine.snapshot.locked_power_percent), (CurveLevel.RIGHT_1, 80))
        machine.apply(command(Kind.TICK, 30.149)); self.assertFalse(machine.snapshot.warning_active)
        machine.apply(command(Kind.TICK, 30.15)); self.assertTrue(machine.snapshot.warning_active)
        machine.apply(command(Kind.TICK, 60.15)); self.assertIs(machine.snapshot.phase, Phase.FOUL)
        self.assertIs(machine.snapshot.outcome.kind, ThrowControlOutcomeKind.FOUL)
        self.assertIsNone(machine.snapshot.outcome.setup)

    def test_ready_back_restarts_power(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.CONFIRM, 0)); machine.apply(command(Kind.CONFIRM, .45)); machine.apply(command(Kind.BACK, 1))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.displayed_power_percent, machine.snapshot.locked_power_percent), (Phase.SET_POWER, 70, None))

    def test_early_curve_recovery_preserves_and_restarts(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.LEFT, 1)); machine.apply(command(Kind.DART_HIT, 2, dart_index=0, x=1, y=2))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level, machine.snapshot.outcome), (Phase.EARLY_DART_RECOVERY, CurveLevel.LEFT_1, None))
        machine.apply(command(Kind.TICK, 100)); self.assertIs(machine.snapshot.phase, Phase.EARLY_DART_RECOVERY)
        machine.apply(command(Kind.REARMED, 101)); machine.apply(command(Kind.TICK, 108.9))
        self.assertIs(machine.snapshot.phase, Phase.SET_CURVE)
        machine.apply(command(Kind.TICK, 109)); self.assertIs(machine.snapshot.phase, Phase.SET_POWER)

    def test_early_power_recovery_restarts_meter(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.RIGHT, 0)); machine.apply(command(Kind.CONFIRM, 0)); machine.apply(command(Kind.DART_HIT, 1, dart_index=0, x=0, y=0))
        machine.apply(command(Kind.DART_HIT, 50, dart_index=1, x=1, y=1)); machine.apply(command(Kind.REARMED, 51))
        self.assertEqual((machine.snapshot.phase, machine.snapshot.curve_level, machine.snapshot.displayed_power_percent), (Phase.SET_POWER, CurveLevel.RIGHT_1, 70))

    def test_monotonic_rejection_is_atomic_and_equal_allowed(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED, 5)
        machine.apply(command(Kind.LEFT, 5)); before = machine.snapshot
        with self.assertRaises(InvalidThrowControlError): machine.apply(command(Kind.RIGHT, 4))
        self.assertEqual(machine.snapshot, before)
        machine.apply(command(Kind.RIGHT, 5))

    def test_sparse_tick_crosses_every_deadline(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(Kind.TICK, 100))
        self.assertIs(machine.snapshot.phase, Phase.FOUL)

    def test_no_public_reset(self):
        self.assertFalse(hasattr(ThrowControlMachine(ControlStyle.QUICK), "reset"))


if __name__ == "__main__": unittest.main()
