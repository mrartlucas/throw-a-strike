"""Deterministic Blue two-throw diagnostic runtime for the Dartsnut emulator."""
from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
import time
from typing import Callable

from throw_a_strike.adapters import DartsnutEmulatorInputPort
from throw_a_strike.application import (ClockPort, InputEventKind, InvalidPortValueError, PortCapabilities,
    ThrowControlCoordinator, ThrowControlPresentation, ThrowControlStyleSelectionSnapshot,
    ThrowControlStyleSelector, build_throw_control_presentation, build_throw_control_step_presentation)
from throw_a_strike.domain import (BowlingRoundMachine, BowlingThrowNumber, BowlingThrowResult,
    BowlingThrowResultKind, PlayerColor, ThrowControlPhase, ThrowSetup,
    emulator_dart_indices_for_player, is_emulator_dart_for_player, player_color_for_number)
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.rendering import (EMULATOR_RGB888_BYTE_LENGTH,
    render_dart_accepted_rgb888, render_round_complete_rgb888, render_round_throw_rgb888,
    render_style_selection_rgb888, render_throw_control_rgb888, render_wrong_color_rgb888)

class EmulatorControlTestPhase(str, Enum):
    SELECT_STYLE="select_style"
    ATTEMPT="attempt"
    RECOVERY_HOLD="recovery_hold"
    FOUL_HOLD="foul_hold"
    ACCEPTED_HOLD="accepted_hold"
    WRONG_COLOR_HOLD="wrong_color_hold"
    ROUND_COMPLETE="round_complete"
    TERMINAL="terminal"

FOUL_HOLD_SECONDS = 1.5
ACCEPTED_HOLD_SECONDS = 1.5
WRONG_COLOR_HOLD_SECONDS = 1.0

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
        elif self.phase is EmulatorControlTestPhase.WRONG_COLOR_HOLD:
            valid = self.selection.confirmed and self.presentation is not None and not self.presentation.terminal
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
        elif self.phase is EmulatorControlTestPhase.ROUND_COMPLETE:
            valid = self.selection.confirmed and self.presentation is not None and self.presentation.terminal
        elif self.phase is EmulatorControlTestPhase.TERMINAL:
            valid = (self.selection.confirmed and self.presentation is not None
                     and self.presentation.terminal
                     and self.presentation.phase is ThrowControlPhase.COMPLETE)
        else:
            valid = False
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

class _PlayerColorInputPort:
    """Forward controls and the first dart belonging to the active player."""
    def __init__(self, source, active_player_number):
        self.source=source
        # Validate immediately through the pure policy.
        player_color_for_number(active_player_number)
        self.active_player_number=active_player_number
        self.wrong_event=None
    @property
    def capabilities(self): return self.source.capabilities
    def poll(self):
        events=self.source.poll(); self.wrong_event=None
        chosen=None
        for event in events:
            if event.kind is InputEventKind.DART_HIT:
                if is_emulator_dart_for_player(self.active_player_number,event.dart_index):
                    if chosen is None: chosen=event
                elif self.wrong_event is None: self.wrong_event=event
        # A legal dart wins the batch. Controls retain their source order, and
        # the chosen dart retains its position relative to those controls.
        if chosen is not None:
            self.wrong_event=None
            return tuple(event for event in events
                         if event.kind is not InputEventKind.DART_HIT or event is chosen)
        return tuple(event for event in events if event.kind is not InputEventKind.DART_HIT)

