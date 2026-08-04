"""Adapters connecting platform boundaries to application ports."""

from .dartsnut_input import DartsnutInputPort
from .dartsnut_emulator_input import DartsnutEmulatorInputPort
from .system_clock import SystemMonotonicClockPort

# Preserve the previously locked wildcard surface; the clock remains available
# as the explicitly named ``adapters.SystemMonotonicClockPort`` export.
__all__ = ("DartsnutInputPort", "DartsnutEmulatorInputPort")
