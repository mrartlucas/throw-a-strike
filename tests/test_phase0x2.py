import unittest
from throw_a_strike.domain import *
from throw_a_strike.domain.bowling_round import FULL_RACK

K=ThrowControlCommandKind

def cmd(k,t=0,**kw): return ThrowControlCommand(k,t,**kw)
def res(style,x,y,p=70,curve=CurveLevel.STRAIGHT,arrow=LaneArrow.CENTER,standing=FULL_RACK):
    return resolve_ball_pinfall(build_ball_trajectory(ThrowSetup(style,0,x,y,curve,p,arrow)),standing)

class Phase0X2Tests(unittest.TestCase):
    def test_quick_bullseye_and_center_line(self):
        self.assertEqual(res(ControlStyle.QUICK,64,64).knocked_down, FULL_RACK)
        self.assertEqual(res(ControlStyle.QUICK,69,66).knocked_down, FULL_RACK)
        self.assertNotEqual(res(ControlStyle.QUICK,64,20).knocked_down, FULL_RACK)
    def test_quick_perfect_game(self):
        g=BowlingGame()
        for _ in range(12):
            r=res(ControlStyle.QUICK,64,64); g.roll(len(r.knocked_down))
        self.assertEqual(g.confirmed_score,300)
    def test_split_contact_recipes(self):
        self.assertEqual(res(ControlStyle.QUICK,34,23,standing=(7,10)).knocked_down,(7,))
        self.assertEqual(res(ControlStyle.QUICK,30,23,standing=(7,10)).knocked_down,(7,10))
        self.assertEqual(res(ControlStyle.QUICK,94,23,standing=(7,10)).knocked_down,(10,))
        self.assertEqual(res(ControlStyle.QUICK,98,23,standing=(7,10)).knocked_down,(7,10))
        self.assertEqual(res(ControlStyle.QUICK,37,23,standing=(7,10)).knocked_down,(7,))
    def test_lone_pin_and_gutter_miss(self):
        self.assertEqual(res(ControlStyle.QUICK,54,23,standing=(8,)).knocked_down,(8,))
        self.assertIs(res(ControlStyle.QUICK,0,64).result_kind, BowlingThrowResultKind.GUTTER)
        self.assertIs(res(ControlStyle.QUICK,64,100).result_kind, BowlingThrowResultKind.MISS)
    def test_advanced_arrow_flow_and_stale_dart(self):
        m=ThrowControlMachine(ControlStyle.ADVANCED)
        self.assertIs(m.snapshot.phase, ThrowControlPhase.SET_CURVE)
        m.apply(cmd(K.CONFIRM,0)); self.assertIs(m.snapshot.phase, ThrowControlPhase.SET_LANE_ARROW)
        m.apply(cmd(K.LEFT,.1)); m.apply(cmd(K.LEFT,.2)); m.apply(cmd(K.LEFT,.3)); self.assertIs(m.snapshot.lane_arrow,LaneArrow.FAR_LEFT)
        m.apply(cmd(K.DART_HIT,.4,dart_index=0,x=1,y=1)); self.assertIs(m.snapshot.phase,ThrowControlPhase.SET_LANE_ARROW); self.assertTrue(m.snapshot.early_warning_active)
        m.apply(cmd(K.RIGHT,.5)); self.assertIs(m.snapshot.lane_arrow,LaneArrow.LEFT)
        m.apply(cmd(K.CONFIRM,.6)); self.assertIs(m.snapshot.phase,ThrowControlPhase.SET_POWER)
        m.apply(cmd(K.CONFIRM,1.4)); self.assertIs(m.snapshot.phase,ThrowControlPhase.THROW_READY)
        self.assertIsNone(m.apply(cmd(K.DART_HIT,1.5,dart_index=0,x=64,y=64)).outcome)
        m.apply(cmd(K.REARMED,1.6)); self.assertIsNone(m.snapshot.stale_dart_index)
        self.assertIs(m.apply(cmd(K.DART_HIT,1.7,dart_index=0,x=64,y=64)).phase, ThrowControlPhase.COMPLETE)
        self.assertIs(m.snapshot.outcome.setup.lane_arrow,LaneArrow.LEFT)
    def test_trajectory_arrows_and_power(self):
        starts=[build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED,0,64,40,CurveLevel.STRAIGHT,70,a)).start_x for a in LaneArrow]
        self.assertEqual(starts, sorted(starts)); self.assertEqual(starts[2]*2, starts[0]+starts[4]); self.assertEqual(starts[2]*2, starts[1]+starts[3])
        a=build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED,0,64,40,CurveLevel.LEFT_3,70,LaneArrow.FAR_RIGHT))
        b=build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED,0,64,40,CurveLevel.STRAIGHT,70,LaneArrow.CENTER))
        self.assertNotEqual((a.start_x,a.control_x,a.arrival_dx,a.entry_angle),(b.start_x,b.control_x,b.arrival_dx,b.entry_angle))
        self.assertIs(ThrowSetup(ControlStyle.ADVANCED,0,1,1,CurveLevel.STRAIGHT,70).power_feedback,PowerFeedback.PERFECT)
    def test_power_risk_and_rebound(self):
        self.assertEqual(res(ControlStyle.ADVANCED,64,64,100,CurveLevel.LEFT_3,LaneArrow.FAR_RIGHT).knocked_down,FULL_RACK)
        self.assertNotEqual(res(ControlStyle.ADVANCED,64,64,100,CurveLevel.STRAIGHT,LaneArrow.FAR_LEFT).knocked_down,FULL_RACK)
        self.assertEqual(res(ControlStyle.ADVANCED,39,23,100,CurveLevel.LEFT_3,LaneArrow.FAR_RIGHT,(7,10)).knocked_down,(7,10))
        self.assertEqual(res(ControlStyle.ADVANCED,39,23,100,CurveLevel.STRAIGHT,LaneArrow.CENTER,(7,10)).knocked_down,(7,))
        self.assertEqual(res(ControlStyle.ADVANCED,89,23,100,CurveLevel.RIGHT_3,LaneArrow.FAR_LEFT,(7,10)).knocked_down,(7,10))
        self.assertEqual(res(ControlStyle.QUICK,39,23,standing=(7,10)).knocked_down,(7,))
        self.assertNotEqual(res(ControlStyle.ADVANCED,39,23,100,CurveLevel.LEFT_3,LaneArrow.FAR_RIGHT,(7,8,10)).knocked_down,(7,8,10))
        self.assertEqual(res(ControlStyle.ADVANCED,54,23,40,standing=(8,)).knocked_down,(8,))
        self.assertNotEqual(res(ControlStyle.ADVANCED,64,64,40).knocked_down,FULL_RACK)

if __name__=='__main__': unittest.main()
