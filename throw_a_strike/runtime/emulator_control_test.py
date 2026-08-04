"""Single-attempt interactive control-test runtime for the Dartsnut emulator."""
from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
import time
from typing import Callable

from throw_a_strike.adapters import DartsnutInputPort
from throw_a_strike.application import (ClockPort, InvalidPortValueError, PortCapabilities,
    ThrowControlCoordinator, ThrowControlPresentation, ThrowControlStyleSelectionSnapshot,
    ThrowControlStyleSelector, build_throw_control_presentation, build_throw_control_step_presentation)
from throw_a_strike.domain import ThrowControlPhase, ThrowSetup
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.rendering import (EMULATOR_RGB888_BYTE_LENGTH,
    render_dart_accepted_rgb888, render_style_selection_rgb888, render_throw_control_rgb888)

class EmulatorControlTestPhase(str, Enum):
    SELECT_STYLE="select_style"
    ATTEMPT="attempt"
    RECOVERY_HOLD="recovery_hold"
    FOUL_HOLD="foul_hold"
    ACCEPTED_HOLD="accepted_hold"
    TERMINAL="terminal"

FOUL_HOLD_SECONDS = 1.5
ACCEPTED_HOLD_SECONDS = 1.5

@dataclass(frozen=True)
class EmulatorControlTestStep:
    phase: EmulatorControlTestPhase
    selection: ThrowControlStyleSelectionSnapshot
    presentation: ThrowControlPresentation | None
    framebuffer: bytes
    framebuffer_accepted: bool
    accepted_setup: ThrowSetup | None = None
    def __post_init__(self):
        if type(self.phase) is not EmulatorControlTestPhase: raise InvalidPortValueError("phase must be exact")
        if type(self.selection) is not ThrowControlStyleSelectionSnapshot: raise InvalidPortValueError("selection must be exact")
        if self.presentation is not None and type(self.presentation) is not ThrowControlPresentation: raise InvalidPortValueError("presentation must be exact or None")
        if type(self.framebuffer) is not bytes or len(self.framebuffer)!=EMULATOR_RGB888_BYTE_LENGTH: raise InvalidPortValueError("framebuffer must be exact RGB888 bytes")
        if type(self.framebuffer_accepted) is not bool: raise InvalidPortValueError("framebuffer_accepted must be exact bool")
        if self.phase is EmulatorControlTestPhase.SELECT_STYLE:
            valid = not self.selection.confirmed and self.presentation is None
        elif self.phase is EmulatorControlTestPhase.ATTEMPT:
            valid = (self.selection.confirmed and self.presentation is not None
                     and not self.presentation.terminal
                     and self.presentation.phase is not ThrowControlPhase.EARLY_DART_RECOVERY)
        elif self.phase is EmulatorControlTestPhase.RECOVERY_HOLD:
            valid = (self.selection.confirmed and self.presentation is not None
                     and not self.presentation.terminal
                     and self.presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY)
        elif self.phase is EmulatorControlTestPhase.FOUL_HOLD:
            valid = (self.selection.confirmed and self.presentation is not None
                     and self.presentation.terminal
                     and self.presentation.phase is ThrowControlPhase.FOUL)
        elif self.phase is EmulatorControlTestPhase.ACCEPTED_HOLD:
            valid = (self.selection.confirmed and self.presentation is not None
                     and self.presentation.terminal
                     and self.presentation.phase is ThrowControlPhase.COMPLETE
                     and type(self.accepted_setup) is ThrowSetup
                     and self.framebuffer == render_dart_accepted_rgb888(
                         self.presentation,self.accepted_setup.dart_index,
                         self.accepted_setup.aim_x,self.accepted_setup.aim_y))
        else:
            valid = (self.selection.confirmed and self.presentation is not None
                     and self.presentation.terminal
                     and self.presentation.phase is ThrowControlPhase.COMPLETE)
        if not valid:
            raise InvalidPortValueError("phase, selection, and presentation are inconsistent")
        if self.phase is not EmulatorControlTestPhase.ACCEPTED_HOLD and self.accepted_setup is not None:
            raise InvalidPortValueError("accepted_setup is allowed only during accepted hold")
    @property
    def terminal(self): return self.phase is EmulatorControlTestPhase.TERMINAL

def _nonnegative(value, name):
    if isinstance(value,bool) or not isinstance(value,Real): raise InvalidPortValueError(f"{name} must be finite nonnegative")
    result=float(value)
    if not math.isfinite(result) or result<0: raise InvalidPortValueError(f"{name} must be finite nonnegative")
    return result

