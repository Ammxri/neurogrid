"""Error types. Every :class:`NeuroGridError` ends a command with exit code 2 (tool error)."""

from __future__ import annotations


class NeuroGridError(Exception):
    """A tool error with a translatable message key and parameters.

    Parameters must not contain personal data; callers pass sanitized values only.
    """

    def __init__(self, message_key: str, **params: object) -> None:
        super().__init__(message_key)
        self.message_key = message_key
        self.params: dict[str, object] = params


class ConfigError(NeuroGridError):
    """Invalid project configuration."""


class RulepackError(NeuroGridError):
    """A rule pack cannot be loaded or does not match the check registry."""


class UnsafePathError(NeuroGridError):
    """A path is outside the allowed area or uses a forbidden form (UNC, device, ADS, '..')."""


class InputError(NeuroGridError):
    """An input file or option is unusable (e.g. a single file of unknown format)."""


class PdfError(NeuroGridError):
    """PDF output is not possible or failed its check: no or another PDF browser, missing system libraries,
    a browser failure or the PDF QA gate (A-26, A-27). Nothing is written.

    ``hint`` is an optional second message (key and parameters), e.g. the command that installs the PDF
    browser; its parameters are NeuroGrid's own values (paths of this installation, package names)."""

    def __init__(
        self, message_key: str, *, hint: tuple[str, dict[str, object]] | None = None, **params: object
    ) -> None:
        super().__init__(message_key, **params)
        self.hint = hint


class NetworkBlockedError(RuntimeError):
    """Raised by the network guard when code tries to reach a non-loopback address."""
