import unittest
from types import MappingProxyType

from throw_a_strike.domain import (
    BALL_PIN_CONTACT_RADIUS_PIXELS,
    COLLISION_SUBDIVISIONS,
    PINFALL_DURATION_SECONDS,
    PINFALL_PIN_DURATION_SECONDS,
    PINFALL_WAVE_DELAY_SECONDS,
    PIN_CHILDREN,
    PIN_CENTERS,
    PIN_RADIUS_PIXELS,
    BowlingThrowResultKind,
    ControlStyle,
    CurveLevel,
    InvalidPinfallValueError,
    PinImpactBias,
    PinContactBand,
    PinfallResolution,
    classify_pin_contact_band,
    ThrowSetup,
    ball_trajectory_derivative_at_progress,
    ball_trajectory_point_at_progress,
    build_ball_trajectory,
    resolve_ball_pinfall,
    sample_ball_roll,
)


class PinfallTests(unittest.TestCase):
    def setup(self, x=64, y=72, power=70, curve=CurveLevel.STRAIGHT):
        return ThrowSetup(ControlStyle.QUICK, 0, x, y, curve, power)

    def resolution(self, x=64, y=72, power=70, curve=CurveLevel.STRAIGHT, standing=tuple(range(1, 11))):
        return resolve_ball_pinfall(build_ball_trajectory(self.setup(x, y, power, curve)), standing)

    def test_all_exact_pin_centers_and_complete_child_graph(self):
        self.assertEqual(dict(PIN_CENTERS), {
            1: (64, 72), 2: (54, 56), 3: (74, 56), 4: (44, 40), 5: (64, 40),
            6: (84, 40), 7: (34, 23), 8: (54, 23), 9: (74, 23), 10: (94, 23),
        })
        self.assertEqual(dict(PIN_CHILDREN), {
            1: (2, 3), 2: (4, 5), 3: (5, 6), 4: (7, 8), 5: (8, 9),
            6: (9, 10), 7: (), 8: (), 9: (), 10: (),
        })

    def test_collision_constants_and_immutable_public_mappings(self):
        self.assertEqual((PIN_RADIUS_PIXELS, BALL_PIN_CONTACT_RADIUS_PIXELS, COLLISION_SUBDIVISIONS), (3, 6, 256))
        self.assertEqual((PINFALL_DURATION_SECONDS, PINFALL_WAVE_DELAY_SECONDS, PINFALL_PIN_DURATION_SECONDS), (0.750, 0.120, 0.300))
        self.assertIs(type(PIN_CENTERS), MappingProxyType)
        self.assertIs(type(PIN_CHILDREN), MappingProxyType)
        with self.assertRaises(TypeError):
            PIN_CENTERS[1] = (0, 0)
        with self.assertRaises(TypeError):
            PIN_CHILDREN[1] = ()

    def test_exact_floating_point_path_and_regression_misses_headpin(self):
        setup = ThrowSetup(ControlStyle.ADVANCED, 0, 0, 12, CurveLevel.RIGHT_1, 70)
        trajectory = build_ball_trajectory(setup)
        point = ball_trajectory_point_at_progress(trajectory, 0.5)
        expected_x = 0.25 * trajectory.start_x + 0.5 * trajectory.control_x + 0.25 * trajectory.target_x
        expected_y = 0.25 * trajectory.start_y + 0.5 * trajectory.control_y + 0.25 * trajectory.target_y
        self.assertEqual(point, (expected_x, expected_y))
        self.assertIsNone(resolve_ball_pinfall(trajectory).direct_hit_pin)

    def test_headpin_fixtures_and_contact_derivative(self):
        for power, expected in ((40, (1, 2, 3)), (70, tuple(range(1, 11))), (100, tuple(range(1, 11)))):
            with self.subTest(power=power):
                r = self.resolution(power=power)
                self.assertEqual(r.direct_hit_pin, 1)
                self.assertEqual(r.knocked_down, expected)
                self.assertEqual((r.impact_dx, r.impact_dy), ball_trajectory_derivative_at_progress(build_ball_trajectory(self.setup(power=power)), r.contact_progress))

    def test_left_and_right_70_fixtures(self):
        self.assertEqual(self.resolution(power=70, curve=CurveLevel.LEFT_1).knocked_down, (1, 2, 3, 4, 5, 6, 9, 10))
        self.assertEqual(self.resolution(power=70, curve=CurveLevel.RIGHT_1).knocked_down, (1, 2, 3, 4, 5, 6, 7, 8))

    def test_gutter_boundaries_and_ordinary_miss(self):
        self.assertEqual(self.resolution(x=0, y=4).result_kind, BowlingThrowResultKind.GUTTER)
        self.assertEqual(self.resolution(x=127, y=4).result_kind, BowlingThrowResultKind.GUTTER)
        self.assertEqual(self.resolution(x=64, y=84).result_kind, BowlingThrowResultKind.MISS)

    def test_partial_standing_missing_child_and_duplicate_parent_maximum(self):
        partial = self.resolution(power=70, standing=(4, 5, 6, 7, 8, 9, 10))
        self.assertNotIn(1, partial.knocked_down)
        missing = self.resolution(power=100, standing=(1, 2, 3, 6, 7, 8, 9, 10))
        self.assertNotIn(7, missing.knocked_down)
        self.assertIn(8, missing.knocked_down)
        duplicate = self.resolution(power=100)
        self.assertIn(9, duplicate.knocked_down)
        self.assertEqual(duplicate.fall_waves[-1], (7, 8, 9, 10))

    def test_no_tunneling_tie_breaking_progress_and_repeatability(self):
        tunneled = self.resolution(x=64, y=4, power=100)
        self.assertEqual(tunneled.direct_hit_pin, 1)
        tied = self.resolution(x=64, y=40, power=100, standing=(4, 5, 6))
        self.assertEqual(tied.direct_hit_pin, 5)
        again = self.resolution(x=64, y=40, power=100, standing=(4, 5, 6))
        self.assertEqual(tied, again)
        self.assertTrue(0.0 <= tied.contact_progress <= 1.0)

    def test_arcade_contact_bands_and_generous_seventy_percent_strike_region(self):
        self.assertIs(classify_pin_contact_band(1, 60.0), PinContactBand.LEFT_CONTACT)
        self.assertIs(classify_pin_contact_band(1, 62.0), PinContactBand.NEAR_LEFT_POCKET)
        self.assertIs(classify_pin_contact_band(1, 64.0), PinContactBand.CENTER_CONTACT)
        self.assertIs(classify_pin_contact_band(1, 66.0), PinContactBand.NEAR_RIGHT_POCKET)
        self.assertIs(classify_pin_contact_band(1, 68.0), PinContactBand.RIGHT_CONTACT)
        for x in (63, 64, 65):
            with self.subTest(x=x):
                self.assertEqual(self.resolution(x=x, y=72, power=70).knocked_down, tuple(range(1, 11)))

    def test_contact_side_biases_transfer_across_the_headpin(self):
        left_contact = self.resolution(x=58, y=72, power=70)
        right_contact = self.resolution(x=70, y=72, power=70)
        self.assertIs(left_contact.impact_bias, PinImpactBias.RIGHT)
        self.assertIs(right_contact.impact_bias, PinImpactBias.LEFT)
        self.assertIn(10, left_contact.knocked_down)
        self.assertNotIn(7, left_contact.knocked_down)
        self.assertIn(7, right_contact.knocked_down)
        self.assertNotIn(10, right_contact.knocked_down)

    def test_power_broadens_propagation_without_auto_striking_bad_aim(self):
        low = self.resolution(x=64, y=72, power=40)
        green_low = self.resolution(x=64, y=72, power=60)
        sweet = self.resolution(x=64, y=72, power=70)
        strong = self.resolution(x=58, y=72, power=80)
        poor = self.resolution(x=64, y=84, power=100)
        self.assertLess(len(low.knocked_down), len(green_low.knocked_down))
        self.assertLess(len(green_low.knocked_down), len(sweet.knocked_down))
        self.assertEqual(sweet.knocked_down, tuple(range(1, 11)))
        self.assertGreater(len(strong.knocked_down), len(self.resolution(x=58, y=72, power=70).knocked_down))
        self.assertNotEqual(poor.result_kind, BowlingThrowResultKind.PIN_HIT)

    def test_nearby_coordinates_can_be_equivalent_and_identical_repeats_match(self):
        outcomes = [self.resolution(x=x, y=72, power=70).knocked_down for x in (63, 64, 65)]
        self.assertEqual(outcomes, [tuple(range(1, 11)), tuple(range(1, 11)), tuple(range(1, 11))])
        first = self.resolution(x=60, y=72, power=70, curve=CurveLevel.LEFT_1)
        second = self.resolution(x=60, y=72, power=70, curve=CurveLevel.LEFT_1)
        self.assertEqual(first, second)

    def test_partial_rear_racks_convert_but_seven_ten_stays_difficult(self):
        self.assertEqual(self.resolution(x=54, y=23, power=70, standing=(7, 8, 9)).standing_after, ())
        self.assertEqual(self.resolution(x=74, y=23, power=70, standing=(8, 9, 10)).standing_after, ())
        self.assertEqual(self.resolution(x=34, y=23, power=100, standing=(7, 10)).standing_after, (10,))
        self.assertEqual(self.resolution(x=94, y=23, power=100, standing=(7, 10)).standing_after, (7,))
        self.assertEqual(self.resolution(x=64, y=23, power=100, standing=(7, 10)).standing_after, (7, 10))


    def test_constructor_rejects_corrupted_public_fields_and_relationships(self):
        r = self.resolution()
        fields = r.__dict__.copy()
        corruptions = (
            ("result_kind", "pin_hit"),
            ("standing_before", [1, 2, 3]),
            ("standing_before", (2, 1)),
            ("direct_hit_pin", "1"),
            ("direct_hit_pin", 9),
            ("contact_progress", float("nan")),
            ("contact_x", 128),
            ("contact_y", -1),
            ("impact_dx", 1),
            ("impact_dy", float("inf")),
            ("impact_bias", "center"),
            ("fall_waves", [(1,)]),
            ("fall_waves", ((),)),
            ("fall_waves", ((2, 1),)),
            ("fall_waves", ((1, 2), (2, 3))),
            ("fall_waves", ((2,), (1, 3, 4, 5, 6))),
            ("knocked_down", (1, 2)),
            ("knocked_down", (1, 2, 3, 4, 5, 6, 7)),
            ("standing_after", (7, 8, 9)),
        )
        for name, value in corruptions:
            with self.subTest(field=name, value=repr(value)):
                values = fields.copy(); values[name] = value
                with self.assertRaises(InvalidPinfallValueError):
                    PinfallResolution(**values)

    def test_no_hit_constructor_relationships_are_exact(self):
        miss = self.resolution(x=64, y=84)
        self.assertEqual(miss.result_kind, BowlingThrowResultKind.MISS)
        base = miss.__dict__.copy()
        corruptions = (
            ("direct_hit_pin", 1),
            ("contact_progress", 0.5),
            ("fall_waves", ((1,),)),
            ("knocked_down", (1,)),
            ("standing_after", (2, 3, 4, 5, 6, 7, 8, 9, 10)),
        )
        for name, value in corruptions:
            with self.subTest(field=name):
                values = base.copy(); values[name] = value
                if name == "knocked_down":
                    values["standing_after"] = tuple(range(2, 11))
                with self.assertRaises(InvalidPinfallValueError):
                    PinfallResolution(**values)

    def test_constructor_validation_and_roll_stops_at_contact(self):
        r = self.resolution()
        with self.assertRaises(InvalidPinfallValueError):
            PinfallResolution(BowlingThrowResultKind.PIN_HIT, r.standing_before, None, r.contact_progress,
                              r.contact_x, r.contact_y, r.impact_dx, r.impact_dy, r.impact_bias,
                              r.fall_waves, r.knocked_down, r.standing_after)
        with self.assertRaises(InvalidPinfallValueError):
            PinfallResolution(r.result_kind, (1, 1), r.direct_hit_pin, r.contact_progress,
                              r.contact_x, r.contact_y, r.impact_dx, r.impact_dy, r.impact_bias,
                              r.fall_waves, r.knocked_down, r.standing_after)
        with self.assertRaises(InvalidPinfallValueError):
            PinfallResolution(r.result_kind, r.standing_before, r.direct_hit_pin, 1.5,
                              r.contact_x, r.contact_y, r.impact_dx, r.impact_dy, r.impact_bias,
                              r.fall_waves, r.knocked_down, r.standing_after)
        trajectory = build_ball_trajectory(self.setup())
        self.assertEqual(sample_ball_roll(trajectory, r, trajectory.duration_seconds).progress, r.contact_progress)
        self.assertIs(type(r.impact_bias), PinImpactBias)


if __name__ == "__main__":
    unittest.main()
