"""Single-player regulation ten-pin emulator runtime."""
from dataclasses import dataclass
from enum import Enum
import time
from typing import Callable

from throw_a_strike.adapters import DartsnutEmulatorInputPort
from throw_a_strike.application import (ClockPort, InputEventKind, InvalidPortValueError, PortCapabilities,
    ThrowControlCoordinator, ThrowControlPresentation, ThrowControlStyleSelectionSnapshot,
    ThrowControlStyleSelector, build_throw_control_presentation, build_throw_control_step_presentation)
from throw_a_strike.application.session import GameSession, SessionPhase
from throw_a_strike.application.regulation_presentation import RegulationPresentationTimeline
from throw_a_strike.domain import (BallTrajectory, BowlingSnapshot, BowlingThrowResultKind, ControlStyle,
    MatchConfig, Mode, Theme, PlayerColor, PinfallResolution, ThrowControlPhase, THROW_FOUL_SECONDS, ThrowSetup,
    build_ball_trajectory, resolve_ball_pinfall, sample_ball_roll, PINFALL_DURATION_SECONDS)
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH, render_regulation_event_view_model_rgb888, render_style_selection_rgb888
from throw_a_strike.rendering.ten_pin_rgb888 import (render_ten_pin_attempt_rgb888,
    render_ten_pin_ball_roll_rgb888, render_ten_pin_pinfall_rgb888, render_ten_pin_result_rgb888,
    render_ten_pin_wrong_color_rgb888, render_ten_pin_foul_rgb888, render_ten_pin_game_over_rgb888, TenPinRenderContext)
from throw_a_strike.runtime.emulator_common import PlayerColorInputPort, nonnegative, update_throw_ready_started_at
from throw_a_strike.runtime.emulator_control_test import WRONG_COLOR_HOLD_SECONDS
from throw_a_strike.runtime.secondary_display import MemorySecondaryDisplayPort
RESULT_HOLD_SECONDS = 1.5
FOUL_HOLD_SECONDS = 1.5

class EmulatorTenPinPhase(str, Enum):
    SELECT_STYLE="select_style"; ATTEMPT="attempt"; BALL_ROLL="ball_roll"; PINFALL="pinfall"
    RECOVERY_HOLD="recovery_hold"; FOUL_HOLD="foul_hold"; RESULT_HOLD="result_hold"
    WRONG_COLOR_HOLD="wrong_color_hold"; GAME_OVER="game_over"

@dataclass(frozen=True)
class EmulatorTenPinStep:
    phase: EmulatorTenPinPhase
    selection: ThrowControlStyleSelectionSnapshot
    presentation: ThrowControlPresentation | None
    framebuffer: bytes
    framebuffer_accepted: bool
    accepted_setup: ThrowSetup | None = None
    def __post_init__(self):
        if type(self.phase) is not EmulatorTenPinPhase: raise InvalidPortValueError("phase must be exact")
        if type(self.selection) is not ThrowControlStyleSelectionSnapshot: raise InvalidPortValueError("selection must be exact")
        if self.presentation is not None and type(self.presentation) is not ThrowControlPresentation: raise InvalidPortValueError("presentation must be exact or None")
        if type(self.framebuffer) is not bytes or len(self.framebuffer) != EMULATOR_RGB888_BYTE_LENGTH: raise InvalidPortValueError("framebuffer must be exact RGB888 bytes")
        if type(self.framebuffer_accepted) is not bool: raise InvalidPortValueError("framebuffer_accepted must be exact bool")
        if self.phase is EmulatorTenPinPhase.SELECT_STYLE:
            valid = not self.selection.confirmed and self.presentation is None and self.accepted_setup is None
        elif self.phase is EmulatorTenPinPhase.ATTEMPT:
            valid = self.selection.confirmed and self.presentation is not None and not self.presentation.terminal and self.presentation.phase is not ThrowControlPhase.EARLY_DART_RECOVERY and self.accepted_setup is None
        elif self.phase in (EmulatorTenPinPhase.BALL_ROLL, EmulatorTenPinPhase.PINFALL):
            valid = self.selection.confirmed and self.presentation is not None and self.presentation.terminal and self.presentation.phase is ThrowControlPhase.COMPLETE and self.accepted_setup is not None
        elif self.phase is EmulatorTenPinPhase.RESULT_HOLD:
            valid = self.selection.confirmed and self.presentation is not None and self.presentation.terminal and self.presentation.phase is ThrowControlPhase.COMPLETE and self.accepted_setup is not None
        elif self.phase is EmulatorTenPinPhase.FOUL_HOLD:
            valid = self.selection.confirmed and self.presentation is not None and self.presentation.terminal and self.presentation.phase is ThrowControlPhase.FOUL and self.accepted_setup is None
        elif self.phase is EmulatorTenPinPhase.RECOVERY_HOLD:
            valid = self.selection.confirmed and self.presentation is not None and not self.presentation.terminal and self.presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY and self.accepted_setup is None
        elif self.phase is EmulatorTenPinPhase.WRONG_COLOR_HOLD:
            valid = self.selection.confirmed and self.presentation is not None and not self.presentation.terminal and self.presentation.phase is not ThrowControlPhase.EARLY_DART_RECOVERY and self.accepted_setup is None
        elif self.phase is EmulatorTenPinPhase.GAME_OVER:
            valid = self.selection.confirmed and self.presentation is None and self.accepted_setup is None
        else:
            valid = False
        if not valid: raise InvalidPortValueError("phase, selection, and presentation are inconsistent")
    @property
    def terminal(self): return self.phase is EmulatorTenPinPhase.GAME_OVER

