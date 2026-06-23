<p align="center">
  <a href="https://www.wisdomaudio.com/">
    <img src="assets/wisdom-audio-logo.png" alt="Wisdom Audio" width="320">
  </a>
</p>

# Wisdom Amplifier — Home Assistant integration

A local-control Home Assistant integration for **[Wisdom Audio](https://www.wisdomaudio.com/)
DSP amplifiers**. It speaks the amplifiers' WebSocket JSON control protocol
(`ws://<ip>:81`) and lets you set the amp's gain structure and power from HA.

Works with the whole Wisdom **SA / IA** DSP amplifier line — they share the same
firmware/control protocol. Verified against **SA-2**, **SA-3**, and **IA-8 MK2**
units; the exact model is auto-detected per device (from the firmware) and shown
in the HA device info. (Not for passive Wisdom amps with no network control.)

These amps are fed audio over Dante/analog; this integration controls the
**amplifier DSP** — system gain, per-channel trim/delay, mute, and power — not the
upstream playback.

> Sibling project: [hass-blaze-amp](https://github.com/salanki/hass-blaze-amp) for
> Sonance Blaze / Origin amplifiers (different protocol, same design).

## Features / entities (per amp)

| Entity | What it does |
|---|---|
| `number` System gain | Master output gain `cfg.gain` (dB), slider −60…+6 |
| `number` `<channel>` trim | Per active channel `trim` (dB), −60…+10 |
| `number` `<channel>` delay | Per active channel `delay` (ms), 0…35 (firmware cap) |
| `switch` Power | `on`/`off`; live state from the pushed `pwrstate` frame |
| `switch` `<speaker>` mute | Mute a jack-group via `setmutes` (transient — see notes) |
| `sensor` (diagnostic) | Power state, firmware, Dante name; MAC + detected model in device info |

- **Active channels** (those with a configured name) get trim/delay controls;
  unused channels are skipped.
- **Mutes are grouped by output jack.** Speakers that share the same amp jacks
  collapse into one mute switch. Mute state is **write-only** on this protocol —
  it can't be read back — so the mute switches are *assumed-state* (they reflect
  HA's own last command, not the amp). A mute set elsewhere (e.g. the Wisdom web
  UI) won't be reflected, and HA only sends mute changes on an explicit toggle
  (never on reconnect) so it won't undo externally-set mutes. Mutes clear on a
  device reboot.
- **Channel trim/delay writes use the device's indexed form** (`cfgset
  {"channels[N]": …}`, a fresh read-modify-write of the one channel). The
  whole-array form clears the channel list on the device — see
  [API_NOTES.md](API_NOTES.md). A web-UI EQ edit made in the brief read→write
  window could still be lost (the firmware exposes no revision id).

## Installation

### HACS (recommended)
1. HACS → Integrations → ⋮ → *Custom repositories* → add
   `https://github.com/salanki/hass-wisdom-amp` as an *Integration*.
2. Install **Wisdom Amplifier**, restart Home Assistant.

### Manual
Copy `custom_components/wisdom_amp` into `config/custom_components/` and restart.

## Configuration

Settings → Devices & Services → **Add Integration** → *Wisdom Amplifier*.
Enter the amp's **management** IP (control port defaults to 81). One entry per
amp; the MAC is the unique id, and **Reconfigure** updates the IP if it changes.

> ⚠️ Use the management-NIC IP (e.g. `192.168.x.x`), **not** the Dante audio IP.
> The WebSocket control protocol has **no authentication** — anyone on that VLAN
> can control the amp.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [API_NOTES.md](API_NOTES.md) for the
design and the reverse-engineered protocol.

## License

MIT — see [LICENSE](LICENSE). This is an **unofficial**, community integration and
is not affiliated with or endorsed by Wisdom Audio; "Wisdom Audio" and its logo
are trademarks of their respective owner, used here only to identify the supported
hardware and link to the manufacturer.
