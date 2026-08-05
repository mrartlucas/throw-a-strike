import unittest

from throw_a_strike.domain import (
    BowlingGame,
    BowlingThrowResultKind,
    ControlStyle,
    CurveLevel,
    LaneArrow,
    PowerFeedback,
    ThrowControlCommand,
    ThrowControlCommandKind,
    ThrowControlMachine,
    ThrowControlPhase,
    ThrowSetup,
    build_ball_trajectory,
    resolve_ball_pinfall,
)
from throw_a_strike.domain.bowling_round import FULL_RACK


def command(kind, timestamp=0, **values):
    return ThrowControlCommand(kind, timestamp, **values)


def resolution(
    style,
    x,
    y,
    power=70,
    curve=CurveLevel.STRAIGHT,
    arrow=LaneArrow.CENTER,
    standing=FULL_RACK,
):
    setup = ThrowSetup(style, 0, x, y, curve, power, arrow)
    return resolve_ball_pinfall(build_ball_trajectory(setup), standing)


class Phase0X2Tests(unittest.TestCase):
    def test_quick_bullseye_and_center_line(self):
        self.assertEqual(resolution(ControlStyle.QUICK, 64, 64).knocked_down, FULL_RACK)
        self.assertEqual(resolution(ControlStyle.QUICK, 69, 66).knocked_down, FULL_RACK)
        self.assertNotEqual(resolution(ControlStyle.QUICK, 64, 20).knocked_down, FULL_RACK)

    def test_quick_perfect_game(self):
        game = BowlingGame()
        for _ in range(12):
            result = resolution(ControlStyle.QUICK, 64, 64)
            game.roll(len(result.knocked_down))
        self.assertEqual(game.confirmed_score, 300)

    def test_split_contact_recipes(self):
        self.assertEqual(resolution(ControlStyle.QUICK, 34, 23, standing=(7, 10)).knocked_down, (7,))
        self.assertEqual(resolution(ControlStyle.QUICK, 30, 23, standing=(7, 10)).knocked_down, (7, 10))
        self.assertEqual(resolution(ControlStyle.QUICK, 94, 23, standing=(7, 10)).knocked_down, (10,))
        self.assertEqual(resolution(ControlStyle.QUICK, 98, 23, standing=(7, 10)).knocked_down, (7, 10))
        self.assertEqual(resolution(ControlStyle.QUICK, 37, 23, standing=(7, 10)).knocked_down, (7,))

    def test_lone_pin_and_gutter_miss(self):
        self.assertEqual(resolution(ControlStyle.QUICK, 54, 23, standing=(8,)).knocked_down, (8,))
        self.assertIs(resolution(ControlStyle.QUICK, 0, 64).result_kind, BowlingThrowResultKind.GUTTER)
        self.assertIs(resolution(ControlStyle.QUICK, 64, 100).result_kind, BowlingThrowResultKind.MISS)

    def test_advanced_arrow_flow_and_stale_dart(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        self.assertIs(machine.snapshot.phase, ThrowControlPhase.SET_AIM)
        for timestamp in (0.1, 0.2, 0.3):
            machine.apply(command(ThrowControlCommandKind.LEFT, timestamp))
        self.assertIs(machine.snapshot.lane_arrow, LaneArrow.FAR_LEFT)
        machine.apply(command(ThrowControlCommandKind.DART_HIT, 0.4, dart_index=0, x=1, y=1))
        self.assertTrue(machine.snapshot.early_warning_active)
        machine.apply(command(ThrowControlCommandKind.RIGHT, 0.5))
        machine.apply(command(ThrowControlCommandKind.CONFIRM, 0.6))
        self.assertIs(machine.snapshot.phase, ThrowControlPhase.SET_CURVE)
        machine.apply(command(ThrowControlCommandKind.CONFIRM, 0.7))
        machine.apply(command(ThrowControlCommandKind.CONFIRM, 1.4))
        self.assertIsNone(machine.apply(command(ThrowControlCommandKind.DART_HIT, 1.5, dart_index=0, x=64, y=64)).outcome)
        machine.apply(command(ThrowControlCommandKind.REARMED, 1.6))
        self.assertIsNone(machine.snapshot.stale_dart_index)
        self.assertIs(machine.apply(command(ThrowControlCommandKind.DART_HIT, 1.7, dart_index=0, x=64, y=64)).phase, ThrowControlPhase.COMPLETE)

    def test_curve_rearm_clears_stale_before_setup_continues(self):
        machine = ThrowControlMachine(ControlStyle.ADVANCED)
        machine.apply(command(ThrowControlCommandKind.DART_HIT, 0.1, dart_index=2, x=5, y=5))
        machine.apply(command(ThrowControlCommandKind.REARMED, 0.2))
        machine.apply(command(ThrowControlCommandKind.CONFIRM, 0.3))
        machine.apply(command(ThrowControlCommandKind.CONFIRM, 0.4))
        machine.apply(command(ThrowControlCommandKind.CONFIRM, 0.5))
        snapshot = machine.apply(command(ThrowControlCommandKind.DART_HIT, 0.6, dart_index=2, x=64, y=64))
        self.assertIs(snapshot.phase, ThrowControlPhase.COMPLETE)

    def test_trajectory_arrows_and_power(self):
        starts = [build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED, 0, 64, 40, CurveLevel.STRAIGHT, 70, arrow)).start_x for arrow in LaneArrow]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(starts[2] * 2, starts[0] + starts[4])
        self.assertEqual(starts[2] * 2, starts[1] + starts[3])
        left = build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED, 0, 54, 40, CurveLevel.RIGHT_1, 70, LaneArrow.LEFT))
        right = build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED, 0, 74, 40, CurveLevel.LEFT_1, 70, LaneArrow.RIGHT))
        self.assertEqual(left.start_x + right.start_x, 128)
        self.assertAlmostEqual(left.control_x + right.control_x, 128.0)
        self.assertAlmostEqual(left.entry_angle, -right.entry_angle)
        self.assertIs(ThrowSetup(ControlStyle.ADVANCED, 0, 1, 1, CurveLevel.STRAIGHT, 70).power_feedback, PowerFeedback.PERFECT)

    def test_advanced_bullseye_requires_aligned_controls(self):
        quick = resolution(ControlStyle.QUICK, 64, 64)
        aligned = resolution(ControlStyle.ADVANCED, 64, 64, 100, CurveLevel.LEFT_3, LaneArrow.FAR_RIGHT)
        poor_arrow = resolution(ControlStyle.ADVANCED, 64, 64, 100, CurveLevel.LEFT_3, LaneArrow.FAR_LEFT)
        poor_curve = resolution(ControlStyle.ADVANCED, 64, 64, 100, CurveLevel.RIGHT_3, LaneArrow.FAR_RIGHT)
        self.assertEqual(quick.knocked_down, FULL_RACK)
        self.assertEqual(aligned.knocked_down, FULL_RACK)
        self.assertNotEqual(poor_arrow.knocked_down, FULL_RACK)
        self.assertNotEqual(poor_curve.knocked_down, FULL_RACK)

    def test_power_risk_and_rebound(self):
        self.assertEqual(resolution(ControlStyle.ADVANCED, 39, 23, 100, CurveLevel.LEFT_3, LaneArrow.FAR_RIGHT, (7, 10)).knocked_down, (7, 10))
        self.assertEqual(resolution(ControlStyle.ADVANCED, 39, 23, 100, CurveLevel.STRAIGHT, LaneArrow.CENTER, (7, 10)).knocked_down, (7,))
        self.assertEqual(resolution(ControlStyle.ADVANCED, 89, 23, 100, CurveLevel.RIGHT_3, LaneArrow.FAR_LEFT, (7, 10)).knocked_down, (7, 10))
        self.assertEqual(resolution(ControlStyle.QUICK, 39, 23, standing=(7, 10)).knocked_down, (7,))
        self.assertNotEqual(resolution(ControlStyle.ADVANCED, 64, 64, 40).knocked_down, FULL_RACK)


if __name__ == "__main__":
    unittest.main()