class EmulatorTenPinRuntime:
    def __init__(self, facade: DartsnutSdkFacade, clock: ClockPort, started_at: float, secondary_display: MemorySecondaryDisplayPort | None = None):
        if type(facade) is not DartsnutSdkFacade: raise InvalidPortValueError("facade must be exact DartsnutSdkFacade")
        if clock is None or isinstance(clock,type) or not isinstance(clock,ClockPort): raise InvalidPortValueError("clock must satisfy ClockPort")
        if type(clock.capabilities) is not PortCapabilities: raise InvalidPortValueError("clock capabilities must be exact")
        start=nonnegative(started_at,"started_at")
        if secondary_display is not None and not isinstance(secondary_display, MemorySecondaryDisplayPort): raise InvalidPortValueError("secondary_display must be a memory secondary display port or None")
        self._facade=facade; self._clock=clock; self._secondary_display=secondary_display; self._raw_input=DartsnutEmulatorInputPort(facade,clock)
        self._input=PlayerColorInputPort(self._raw_input,1); self._selector=ThrowControlStyleSelector(start); self._coordinator=None
        self._session=GameSession(); self._presentation_timeline=RegulationPresentationTimeline(); self._standing_pins=FULL_RACK; self._phase=EmulatorTenPinPhase.SELECT_STYLE
        self._cached=None; self._presentation=None; self._wrong_timestamp=None; self._foul_timestamp=None; self._result_started_at=None
        self._accepted_snapshot=None; self._accepted_setup=None; self._ball_trajectory=None; self._ball_started_at=None
        self._pinfall_resolution=None; self._pinfall_started_at=None; self._recovery_dart_index=None; self._last_result_kind=None; self._last_label=""; self._throw_ready_started_at=None
    @property
    def phase(self): return self._phase
    @property
    def selected_style(self): return self._selector.snapshot.selected_style if self._selector.snapshot.confirmed else None
    @property
    def presentation(self): return self._presentation
    @property
    def presentation_timeline(self): return self._presentation_timeline
    def secondary_event_view_model(self): return self._presentation_timeline.view_model(self._clock.monotonic_seconds())
    @property
    def session_snapshot(self): return self._session.snapshot()
    @property
    def throw_ready_started_at(self): return self._throw_ready_started_at
    @property
    def bowling_snapshot(self):
        m=self.session_snapshot.match
        return None if m is None else m.players[0].bowling
    @property
    def standing_pins(self): return self._standing_pins
    @property
    def accepted_snapshot(self): return self._accepted_snapshot
    @property
    def accepted_setup(self): return self._accepted_setup
    @property
    def ball_trajectory(self): return self._ball_trajectory
    @property
    def ball_started_at(self): return self._ball_started_at
    @property
    def pinfall_resolution(self): return self._pinfall_resolution
    @property
    def pinfall_started_at(self): return self._pinfall_started_at
    @property
    def result_started_at(self): return self._result_started_at
    @property
    def current_frame_number(self):
        snap=self.session_snapshot
        if self._phase is not EmulatorTenPinPhase.GAME_OVER and snap.last_throw is not None and snap.phase is SessionPhase.SHOWING_RESULT:
            return snap.last_throw.frame_number
        return snap.current_frame_number
    @property
    def current_roll_number(self):
        snap=self.session_snapshot
        if self._phase is not EmulatorTenPinPhase.GAME_OVER and snap.last_throw is not None and snap.phase is SessionPhase.SHOWING_RESULT:
            return snap.last_throw.throw_number
        return snap.current_throw_number
    @property
    def confirmed_score(self):
        b=self.bowling_snapshot; return 0 if b is None else b.confirmed_score
    @property
    def complete(self):
        b=self.bowling_snapshot; return bool(b and b.complete)
    def _begin_attempt(self, style, started_at):
        if self.session_snapshot.phase is SessionPhase.CONFIGURING:
            self._session.configure(MatchConfig(Mode.TEN_PIN,Theme.REGULAR,1,10,0,style)); self._session.start()
        elif self.session_snapshot.phase is SessionPhase.FRAME_TRANSITION:
            self._session.continue_transition()
        elif self.session_snapshot.phase is SessionPhase.PLAYER_TRANSITION:
            raise RuntimeError("unexpected player transition in one-player ten-pin")
        if len(self._standing_pins) != self.session_snapshot.current_available: raise RuntimeError("standing rack mismatch")
        self._coordinator=ThrowControlCoordinator(style,self._input,self._clock,started_at)
        self._foul_timestamp=self._result_started_at=None; self._accepted_snapshot=None; self._accepted_setup=None; self._ball_trajectory=None; self._ball_started_at=None; self._pinfall_resolution=None; self._pinfall_started_at=None; self._last_result_kind=None; self._last_label=""
        self._presentation=build_throw_control_presentation(self._coordinator.snapshot)
        self._throw_ready_started_at=started_at if self._presentation.phase is ThrowControlPhase.THROW_READY else None
        if self._throw_ready_started_at is not None:
            self._presentation_timeline.throw_ready(started_at, frame_number=self.session_snapshot.current_frame_number, roll_number=self.session_snapshot.current_throw_number)
        self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        self._phase=EmulatorTenPinPhase.ATTEMPT
        return self._step_obj(self._facade.submit_framebuffer(self._cached))
    def _publish_secondary(self):
        if self._secondary_display is not None:
            self._secondary_display.present(render_regulation_event_view_model_rgb888(self.secondary_event_view_model()))
    def _step_obj(self, accepted):
        self._publish_secondary()
        return EmulatorTenPinStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,self._accepted_setup)
    def _label(self, pins, kind):
        marks=self.bowling_snapshot.frames[self.session_snapshot.last_throw.frame_number-1].marks
        mark=marks[-1] if marks else ""
        if mark == "X": return "STRIKE"
        if mark == "/": return "SPARE"
        if pins > 0: return f"{pins} PINS"
        return "FOUL" if kind is BowlingThrowResultKind.FOUL else ("GUTTER" if kind is BowlingThrowResultKind.GUTTER else "MISS")
    def _submit(self, pins, kind, timestamp, pins_before=None, pins_after=None):
        self._presentation_timeline.cancel_throw_ready()
        before = self._standing_pins if pins_before is None else pins_before
        after = before if pins_after is None else pins_after
        self._session.submit_throw(pins); self._last_result_kind=kind; self._last_label=self._label(pins,kind); self._result_started_at=timestamp
        self._presentation_timeline.acknowledge_result(self.session_snapshot, kind, timestamp, pins_before=before, pins_after=after)
    def _after_hold(self, now):
        snap=self._session.acknowledge_result()
        if snap.phase is SessionPhase.GAME_OVER:
            self._accepted_snapshot=None; self._accepted_setup=None; self._ball_trajectory=None; self._ball_started_at=None; self._pinfall_resolution=None; self._pinfall_started_at=None; self._result_started_at=None; self._last_result_kind=None; self._last_label=""; self._throw_ready_started_at=None; self._presentation=None; self._phase=EmulatorTenPinPhase.GAME_OVER; self._presentation_timeline.observe_game_over(self.session_snapshot, now); self._cached=render_ten_pin_game_over_rgb888(self.bowling_snapshot)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        avail=snap.current_available
        if snap.phase is SessionPhase.FRAME_TRANSITION:
            snap=self._session.continue_transition(); avail=snap.current_available
        elif snap.phase is SessionPhase.PLAYER_TRANSITION: raise RuntimeError("unexpected player transition")
        self._standing_pins = FULL_RACK if avail == 10 else self._standing_pins
        if len(self._standing_pins) != avail: raise RuntimeError("standing rack mismatch after result")
        return self._begin_attempt(self._selector.snapshot.selected_style, now)
    def step(self):
        if self._phase is EmulatorTenPinPhase.GAME_OVER:
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase is EmulatorTenPinPhase.RECOVERY_HOLD:
            active=self._raw_input.observe_active_darts()
            if any(dart.dart_index == self._recovery_dart_index for dart in active):
                return self._step_obj(self._facade.submit_framebuffer(self._cached))
            self._raw_input.discard_pending_events(); now=self._clock.monotonic_seconds(); snapshot=self._coordinator.rearm(now); self._recovery_dart_index=None
            self._presentation=build_throw_control_presentation(snapshot); self._phase=EmulatorTenPinPhase.ATTEMPT; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase is EmulatorTenPinPhase.SELECT_STYLE:
            events=self._raw_input.poll(); now=events[0].timestamp if events else self._clock.monotonic_seconds(); sel=self._selector.apply(events,now)
            if not sel.confirmed:
                self._cached=render_style_selection_rgb888(sel); return EmulatorTenPinStep(self._phase,sel,None,self._cached,self._facade.submit_framebuffer(self._cached))
            return self._begin_attempt(sel.selected_style,sel.confirmed_at)
        if self._phase is EmulatorTenPinPhase.BALL_ROLL:
            now=self._clock.monotonic_seconds(); traj=self._ball_trajectory; res=self._pinfall_resolution; deadline=self._ball_started_at+traj.duration_seconds
            sample=sample_ball_roll(traj,res,traj.duration_seconds if now>=deadline else now-self._ball_started_at)
            if now>=deadline:
                if res.result_kind is BowlingThrowResultKind.PIN_HIT:
                    self._pinfall_started_at=deadline; self._phase=EmulatorTenPinPhase.PINFALL; self._cached=render_ten_pin_pinfall_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,res,0,self.bowling_snapshot)
                    return self._step_obj(self._facade.submit_framebuffer(self._cached))
                self._submit(0,res.result_kind,deadline,res.standing_before,res.standing_after); self._phase=EmulatorTenPinPhase.RESULT_HOLD; ctx=TenPinRenderContext(self.session_snapshot.last_throw.frame_number,self.session_snapshot.last_throw.throw_number); self._cached=render_ten_pin_result_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,res,self.bowling_snapshot,self._last_label,context=ctx)
                return self._step_obj(self._facade.submit_framebuffer(self._cached))
            self._cached=render_ten_pin_ball_roll_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,sample,PlayerColor.BLUE)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase is EmulatorTenPinPhase.PINFALL:
            now=self._clock.monotonic_seconds(); deadline=self._pinfall_started_at+PINFALL_DURATION_SECONDS; sample=sample_ball_roll(self._ball_trajectory,self._pinfall_resolution,self._ball_trajectory.duration_seconds)
            if now>=deadline:
                self._standing_pins=self._pinfall_resolution.standing_after; pins=len(self._pinfall_resolution.knocked_down); self._submit(pins,BowlingThrowResultKind.PIN_HIT,deadline,self._pinfall_resolution.standing_before,self._pinfall_resolution.standing_after)
                self._phase=EmulatorTenPinPhase.RESULT_HOLD; ctx=TenPinRenderContext(self.session_snapshot.last_throw.frame_number,self.session_snapshot.last_throw.throw_number); self._cached=render_ten_pin_result_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,self._pinfall_resolution,self.bowling_snapshot,self._last_label,context=ctx)
                return self._step_obj(self._facade.submit_framebuffer(self._cached))
            self._cached=render_ten_pin_pinfall_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,self._pinfall_resolution,now-self._pinfall_started_at,self.bowling_snapshot)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase in (EmulatorTenPinPhase.RESULT_HOLD, EmulatorTenPinPhase.FOUL_HOLD):
            now=self._clock.monotonic_seconds(); hold=FOUL_HOLD_SECONDS if self._phase is EmulatorTenPinPhase.FOUL_HOLD else RESULT_HOLD_SECONDS
            deadline=self._result_started_at+hold
            if now>=deadline: return self._after_hold(deadline)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase is EmulatorTenPinPhase.WRONG_COLOR_HOLD:
            now=self._clock.monotonic_seconds()
            if now>=self._wrong_timestamp+WRONG_COLOR_HOLD_SECONDS:
                self._phase=EmulatorTenPinPhase.ATTEMPT; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        before_phase=self._coordinator.snapshot.phase
        result=self._coordinator.step(); self._presentation=build_throw_control_step_presentation(result)
        old_ready=self._throw_ready_started_at
        self._throw_ready_started_at=update_throw_ready_started_at(self._selector.snapshot.selected_style,before_phase,result.commands,self._throw_ready_started_at)
        if old_ready is None and self._throw_ready_started_at is not None:
            self._presentation_timeline.throw_ready(self._throw_ready_started_at, frame_number=self.session_snapshot.current_frame_number, roll_number=self.session_snapshot.current_throw_number)
        if old_ready is not None and self._throw_ready_started_at is None:
            self._presentation_timeline.cancel_throw_ready()
        if self._input.wrong_event is not None and not self._presentation.terminal:
            self._wrong_timestamp=self._input.wrong_event.timestamp; self._phase=EmulatorTenPinPhase.WRONG_COLOR_HOLD; self._cached=render_ten_pin_wrong_color_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        elif self._presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY:
            dart_commands=tuple(command for command in result.commands if command.dart_index is not None)
            if not dart_commands: raise InvalidPortValueError("early recovery requires an offending dart")
            self._recovery_dart_index=dart_commands[-1].dart_index
            self._phase=EmulatorTenPinPhase.RECOVERY_HOLD; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        elif self._presentation.phase is ThrowControlPhase.FOUL:
            foul_deadline=self._throw_ready_started_at+THROW_FOUL_SECONDS
            self._submit(0,BowlingThrowResultKind.FOUL,foul_deadline,self._standing_pins,self._standing_pins); self._phase=EmulatorTenPinPhase.FOUL_HOLD; ctx=TenPinRenderContext(self.session_snapshot.last_throw.frame_number,self.session_snapshot.last_throw.throw_number); self._cached=render_ten_pin_foul_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,context=ctx)
        elif self._presentation.terminal:
            self._presentation_timeline.cancel_throw_ready()
            self._accepted_snapshot=result.snapshot; self._accepted_setup=result.snapshot.outcome.setup
            darts=tuple(e for e in result.events if e.kind is InputEventKind.DART_HIT)
            self._ball_started_at=darts[-1].timestamp; self._ball_trajectory=build_ball_trajectory(self._accepted_setup); self._pinfall_resolution=resolve_ball_pinfall(self._ball_trajectory,self._standing_pins)
            sample=sample_ball_roll(self._ball_trajectory,self._pinfall_resolution,0); self._phase=EmulatorTenPinPhase.BALL_ROLL; self._cached=render_ten_pin_ball_roll_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,sample,PlayerColor.BLUE)
        else:
            blink=True if result.tick_timestamp is None else int(result.tick_timestamp*2)%2==0; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,blink)
        return self._step_obj(self._facade.submit_framebuffer(self._cached))

def run_emulator_ten_pin(facade: DartsnutSdkFacade, clock: ClockPort, started_at: float, *, frame_seconds: float=1/30, sleeper: Callable[[float],object]=time.sleep, max_iterations: int|None=None, secondary_display: MemorySecondaryDisplayPort | None = None) -> None:
    if type(facade) is not DartsnutSdkFacade:
        raise InvalidPortValueError("facade must be exact DartsnutSdkFacade")
    try:
        delay=nonnegative(frame_seconds,"frame_seconds")
        if not callable(sleeper): raise InvalidPortValueError("sleeper must be callable")
        if max_iterations is not None and (type(max_iterations) is not int or max_iterations<0): raise InvalidPortValueError("max_iterations must be nonnegative or None")
        runtime=EmulatorTenPinRuntime(facade,clock,started_at,secondary_display); count=0
        while (max_iterations is None or count<max_iterations) and facade.is_running(): runtime.step(); count+=1; sleeper(delay)
    finally:
        if secondary_display is not None:
            secondary_display.close()
        facade.close()
