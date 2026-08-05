# Emulator control test

## Purpose and scope

Phase 0S is a deterministic diagnostic harness for one Blue two-throw bowling round. It selects Quick or Advanced controls, preserves the standing ten-pin rack between throws, and submits only the observed 128×128 packed RGB888 main framebuffer. The 64×32 second screen remains unused because no verified submission API exists.

The color grouping is confirmed **Dartsnut Agent emulator evidence only** and is not a physical-board parity claim: Blue is displayed 1/5/9 (raw 0/4/8), Red 2/6/10 (raw 1/5/9), Green 3/7/11 (raw 2/6/10), and Yellow 4/8/12 (raw 3/7/11).

## Round procedure

1. Choose Quick or Advanced and confirm with A.
2. Verify **THROW 1**, **P1 BLUE**, and the existing control prompts.
3. Place any fresh Blue dart (raw 0, 4, or 8) and verify **DART ACCEPTED** with unchanged raw index/X/Y.
4. After exactly 1.5 seconds verify **THROW 2** and **P1 BLUE**. Quick does not require retrieval: either remaining Blue dart can be placed. Advanced returns to SET CURVE and may reuse the same dart after removal and a fresh placement.
5. Place any fresh Blue dart and, after its accepted hold, verify **ROUND COMPLETE**. Physical dart identity never selects Throw 1 or Throw 2; round state does, and the round still has at most two throws.

An unchanged active coordinate is not fresh. Startup active darts remain a non-scoring baseline. After a Throw 1 FOUL, no physical dart was consumed, so any fresh Blue raw 0, 4, or 8 may complete Throw 2.

A Red, Green, or Yellow event displays **WRONG COLOR** and **USE BLUE DART** for exactly 1.0 second. It creates no result, does not consume or change the current throw, does not reset blocking state, and returns to that throw. If a batch also contains a Blue event, the first Blue event in source order wins and is forwarded unchanged; additional darts are ignored while controls retain deterministic order.

## Timing and FOUL

THROW NOW appears at exactly 20 seconds and FOUL occurs at exactly 30 seconds. Time advances before commands at an equal timestamp: a Blue dart strictly before the deadline is legal, but any dart at or after 30 seconds loses to FOUL. Terminal FOUL always suppresses wrong-color feedback, is recorded once, launches no ball, preserves the rack, and consumes exactly one throw. Accepted and FOUL holds remain 1.5 seconds; the wrong-color hold is 1.0 second. Advanced setup time remains excluded from the throw timer. The runtime makes zero automatic `reset_blocking_state` calls.

## Result vocabulary

* **GUTTER** — the ball enters a side trench, touches no pins, and consumes the throw with zero pinfall.
* **MISS** — the ball remains on the playable lane or pin deck, touches no currently standing pin, and consumes the throw with zero pinfall.
* **FIELD GOAL** — a special MISS in which a separated or split leave remains untouched as the ball passes cleanly between its standing pins.
* **FOUL** — the 30-second deadline expires without a legal dart; no ball launches and the unchanged rack advances.
* **PIN HIT** — a legal ball contacts a standing pin and one or more pins may fall; later physics will supply exact pinfall.

Until physics exists, every accepted active-player dart is recorded as a temporary diagnostic **MISS**, preserving its exact raw index/X/Y and the full rack. This placeholder is not a claim about the future ball path. Coordinates do not generate GUTTER or FIELD GOAL in this phase, and a known named zero event should not be replaced by generic “0 PINS” gameplay text (FOUL retains that secondary diagnostic here).

**CHERRY PICK**, also called **LILY DIP**, means hitting only the front pin of a multi-pin spare leave while the others remain standing. **BLOWOUT** means all remaining pins fall except one, commonly the 7 or 10. These are documented future callouts only: the runtime does not detect or emit them and they are not scoring rules.

## Deliberate exclusions

The display keeps the static pin deck, curve, power, and style. There is no trajectory or ball animation, collision, pinfall calculation or animation, scoring or bonuses, strike/spare logic, frame progression, multiplayer rotation, coordinate transformation, secondary-display API, or physical-board claim.

Early Advanced darts still enter restart-only TOO SOON / REMOVE DART recovery. No verified removal signal exists, so recovery and ROUND COMPLETE republish cached artwork without polling input. Run locally with `python main.py`; validate with `python -m unittest discover -s tests -v`.

## Phase 0S.1 stale-safe emulator input

**Status: IMPLEMENTED - STALE-SAFE EMULATOR INPUT RETEST READY**

