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
from throw_a_strike.domain import ThrowControlPhase
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.rendering import (EMULATOR_RGB888_BYTE_LENGTH,
    render_style_selection_rgb888, render_throw_control_rgb888)

class EmulatorControlTestPhase(str, Enum):
    SELECT_STYLE="select_style"
    ATTEMPT="attempt"
    RECOVERY_HOLD="recovery_hold"
    TERMINAL="terminal"

@dataclass(frozen=True)
class EmulatorControlTestStep:
    phase: EmulatorControlTestPhase
    selection: ThrowControlStyleSelectionSnapshot
    presentation: ThrowControlPresentation | None
    framebuffer: bytes
    framebuffer_accepted: bool
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
        else:
            valid = (self.selection.confirmed and self.presentation is not None
                     and self.presentation.terminal
                     and self.presentation.phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL))
        if not valid:
            raise InvalidPortValueError("phase, selection, and presentation are inconsistent")
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
    @property
    def phase(self): return self._phase
    @property
    def coordinator(self): return self._coordinator
    def step(self):
        if self._phase in (EmulatorControlTestPhase.RECOVERY_HOLD,EmulatorControlTestPhase.TERMINAL):
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
        if self._phase is EmulatorControlTestPhase.SELECT_STYLE:
            events=self._input.poll()
            now=events[0].timestamp if events else self._clock.monotonic_seconds()
            selection=self._selector.apply(events,now)
            if not selection.confirmed:
                frame=render_style_selection_rgb888(selection)
                return EmulatorControlTestStep(self._phase,selection,None,frame,self._facade.submit_framebuffer(frame))
            self._coordinator=ThrowControlCoordinator(selection.selected_style,self._input,self._clock,selection.confirmed_at)
            self._presentation=build_throw_control_presentation(self._coordinator.snapshot)
            self._cached=render_throw_control_rgb888(self._presentation)
            self._phase=EmulatorControlTestPhase.ATTEMPT
            return EmulatorControlTestStep(self._phase,selection,self._presentation,self._cached,self._facade.submit_framebuffer(self._cached))
        result=self._coordinator.step()
        self._presentation=build_throw_control_step_presentation(result)
        blink=True if result.tick_timestamp is None else int(result.tick_timestamp*2)%2==0
        self._cached=render_throw_control_rgb888(self._presentation,blink)
        if self._presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY: self._phase=EmulatorControlTestPhase.RECOVERY_HOLD
        elif self._presentation.terminal: self._phase=EmulatorControlTestPhase.TERMINAL
        accepted=self._facade.submit_framebuffer(self._cached)
        return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)

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
