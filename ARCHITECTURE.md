# Architecture

```
custom_components/wisdom_amp/
  pywisdomamp/           # standalone async client (no Home Assistant imports)
    client.py            # aiohttp WebSocket client (reader task + serialized requests)
    models.py            # WisdomInfo / WisdomStatus / ChannelInfo / JackGroup
    exceptions.py        # WisdomError / ConnectionError / TimeoutError
  coordinator.py         # discovery + DataUpdateCoordinator (one per amp)
  __init__.py            # setup/unload, runtime_data
  entity.py              # device wiring (DeviceInfo, unique_id = {mac}_{key})
  config_flow.py         # manual host + reconfigure
  number.py / switch.py / sensor.py
```

## Why this is harder than the Blaze sibling

The Wisdom DSP amps (SA / IA line) expose **one WebSocket with mixed push +
response and no request IDs** (the model is auto-detected from the firmware). The
same verbs that answer a request (`cfg`) are *also* pushed unsolicited (a flood of
`log` on connect, `pwrstate`, `cfgbusy`, and `cfg` after a config apply). So the
client/coordinator boundary needs stricter synchronisation than Blaze's serialized
ack'd line protocol.

## Client (`pywisdomamp.client.WisdomClient`)

- **One reader task** consumes every frame (`<verb> <json>`) and routes it. A
  single `asyncio.Lock` **serializes request/response exchanges** so at most one
  waiter exists per verb; concurrent callers coalesce behind the lock.
- A request **timeout drops the socket** and lets the reader reconnect — a late
  reply must never resolve a newer waiter on this ID-less protocol.
- **Unsolicited frames go to callbacks**, never to request waiters: `pwrstate` →
  power callback; `cfgbusy`/unsolicited `cfg` → "config changed" callback. The
  client **does not** schedule its own refreshes.
- On every (re)connect it sends `setmutes 0` (mutes are transient); on *reconnect*
  it also fails pending waiters and fires a reconnect callback so the coordinator
  resyncs.
- Uses HA's shared aiohttp session (passed in); `async_close()` cancels/awaits the
  reader and closes the socket.

## Coordinator

- `local_polling`, ~45 s `cfgget` (catches web-UI/out-of-band edits); push is
  supplemental. **The coordinator owns all refresh scheduling** — the client's
  "config changed" callback triggers a debounced `async_request_refresh`.
- `pwrstate` callback copy-replaces the snapshot (`async_set_updated_data(replace(
  data, power=...))`) so state actually changes; `state:2` → `transitioning`
  (switch shows unknown, not an optimistic on/off).
- Discovery (once): `getFWinfo` (MAC→unique_id), `getDanteInfo`, `cfgget` →
  active channels (named) + jack-group map. Topology is fixed at setup; an
  out-of-band channel/speaker change needs a reload.
- **Channel writes** take a write lock, do a **fresh `cfgget`**, deep-copy the one
  channel object, change a field, and send the **indexed** `cfgset {"channels[N]":
  {...}}` (what the web app sends). The whole-array form `{"channels":[...]}`
  **clears** the channel list on the device — never use it.
- **Mute** is a jack mask: muted jack-groups → OR of their jack bits → `setmutes`.
  A jack is muted iff any muted group includes it, so overlapping groups compose
  correctly.

## Entities

- Stable unique ids `{mac}_{key}` with positional keys (`channel_0_trim`,
  `mute_jacks_1_2_3`); channel/speaker display names come from the config.
- Gain/trim/delay are `EntityCategory.CONFIG`; power + mute are operational;
  power-state/firmware/Dante-name are diagnostic sensors. Static identity lives in
  `DeviceInfo` (`CONNECTION_NETWORK_MAC`).
- Control failures raise `HomeAssistantError`; poll failures map to `UpdateFailed`.
