"""Single-player regulation ten-pin emulator runtime."""
from dataclasses import dataclass
from enum import Enum
import math, time
from numbers import Real
from typing import Callable

from throw_a_strike.adapters import DartsnutEmulatorInputPort
from throw_a_strike.application import (ClockPort, InputEventKind, InvalidPortValueError, PortCapabilities,
    ThrowControlCoordinator, ThrowControlPresentation, ThrowControlStyleSelectionSnapshot,
    ThrowControlStyleSelector, build_throw_control_presentation, build_throw_control_step_presentation)
from throw_a_strike.application.session import GameSession, SessionPhase
from throw_a_strike.domain import (BallTrajectory, BowlingSnapshot, BowlingThrowResultKind, ControlStyle,
    MatchConfig, Mode, Theme, PlayerColor, PinfallResolution, ThrowControlPhase, ThrowSetup,
    build_ball_trajectory, resolve_ball_pinfall, sample_ball_roll, PINFALL_DURATION_SECONDS,
    is_emulator_dart_for_player, player_color_for_number)
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH, render_style_selection_rgb888
from throw_a_strike.rendering.ten_pin_rgb888 import (render_ten_pin_attempt_rgb888,
    render_ten_pin_ball_roll_rgb888, render_ten_pin_pinfall_rgb888, render_ten_pin_result_rgb888,
    render_ten_pin_wrong_color_rgb888, render_ten_pin_foul_rgb888, render_ten_pin_game_over_rgb888)
from throw_a_strike.runtime.emulator_control_test import _PlayerColorInputPort, _nonnegative, WRONG_COLOR_HOLD_SECONDS

FULL_RACK = (1,2,3,4,5,6,7,8,9,10)
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
    @property
    def terminal(self): return self.phase is EmulatorTenPinPhase.GAME_OVER

