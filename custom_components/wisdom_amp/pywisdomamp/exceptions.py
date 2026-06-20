"""Exceptions for the Wisdom SA-3 amplifier client."""

from __future__ import annotations


class WisdomError(Exception):
    """Base error for all Wisdom amplifier client failures."""


class WisdomConnectionError(WisdomError):
    """Raised when the WebSocket connection cannot be established or is lost."""


class WisdomTimeoutError(WisdomConnectionError):
    """Raised when a request did not get its expected response in time.

    Treated as stream-corrupting: the socket is dropped and reconnected, because
    a late response would otherwise satisfy the wrong future on this ID-less,
    mixed push/response protocol.
    """
