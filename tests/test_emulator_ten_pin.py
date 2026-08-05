import unittest
from unittest.mock import patch
from throw_a_strike.application import PortCapabilities
from throw_a_strike.platform import DartsnutSdkFacade, FakeDartsnutSdk, DartsnutButtonId, RawDartHit, DartsnutSdkOperation
from throw_a_strike.runtime import EmulatorTenPinRuntime, EmulatorTenPinPhase
from throw_a_strike.application.session import SessionPhase
from throw_a_strike.domain import ControlStyle, Mode, Theme, BowlingThrowResultKind, PINFALL_DURATION_SECONDS, PinfallResolution, PinImpactBias
from throw_a_strike.domain.bowling_round import FULL_RACK

class Clock:
    def __init__(self, t=0): self.t=float(t); self.reads=0
    @property
    def capabilities(self): return PortCapabilities(True)
    def monotonic_seconds(self): self.reads += 1; return self.t
    def set(self,t): self.t=float(t)
    def advance(self,dt): self.t += float(dt)

def resolution(kind, before=FULL_RACK, knocked=()):
    after=tuple(p for p in before if p not in knocked)
    if kind is BowlingThrowResultKind.PIN_HIT:
        return PinfallResolution(kind,before,knocked[0],0.5,64,72,0.0,-1.0,PinImpactBias.CENTER,((knocked[0],), tuple(knocked[1:])) if len(knocked)>1 else ((knocked[0],),),tuple(knocked),after)
    return PinfallResolution(kind,before,None,1.0,64,10,0.0,-1.0,PinImpactBias.CENTER,(),(),before)

class TenPinRuntimeTests(unittest.TestCase):
    def make_runtime(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        return sdk,clock,rt
    def roll_with(self, rt, sdk, clock, res):
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=res):
            sdk.queue_dart_hits((RawDartHit(0,64,72),)); step=rt.step(); self.assertEqual(step.phase, EmulatorTenPinPhase.BALL_ROLL)
        clock.set(rt.ball_started_at + rt.ball_trajectory.duration_seconds); step=rt.step()
        if step.phase is EmulatorTenPinPhase.PINFALL:
            clock.set(rt.pinfall_started_at + PINFALL_DURATION_SECONDS); step=rt.step()
        self.assertEqual(step.phase, EmulatorTenPinPhase.RESULT_HOLD)
        clock.set(rt.result_started_at + 1.5); return rt.step()
    def test_style_confirmation_configures_one_player_ten_pin(self):
        sdk,clock,rt=self.make_runtime(); snap=rt.session_snapshot
        self.assertEqual((snap.config.mode,snap.config.theme,snap.config.player_count,snap.config.frame_count,snap.config.seed,snap.config.control_style),(Mode.TEN_PIN,Theme.REGULAR,1,10,0,ControlStyle.QUICK))
        self.assertEqual(rt.standing_pins, FULL_RACK); self.assertEqual(rt.current_frame_number,1); self.assertEqual(rt.current_roll_number,1)
    def test_pin_hit_spare_and_strike_progression_uses_session(self):
        sdk,clock,rt=self.make_runtime()
        step=self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,2,3,4,5)))
        self.assertEqual(step.phase, EmulatorTenPinPhase.ATTEMPT); self.assertEqual(len(rt.standing_pins),5); self.assertEqual(rt.current_roll_number,2)
        step=self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,rt.standing_pins,rt.standing_pins))
        self.assertEqual((rt.current_frame_number,rt.current_roll_number,rt.standing_pins),(2,1,FULL_RACK))
        step=self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
        self.assertEqual((rt.current_frame_number,rt.current_roll_number,rt.standing_pins),(3,1,FULL_RACK))
    def test_miss_gutter_wrong_color_and_queued_input_do_not_mutate_rack(self):
        sdk,clock,rt=self.make_runtime()
        sdk.queue_dart_hits((RawDartHit(1,1,1),)); before=rt.bowling_snapshot
        self.assertEqual(rt.step().phase, EmulatorTenPinPhase.WRONG_COLOR_HOLD)
        self.assertEqual(rt.bowling_snapshot, before); self.assertEqual(rt.standing_pins,FULL_RACK)
        clock.advance(1); rt.step()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.MISS)):
            sdk.queue_dart_hits((RawDartHit(0,64,84),)); rt.step()
        sdk.queue_button_events((DartsnutButtonId.RIGHT,))
        self.assertEqual(sdk.queued_button_batch_count,1)
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); rt.step()
        self.assertEqual(rt.session_snapshot.phase, SessionPhase.SHOWING_RESULT); self.assertEqual(rt.standing_pins,FULL_RACK)
        self.assertEqual(sdk.reset_blocking_count,0)
    def test_regulation_sequences_reach_expected_scores(self):
        from throw_a_strike.application.session import GameSession
        from throw_a_strike.domain import MatchConfig
        cases=[([0,0]*10,0), ([9,0]*10,90), ([5,5]*10+[5],150), ([10]*12,300), ([10,7,3,9,0,10,0,8,8,2,0,6,10,10,10,8,1],167)]
        for rolls,score in cases:
            s=GameSession(); s.configure(MatchConfig(Mode.TEN_PIN,Theme.REGULAR,1,10,0,ControlStyle.QUICK)); s.start()
            for pins in rolls:
                s.submit_throw(pins); snap=s.acknowledge_result()
                if snap.phase is SessionPhase.FRAME_TRANSITION: s.continue_transition()
            self.assertEqual(s.snapshot().phase, SessionPhase.GAME_OVER); self.assertEqual(s.snapshot().match.players[0].bowling.confirmed_score, score)
    def test_game_over_stable_after_final_roll(self):
        sdk,clock,rt=self.make_runtime()
        for _ in range(20):
            self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER))
        self.assertEqual(rt.phase, EmulatorTenPinPhase.GAME_OVER); reads=clock.reads; calls=len(sdk.calls); frames=len(sdk.submitted_framebuffers)
        rt.step(); self.assertEqual(clock.reads, reads); self.assertEqual(len(sdk.submitted_framebuffers), frames+1)
        self.assertNotIn(DartsnutSdkOperation.DART_HITS, sdk.calls[calls:])
