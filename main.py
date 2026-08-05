"""Throw a Strike single-player ten-pin emulator entry point."""

from throw_a_strike.adapters import SystemMonotonicClockPort
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.runtime import EmulatorSecondaryDisplayPort, render_gallery, run_emulator_ten_pin, run_visible_gallery


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Throw A Strike emulator runtime")
    parser.add_argument("--event-gallery", action="store_true", help="developer-only Screen 2 regulation event gallery")
    parser.add_argument("--screen2-window", action="store_true", help="show emulator-only secondary display window")
    args = parser.parse_args()
    if args.event_gallery:
        if args.screen2_window:
            run_visible_gallery(EmulatorSecondaryDisplayPort(visible=True))
        else:
            render_gallery()
        return
    from pydartsnut import Dartsnut

    facade = DartsnutSdkFacade(Dartsnut())
    clock = SystemMonotonicClockPort()
    started_at = clock.monotonic_seconds()
    secondary = EmulatorSecondaryDisplayPort(visible=True) if args.screen2_window else None
    run_emulator_ten_pin(facade, clock, started_at, secondary_display=secondary)


if __name__ == "__main__":
    main()
