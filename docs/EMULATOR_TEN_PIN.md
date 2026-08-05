# Single-Player Regulation 10-Pin Emulator

Status: IMPLEMENTED - SINGLE-PLAYER 10-PIN RETEST READY

The normal emulator entry point now runs a one-player Blue-only regulation 10-Pin game. After Quick or Advanced control-style confirmation, the runtime configures a `GameSession` with `Mode.TEN_PIN`, `Theme.REGULAR`, one player, ten frames, seed `0`, and the selected control style.

## Scoring source of truth

The emulator does not implement a replacement scoring engine. Every completed throw submits only the knocked-down pin count to `GameSession.submit_throw()`, which delegates scoring, marks, frame advancement, strikes, spares, bonus resolution, cumulative score, tenth-frame bonus rolls, and game completion to the existing `BowlingGame`/`BowlingMatch` engine.

## Game flow

A legal Blue dart builds one immutable ball trajectory and resolves one immutable swept pinfall result. Ball roll, pinfall, result hold, acknowledgements, frame transitions, and game over follow the session state. Misses, gutters, and fouls submit zero pins. Result and foul holds last 1.5 seconds.

## Exact rack tracking

The scoring engine owns the count of available pins. The emulator additionally retains the exact standing pin tuple for rendering and collision. Strike and spare progression resets to the full rack when the session reports ten available pins; otherwise survivor pins carry into the next roll. This includes tenth-frame bonus rack behavior.

## HUD and game over

The HUD shows frame, roll, confirmed cumulative score, recent frame marks, Curve, Power, and prompts. Result screens show STRIKE, SPARE, pin-count, MISS, GUTTER, or FOUL labels, while retaining raw dart diagnostics. Pending bonuses remain unresolved until the existing scoring engine confirms them.

Game over is terminal and stable. It displays `THROW A STRIKE`, `GAME OVER`, `FINAL <score>`, and all ten frames in two rows, with no ball or standing pins.

## Preserved diagnostic runtime

The existing two-throw emulator control-test runtime remains importable and tested for Phase 0U regression coverage.

## Locked out of scope

This runtime intentionally adds no multiplayer rotation, Red/Green/Yellow active turns, 100-Pin, Remix, Party, Blacklight, audio, secondary display, persistent saves, online behavior, physical-board calibration, or physical `DartsnutInputPort` changes.

## Regulation presentation events

The ten-pin emulator now maintains a pure regulation presentation timeline alongside the existing Screen 1 gameplay framebuffer. The timeline emits `THROW_READY` once for each genuine ready transition, with a fixed 1.5-second logical deadline. The cue is static, expires without drift even when observed late, and is cancelled immediately when play leaves the ready state.

Result events are acknowledged from the existing session result snapshot, including the producing frame and roll. Physical secondary-display hookup is intentionally not implemented in this phase because no verified cabinet Screen 2 API is assumed here; the new RGB888/view-model renderer is the deterministic adapter boundary for future integration.

## Phase 0X secondary-display emulator preview

Phase 0X adds an emulator-only Screen 2 preview path for the existing regulation presentation timeline. The playable Screen 1 ten-pin framebuffer is still submitted through the existing Dartsnut main-frame path; the Screen 2 preview receives a separate memory-backed RGB888 framebuffer rendered from `RegulationPresentationTimeline.view_model(...)` by the existing regulation event renderer.

Run the normal emulator with a visible optional Screen 2 window:

```sh
python main.py --screen2-window
```

Run the developer-only Screen 2 event gallery without touching scoring or session state:

```sh
python main.py --event-gallery --screen2-window
# or
python -m throw_a_strike.runtime.secondary_display_gallery
```

The gallery is an emulator development tool only. It cycles through the real renderer labels for THROW READY, STRIKE, SPARE, SPLIT, SPLIT CONVERTED, FIELD GOAL, GUTTER, MISS, FOUL, TURKEY, and GAME OVER. Headless tests use the same adapter boundary with `MemorySecondaryDisplayPort`, so no desktop window is required in automation.

No physical Screen 2 SDK, physical secondary-display API assumption, physical Dartsnut adapter change, scoring change, pinfall change, timing change, control change, or presentation-event reclassification is introduced.
