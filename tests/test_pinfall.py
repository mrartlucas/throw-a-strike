import unittest
from throw_a_strike.domain import *

class PinfallTests(unittest.TestCase):
    def setup(self,x=64,y=72,power=70,curve=CurveLevel.STRAIGHT):
        return ThrowSetup(ControlStyle.QUICK,0,x,y,curve,power)
    def test_exact_constants_centers_and_graph(self):
        self.assertEqual((PIN_RADIUS_PIXELS,BALL_PIN_CONTACT_RADIUS_PIXELS,COLLISION_SUBDIVISIONS),(3,6,256))
        self.assertEqual(PIN_CENTERS[1],(64,72)); self.assertEqual(PIN_CHILDREN[1],(2,3)); self.assertEqual(PIN_CHILDREN[10],())
    def test_headpin_fixtures(self):
        for power, expected in ((40,(1,2,3)),(70,(1,2,3,4,5,6)),(100,tuple(range(1,11)))):
            r=resolve_ball_pinfall(build_ball_trajectory(self.setup(power=power)))
            self.assertEqual(r.direct_hit_pin,1); self.assertEqual(r.knocked_down,expected)
    def test_bias_fixtures(self):
        left=resolve_ball_pinfall(build_ball_trajectory(self.setup(power=70,curve=CurveLevel.LEFT_1)))
        right=resolve_ball_pinfall(build_ball_trajectory(self.setup(power=70,curve=CurveLevel.RIGHT_1)))
        self.assertEqual(left.knocked_down,(1,2,3,4,5,7)); self.assertEqual(right.knocked_down,(1,2,3,5,6,10))
    def test_gutter_and_miss(self):
        self.assertEqual(resolve_ball_pinfall(build_ball_trajectory(self.setup(x=0,y=4))).result_kind,BowlingThrowResultKind.GUTTER)
        self.assertEqual(resolve_ball_pinfall(build_ball_trajectory(self.setup(x=127,y=4))).result_kind,BowlingThrowResultKind.GUTTER)
        self.assertEqual(resolve_ball_pinfall(build_ball_trajectory(self.setup(x=64,y=84))).result_kind,BowlingThrowResultKind.MISS)
    def test_survivor_rack_and_repeatability(self):
        t=build_ball_trajectory(self.setup(power=70)); r=resolve_ball_pinfall(t,(4,5,6,7,8,9,10))
        self.assertNotIn(1,r.knocked_down); self.assertEqual(r,resolve_ball_pinfall(t,(4,5,6,7,8,9,10)))
    def test_roll_stops_at_contact(self):
        t=build_ball_trajectory(self.setup()); r=resolve_ball_pinfall(t)
        self.assertEqual(sample_ball_roll(t,r,t.duration_seconds).progress, r.contact_progress)

if __name__ == '__main__': unittest.main()