class EmulatorTenPinRuntime:
    def __init__(self, facade: DartsnutSdkFacade, clock: ClockPort, started_at: float):
        if type(facade) is not DartsnutSdkFacade: raise InvalidPortValueError("facade must be exact DartsnutSdkFacade")
        if clock is None or isinstance(clock,type) or not isinstance(clock,ClockPort): raise InvalidPortValueError("clock must satisfy ClockPort")
        if type(clock.capabilities) is not PortCapabilities: raise InvalidPortValueError("clock capabilities must be exact")
        start=_nonnegative(started_at,"started_at")
        self._facade=facade; self._clock=clock; self._raw_input=DartsnutEmulatorInputPort(facade,clock)
        self._input=_PlayerColorInputPort(self._raw_input,1); self._selector=ThrowControlStyleSelector(start); self._coordinator=None
        self._session=GameSession(); self._standing_pins=FULL_RACK; self._phase=EmulatorTenPinPhase.SELECT_STYLE
        self._cached=None; self._presentation=None; self._wrong_timestamp=None; self._foul_timestamp=None; self._result_started_at=None
        self._accepted_snapshot=None; self._accepted_setup=None; self._ball_trajectory=None; self._ball_started_at=None
        self._pinfall_resolution=None; self._pinfall_started_at=None; self._recovery_dart_index=None; self._last_result_kind=None; self._last_label=""
    @property
    def phase(self): return self._phase
    @property
    def selected_style(self): return self._selector.snapshot.selected_style if self._selector.snapshot.confirmed else None
    @property
    def session_snapshot(self): return self._session.snapshot()
    @property
    def bowling_snapshot(self):
        m=self.session_snapshot.match
        return None if m is None else m.players[0].bowling
    @property
    def standing_pins(self): return self._standing_pins
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
    def current_frame_number(self): return self.session_snapshot.current_frame_number
    @property
    def current_roll_number(self): return self.session_snapshot.current_throw_number
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
        self._foul_timestamp=self._result_started_at=None; self._accepted_setup=None; self._ball_trajectory=None; self._pinfall_resolution=None
        self._presentation=build_throw_control_presentation(self._coordinator.snapshot)
        self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        self._phase=EmulatorTenPinPhase.ATTEMPT
        return self._step_obj(self._facade.submit_framebuffer(self._cached))
    def _step_obj(self, accepted): return EmulatorTenPinStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,self._accepted_setup)
    def _label(self, pins, kind):
        marks=self.bowling_snapshot.frames[self.session_snapshot.last_throw.frame_number-1].marks
        mark=marks[-1] if marks else ""
        if mark == "X": return "STRIKE"
        if mark == "/": return "SPARE"
        if pins > 0: return f"{pins} PINS"
        return "FOUL" if kind is BowlingThrowResultKind.FOUL else ("GUTTER" if kind is BowlingThrowResultKind.GUTTER else "MISS")
    def _submit(self, pins, kind, timestamp):
        self._session.submit_throw(pins); self._last_result_kind=kind; self._last_label=self._label(pins,kind); self._result_started_at=timestamp
    def _after_hold(self, now):
        snap=self._session.acknowledge_result()
        if snap.phase is SessionPhase.GAME_OVER:
            self._phase=EmulatorTenPinPhase.GAME_OVER; self._cached=render_ten_pin_game_over_rgb888(self.bowling_snapshot)
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
                self._submit(0,res.result_kind,deadline); self._phase=EmulatorTenPinPhase.RESULT_HOLD; self._cached=render_ten_pin_result_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,res,self.bowling_snapshot,self._last_label)
                return self._step_obj(self._facade.submit_framebuffer(self._cached))
            self._cached=render_ten_pin_ball_roll_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,sample,PlayerColor.BLUE)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase is EmulatorTenPinPhase.PINFALL:
            now=self._clock.monotonic_seconds(); deadline=self._pinfall_started_at+PINFALL_DURATION_SECONDS; sample=sample_ball_roll(self._ball_trajectory,self._pinfall_resolution,self._ball_trajectory.duration_seconds)
            if now>=deadline:
                self._standing_pins=self._pinfall_resolution.standing_after; pins=len(self._pinfall_resolution.knocked_down); self._submit(pins,BowlingThrowResultKind.PIN_HIT,deadline)
                self._phase=EmulatorTenPinPhase.RESULT_HOLD; self._cached=render_ten_pin_result_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,self._pinfall_resolution,self.bowling_snapshot,self._last_label)
                return self._step_obj(self._facade.submit_framebuffer(self._cached))
            self._cached=render_ten_pin_pinfall_rgb888(self._presentation,self._accepted_setup,PlayerColor.BLUE,sample,self._pinfall_resolution,now-self._pinfall_started_at,self.bowling_snapshot)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase in (EmulatorTenPinPhase.RESULT_HOLD, EmulatorTenPinPhase.FOUL_HOLD):
            now=self._clock.monotonic_seconds(); hold=FOUL_HOLD_SECONDS if self._phase is EmulatorTenPinPhase.FOUL_HOLD else RESULT_HOLD_SECONDS
            if now>=self._result_started_at+hold: return self._after_hold(now)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        if self._phase is EmulatorTenPinPhase.WRONG_COLOR_HOLD:
            now=self._clock.monotonic_seconds()
            if now>=self._wrong_timestamp+WRONG_COLOR_HOLD_SECONDS:
                self._phase=EmulatorTenPinPhase.ATTEMPT; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
            return self._step_obj(self._facade.submit_framebuffer(self._cached))
        result=self._coordinator.step(); self._presentation=build_throw_control_step_presentation(result)
        if self._input.wrong_event is not None and not self._presentation.terminal:
            self._wrong_timestamp=self._input.wrong_event.timestamp; self._phase=EmulatorTenPinPhase.WRONG_COLOR_HOLD; self._cached=render_ten_pin_wrong_color_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        elif self._presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY:
            dart_commands=tuple(command for command in result.commands if command.dart_index is not None)
            if not dart_commands: raise InvalidPortValueError("early recovery requires an offending dart")
            self._recovery_dart_index=dart_commands[-1].dart_index
            self._phase=EmulatorTenPinPhase.RECOVERY_HOLD; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        elif self._presentation.phase is ThrowControlPhase.FOUL:
            self._submit(0,BowlingThrowResultKind.FOUL,result.tick_timestamp); self._phase=EmulatorTenPinPhase.FOUL_HOLD; self._cached=render_ten_pin_foul_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins)
        elif self._presentation.terminal:
            self._accepted_snapshot=result.snapshot; self._accepted_setup=result.snapshot.outcome.setup
            darts=tuple(e for e in result.events if e.kind is InputEventKind.DART_HIT)
            self._ball_started_at=darts[-1].timestamp; self._ball_trajectory=build_ball_trajectory(self._accepted_setup); self._pinfall_resolution=resolve_ball_pinfall(self._ball_trajectory,self._standing_pins)
            sample=sample_ball_roll(self._ball_trajectory,self._pinfall_resolution,0); self._phase=EmulatorTenPinPhase.BALL_ROLL; self._cached=render_ten_pin_ball_roll_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,sample,PlayerColor.BLUE)
        else:
            blink=True if result.tick_timestamp is None else int(result.tick_timestamp*2)%2==0; self._cached=render_ten_pin_attempt_rgb888(self._presentation,self.bowling_snapshot,self._standing_pins,blink)
        return self._step_obj(self._facade.submit_framebuffer(self._cached))

def run_emulator_ten_pin(facade: DartsnutSdkFacade, clock: ClockPort, started_at: float, *, frame_seconds: float=1/30, sleeper: Callable[[float],object]=time.sleep, max_iterations: int|None=None) -> None:
    try:
        delay=_nonnegative(frame_seconds,"frame_seconds"); runtime=EmulatorTenPinRuntime(facade,clock,started_at); count=0
        while (max_iterations is None or count<max_iterations) and facade.is_running(): runtime.step(); count+=1; sleeper(delay)
    finally: facade.close()
