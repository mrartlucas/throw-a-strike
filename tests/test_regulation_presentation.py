import unittest
from unittest.mock import patch

from throw_a_strike.application.regulation_presentation import (
    RegulationPresentationEvent,
    RegulationPresentationEventKind,
    RegulationPresentationTimeline,
    event_label,
    is_split_leave,
)
from throw_a_strike.rendering.regulation_event_rgb888 import (
    render_regulation_event_rgb888,
    render_regulation_event_view_model_rgb888,
)
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH
from throw_a_strike.domain import BowlingThrowResultKind, PINFALL_DURATION_SECONDS
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.platform import DartsnutButtonId, RawDartHit, FakeDartsnutSdk, DartsnutSdkFacade
from throw_a_strike.runtime import EmulatorTenPinRuntime, EmulatorTenPinPhase
from throw_a_strike.application import InvalidPortValueError, PortCapabilities
from throw_a_strike.domain import PinfallResolution, PinImpactBias


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


class RegulationPresentationTimelineTests(unittest.TestCase):
    def test_every_required_event_label_constructs_and_renders(self):
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
            with self.subTest(kind=kind):
                self.assertEqual(event_label(kind), label)
                event = RegulationPresentationEvent(kind, 2, 3.5, 1, 1, label, 0)
                self.assertEqual(event.label, label)
                self.assertEqual(len(render_regulation_event_rgb888(event, 2)), EMULATOR_RGB888_BYTE_LENGTH)
                self.assertEqual(len(render_regulation_event_view_model_rgb888(RegulationPresentationTimeline().view_model(99))), EMULATOR_RGB888_BYTE_LENGTH)

    def test_renderer_draws_each_required_visible_label(self):
        import throw_a_strike.rendering.regulation_event_rgb888 as renderer
        labels = (
            "THROW READY", "STRIKE", "SPARE", "SPLIT", "SPLIT CONVERTED",
            "FIELD GOAL", "GUTTER", "MISS", "FOUL", "TURKEY", "GAME OVER",
        )
        seen=[]; original=renderer._center
        def capture(buf, text, y, color, scale=1):
            seen.append(text); return original(buf, text, y, color, scale)
        with patch.object(renderer, "_center", capture):
            for kind in (
                RegulationPresentationEventKind.THROW_READY,
                RegulationPresentationEventKind.STRIKE,
                RegulationPresentationEventKind.SPARE,
                RegulationPresentationEventKind.SPLIT,
                RegulationPresentationEventKind.SPLIT_CONVERTED,
                RegulationPresentationEventKind.FIELD_GOAL,
                RegulationPresentationEventKind.GUTTER,
                RegulationPresentationEventKind.MISS,
                RegulationPresentationEventKind.FOUL,
                RegulationPresentationEventKind.TURKEY,
                RegulationPresentationEventKind.GAME_OVER,
            ):
                render_regulation_event_rgb888(RegulationPresentationEvent(kind, 0, 1.5, result_label=event_label(kind)), 0)
        for label in labels:
            self.assertIn(label, seen)

    def test_split_detection_uses_rack_geometry_without_scoring(self):
        self.assertTrue(is_split_leave((7, 10), FULL_RACK))
        self.assertTrue(is_split_leave((4, 6, 7, 10), FULL_RACK))
        self.assertFalse(is_split_leave((2, 3), FULL_RACK))
        self.assertFalse(is_split_leave((7, 10), (2, 3, 4, 5, 6, 7, 8, 9, 10)))
        with self.assertRaises(InvalidPortValueError):
            is_split_leave((0, 7), FULL_RACK)

    def test_duplicate_first_strike_acknowledgement_has_zero_side_effects(self):
        from throw_a_strike.application.session import GameSession, SessionPhase
        from throw_a_strike.domain import MatchConfig, Mode, Theme, ControlStyle
        session=GameSession(); session.configure(MatchConfig(Mode.TEN_PIN,Theme.REGULAR,1,10,0,ControlStyle.QUICK)); session.start()
        timeline=RegulationPresentationTimeline()
        snapshots=[]
        for _ in range(3):
            session.submit_throw(10); snapshots.append(session.snapshot())
            snap=session.acknowledge_result()
            if snap.phase is SessionPhase.FRAME_TRANSITION:
                session.continue_transition()
        first=timeline.acknowledge_result(snapshots[0], BowlingThrowResultKind.PIN_HIT, 1, pins_before=FULL_RACK, pins_after=())
        duplicate=timeline.acknowledge_result(snapshots[0], BowlingThrowResultKind.PIN_HIT, 1, pins_before=FULL_RACK, pins_after=())
        second=timeline.acknowledge_result(snapshots[1], BowlingThrowResultKind.PIN_HIT, 3, pins_before=FULL_RACK, pins_after=())
        third=timeline.acknowledge_result(snapshots[2], BowlingThrowResultKind.PIN_HIT, 5, pins_before=FULL_RACK, pins_after=())
        self.assertEqual([event.kind for event in first], [RegulationPresentationEventKind.STRIKE])
        self.assertEqual(duplicate, ())
        self.assertEqual([event.kind for event in second], [RegulationPresentationEventKind.STRIKE])
        self.assertEqual([event.kind for event in third], [RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.TURKEY])


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
        return step

    def special_events(self, rt):
        return tuple(e for e in rt.presentation_timeline.events if e.kind is not RegulationPresentationEventKind.THROW_READY)

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
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        clock.advance(.5); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        self.assertEqual(rt.presentation_timeline.events[-1].kind, RegulationPresentationEventKind.THROW_READY)
        first_count=len(rt.presentation_timeline.events)
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.B,)); rt.step()
        self.assertFalse(rt.presentation_timeline.view_model(clock.t).visible)
        clock.advance(.1); sdk.queue_button_events((DartsnutButtonId.A,)); rt.step()
        self.assertEqual(len(rt.presentation_timeline.events), first_count+1)
        self.assertEqual(rt.presentation_timeline.events[-1].kind, RegulationPresentationEventKind.THROW_READY)

    def test_result_events_are_visible_and_ordinary_pin_hit_has_no_special_callout(self):
        sdk,clock,rt,step=self.make_runtime()
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,2,3)))
        self.assertEqual(self.special_events(rt), ())
        self.assertFalse(rt.presentation_timeline.view_model(clock.t).visible)
        clock.set(rt.result_started_at+1.5); rt.step()
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.MISS,rt.standing_pins,()))
        event=self.special_events(rt)[-1]
        self.assertEqual((event.kind, event.label), (RegulationPresentationEventKind.MISS, "MISS"))
        self.assertEqual(rt.presentation_timeline.view_model(clock.t).label, "MISS")
        self.assertEqual(len(render_regulation_event_rgb888(event, clock.t)), EMULATOR_RGB888_BYTE_LENGTH)

    def test_split_and_split_converted_sequence_is_visible(self):
        sdk,clock,rt,step=self.make_runtime()
        leave=(7,10); knocked=tuple(pin for pin in FULL_RACK if pin not in leave)
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,knocked))
        split=self.special_events(rt)[-1]
        self.assertEqual((split.kind, split.label, split.frame_number, split.roll_number), (RegulationPresentationEventKind.SPLIT, "SPLIT", 1, 1))
        self.assertEqual(rt.presentation_timeline.view_model(clock.t).label, "SPLIT")
        clock.set(rt.result_started_at+1.5); rt.step()
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,leave,leave))
        converted=self.special_events(rt)[-1]
        self.assertEqual((converted.kind, converted.label, converted.frame_number, converted.roll_number), (RegulationPresentationEventKind.SPLIT_CONVERTED, "SPLIT CONVERTED", 1, 2))
        self.assertEqual(rt.presentation_timeline.view_model(clock.t).label, "SPLIT CONVERTED")

    def test_strike_turkey_ordering_and_fourth_strike_regression(self):
        sdk,clock,rt,step=self.make_runtime()
        for _ in range(4):
            self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
            clock.set(rt.result_started_at+99); rt.step()
        kinds=[e.kind for e in self.special_events(rt)]
        self.assertEqual(kinds, [RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.STRIKE, RegulationPresentationEventKind.TURKEY, RegulationPresentationEventKind.STRIKE])
        third=self.special_events(rt)[-3]
        turkey=self.special_events(rt)[-2]
        self.assertEqual((third.frame_number, third.roll_number, third.label), (3, 1, "STRIKE"))
        self.assertEqual((third.deadline, turkey.started_at, turkey.deadline), (third.started_at + 0.75, third.started_at + 0.75, third.started_at + 1.5))
        self.assertEqual(rt.presentation_timeline.view_model(third.started_at).label, "STRIKE")
        self.assertEqual(rt.presentation_timeline.view_model(turkey.started_at).label, "TURKEY")

    def test_throw_ready_is_visible_after_third_runtime_strike_hold(self):
        sdk,clock,rt,step=self.make_runtime()
        for _ in range(3):
            self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
            clock.set(rt.result_started_at+1.5); rt.step()
        view=rt.presentation_timeline.view_model(clock.t)
        self.assertEqual((view.kind, view.label), (RegulationPresentationEventKind.THROW_READY, "THROW READY"))

    def test_tenth_frame_bonus_rack_split_and_conversion(self):
        sdk,clock,rt,step=self.make_runtime()
        for _ in range(18):
            self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER))
            clock.set(rt.result_started_at+1.5); rt.step()
        self.assertEqual(rt.current_frame_number, 10)
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
        clock.set(rt.result_started_at+1.5); rt.step()
        leave=(7,10); knocked=tuple(pin for pin in FULL_RACK if pin not in leave)
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,knocked))
        split=self.special_events(rt)[-1]
        self.assertEqual((split.kind, split.frame_number, split.roll_number), (RegulationPresentationEventKind.SPLIT, 10, 2))
        clock.set(rt.result_started_at+1.5); rt.step()
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,leave,leave))
        converted=self.special_events(rt)[-1]
        self.assertEqual((converted.kind, converted.frame_number, converted.roll_number), (RegulationPresentationEventKind.SPLIT_CONVERTED, 10, 3))

    def test_miss_gutter_foul_spare_and_game_over_are_visible_once(self):
        sdk,clock,rt,step=self.make_runtime()
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.MISS)); self.assertEqual(rt.presentation_timeline.view_model(clock.t).label,"MISS")
        clock.set(rt.result_started_at+1.5); rt.step()
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); self.assertEqual(rt.presentation_timeline.view_model(clock.t).label,"GUTTER")
        sdk,clock,rt,step=self.make_runtime(); self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,(1,2,3,4,5)))
        clock.set(rt.result_started_at+1.5); rt.step(); self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,rt.standing_pins,rt.standing_pins)); self.assertEqual(rt.presentation_timeline.view_model(clock.t).label,"SPARE")
        sdk,clock,rt,step=self.make_runtime(); clock.set(30); rt.step(); self.assertEqual(rt.presentation_timeline.view_model(clock.t).label,"FOUL")
        sdk,clock,rt,step=self.make_runtime()
        for _ in range(20):
            self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER)); clock.set(rt.result_started_at+1.5); rt.step()
        game_overs=[e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.GAME_OVER]
        self.assertEqual(len(game_overs),1)
        self.assertEqual(rt.presentation_timeline.view_model(clock.t+999).label,"GAME OVER")
        rt.step(); self.assertEqual(game_overs, [e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.GAME_OVER])

    def test_field_goal_can_be_acknowledged_from_existing_result_kind(self):
        from throw_a_strike.application.session import GameSession, SessionPhase
        from throw_a_strike.domain import MatchConfig, Mode, Theme, ControlStyle
        s=GameSession(); s.configure(MatchConfig(Mode.TEN_PIN,Theme.REGULAR,1,10,0,ControlStyle.QUICK)); s.start(); s.submit_throw(0)
        timeline=RegulationPresentationTimeline()
        events=timeline.acknowledge_result(s.snapshot(), BowlingThrowResultKind.FIELD_GOAL, 4, pins_before=FULL_RACK, pins_after=FULL_RACK)
        self.assertEqual((events[0].kind, events[0].label), (RegulationPresentationEventKind.FIELD_GOAL, "FIELD GOAL"))
        self.assertEqual(timeline.view_model(4).label, "FIELD GOAL")
        self.assertIs(s.acknowledge_result().phase, SessionPhase.AWAITING_THROW)