The SDK's `get_dart_hits` feed is transition/block based. For this emulator diagnostic only, the input adapter also observes `get_active_darts`: the initial active set is a non-scoring baseline, and a later absent-to-active transition or coordinate change is treated as a fresh emulator placement. Normal hit evidence wins and is deduplicated when both feeds describe the same dart. Thus a stale raw Dart 0 at launch is ignored, while moving that blocked dart after confirmation can complete Throw 1 with its updated coordinates. Throw 1 FOUL advances after 1.5 seconds to Throw 2, where any fresh Blue raw 0, 4, or 8 may complete the round.

The physical-board `DartsnutInputPort` remains event based and unchanged. No automatic `reset_blocking_state` call is used. Active-dart observation is an emulator compatibility policy, not a physical-board behavior claim. No physics, scoring, multiplayer rotation, coordinate transform, or secondary-display API is added.

## Phase 0S.2 player-color dart policy

**Status: IMPLEMENTED - PLAYER-COLOR DART RETEST READY**

Fixed DART 1 then DART 5 enforcement has been removed. Bowling throw number comes exclusively from round state; all three active-player-color darts are legal on either throw when fresh. Quick may leave Throw 1's dart in place and use either remaining same-color dart. Advanced may remove and freshly replace the same dart. Wrong player colors do not consume the throw. No physics, scoring, multiplayer rotation, coordinate transform, secondary-display API, or physical-board assumption was added.

## Phase 0S.3 Advanced manual setup

Advanced Play now requires a distinct A-button event to lock Curve and another
distinct A-button event to stop Power. Curve selection has no setup timeout, and
Power never locks automatically. Power starts at 40 and follows the deterministic
0.200-second sequence `40, 50, 60, 70, 80, 90, 100, 90, 80, 70, 60, 50`, repeating
every 2.400 seconds. The value at the exact input-event timestamp is locked; only
entry into THROW READY starts the fresh 30-second throw timer.

In the emulator diagnostic, an early active-player dart is tracked by its exact
raw index. TOO SOON / REMOVE DART remains cached while that dart is active. Once
it is removed, active-dart observation synchronizes the emulator baseline and an
explicit semantic rearm returns to the interrupted setup phase; Power restarts
at 40. Replacing that same dart is therefore fresh input. Pending dart-hit and button batches accumulated behind the recovery screen are discarded at removal before rearming, so setup resumes only from fresh input. This emulator-only
observation does **not** establish physical-board removal behavior.

This phase adds no trajectory, physics, pinfall, scoring integration, multiplayer
rotation, coordinate transform, secondary-display, or audio behavior.

## Phase 0T deterministic ball trajectory

**Status: IMPLEMENTED - BALL TRAJECTORY RETEST READY**

A ball appears only after a legal active-player dart completes throw setup. The emulator maps the visual target with the display-local clamp x=12..115 and y=4..84; this is not physical-board orientation or calibration, and `ThrowSetup` and diagnostic results retain the original raw coordinates. Curve selects a deterministic quadratic Bézier bend, while Power selects the exact duration (40–100 percent: 1.20, 1.10, 1.00, 0.90, 0.80, 0.70, and 0.60 seconds).

Animation samples elapsed monotonic-clock time rather than frame count. BALL ROLL consumes no gameplay input and records the temporary MISS only when the ball arrives. The standing pin deck remains unchanged. This phase adds no collision, pinfall, scoring integration, multiplayer rotation, audio, physical calibration, or secondary-display behavior.

## IMPLEMENTED - PINFALL RETEST READY

Legal emulator darts build one deterministic ball trajectory, resolve one immutable pinfall result against the currently standing rack, and roll for the existing power duration. Hits stop visually at `contact_progress`; misses and gutters roll to progress 1. No gameplay input, queued dart, queued button, or reset behavior is consumed during BALL_ROLL or PINFALL.

Pin collision is swept over the full visible path: the quadratic Bézier is split into exactly 256 segments and each segment is intersected against standing pin circles using the exact 6-pixel contact radius. Ties choose earliest progress, then lowest pin number.

PINFALL lasts 0.750 seconds. Waves start every 0.120 seconds, individual pins animate for 0.300 seconds, and the deterministic energy graph uses `power_percent // 10` with CENTER 3/3, LEFT 2/4, and RIGHT 4/2 child costs. Throw 2 uses exactly the survivors from Throw 1. A first-throw rack clear enters ROUND_COMPLETE after accepted hold; this is diagnostic completion only, with no scoring, multiplayer, audio, calibration, or secondary-display expansion.

## Phase 0V Preservation Note

The two-throw diagnostic emulator control test remains available for regression coverage after the normal emulator entry point moved to the single-player regulation 10-Pin runtime. It is still importable as `run_emulator_control_test` and continues to exercise the Phase 0U ball-roll and pinfall diagnostic flow.
