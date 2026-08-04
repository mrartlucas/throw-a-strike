# Emulator control test

## Purpose and scope

Phase 0S is a deterministic diagnostic harness for one Blue two-throw bowling round. It selects Quick or Advanced controls, preserves the standing ten-pin rack between throws, and submits only the observed 128×128 packed RGB888 main framebuffer. The 64×32 second screen remains unused because no verified submission API exists.

This mapping is confirmed **Dartsnut Agent emulator evidence only** and is not a physical-board parity claim:

| Blue round slot | Displayed dart | Raw SDK index |
| --- | ---: | ---: |
| Throw 1 | 1 | 0 |
| Throw 2 | 5 | 4 |
| Reserved third dart | 9 | 8 |

Red uses displayed 2/6/10 (raw 1/5/9), Green 3/7/11 (raw 2/6/10), and Yellow 4/8/12 (raw 3/7/11). Only Blue raw indices 0 then 4 are consumed by this runtime.

## Round procedure

1. Remove every dart, launch the app, choose Quick or Advanced, and confirm with A.
2. Verify **THROW 1** and **DART 1**. Confirmation alone is not a dart.
3. Emit raw dart 0 and verify **DART ACCEPTED** with unchanged raw index/X/Y.
4. After exactly 1.5 seconds verify **THROW 2** and **DART 5**. Advanced starts again at SET CURVE and retains the selected Advanced style.
5. Emit raw dart 4 and verify DART ACCEPTED.
6. After exactly 1.5 seconds verify **ROUND COMPLETE**. It holds without polling until restart.

During every active throw, a compact THROW/DART header is shown without replacing the control prompts below it. THROW READY and THROW NOW, SET CURVE and SET POWER, TOO SOON and REMOVE DART, or FOUL and 0 PINS therefore remain visible alongside curve, power, feedback, and style diagnostics.

A nonmatching raw index displays **WRONG DART** and the expected displayed number for exactly 1.0 second. It creates no result, does not consume the throw, does not reset blocking state, and returns to the same throw. Raw 8 is reserved and cannot complete Throw 2.

Advanced SET CURVE and SET POWER occur separately for each throw. Setup time does not count toward the 30-second throw timer, which begins only at THROW READY. The selected Advanced style remains active throughout the round.

## Timing and FOUL

THROW NOW appears at exactly 20 seconds and FOUL occurs at exactly 30 seconds. FOUL means that no legal dart occurred before the deadline: no bowling ball launches, zero pins fall, and the current throw is consumed. The FOUL/0 PINS diagnostic holds exactly 1.5 seconds. Throw 1 FOUL advances to a fresh Throw 2 timer; Throw 2 FOUL completes the round. The runtime makes zero automatic `reset_blocking_state` calls.

A wrong dart strictly before the deadline may show the one-second WRONG DART hold. At or after exactly 30 seconds, the coordinator's terminal FOUL takes precedence; the wrong event never produces a terminal WRONG DART screen and the round records that FOUL only once.

## Result vocabulary

* **GUTTER** — the ball enters a side trench, touches no pins, and consumes the throw with zero pinfall.
* **MISS** — the ball remains on the playable lane or pin deck, touches no currently standing pin, and consumes the throw with zero pinfall.
* **FIELD GOAL** — a special MISS in which a separated or split leave remains untouched as the ball passes cleanly between its standing pins.
* **FOUL** — the 30-second deadline expires without a legal dart; no ball launches and the unchanged rack advances.
* **PIN HIT** — a legal ball contacts a standing pin and one or more pins may fall; later physics will supply exact pinfall.

Until physics exists, every legal expected dart is recorded as a temporary diagnostic **MISS**, preserving its exact raw index/X/Y and the full rack. This placeholder is not a claim about the future ball path. Coordinates do not generate GUTTER or FIELD GOAL in this phase, and a known named zero event should not be replaced by generic “0 PINS” gameplay text (FOUL retains that secondary diagnostic here).

**CHERRY PICK**, also called **LILY DIP**, means hitting only the front pin of a multi-pin spare leave while the others remain standing. **BLOWOUT** means all remaining pins fall except one, commonly the 7 or 10. These are documented future callouts only: the runtime does not detect or emit them and they are not scoring rules.

## Deliberate exclusions

The display keeps the static pin deck, curve, power, and style. There is no trajectory or ball animation, collision, pinfall calculation or animation, scoring or bonuses, strike/spare logic, frame progression, multiplayer rotation, coordinate transformation, secondary-display API, or physical-board claim.

Early Advanced darts still enter restart-only TOO SOON / REMOVE DART recovery. No verified removal signal exists, so recovery and ROUND COMPLETE republish cached artwork without polling input. Run locally with `python main.py`; validate with `python -m unittest discover -s tests -v`.
