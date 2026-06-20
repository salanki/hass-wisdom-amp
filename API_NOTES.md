# Wisdom DSP amplifier control protocol notes

Reverse-engineered and verified live (read-only) against Wisdom **SA-2 / SA-3 /
IA-8 MK2** units (RP2040 firmware) — the SA / IA DSP line shares one protocol. The
model is auto-detected from `fwinfo.app_fw` (e.g. `SA3-…` → `SA-3`, `IA8MK2-…` →
`IA-8 MK2`). This is the integration-facing summary; fuller device notes live in
the home-automation repo at `115beach/ha/wisdom-amplifiers.md`.

## Transport

- **WebSocket**, `ws://<ip>:81` (legacy fallback `:443`, not TLS). **No auth.**
- Text frames both ways: `"<verb> <json>"`; some verbs are bare (`cfgbusy`,
  `rebooting`). aiohttp handles the handshake, masking, and fragmentation.
- On connect the amp **floods `log` frames + a `pwrstate`** — unsolicited; the
  client routes them to callbacks, never to request waiters.
- Mixed push/response with **no request IDs**: `cfg` answers `cfgget` *and* is
  pushed after a config apply. Correlation must serialize requests and treat a
  response timeout as stream-corrupting (drop + reconnect).

## Commands used

| Verb | Response | Use |
|---|---|---|
| `getFWinfo` | `fwinfo {app_ver, app_plfm, MAC, ...}` | identity, unique_id (MAC) |
| `getDanteInfo` | `updateDanteInfo` | Dante friendly name |
| `cfgget` | `cfg {network,gain,MainsOnAction,PowerSave,inputs[],channels[],speakers[]}` | full config |
| `cfgset <json>` | (no ack; `cfgbusy` then `cfg` follow) | partial **top-level** merge write |
| `on` / `off` | pushed `pwrstate` | power |
| `setmutes <mask>` | — | mute by **jack** bitmask (bit0=jack1); **transient** |

Pushed: `pwrstate {state:0|1|2}` (off/on/transitioning), `cfgbusy`, `rebooting`,
`log`.

## Config fields this integration uses

- `gain` — master gain (dB), scalar. Write `cfgset {"gain": v}`.
- `channels[i].name` — empty ⇒ unused (no entities). `.trim` (dB), `.delay` (ms;
  firmware max **35 ms**).
- `speakers[i].definition.drivers[].jack` — physical output jacks → mute groups.
- `network.hostname` — display name fallback.

## Channel writes — use the INDEXED key (critical)

Change a channel field with the **indexed single-channel** form (exactly what the
SA-3 web app sends):

```
cfgset {"channels[0]": { <full channel object, one field changed> }}
```

⚠️ **Do NOT send the whole-array form** `cfgset {"channels": [...]}` — it does not
merge or replace, it **clears the channel list** on the device (verified the hard
way on a live amp; recovered by copying the mirror amp's channel via `channels[0]`).
The integration reads fresh, deep-copies the one channel object (preserving
`equalizers`/`source`/etc.), changes only `trim`/`delay`, and writes it back under
`channels[N]`. Channel object:
`{source:[int], isSubwoofer:bool, delay, trim, name, equalizers:[10 bands]}`;
each band `{type:"peq", order:2, shape:"p", fc, Q, gain, bypass}`.

## Gotchas baked into the integration

1. **Channel writes must be indexed** (`channels[N]`); the whole-array form clears
   channels (see above). Residual race: an external edit inside the read→write
   window is unguarded (no firmware revision id).
2. **Mute state is WRITE-ONLY.** `setmutes` sets a jack bitmask, but there is no
   way to *read* current mutes — not in `cfg`, not pushed on connect (only
   `pwrstate`+`log`), and no query verb (verified: `getmutes`/`getMutes`/`mutes`
   return nothing). The official web UI also tracks mutes client-side. So HA's
   mute switches are **assumed-state** (reflect HA's own last command, not the
   amp) and a mute set elsewhere won't show. HA sends `setmutes` **only** on an
   explicit service call — never on connect/reconnect — so it won't clobber
   externally-set mutes. The device keeps mutes across client connections; they
   clear on a device **reboot** (which HA can't observe).
3. **Management IP ≠ Dante IP.** WebSocket is on the management NIC.
4. **No auth** — anyone on the VLAN can read/write config, factory reset, or flash.
5. **`pwrstate=2`** is transitioning → power switch reports unknown, not on/off.