class EmulatorControlTestRuntime:
    def __init__(self, facade: DartsnutSdkFacade, clock: ClockPort, started_at: float):
        if type(facade) is not DartsnutSdkFacade: raise InvalidPortValueError("facade must be exact DartsnutSdkFacade")
        if clock is None or isinstance(clock,type) or not isinstance(clock,ClockPort): raise InvalidPortValueError("clock must satisfy ClockPort")
        capabilities=clock.capabilities
        if type(capabilities) is not PortCapabilities: raise InvalidPortValueError("clock capabilities must be exact PortCapabilities")
        start=_nonnegative(started_at,"started_at")
        self._facade=facade; self._clock=clock; self._input=DartsnutInputPort(facade,clock)
        self._selector=ThrowControlStyleSelector(start); self._coordinator=None
        self._phase=EmulatorControlTestPhase.SELECT_STYLE; self._cached=None; self._presentation=None
        self._foul_timestamp=None
        self._accepted_timestamp=None; self._accepted_snapshot=None; self._accepted_setup=None
    @property
    def phase(self): return self._phase
    @property
    def coordinator(self): return self._coordinator
    @property
    def accepted_timestamp(self): return self._accepted_timestamp
    @property
    def accepted_snapshot(self): return self._accepted_snapshot
    @property
    def accepted_setup(self): return self._accepted_setup
    def _begin_attempt(self, style, started_at):
        self._coordinator=ThrowControlCoordinator(style,self._input,self._clock,started_at)
        self._foul_timestamp=None
        self._accepted_timestamp=None; self._accepted_snapshot=None; self._accepted_setup=None
        self._presentation=build_throw_control_presentation(self._coordinator.snapshot)
        self._cached=render_throw_control_rgb888(self._presentation)
        self._phase=EmulatorControlTestPhase.ATTEMPT
        accepted=self._facade.submit_framebuffer(self._cached)
        return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
    def step(self):
        if self._phase in (EmulatorControlTestPhase.RECOVERY_HOLD,EmulatorControlTestPhase.TERMINAL):
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,
                                           self._accepted_setup)
        if self._phase is EmulatorControlTestPhase.FOUL_HOLD:
            now=self._clock.monotonic_seconds()
            if now >= self._foul_timestamp + FOUL_HOLD_SECONDS:
                return self._begin_attempt(self._selector.snapshot.selected_style,now)
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,
                                           self._accepted_setup)
        if self._phase is EmulatorControlTestPhase.ACCEPTED_HOLD:
            now=self._clock.monotonic_seconds()
            if now >= self._accepted_timestamp + ACCEPTED_HOLD_SECONDS:
                return self._begin_attempt(self._selector.snapshot.selected_style,now)
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,
                                           self._accepted_setup)
        if self._phase is EmulatorControlTestPhase.SELECT_STYLE:
            events=self._input.poll()
            now=events[0].timestamp if events else self._clock.monotonic_seconds()
            selection=self._selector.apply(events,now)
            if not selection.confirmed:
                frame=render_style_selection_rgb888(selection)
                return EmulatorControlTestStep(self._phase,selection,None,frame,self._facade.submit_framebuffer(frame))
            return self._begin_attempt(selection.selected_style,selection.confirmed_at)
        result=self._coordinator.step()
        self._presentation=build_throw_control_step_presentation(result)
        blink=True if result.tick_timestamp is None else int(result.tick_timestamp*2)%2==0
        self._cached=render_throw_control_rgb888(self._presentation,blink)
        if self._presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY: self._phase=EmulatorControlTestPhase.RECOVERY_HOLD
        elif self._presentation.phase is ThrowControlPhase.FOUL:
            self._foul_timestamp=result.tick_timestamp
            self._phase=EmulatorControlTestPhase.FOUL_HOLD
        elif self._presentation.terminal:
            self._accepted_snapshot=result.snapshot
            self._accepted_setup=result.snapshot.outcome.setup
            setup=self._accepted_setup
            self._accepted_timestamp=result.events[-1].timestamp
            self._cached=render_dart_accepted_rgb888(
                self._presentation,setup.dart_index,setup.aim_x,setup.aim_y)
            self._phase=EmulatorControlTestPhase.ACCEPTED_HOLD
        accepted=self._facade.submit_framebuffer(self._cached)
        return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,
                                       self._accepted_setup if self._phase is EmulatorControlTestPhase.ACCEPTED_HOLD else None)

def run_emulator_control_test(facade: DartsnutSdkFacade, clock: ClockPort, started_at: float, *,
                              frame_seconds: float=1/30, sleeper: Callable[[float],object]=time.sleep,
                              max_iterations: int|None=None) -> None:
    if type(facade) is not DartsnutSdkFacade:
        raise InvalidPortValueError("facade must be exact DartsnutSdkFacade")
    try:
        delay=_nonnegative(frame_seconds,"frame_seconds")
        if not callable(sleeper): raise InvalidPortValueError("sleeper must be callable")
        if max_iterations is not None and (type(max_iterations) is not int or max_iterations<0): raise InvalidPortValueError("max_iterations must be nonnegative or None")
        runtime=EmulatorControlTestRuntime(facade,clock,started_at)
        count=0
        while (max_iterations is None or count<max_iterations) and facade.is_running():
            runtime.step(); count+=1; sleeper(delay)
    finally:
        facade.close()
