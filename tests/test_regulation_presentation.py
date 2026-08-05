import unittest
from unittest.mock import patch

from throw_a_strike.application.regulation_presentation import RegulationPresentationEventKind, RegulationPresentationTimeline, event_label
from throw_a_strike.rendering.regulation_event_rgb888 import render_regulation_event_rgb888
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH
from throw_a_strike.domain import BowlingThrowResultKind, PINFALL_DURATION_SECONDS, ControlStyle
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.platform import DartsnutButtonId, RawDartHit, FakeDartsnutSdk, DartsnutSdkFacade
from throw_a_strike.runtime import EmulatorTenPinRuntime, EmulatorTenPinPhase
from tests.test_emulator_ten_pin import Clock, resolution

class RegulationPresentationTimelineTests(unittest.TestCase):
    def test_every_required_result_label_is_exact(self):
        labels = {
            RegulationPresentationEventKind.THROW_READY: "THROW READY",
            RegulationPresentationEventKind.STRIKE: "STRIKE",
            RegulationPresentationEventKind.SPARE: "SPARE",
            RegulationPresentationEventKind.SPLIT: "SPLIT",
            RegulationPresentationEventKind.SPLIT_CONVERTED: "SPLIT CONVERTED",
            RegulationPresentationEventKind.FIELD_GOAL: "FIELD GOAL",
            RegulationPresentationEventKind.GUTTER: "GUTTER",
            RegulationPresentationEventKind.MISS: "MISS",
            RegulationPresentationEventKind.FOUL: "FOUL",
            RegulationPresentationEventKind.TURKEY: "TURKEY",
            RegulationPresentationEventKind.GAME_OVER: "GAME OVER",
        }
        for kind, label in labels.items():
            self.assertEqual(event_label(kind), label)
            self.assertEqual(len(render_regulation_event_rgb888(RegulationPresentationTimeline().throw_ready(0) if kind is RegulationPresentationEventKind.THROW_READY else None, 0)), EMULATOR_RGB888_BYTE_LENGTH)

class RuntimePresentationEventTests(unittest.TestCase):
    def make_runtime(self, advanced=False):
        sdk=FakeDartsnutSdk(); clock=Clock(0); rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT if advanced else DartsnutButtonId.A,)); step=rt.step()
        if advanced:
            clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); step=rt.step()
        return sdk,clock,rt,step

    def roll_to_result(self, rt, sdk, clock, res):
        clock.set((rt.throw_ready_started_at or clock.t)+0.1)
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=res):
            sdk.queue_dart_hits((RawDartHit(0,64,72),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); step=rt.step()
        if step.phase is EmulatorTenPinPhase.PINFALL:
            clock.set(rt.pinfall_started_at+PINFALL_DURATION_SECONDS); step=rt.step()
        self.assertEqual(step.phase, EmulatorTenPinPhase.RESULT_HOLD)
        return rt.presentation_timeline.events[-1]

    def test_quick_ready_once_expires_sparse_and_legal_dart_interrupts(self):
        sdk,clock,rt,step=self.make_runtime()
        events=rt.presentation_timeline.events
        self.assertEqual([e.kind for e in events], [RegulationPresentationEventKind.THROW_READY])
        first=events[0]; self.assertEqual((first.started_at, first.deadline, first.frame_number, first.roll_number), (0.0, 1.5, 1, 1))
        for t in (.1, 1.4):
            clock.set(t); rt.step()
        self.assertEqual(rt.presentation_timeline.events, events)
        self.assertTrue(rt.presentation_timeline.view_model(1.49).visible)
        self.assertFalse(rt.presentation_timeline.view_model(99).visible)
        self.assertEqual(first.deadline, 1.5)
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=resolution(BowlingThrowResultKind.GUTTER)):
            sdk.queue_dart_hits((RawDartHit(0,64,84),)); rt.step()
        self.assertFalse(rt.presentation_timeline.view_model(clock.t).visible)

    def test_wrong_color_dart_does_not_duplicate_ready(self):
        sdk,clock,rt,step=self.make_runtime(); before=rt.presentation_timeline.events
        sdk.queue_dart_hits((RawDartHit(1,1,1),)); rt.step()
        self.assertEqual(rt.presentation_timeline.events, before)

    def test_advanced_power_back_and_reconfirmation_ready_events(self):
        sdk,clock,rt,step=self.make_runtime(advanced=True)
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()  # lock curve
        clock.advance(.5); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()  # lock power
        self.assertEqual(rt.presentation_timeline.events[-1].kind, RegulationPresentationEventKind.THROW_READY)
        first_count=len(rt.presentation_timeline.events)
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.B,)); rt.step()
        self.assertFalse(rt.presentation_timeline.view_model(clock.t).visible)
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        self.assertEqual(len(rt.presentation_timeline.events), first_count+1)
        self.assertEqual(rt.presentation_timeline.events[-1].kind, RegulationPresentationEventKind.THROW_READY)

    def test_result_context_ack_once_and_strike_turkey_ordering(self):
        sdk,clock,rt,step=self.make_runtime()
        labels=[]
        for _ in range(3):
            event=self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
            labels.append(event.kind)
            clock.set(rt.result_started_at+99); rt.step()
        kinds_events=[e for e in rt.presentation_timeline.events if e.kind is not RegulationPresentationEventKind.THROW_READY]
        kinds=[e.kind for e in kinds_events]
        self.assertEqual(kinds, [RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.TURKEY])
        third=kinds_events[-2]
        self.assertEqual((third.frame_number, third.roll_number, third.label), (3, 1, "STRIKE"))

    def test_miss_gutter_foul_spare_game_over_once(self):
        sdk,clock,rt,step=self.make_runtime()
        miss=self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.MISS)); self.assertEqual(miss.label,"MISS")
        clock.set(rt.result_started_at+1.5); rt.step()
        gutter=self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); self.assertEqual(gutter.label,"GUTTER")
        sdk,clock,rt,step=self.make_runtime(); self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,2,3,4,5)))
        clock.set(rt.result_started_at+1.5); rt.step(); spare=self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,rt.standing_pins,rt.standing_pins)); self.assertEqual(spare.label,"SPARE")
        sdk,clock,rt,step=self.make_runtime(); clock.set(30); rt.step(); self.assertEqual(rt.presentation_timeline.events[-1].label,"FOUL")
        sdk,clock,rt,step=self.make_runtime()
        for _ in range(20):
            self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); clock.set(rt.result_started_at+1.5); rt.step()
        game_overs=[e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.GAME_OVER]
        rt.step(); self.assertEqual(game_overs, [e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.GAME_OVER])
