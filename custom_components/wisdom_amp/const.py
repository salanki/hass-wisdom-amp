"""Constants for the Wisdom SA-3 amplifier integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "wisdom_amp"

DEFAULT_PORT = 81
DEFAULT_SCAN_INTERVAL = timedelta(seconds=45)

# System (master) gain slider — Wisdom default is -10 dB; allow up to +6 dB boost.
GAIN_MIN = -60.0
GAIN_MAX = 6.0
GAIN_STEP = 0.5

# Per-channel trim (dB) and delay (ms) ranges.
TRIM_MIN = -12.0
TRIM_MAX = 12.0
TRIM_STEP = 0.5

# Wisdom firmware caps channel delay at 35 ms.
DELAY_MIN = 0.0
DELAY_MAX = 35.0
DELAY_STEP = 0.1
