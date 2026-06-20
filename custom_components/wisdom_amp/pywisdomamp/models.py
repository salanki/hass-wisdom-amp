"""Data models for the Wisdom SA-3 amplifier client.

Plain dataclasses. The device speaks JSON over a WebSocket, but the integration
only needs a small typed projection of the full ``cfg`` document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def model_from_fw(app_fw: str | None) -> str:
    """Derive a friendly model from ``fwinfo.app_fw``.

    The firmware blob name encodes the model, e.g. ``SA3-SC-RP2040_AIDE...`` →
    ``SA-3``, ``SA2-...`` → ``SA-2``, ``IA8MK2-...`` → ``IA-8 MK2``. Falls back to
    a generic label for unknown firmware names.
    """
    if not app_fw:
        return "DSP amplifier"
    code = app_fw.split("-", 1)[0]  # SA3 / SA2 / IA8MK2 / ...
    m = re.fullmatch(r"([A-Za-z]+)(\d+)(MK\d+)?", code)
    if not m:
        return code or "DSP amplifier"
    base, num, mk = m.group(1), m.group(2), m.group(3)
    return f"{base}-{num}" + (f" {mk}" if mk else "")


# Power states (from the pushed ``pwrstate`` frame).
POWER_ON = "on"
POWER_OFF = "off"
POWER_TRANSITIONING = "transitioning"
POWER_UNKNOWN = "unknown"


def power_from_pwrstate(state: int | None) -> str:
    """Map a ``pwrstate {state:N}`` value to a power string."""
    return {0: POWER_OFF, 1: POWER_ON, 2: POWER_TRANSITIONING}.get(
        state, POWER_UNKNOWN
    )


@dataclass(frozen=True)
class ChannelInfo:
    """Static per-channel metadata, discovered once at setup."""

    index: int
    name: str
    active: bool


@dataclass(frozen=True)
class JackGroup:
    """A set of amplifier output jacks that are muted together.

    Speakers whose driver jack-sets are identical collapse into one group (one
    mute entity). ``key`` is a stable positional identifier for the unique_id.
    """

    key: str
    name: str
    jacks: tuple[int, ...]


@dataclass(frozen=True)
class WisdomInfo:
    """Static device identity + topology, read once at setup."""

    mac: str
    model: str = "DSP amplifier"
    firmware: str | None = None
    platform: str | None = None
    hostname: str | None = None
    dante_name: str | None = None
    channels: tuple[ChannelInfo, ...] = ()
    jack_groups: tuple[JackGroup, ...] = ()

    @property
    def name(self) -> str:
        return self.dante_name or self.hostname or f"Wisdom {self.mac}"


@dataclass
class ChannelState:
    """Dynamic per-channel state, refreshed each poll."""

    index: int
    trim: float | None = None
    delay: float | None = None


@dataclass
class WisdomStatus:
    """Dynamic amp state, refreshed each poll cycle / power push."""

    power: str = POWER_UNKNOWN
    gain: float | None = None
    channels: dict[int, ChannelState] = field(default_factory=dict)
    muted_groups: frozenset[str] = frozenset()

    @property
    def is_on(self) -> bool:
        return self.power == POWER_ON
