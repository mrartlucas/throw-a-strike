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
