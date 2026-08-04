# Emulator control test

## Purpose

Phase 0R is a one-attempt interactive verification harness for **Throw A Way Games presents Throw a Strike**. It exercises the completed Phase 0Q control architecture; it is not a bowling match.

## Current supported emulator behavior

The harness selects Quick or Advanced control style, displays curve and power state, accepts an unchanged dart index/x/y, and holds COMPLETE, early-recovery, or FOUL terminal artwork. It submits one packed, row-major RGB888 main framebuffer per iteration.

## Exact controls

On **CONTROL STYLE**, Left selects **QUICK PLAY**, Right selects **ADVANCED PLAY**, and A confirms. With no confirmation for 15 seconds, Quick Play is confirmed. B, Up, Down, and darts have no selection effect.

## Quick Play procedure

1. Confirm Quick Play and verify **THROW READY**, STR, and 70%.
2. Throw one dart.
3. Verify the prompt disappears and the terminal HUD preserves curve and power.

## Advanced Play procedure

1. Confirm Advanced Play. Use Left/Right at **SET CURVE**, then A to lock.
2. Watch the moving percentage at **SET POWER**, then press A to lock it.
3. Verify **THROW READY**, throw one dart, and verify the terminal HUD preserves the selected curve and power.

## Early-dart recovery procedure

In Advanced Play, throw before THROW READY. Verify **TOO SOON** and **REMOVE DART**. Close and restart the emulator after validating this hold state.

## Warning and FOUL procedure

Reach THROW READY, wait 30 seconds, and verify **THROW NOW** remains visible. At 60 seconds verify **FOUL** and **0 PINS**.

## Expected 128×128 screen

The observed 128×128 emulator main canvas contains a close overhead ten-pin deck at y=0–87 and a compact HUD at y=88–127. The HUD shows the prompt(s), curve arrow and label, percentage, feedback, and Q/A style indicator. No pre-physics bowling ball, scorecard, frame, or player appears.

Packed RGB888 and 128×128 (49,152 bytes) are emulator-test assumptions based on direct visual observation. The SDK does not prove dimensions, orientation, physical RGB ordering, or physical-cabinet parity.

## Known secondary-screen limitation

The emulator visibly has a 64×32 control canvas, but no verified submission API exists. This harness submits only to the main framebuffer and invents no secondary-display operation.

## Recovery-hold restart limitation

No verified dart-removal signal exists and the coordinator intentionally has no rearm operation. Recovery hold therefore republishes cached artwork without polling, reading time, resetting hardware, or consuming future input. Restart the app to repeat the test.

## COMPLETE behavior

An accepted dart produces COMPLETE with the exact raw coordinates retained by the coordinator. COMPLETE has no completion prompt, ball animation, or calculated pin result; the deck and locked HUD remain.

## What is not implemented

There is no trajectory, ball animation, collision, pin result, scoring, frame progression, multiplayer, player/color or dart-index mapping, coordinate transformation, audio, theme switching, automatic reset, or physical-cabinet claim.

## Run/deploy steps

Use the repository's Python environment and run `python main.py`. For local verification run `python -m unittest discover -s tests -v`. Packaging dependencies remain unchanged in this phase.

## Bug-report checklist

Record the selected style, exact control sequence, elapsed time, displayed curve/power/feedback, prompt text, dart index/x/y, whether framebuffer submission was accepted, emulator version, main-canvas appearance, and whether the failure occurred in selection, attempt, recovery hold, or terminal hold. Do not infer cabinet behavior from an emulator report.