class EmulatorControlTestRuntime:
    def __init__(self, facade: DartsnutSdkFacade, clock: ClockPort, started_at: float):
        if type(facade) is not DartsnutSdkFacade: raise InvalidPortValueError("facade must be exact DartsnutSdkFacade")
        if clock is None or isinstance(clock,type) or not isinstance(clock,ClockPort): raise InvalidPortValueError("clock must satisfy ClockPort")
        capabilities=clock.capabilities
        if type(capabilities) is not PortCapabilities: raise InvalidPortValueError("clock capabilities must be exact PortCapabilities")
        start=_nonnegative(started_at,"started_at")
        self._facade=facade; self._clock=clock; self._raw_input=DartsnutEmulatorInputPort(facade,clock)
        self._active_player_number=1
        self._input=_PlayerColorInputPort(self._raw_input,self._active_player_number)
        self._selector=ThrowControlStyleSelector(start); self._coordinator=None
        self._round=BowlingRoundMachine(); self._wrong_timestamp=None
        self._phase=EmulatorControlTestPhase.SELECT_STYLE; self._cached=None; self._presentation=None
        self._foul_timestamp=None
        self._accepted_timestamp=None; self._accepted_snapshot=None; self._accepted_setup=None
        self._recovery_dart_index=None
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
    @property
    def round_snapshot(self): return self._round.snapshot
    @property
    def active_player_number(self): return self._active_player_number
    @property
    def active_player_color(self): return player_color_for_number(self.active_player_number)
    @property
    def accepted_player_dart_indices(self): return emulator_dart_indices_for_player(self.active_player_number)
    def _begin_attempt(self, style, started_at):
        self._coordinator=ThrowControlCoordinator(style,self._input,self._clock,started_at)
        self._foul_timestamp=None
        self._accepted_timestamp=None; self._accepted_snapshot=None; self._accepted_setup=None
        self._presentation=build_throw_control_presentation(self._coordinator.snapshot)
        self._cached=render_round_throw_rgb888(self._presentation,int(self._round.snapshot.throw_number),
                                                self.active_player_number,self.active_player_color)
        self._phase=EmulatorControlTestPhase.ATTEMPT
        accepted=self._facade.submit_framebuffer(self._cached)
        return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
    def step(self):
        if self._phase in (EmulatorControlTestPhase.ROUND_COMPLETE,EmulatorControlTestPhase.TERMINAL):
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
        if self._phase is EmulatorControlTestPhase.RECOVERY_HOLD:
            active=self._raw_input.observe_active_darts()
            if any(dart.dart_index == self._recovery_dart_index for dart in active):
                accepted=self._facade.submit_framebuffer(self._cached)
                return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
            now=self._clock.monotonic_seconds()
            snapshot=self._coordinator.rearm(now)
            self._recovery_dart_index=None
            self._presentation=build_throw_control_presentation(snapshot)
            self._cached=render_round_throw_rgb888(
                self._presentation,int(self._round.snapshot.throw_number),
                self.active_player_number,self.active_player_color)
            self._phase=EmulatorControlTestPhase.ATTEMPT
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
        if self._phase is EmulatorControlTestPhase.WRONG_COLOR_HOLD:
            now=self._clock.monotonic_seconds()
            if now >= self._wrong_timestamp + WRONG_COLOR_HOLD_SECONDS:
                self._phase=EmulatorControlTestPhase.ATTEMPT
                self._cached=render_round_throw_rgb888(self._presentation,int(self._round.snapshot.throw_number),self.active_player_number,self.active_player_color)
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
        if self._phase is EmulatorControlTestPhase.FOUL_HOLD:
            now=self._clock.monotonic_seconds()
            if now >= self._foul_timestamp + FOUL_HOLD_SECONDS:
                if self._round.snapshot.complete:
                    self._phase=EmulatorControlTestPhase.ROUND_COMPLETE
                    self._cached=render_round_complete_rgb888(self._presentation)
                    accepted=self._facade.submit_framebuffer(self._cached)
                    return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
                return self._begin_attempt(self._selector.snapshot.selected_style,now)
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,
                                           self._accepted_setup)
        if self._phase is EmulatorControlTestPhase.ACCEPTED_HOLD:
            now=self._clock.monotonic_seconds()
            if now >= self._accepted_timestamp + ACCEPTED_HOLD_SECONDS:
                if self._round.snapshot.complete:
                    self._phase=EmulatorControlTestPhase.ROUND_COMPLETE
                    self._cached=render_round_complete_rgb888(self._presentation)
                    accepted=self._facade.submit_framebuffer(self._cached)
                    return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
                return self._begin_attempt(self._selector.snapshot.selected_style,now)
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted,
                                           self._accepted_setup)
        if self._phase is EmulatorControlTestPhase.SELECT_STYLE:
            events=self._raw_input.poll()
            now=events[0].timestamp if events else self._clock.monotonic_seconds()
            selection=self._selector.apply(events,now)
            if not selection.confirmed:
                frame=render_style_selection_rgb888(selection)
                return EmulatorControlTestStep(self._phase,selection,None,frame,self._facade.submit_framebuffer(frame))
            return self._begin_attempt(selection.selected_style,selection.confirmed_at)
        result=self._coordinator.step()
        self._presentation=build_throw_control_step_presentation(result)
        # The coordinator's established input-before-tick ordering decides the
        # deadline. A terminal tick (notably FOUL at/after 30 seconds) always
        # takes precedence over temporary wrong-dart feedback.
        if self._input.wrong_event is not None and not self._presentation.terminal:
            self._wrong_timestamp=self._input.wrong_event.timestamp
            self._cached=render_wrong_color_rgb888(self._presentation,int(self._round.snapshot.throw_number),
                                                   self.active_player_number,self.active_player_color)
            self._phase=EmulatorControlTestPhase.WRONG_COLOR_HOLD
            accepted=self._facade.submit_framebuffer(self._cached)
            return EmulatorControlTestStep(self._phase,self._selector.snapshot,self._presentation,self._cached,accepted)
        blink=True if result.tick_timestamp is None else int(result.tick_timestamp*2)%2==0
        self._cached=render_round_throw_rgb888(self._presentation,int(self._round.snapshot.throw_number),
                                                self.active_player_number,self.active_player_color,blink)
        if self._presentation.phase is ThrowControlPhase.EARLY_DART_RECOVERY:
            dart_commands=tuple(command for command in result.commands
                                if command.dart_index is not None)
            if not dart_commands:
                raise InvalidPortValueError("early recovery requires an offending dart")
            self._recovery_dart_index=dart_commands[-1].dart_index
            self._phase=EmulatorControlTestPhase.RECOVERY_HOLD
        elif self._presentation.phase is ThrowControlPhase.FOUL:
            rack=self._round.snapshot.standing_pins
            self._round.record_throw(BowlingThrowResult(BowlingThrowResultKind.FOUL,rack,(),rack,None,None,None))
            self._foul_timestamp=result.tick_timestamp
            self._phase=EmulatorControlTestPhase.FOUL_HOLD
        elif self._presentation.terminal:
            self._accepted_snapshot=result.snapshot
            self._accepted_setup=result.snapshot.outcome.setup
            setup=self._accepted_setup
            rack=self._round.snapshot.standing_pins
            self._round.record_throw(BowlingThrowResult(BowlingThrowResultKind.MISS,rack,(),rack,
                                                        setup.dart_index,setup.aim_x,setup.aim_y))
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
