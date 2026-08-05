import unittest
from unittest.mock import patch
from throw_a_strike.application import PortCapabilities
from throw_a_strike.platform import DartsnutSdkFacade, FakeDartsnutSdk, DartsnutButtonId, RawDartHit, DartsnutSdkOperation
from throw_a_strike.runtime import EmulatorTenPinRuntime, EmulatorTenPinPhase
from throw_a_strike.application.session import SessionPhase
from throw_a_strike.domain import ControlStyle, CurveLevel, Mode, Theme, BowlingThrowResultKind, PINFALL_DURATION_SECONDS, PinfallResolution, PinImpactBias
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

class TenPinRuntimeCorrectionTests(unittest.TestCase):

    def make_runtime(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        return sdk,clock,rt
    def make_advanced_runtime(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); rt.step()
        clock.advance(0.1); sdk.queue_button_events((DartsnutButtonId.A,)); step=rt.step()
        return sdk,clock,rt,step
    def roll_with(self, rt, sdk, clock, res):
        self.assertEqual(rt.standing_pins, tuple(range(1, rt.session_snapshot.current_available + 1)) if rt.session_snapshot.current_available == 10 else rt.standing_pins)
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=res):
            sdk.queue_dart_hits((RawDartHit(0,64,72),)); step=rt.step(); self.assertEqual(step.phase, EmulatorTenPinPhase.BALL_ROLL)
        clock.set(rt.ball_started_at + rt.ball_trajectory.duration_seconds); step=rt.step()
        if step.phase is EmulatorTenPinPhase.PINFALL:
            clock.set(rt.pinfall_started_at + PINFALL_DURATION_SECONDS); step=rt.step()
        self.assertEqual(step.phase, EmulatorTenPinPhase.RESULT_HOLD)
        clock.set(rt.result_started_at + 1.5); return rt.step()
    def test_quick_starts_straight_70(self):
        sdk,clock,rt=self.make_runtime(); self.assertEqual(rt.phase, EmulatorTenPinPhase.ATTEMPT)
        self.assertEqual(rt.presentation.curve_label, "STR"); self.assertEqual(rt.presentation.power_percent, 70)
    def test_legal_blue_dart_enters_ball_roll(self):
        sdk,clock,rt=self.make_runtime()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.GUTTER)):
            sdk.queue_dart_hits((RawDartHit(4,64,84),)); self.assertEqual(rt.step().phase, EmulatorTenPinPhase.BALL_ROLL)
    def test_ball_roll_one_clock_one_frame(self):
        sdk,clock,rt=self.make_runtime()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.GUTTER)):
            sdk.queue_dart_hits((RawDartHit(0,64,84),)); rt.step()
        reads=clock.reads; frames=len(sdk.submitted_framebuffers); clock.set(rt.ball_started_at+0.1); rt.step()
        self.assertEqual(clock.reads, reads+1); self.assertEqual(len(sdk.submitted_framebuffers), frames+1)
    def test_pinfall_one_clock_one_frame(self):
        sdk,clock,rt=self.make_runtime()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,))):
            sdk.queue_dart_hits((RawDartHit(0,64,72),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); rt.step()
        reads=clock.reads; frames=len(sdk.submitted_framebuffers); clock.set(rt.pinfall_started_at+0.1); rt.step()
        self.assertEqual(clock.reads, reads+1); self.assertEqual(len(sdk.submitted_framebuffers), frames+1)
    def test_score_committed_once_sparse_result(self):
        sdk,clock,rt=self.make_runtime()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.GUTTER)):
            sdk.queue_dart_hits((RawDartHit(0,64,84),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); rt.step(); hist=rt.bowling_snapshot.roll_history[0]
        clock.set(clock.t+99); rt.step(); self.assertEqual(rt.bowling_snapshot.roll_history[0], hist)
    def test_foul_zero_and_exact_deadline_cleanup(self):
        sdk,clock,rt=self.make_runtime(); clock.set(30); step=rt.step(); self.assertEqual(step.phase, EmulatorTenPinPhase.FOUL_HOLD)
        self.assertEqual(rt.session_snapshot.last_throw.scored_value,0); clock.set(99); rt.step(); self.assertIsNone(rt.result_started_at)
    def test_sparse_result_hold_next_attempt_deadline(self):
        sdk,clock,rt=self.make_runtime()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.GUTTER)):
            sdk.queue_dart_hits((RawDartHit(0,64,84),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); rt.step(); deadline=rt.result_started_at+1.5
        clock.set(deadline+99); self.assertEqual(rt.step().phase, EmulatorTenPinPhase.ATTEMPT)
        clock.set(deadline+29.9); self.assertEqual(rt.step().phase, EmulatorTenPinPhase.ATTEMPT)
    def test_stale_public_properties_clear_on_attempt(self):
        sdk,clock,rt=self.make_runtime(); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER))
        self.assertEqual(rt.phase, EmulatorTenPinPhase.ATTEMPT)
        self.assertIsNone(rt.accepted_setup); self.assertIsNone(rt.ball_trajectory); self.assertIsNone(rt.ball_started_at); self.assertIsNone(rt.pinfall_resolution); self.assertIsNone(rt.pinfall_started_at); self.assertIsNone(rt.result_started_at)
    def test_game_over_public_properties_clear(self):
        sdk,clock,rt=self.make_runtime()
        for _ in range(20): self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER))
        self.assertIsNone(rt.accepted_setup); self.assertIsNone(rt.ball_trajectory); self.assertIsNone(rt.result_started_at)
    def test_pending_strike_bonus_unresolved_then_resolved(self):
        sdk,clock,rt=self.make_runtime(); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
        self.assertEqual(rt.confirmed_score,0); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); self.assertEqual(rt.confirmed_score,10)
    def test_pending_spare_bonus_unresolved_then_resolved(self):
        sdk,clock,rt=self.make_runtime(); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,2,3,4,5))); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,rt.standing_pins,rt.standing_pins))
        self.assertEqual(rt.confirmed_score,0); self.roll_with(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); self.assertEqual(rt.confirmed_score,10)
    def test_queued_dart_and_button_preserved_during_pinfall(self):
        sdk,clock,rt=self.make_runtime()
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,))): sdk.queue_dart_hits((RawDartHit(0,64,72),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); rt.step(); sdk.queue_dart_hits((RawDartHit(0,1,1),)); sdk.queue_button_events((DartsnutButtonId.RIGHT,)); clock.set(rt.pinfall_started_at+0.1); rt.step()
        self.assertEqual((sdk.queued_dart_batch_count,sdk.queued_button_batch_count),(1,1))
    def test_runner_invalid_facade_does_not_close(self):
        from throw_a_strike.runtime import run_emulator_ten_pin
        from throw_a_strike.application import InvalidPortValueError
        with self.assertRaises(InvalidPortValueError): run_emulator_ten_pin(object(), Clock(), 0)
    def test_runner_validation_closes_valid_facade(self):
        from throw_a_strike.runtime import run_emulator_ten_pin
        from throw_a_strike.application import InvalidPortValueError
        for kwargs in ({'frame_seconds':-1},{'sleeper':None},{'max_iterations':True},{'max_iterations':-1}):
            sdk=FakeDartsnutSdk()
            with self.assertRaises(InvalidPortValueError): run_emulator_ten_pin(DartsnutSdkFacade(sdk), Clock(), 0, **kwargs)
            self.assertEqual(sdk.close_count,1)
    def test_runner_closes_on_normal_completion(self):
        from throw_a_strike.runtime import run_emulator_ten_pin
        sdk=FakeDartsnutSdk(False); run_emulator_ten_pin(DartsnutSdkFacade(sdk), Clock(), 0, max_iterations=0, sleeper=lambda _:None); self.assertEqual(sdk.close_count,1)
    def test_tenth_open_ends_after_two(self): self._session_rolls([0,0]*10,0)
    def test_tenth_spare_one_bonus(self): self._session_rolls([0,0]*9+[7,3,10],20)
    def test_tenth_strike_two_bonus(self): self._session_rolls([0,0]*9+[10,7,2],19)
    def test_tenth_xxx(self): self._session_rolls([0,0]*9+[10,10,10],30)
    def test_tenth_x7_spare(self): self._session_rolls([0,0]*9+[10,7,3],20)
    def test_tenth_x72(self): self._session_rolls([0,0]*9+[10,7,2],19)
    def test_tenth_7_spare_x(self): self._session_rolls([0,0]*9+[7,3,10],20)
    def test_tenth_gutter_spare_x(self): self._session_rolls([0,0]*9+[0,10,10],20)
    def test_no_fourth_roll(self):
        from throw_a_strike.application.session import GameSession, InvalidSessionTransitionError
        from throw_a_strike.domain import MatchConfig
        s=GameSession(); s.configure(MatchConfig(Mode.TEN_PIN,Theme.REGULAR,1,10,0,ControlStyle.QUICK)); s.start()
        for pins in [0,0]*9+[10,10,10]: s.submit_throw(pins); snap=s.acknowledge_result(); (snap.phase is SessionPhase.FRAME_TRANSITION) and s.continue_transition()
        with self.assertRaises(InvalidSessionTransitionError): s.submit_throw(10)
    def _session_rolls(self, rolls, score):
        from throw_a_strike.application.session import GameSession
        from throw_a_strike.domain import MatchConfig
        s=GameSession(); s.configure(MatchConfig(Mode.TEN_PIN,Theme.REGULAR,1,10,0,ControlStyle.QUICK)); s.start()
        for pins in rolls:
            s.submit_throw(pins); snap=s.acknowledge_result()
            if snap.phase is SessionPhase.FRAME_TRANSITION: s.continue_transition()
        self.assertEqual(s.snapshot().phase, SessionPhase.GAME_OVER); self.assertEqual(s.snapshot().match.players[0].bowling.confirmed_score, score)
    def test_advanced_begins_in_set_curve(self):
        sdk,clock,rt,step=self.make_advanced_runtime()
        self.assertEqual(step.presentation.primary_prompt.label, "SET CURVE")
        self.assertEqual(step.presentation.curve_label, "STR")
    def test_advanced_left_right_controls_exact_curve_levels(self):
        sdk,clock,rt,step=self.make_advanced_runtime()
        labels=[]
        for button in (DartsnutButtonId.LEFT,DartsnutButtonId.LEFT,DartsnutButtonId.RIGHT,DartsnutButtonId.RIGHT,DartsnutButtonId.RIGHT):
            clock.advance(0.1); sdk.queue_button_events((button,)); labels.append(rt.step().presentation.curve_label)
        self.assertEqual(labels, ["L1","L2","L1","STR","R1"])
    def test_advanced_a_locks_selected_curve_and_power_begins_40(self):
        sdk,clock,rt,step=self.make_advanced_runtime(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.RIGHT,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); step=rt.step()
        self.assertEqual(step.presentation.primary_prompt.label, "SET POWER"); self.assertEqual(step.presentation.curve_label, "R1"); self.assertEqual(step.presentation.power_percent,40)
    def test_advanced_power_meter_sequence(self):
        sdk,clock,rt,step=self.make_advanced_runtime(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        seen=[]; base=clock.t
        for elapsed in (0,.2,.4,.6,.8,1.0,1.2,1.400001):
            clock.set(base+elapsed); seen.append(rt.step().presentation.power_percent)
        self.assertEqual(seen, [40,50,60,70,80,90,100,90])
    def test_advanced_a_locks_power_then_throw_ready_timer_and_setup(self):
        sdk,clock,rt,step=self.make_advanced_runtime(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.LEFT,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); clock.advance(.8); sdk.queue_button_events((DartsnutButtonId.A,)); step=rt.step()
        self.assertEqual(step.presentation.primary_prompt.label, "THROW READY"); self.assertEqual(step.presentation.power_percent,70)
        clock.set(clock.t+29.9); self.assertEqual(rt.step().phase, EmulatorTenPinPhase.ATTEMPT)
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.GUTTER)):
            sdk.queue_dart_hits((RawDartHit(0,64,84),)); rt.step()
        self.assertEqual((rt.accepted_setup.curve_level, rt.accepted_setup.power_percent), (CurveLevel.LEFT_1,70))
    def test_public_result_context_frame_one_strike_spare_open(self):
        for first, second, expected in ((10,None,(1,1)), (7,3,(1,2)), (7,2,(1,2))):
            sdk,clock,rt=self.make_runtime(); self.roll_to_result(rt,sdk,clock,first);
            if second is not None:
                clock.set(rt.result_started_at+1.5); rt.step(); self.roll_to_result(rt,sdk,clock,second)
            self.assertEqual((rt.current_frame_number, rt.current_roll_number), expected); self.assertNotEqual(rt.current_roll_number,0)
    def roll_to_result(self, rt, sdk, clock, pins):
        before=rt.standing_pins; knocked=before[:pins]
        kind=BowlingThrowResultKind.PIN_HIT if pins else BowlingThrowResultKind.GUTTER
        res=resolution(kind,before,knocked) if pins else resolution(kind,before,())
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=res): sdk.queue_dart_hits((RawDartHit(0,64,72),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); step=rt.step()
        if step.phase is EmulatorTenPinPhase.PINFALL: clock.set(rt.pinfall_started_at+PINFALL_DURATION_SECONDS); step=rt.step()
        self.assertEqual(step.phase, EmulatorTenPinPhase.RESULT_HOLD); return step
    def test_runtime_tenth_frame_rack_sequences(self):
        sequences=[([0,0]*9+[7,3,10], None), ([0,0]*9+[10,10,10], None), ([0,0]*9+[10,7,3], None), ([0,0]*9+[10,7,2], None), ([0,0]*9+[0,10,10], None)]
        for rolls,_ in sequences:
            sdk,clock,rt=self.make_runtime()
            for pins in rolls:
                self.assertEqual(len(rt.standing_pins), rt.session_snapshot.current_available)
                self.roll_to_result(rt,sdk,clock,pins); last=rt.session_snapshot.last_throw
                if last.match_complete: clock.set(rt.result_started_at+1.5); rt.step(); break
                clock.set(rt.result_started_at+1.5); rt.step()
            self.assertEqual(rt.phase, EmulatorTenPinPhase.GAME_OVER)
    def test_result_renderer_text_calls_include_exact_contexts(self):
        import throw_a_strike.rendering.ten_pin_rgb888 as r
        seen=[]; orig=r._text
        def capture(buf,text,x,y,c,scale=1): seen.append(text); return orig(buf,text,x,y,c,scale)
        sdk,clock,rt=self.make_runtime()
        with patch.object(r,'_text',capture): self.roll_to_result(rt,sdk,clock,10)
        self.assertIn('F1 R1', seen)

class TenPinFoulDeadlineRegressionTests(unittest.TestCase):
    def make_runtime(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); return sdk,clock,rt
    def foul_at(self, *, dart=None, button=None, at=30.0):
        sdk,clock,rt=self.make_runtime(); clock.set(rt.throw_ready_started_at+at)
        if dart is not None: sdk.queue_dart_hits((dart,))
        if button is not None: sdk.queue_button_events((button,))
        step=rt.step(); return sdk,clock,rt,step
    def test_no_input_at_exact_ready_plus_30_fouls_at_deadline(self):
        sdk,clock,rt,step=self.foul_at()
        self.assertEqual(step.phase, EmulatorTenPinPhase.FOUL_HOLD); self.assertEqual(rt.result_started_at,30.0)
    def test_legal_blue_dart_at_exact_deadline_is_foul_not_throw(self):
        sdk,clock,rt,step=self.foul_at(dart=RawDartHit(0,64,72))
        self.assertEqual(step.phase, EmulatorTenPinPhase.FOUL_HOLD); self.assertIsNone(rt.accepted_setup); self.assertEqual(rt.session_snapshot.last_throw.scored_value,0)
    def test_legal_blue_dart_after_deadline_is_foul_not_throw(self):
        sdk,clock,rt,step=self.foul_at(dart=RawDartHit(0,64,72), at=30.001)
        self.assertEqual(step.phase, EmulatorTenPinPhase.FOUL_HOLD); self.assertIsNone(rt.accepted_setup); self.assertEqual(rt.result_started_at,30.0)
    def test_control_button_at_deadline_uses_input_terminal_none_path(self):
        sdk,clock,rt,step=self.foul_at(button=DartsnutButtonId.RIGHT)
        self.assertEqual(step.phase, EmulatorTenPinPhase.FOUL_HOLD); self.assertEqual(rt.result_started_at,30.0)
    def test_sparse_first_foul_observation_uses_logical_deadline(self):
        sdk,clock,rt,step=self.foul_at(at=99.0)
        self.assertEqual(rt.result_started_at,30.0); self.assertEqual(rt.session_snapshot.last_throw.scored_value,0)
    def test_foul_hold_ends_at_ready_plus_31_5_and_next_attempt_starts_there(self):
        sdk,clock,rt,step=self.foul_at(at=99.0); clock.set(31.5); step=rt.step()
        self.assertEqual(step.phase, EmulatorTenPinPhase.ATTEMPT); self.assertEqual(rt.throw_ready_started_at,31.5)
    def test_no_duplicate_zero_pin_roll_after_sparse_foul(self):
        sdk,clock,rt,step=self.foul_at(at=99.0); hist=rt.bowling_snapshot.roll_history[0]
        clock.set(30.75); rt.step(); clock.set(31.49); rt.step(); self.assertEqual(rt.bowling_snapshot.roll_history[0], hist)
    def test_advanced_ready_timestamp_replaced_after_back_and_reconfirm(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); first=rt.throw_ready_started_at
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.B,)); rt.step(); self.assertIsNone(rt.throw_ready_started_at)
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); self.assertGreater(rt.throw_ready_started_at, first)
    def test_quick_ignored_controls_do_not_reset_ready_timestamp(self):
        for button in (DartsnutButtonId.A,DartsnutButtonId.LEFT,DartsnutButtonId.RIGHT):
            sdk,clock,rt=self.make_runtime(); clock.set(29.0); sdk.queue_button_events((button,)); rt.step()
            self.assertEqual(rt.throw_ready_started_at,0.0); clock.set(30.0); self.assertEqual(rt.step().phase, EmulatorTenPinPhase.FOUL_HOLD); self.assertEqual(rt.result_started_at,30.0)
    def test_quick_multiple_ignored_controls_then_deadline_dart_fouls_once(self):
        sdk,clock,rt=self.make_runtime()
        for t,button in ((20.0,DartsnutButtonId.A),(25.0,DartsnutButtonId.LEFT),(29.9,DartsnutButtonId.RIGHT)):
            clock.set(t); sdk.queue_button_events((button,)); rt.step(); self.assertEqual(rt.throw_ready_started_at,0.0)
        clock.set(30.0); sdk.queue_dart_hits((RawDartHit(0,64,72),)); rt.step(); hist=rt.bowling_snapshot.roll_history[0]
        clock.set(31.49); rt.step(); self.assertEqual(rt.bowling_snapshot.roll_history[0], hist)
    def test_advanced_ignored_ready_controls_do_not_reset_timestamp(self):
        for button in (DartsnutButtonId.A,DartsnutButtonId.LEFT,DartsnutButtonId.RIGHT):
            sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
            sdk.queue_button_events((DartsnutButtonId.RIGHT,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step(); ready=rt.throw_ready_started_at
            clock.advance(1); sdk.queue_button_events((button,)); rt.step(); self.assertEqual(rt.throw_ready_started_at, ready)
    def test_advanced_multi_event_batch_preserves_true_ready_transition_timestamp(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); rt.step(); clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,DartsnutButtonId.LEFT,DartsnutButtonId.RIGHT)); rt.step()
        self.assertEqual(rt.throw_ready_started_at, clock.t)
