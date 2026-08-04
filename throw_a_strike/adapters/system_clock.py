"""System monotonic-clock adapter."""

import math
import time
from numbers import Real

from throw_a_strike.application import InvalidPortValueError, PortCapabilities


class SystemMonotonicClockPort:
    """Expose only Python's process monotonic clock through ``ClockPort``."""

    @property
    def capabilities(self) -> PortCapabilities:
        return PortCapabilities(True)

    def monotonic_seconds(self) -> float:
        value = time.monotonic()
        if isinstance(value, bool) or not isinstance(value, Real):
            raise InvalidPortValueError("time.monotonic must return a finite nonnegative real number")
        try:
            result = float(value)
        except (ValueError, OverflowError):
            raise InvalidPortValueError("time.monotonic must return a finite nonnegative real number") from None
        if not math.isfinite(result) or result < 0:
            raise InvalidPortValueError("time.monotonic must return a finite nonnegative real number")
        return result
