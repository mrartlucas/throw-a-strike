"""Throw a Strike emulator control-test entry point."""

from throw_a_strike.adapters import SystemMonotonicClockPort
from throw_a_strike.platform import DartsnutSdkFacade
from throw_a_strike.runtime import run_emulator_control_test


def main() -> None:
    from pydartsnut import Dartsnut

    facade = DartsnutSdkFacade(Dartsnut())
    clock = SystemMonotonicClockPort()
    started_at = clock.monotonic_seconds()
    run_emulator_control_test(facade, clock, started_at)


if __name__ == "__main__":
    main()
