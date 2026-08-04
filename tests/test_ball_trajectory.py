import unittest
from throw_a_strike.domain import (
    BallTrajectory, BallTrajectorySample, ControlStyle, CurveLevel,
    InvalidBallTrajectoryValueError, ThrowSetup, build_ball_trajectory,
    sample_ball_trajectory, sample_ball_trajectory_progress,
    ball_trajectory_point_at_progress, ball_trajectory_derivative_at_progress,
)

class BallTrajectoryTests(unittest.TestCase):
    def setup(self, curve=CurveLevel.STRAIGHT, power=70, x=64, y=40):
        return ThrowSetup(ControlStyle.QUICK if curve is CurveLevel.STRAIGHT and power==70 else ControlStyle.ADVANCED,0,x,y,curve,power)
    def test_constants_mapping_and_raw_coordinates(self):
        t=build_ball_trajectory(self.setup(x=0,y=127))
        self.assertEqual((t.start_x,t.start_y),(64,84)); self.assertEqual((t.raw_aim_x,t.raw_aim_y),(0,127)); self.assertEqual((t.target_x,t.target_y),(12,84))
    def test_pin_centers_are_not_clamped(self):
        for x,y in ((64,72),(54,56),(74,56),(44,40),(64,40),(84,40),(34,23),(54,23),(74,23),(94,23)):
            self.assertEqual((build_ball_trajectory(self.setup(x=x,y=y)).target_x,build_ball_trajectory(self.setup(x=x,y=y)).target_y),(x,y))
    def test_curve_geometry_and_common_target(self):
        levels=list(CurveLevel); paths=[build_ball_trajectory(self.setup(c)) for c in levels]
        self.assertEqual(len({(p.target_x,p.target_y) for p in paths}),1)
        xs=[sample_ball_trajectory(p,p.duration_seconds/2).x for p in paths]
        self.assertEqual(xs,sorted(xs)); self.assertLess(xs[0],xs[2]); self.assertLess(xs[2],xs[3]); self.assertLess(xs[3],xs[4]); self.assertLess(xs[4],xs[6])
    def test_exact_durations_and_order(self):
        expected={40:1.2,50:1.1,60:1.0,70:.9,80:.8,90:.7,100:.6}
        actual={p:build_ball_trajectory(self.setup(power=p)).duration_seconds for p in expected}
        self.assertEqual(actual,expected); self.assertEqual(list(actual.values()),sorted(actual.values(),reverse=True))
    def test_sampling_clamps_and_is_repeatable(self):
        t=build_ball_trajectory(self.setup(x=65,y=23))
        self.assertEqual(sample_ball_trajectory(t,-1),BallTrajectorySample(0.0,64,84))
        self.assertEqual(sample_ball_trajectory(t,t.duration_seconds),BallTrajectorySample(1.0,65,23))
        self.assertEqual(sample_ball_trajectory(t,99),BallTrajectorySample(1.0,65,23))
        self.assertEqual(sample_ball_trajectory(t,.45),sample_ball_trajectory(t,.45))
    def test_half_up_rounding_and_arrival_vector(self):
        t=build_ball_trajectory(self.setup(x=66,y=84))
        self.assertEqual(sample_ball_trajectory(t,.45).x,65)
        self.assertEqual((t.arrival_dx,t.arrival_dy),(2.0,0.0))
    def test_exact_input_validation(self):
        with self.assertRaises(InvalidBallTrajectoryValueError): build_ball_trajectory(None)
        with self.assertRaises(InvalidBallTrajectoryValueError): sample_ball_trajectory(build_ball_trajectory(self.setup()),float('inf'))


    def test_progress_helpers_reject_non_finite_bool_and_non_real_before_clamping(self):
        trajectory = build_ball_trajectory(self.setup())
        helpers = (
            ball_trajectory_point_at_progress,
            ball_trajectory_derivative_at_progress,
            sample_ball_trajectory_progress,
        )
        bad_values = (float("nan"), float("inf"), float("-inf"), True, "0.5")
        for helper in helpers:
            for value in bad_values:
                with self.subTest(helper=helper.__name__, value=repr(value)):
                    with self.assertRaises(InvalidBallTrajectoryValueError):
                        helper(trajectory, value)
        self.assertEqual(sample_ball_trajectory_progress(trajectory, -10), BallTrajectorySample(0.0, 64, 84))
        self.assertEqual(sample_ball_trajectory_progress(trajectory, 10), BallTrajectorySample(1.0, trajectory.target_x, trajectory.target_y))

    def test_public_value_constructors_validate_exact_metadata(self):
        trajectory = build_ball_trajectory(self.setup())
        values = list(trajectory.__dict__.values())
        for index, replacement in ((0, True), (2, 11), (6, float("nan")),
                                   (8, "straight"), (10, 45), (11, 9.0),
                                   (12, float("inf"))):
            with self.subTest(index=index):
                invalid = values.copy(); invalid[index] = replacement
                with self.assertRaises(InvalidBallTrajectoryValueError):
                    BallTrajectory(*invalid)

    def test_public_sample_constructor_validates_progress_and_pixels(self):
        for arguments in ((0,64,84), (-0.1,64,84), (1.1,64,84),
                          (float("nan"),64,84), (0.5,64.0,84), (0.5,-1,84)):
            with self.subTest(arguments=arguments):
                with self.assertRaises(InvalidBallTrajectoryValueError):
                    BallTrajectorySample(*arguments)

if __name__=='__main__': unittest.main()
