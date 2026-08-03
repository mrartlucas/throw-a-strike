"""Pure publication of already-built presentation models.

Publication across two ports is deliberately sequential, not transactional: a
secondary failure cannot roll back a completed main publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .ports import DisplayCapabilities, PortUnavailableError
from .presentation import (
    MainDisplayViewModel,
    PresentationBundle,
    ScoreboardPlacement,
    SecondaryScoreboardViewModel,
)


class InvalidPresentationPublisherValueError(ValueError):
    """Raised when a publisher value violates the publication contract."""


class PublicationTarget(str, Enum):
    MAIN = "main"
    SECONDARY = "secondary"


@dataclass(frozen=True)
class PublicationReceipt:
    scoreboard_placement: ScoreboardPlacement
    main_published: bool
    secondary_published: bool

    def __post_init__(self) -> None:
        if type(self.scoreboard_placement) is not ScoreboardPlacement:
            raise InvalidPresentationPublisherValueError(
                "scoreboard_placement must be an exact ScoreboardPlacement"
            )
        if type(self.main_published) is not bool or type(self.secondary_published) is not bool:
            raise InvalidPresentationPublisherValueError("publication flags must be bool values")
        if not self.main_published:
            raise InvalidPresentationPublisherValueError("a successful receipt requires main publication")
        expected_secondary = self.scoreboard_placement is ScoreboardPlacement.SECONDARY
        if self.secondary_published is not expected_secondary:
            raise InvalidPresentationPublisherValueError(
                "secondary publication must match scoreboard placement"
            )


@runtime_checkable
class MainPresentationPort(Protocol):
    @property
    def capabilities(self) -> DisplayCapabilities: ...

    def present(self, model: MainDisplayViewModel) -> None: ...


@runtime_checkable
class SecondaryPresentationPort(Protocol):
    @property
    def capabilities(self) -> DisplayCapabilities: ...

    def present(self, model: SecondaryScoreboardViewModel) -> None: ...


class PresentationPublishError(RuntimeError):
    """Reports a port operation failure and the publication progress made."""

    def __init__(
        self,
        target: PublicationTarget,
        main_published: bool,
        secondary_published: bool,
        cause: Exception,
    ) -> None:
        if type(target) is not PublicationTarget:
            raise InvalidPresentationPublisherValueError("target must be an exact PublicationTarget")
        if type(main_published) is not bool or type(secondary_published) is not bool:
            raise InvalidPresentationPublisherValueError("publication flags must be bool values")
        if not isinstance(cause, Exception):
            raise InvalidPresentationPublisherValueError("cause must be an Exception")
        valid = (
            target is PublicationTarget.MAIN and not main_published and not secondary_published
        ) or (
            target is PublicationTarget.SECONDARY and main_published and not secondary_published
        )
        if not valid:
            raise InvalidPresentationPublisherValueError("publication progress conflicts with target")
        super().__init__(f"presentation publication failed for {target.value}: {cause}")
        self._target = target
        self._main_published = main_published
        self._secondary_published = secondary_published
        self._cause = cause

    @property
    def target(self) -> PublicationTarget:
        return self._target

    @property
    def main_published(self) -> bool:
        return self._main_published

    @property
    def secondary_published(self) -> bool:
        return self._secondary_published

    @property
    def cause(self) -> Exception:
        return self._cause


def _capabilities(port: object, name: str) -> DisplayCapabilities:
    try:
        value = port.capabilities  # type: ignore[attr-defined]
    except Exception as error:
        raise InvalidPresentationPublisherValueError(
            f"{name} capability could not be read"
        ) from error
    if type(value) is not DisplayCapabilities:
        raise InvalidPresentationPublisherValueError(
            f"{name} capability must be an exact DisplayCapabilities"
        )
    return value


class PresentationPublisher:
    """Publishes a supplied bundle once, main first and secondary second."""

    def __init__(
        self,
        main_port: MainPresentationPort,
        secondary_port: SecondaryPresentationPort | None = None,
    ) -> None:
        if not isinstance(main_port, MainPresentationPort):
            raise InvalidPresentationPublisherValueError("main_port must satisfy MainPresentationPort")
        if secondary_port is not None and not isinstance(secondary_port, SecondaryPresentationPort):
            raise InvalidPresentationPublisherValueError(
                "secondary_port must satisfy SecondaryPresentationPort"
            )
        _capabilities(main_port, "main_port")
        if secondary_port is not None:
            _capabilities(secondary_port, "secondary_port")
        self._main_port = main_port
        self._secondary_port = secondary_port

    def publish(self, bundle: PresentationBundle) -> PublicationReceipt:
        if type(bundle) is not PresentationBundle:
            raise InvalidPresentationPublisherValueError(
                "bundle must be an exact PresentationBundle"
            )

        main_capabilities = _capabilities(self._main_port, "main_port")
        if not main_capabilities.available:
            raise PortUnavailableError("main presentation port is unavailable")

        secondary_port = self._secondary_port
        if bundle.secondary is not None:
            if secondary_port is None:
                raise InvalidPresentationPublisherValueError(
                    "a secondary presentation port is required"
                )
            secondary_capabilities = _capabilities(secondary_port, "secondary_port")
            if not secondary_capabilities.available:
                raise PortUnavailableError("secondary presentation port is unavailable")

        try:
            self._main_port.present(bundle.main)
        except Exception as error:
            raise PresentationPublishError(
                PublicationTarget.MAIN, False, False, error
            ) from error

        if bundle.secondary is not None:
            try:
                secondary_port.present(bundle.secondary)  # type: ignore[union-attr]
            except Exception as error:
                raise PresentationPublishError(
                    PublicationTarget.SECONDARY, True, False, error
                ) from error
            return PublicationReceipt(ScoreboardPlacement.SECONDARY, True, True)

        return PublicationReceipt(bundle.scoreboard_placement, True, False)
