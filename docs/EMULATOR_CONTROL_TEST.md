# Emulator control test

## Purpose

Phase 0R.1 is an interactive verification harness for **Throw A Way Games presents Throw a Strike**. It exercises the completed Phase 0Q control architecture; it is not a bowling match.

## Current supported emulator behavior

The harness selects Quick or Advanced control style, calls the verified `reset_blocking_state` operation before each fresh attempt, displays curve and power state, and accepts an unchanged dart index/x/y. COMPLETE and early recovery remain restart-only holds. FOUL holds for exactly 1.5 seconds and then starts a fresh attempt in the already selected style. It submits one packed, row-major RGB888 main framebuffer per iteration.

## Exact controls

On **CONTROL STYLE**, Left selects **QUICK PLAY**, Right selects **ADVANCED PLAY**, and A confirms. With no confirmation for 15 seconds, Quick Play is confirmed. B, Up, Down, and darts have no selection effect.

## Hardware retest procedure

1. Remove every dart from the board.
2. Launch Throw a Strike.
3. Select Quick Play.
4. Confirm with A.
5. Verify THROW READY, STR, 70%, and GOOD.
6. Throw one physical dart.
7. Verify THROW READY disappears and COMPLETE holds.
8. Record whether the dart registered.
9. Restart after a successful COMPLETE test.
10. For FOUL testing, do not throw.
11. Verify FOUL plus 0 PINS.
12. Verify a fresh Quick attempt begins after 1.5 seconds.

## Advanced Play procedure

1. Confirm Advanced Play. Use Left/Right at **SET CURVE**, then A to lock.
2. Watch the moving percentage at **SET POWER**, then press A to lock it.
3. Verify **THROW READY**, throw one dart, and verify the terminal HUD preserves the selected curve and power.

## Early-dart recovery procedure

In Advanced Play, throw before THROW READY. Verify **TOO SOON** and **REMOVE DART**. Close and restart the emulator after validating this hold state.

## Warning and FOUL procedure

Reach THROW READY, wait 30 seconds, and verify **THROW NOW** remains visible. At 60 seconds verify **FOUL** and **0 PINS**. The cached FOUL frame holds for 1.5 seconds without polling input; the harness then rearms and begins a clean attempt without returning to style selection.

## Expected 128×128 screen

The observed 128×128 emulator main canvas contains a close overhead ten-pin deck at y=0–87 and a compact HUD at y=88–127. The HUD shows the prompt(s), curve arrow and label, percentage, feedback, and Q/A style indicator. No pre-physics bowling ball, scorecard, frame, or player appears.

Packed RGB888 and 128×128 (49,152 bytes) are emulator-test assumptions based on direct visual observation. The SDK does not prove dimensions, orientation, physical RGB ordering, or physical-cabinet parity.

## Known secondary-screen limitation

The emulator visibly has a 64×32 control canvas, but no verified submission API exists. This harness submits only to the main framebuffer and invents no secondary-display operation.

## Hold and retry limitations

No verified dart-removal signal exists and the coordinator intentionally has no rearm operation. Recovery hold therefore republishes cached artwork without polling, reading time, resetting hardware, or consuming future input. Restart the app to repeat the test.

COMPLETE likewise remains held until restart so the accepted raw dart can be confirmed. Only FOUL automatically retries. The blocking-state reset and FOUL retry are based on emulator testing and are retest preparation, not proof of physical-cabinet parity.

## COMPLETE behavior

An accepted dart produces COMPLETE with the exact raw coordinates retained by the coordinator. COMPLETE has no completion prompt, ball animation, or calculated pin result; the deck and locked HUD remain.

## What is not implemented

There is no trajectory, ball animation, collision, pin result, scoring, frame progression, multiplayer, player/color or dart-index mapping, coordinate transformation, audio, theme switching, or physical-cabinet claim. No secondary screen or secondary-display API is used.

## Run/deploy steps

Use the repository's Python environment and run `python main.py`. For local verification run `python -m unittest discover -s tests -v`. Packaging dependencies remain unchanged in this phase.

## Bug-report checklist

Record the selected style, exact control sequence, elapsed time, displayed curve/power/feedback, prompt text, dart index/x/y, whether framebuffer submission was accepted, emulator version, main-canvas appearance, and whether the failure occurred in selection, attempt, recovery hold, or terminal hold. Do not infer cabinet behavior from an emulator report.
