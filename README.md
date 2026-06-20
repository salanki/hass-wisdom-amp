# Wisdom SA-3 Amplifier — Home Assistant integration

A local-control Home Assistant integration for **Wisdom Audio SA-3** DSP
amplifiers. It speaks the SA-3's WebSocket JSON control protocol
(`ws://<ip>:81`) and lets you set the amp's gain structure and power from HA.

These amps are fed audio over Dante; this integration controls the **amplifier
DSP** — system gain, per-channel trim/delay, mute, and power — not the upstream
playback (which lives in Music Assistant / spin2dante).

> Sibling project: [hass-blaze-amp](https://github.com/salanki/hass-blaze-amp) for
> Sonance Blaze / Origin amplifiers (different protocol, same design).

## Features / entities (per amp)

| Entity | What it does |
|---|---|
| `number` System gain | Master output gain `cfg.gain` (dB), slider −60…0 |
| `number` `<channel>` trim | Per active channel `trim` (dB) |
| `number` `<channel>` delay | Per active channel `delay` (ms) |
| `switch` Power | `on`/`off`; live state from the pushed `pwrstate` frame |
| `switch` `<speaker>` mute | Mute a jack-group via `setmutes` (transient — see notes) |
| `sensor` (diagnostic) | Power state, firmware, Dante name; MAC/model in device info |

- **Active channels** (those with a configured name) get trim/delay controls;
  unused channels are skipped.
- **Mutes are grouped by output jack.** Speakers that share the same amp jacks
  collapse into one mute switch. Mutes are *transient* on the device (reset on
  reboot/reconnect); the integration clears its mute state on reconnect to match.
- **Channel trim/delay writes are read-modify-write** of the full `channels`
  array (a fresh `cfgget` immediately before each write), because `cfgset`
  replaces arrays rather than deep-merging. A web-UI EQ edit made in the brief
  read→write window could still be lost (the firmware exposes no revision id).

## Installation

### HACS (recommended)
1. HACS → Integrations → ⋮ → *Custom repositories* → add
   `https://github.com/salanki/hass-wisdom-amp` as an *Integration*.
2. Install **Wisdom SA-3 Amplifier**, restart Home Assistant.

### Manual
Copy `custom_components/wisdom_amp` into `config/custom_components/` and restart.

## Configuration

Settings → Devices & Services → **Add Integration** → *Wisdom SA-3 Amplifier*.
Enter the amp's **management** IP (control port defaults to 81). One entry per
amp; the MAC is the unique id, and **Reconfigure** updates the IP if it changes.

> ⚠️ Use the management-NIC IP (e.g. `192.168.30.x`), **not** the Dante audio IP.
> The SA-3 WebSocket has **no authentication** — anyone on that VLAN can control it.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [API_NOTES.md](API_NOTES.md) for the
design and the reverse-engineered protocol.

## License

MIT — see [LICENSE](LICENSE).
