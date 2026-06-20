# Wisdom SA-3 control protocol notes

Reverse-engineered and verified live (read-only) against the East Deck SA-3
(firmware 03.02.71, RP2040). Full device docs live in the home-automation repo at
`115beach/ha/wisdom-amplifiers.md`; this is the integration-facing summary.

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
- `channels[i].name` — empty ⇒ unused (no entities). `.trim` (dB), `.delay` (ms).
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
2. **Mutes are transient** — reset on reboot/reconnect. The client sends
   `setmutes 0` on every connect and the coordinator clears its mute model on
   reconnect.
3. **Management IP ≠ Dante IP.** WebSocket is on the management NIC.
4. **No auth** — anyone on the VLAN can read/write config, factory reset, or flash.
5. **`pwrstate=2`** is transitioning → power switch reports unknown, not on/off.
