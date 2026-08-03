"""Pure command-driven coordination of sessions and presentation publication.

Session commands complete before publication begins.  Publication is therefore
deliberately not a cross-layer transaction: a publication failure neither
rolls back the session nor retries either the command or a presentation port.
The current, already-advanced state can be published explicitly with
``PublishCurrentCommand``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.config import MatchConfig
from ..domain.schedule import PartySchedule, RemixSchedule
from .ports import ApplicationCapabilities, PortUnavailableError
from .presentation import PresentationBundle, build_presentation
from .publisher import (
    InvalidPresentationPublisherValueError,
    PresentationPublishError,
    PresentationPublisher,
    PublicationReceipt,
)
from .session import GameSession, SessionSnapshot


class InvalidApplicationCommandError(TypeError):
    """Raised when an object is not one of the exact supported commands."""


class InvalidApplicationControllerValueError(ValueError):
    """Raised when a controller-layer value violates its exact contract."""


class ApplicationCommandKind(str, Enum):
    CONFIGURE = "configure"
    START = "start"
    SUBMIT_THROW = "submit_throw"
    ACKNOWLEDGE_RESULT = "acknowledge_result"
    CONTINUE_TRANSITION = "continue_transition"
    REPLAY = "replay"
    CANCEL = "cancel"
    PUBLISH_CURRENT = "publish_current"


@dataclass(frozen=True)
class ConfigureCommand:
    config: MatchConfig
    schedule: RemixSchedule | PartySchedule | None = None

    def __post_init__(self) -> None:
        if type(self.config) is not MatchConfig:
            raise InvalidApplicationControllerValueError(
                "config must be an exact MatchConfig"
            )
        if self.schedule is not None and type(self.schedule) not in (
            RemixSchedule,
            PartySchedule,
        ):
            raise InvalidApplicationControllerValueError(
                "schedule must be an exact RemixSchedule, PartySchedule, or None"
            )


@dataclass(frozen=True)
class StartCommand:
    pass


@dataclass(frozen=True)
class SubmitThrowCommand:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise InvalidApplicationControllerValueError(
                "value must be an exact integer"
            )


@dataclass(frozen=True)
class AcknowledgeResultCommand:
    pass


@dataclass(frozen=True)
class ContinueTransitionCommand:
    pass


@dataclass(frozen=True)
class ReplayCommand:
    pass


@dataclass(frozen=True)
class CancelCommand:
    pass


@dataclass(frozen=True)
class PublishCurrentCommand:
    pass


@dataclass(frozen=True)
class ApplicationCommandResult:
    command_kind: ApplicationCommandKind
    snapshot: SessionSnapshot
    presentation: PresentationBundle
    receipt: PublicationReceipt

    def __post_init__(self) -> None:
        expected = (
            (self.command_kind, ApplicationCommandKind, "command_kind"),
            (self.snapshot, SessionSnapshot, "snapshot"),
            (self.presentation, PresentationBundle, "presentation"),
            (self.receipt, PublicationReceipt, "receipt"),
        )
        for value, kind, name in expected:
            if type(value) is not kind:
                raise InvalidApplicationControllerValueError(
                    f"{name} must be an exact {kind.__name__}"
                )


class ApplicationControllerPublishError(RuntimeError):
    """Retains the exact command output and publisher failure progress."""

    def __init__(
        self,
        command_kind: ApplicationCommandKind,
        snapshot: SessionSnapshot,
        presentation: PresentationBundle,
        cause: Exception,
    ) -> None:
        if type(command_kind) is not ApplicationCommandKind:
            raise InvalidApplicationControllerValueError(
                "command_kind must be an exact ApplicationCommandKind"
            )
        if type(snapshot) is not SessionSnapshot:
            raise InvalidApplicationControllerValueError(
                "snapshot must be an exact SessionSnapshot"
            )
        if type(presentation) is not PresentationBundle:
            raise InvalidApplicationControllerValueError(
                "presentation must be an exact PresentationBundle"
            )
        if not isinstance(
            cause,
            (
                InvalidPresentationPublisherValueError,
                PortUnavailableError,
                PresentationPublishError,
            ),
        ):
            raise InvalidApplicationControllerValueError(
                "cause must be a publisher-related exception"
            )
        super().__init__(f"publication failed for {command_kind.value}: {cause}")
        self._command_kind = command_kind
        self._snapshot = snapshot
        self._presentation = presentation
        self._cause = cause

    @property
    def command_kind(self) -> ApplicationCommandKind:
        return self._command_kind

    @property
    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    @property
    def presentation(self) -> PresentationBundle:
        return self._presentation

    @property
    def cause(self) -> Exception:
        return self._cause

    @property
    def main_published(self) -> bool:
        if isinstance(self._cause, PresentationPublishError):
            return self._cause.main_published
        return False

    @property
    def secondary_published(self) -> bool:
        if isinstance(self._cause, PresentationPublishError):
            return self._cause.secondary_published
        return False


class ApplicationController:
    """Own one session and execute one explicit operation per command."""

    def __init__(
        self,
        capabilities: ApplicationCapabilities,
        publisher: PresentationPublisher,
    ) -> None:
        if type(capabilities) is not ApplicationCapabilities:
            raise InvalidApplicationControllerValueError(
                "capabilities must be an exact ApplicationCapabilities"
            )
        if type(publisher) is not PresentationPublisher:
            raise InvalidApplicationControllerValueError(
                "publisher must be an exact PresentationPublisher"
            )
        self._capabilities = capabilities
        self._publisher = publisher
        self._session = GameSession()

    def snapshot(self) -> SessionSnapshot:
        return self._session.snapshot()

    def execute(
        self,
        command: ConfigureCommand
        | StartCommand
        | SubmitThrowCommand
        | AcknowledgeResultCommand
        | ContinueTransitionCommand
        | ReplayCommand
        | CancelCommand
        | PublishCurrentCommand,
    ) -> ApplicationCommandResult:
        command_type = type(command)
        if command_type is ConfigureCommand:
            kind = ApplicationCommandKind.CONFIGURE
            snapshot = self._session.configure(command.config, command.schedule)
        elif command_type is StartCommand:
            kind = ApplicationCommandKind.START
            snapshot = self._session.start()
        elif command_type is SubmitThrowCommand:
            kind = ApplicationCommandKind.SUBMIT_THROW
            snapshot = self._session.submit_throw(command.value)
        elif command_type is AcknowledgeResultCommand:
            kind = ApplicationCommandKind.ACKNOWLEDGE_RESULT
            snapshot = self._session.acknowledge_result()
        elif command_type is ContinueTransitionCommand:
            kind = ApplicationCommandKind.CONTINUE_TRANSITION
            snapshot = self._session.continue_transition()
        elif command_type is ReplayCommand:
            kind = ApplicationCommandKind.REPLAY
            snapshot = self._session.replay()
        elif command_type is CancelCommand:
            kind = ApplicationCommandKind.CANCEL
            snapshot = self._session.cancel()
        elif command_type is PublishCurrentCommand:
            kind = ApplicationCommandKind.PUBLISH_CURRENT
            snapshot = self._session.snapshot()
        else:
            raise InvalidApplicationCommandError(
                "command must be an exact supported application command"
            )

        presentation = build_presentation(snapshot, self._capabilities)
        try:
            receipt = self._publisher.publish(presentation)
        except (
            InvalidPresentationPublisherValueError,
            PortUnavailableError,
            PresentationPublishError,
        ) as error:
            raise ApplicationControllerPublishError(
                kind, snapshot, presentation, error
            ) from error
        return ApplicationCommandResult(kind, snapshot, presentation, receipt)
