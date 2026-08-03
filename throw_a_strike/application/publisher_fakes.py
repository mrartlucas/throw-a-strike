"""Deterministic in-memory presentation-port fakes."""

from __future__ import annotations

from .ports import DisplayCapabilities, PortUnavailableError
from .presentation import MainDisplayViewModel, SecondaryScoreboardViewModel
from .publisher import InvalidPresentationPublisherValueError


def _exact(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise InvalidPresentationPublisherValueError(
            f"{name} must be an exact {expected.__name__}"
        )


class FakeMainPresentationPort:
    def __init__(self, capabilities: DisplayCapabilities) -> None:
        _exact(capabilities, DisplayCapabilities, "capabilities")
        self._capabilities = capabilities
        self._presented: list[MainDisplayViewModel] = []

    @property
    def capabilities(self) -> DisplayCapabilities:
        return self._capabilities

    @property
    def presented(self) -> tuple[MainDisplayViewModel, ...]:
        return tuple(self._presented)

    def present(self, model: MainDisplayViewModel) -> None:
        _exact(model, MainDisplayViewModel, "model")
        if not self._capabilities.available:
            raise PortUnavailableError("main presentation port is unavailable")
        self._presented.append(model)


class FakeSecondaryPresentationPort:
    def __init__(self, capabilities: DisplayCapabilities) -> None:
        _exact(capabilities, DisplayCapabilities, "capabilities")
        self._capabilities = capabilities
        self._presented: list[SecondaryScoreboardViewModel] = []

    @property
    def capabilities(self) -> DisplayCapabilities:
        return self._capabilities

    @property
    def presented(self) -> tuple[SecondaryScoreboardViewModel, ...]:
        return tuple(self._presented)

    def present(self, model: SecondaryScoreboardViewModel) -> None:
        _exact(model, SecondaryScoreboardViewModel, "model")
        if not self._capabilities.available:
            raise PortUnavailableError("secondary presentation port is unavailable")
        self._presented.append(model)
