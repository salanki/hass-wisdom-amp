# Testing

Runs in a disposable Docker container (`python:3.12-slim`); only Docker needed.

```bash
make test         # full suite (live tests excluded)
make test-verbose
make test-fast    # -x --tb=short
make test-cov
make test-one TEST=tests/test_client.py::test_request_timeout_drops_socket
make lint         # ruff
make check        # lint + test (CI gate)
```

## Coverage

- `test_client.py` — frame routing (`<verb> <json>` split, bare verbs, malformed
  JSON), `pwrstate` routing incl. `state:2`, solicited-vs-unsolicited `cfg`,
  request resolve, **timeout → socket drop**, outbound formatting
  (`setmutes 7` / `on` / `cfgset {...}`), waiter-failure on close.
- `test_coordinator.py` — discovery (active channels, jack-group collapse,
  MAC-required), status build, **channel read-modify-write resends the full array
  with EQ preserved**, mute-mask from jack groups.
- `test_config_flow.py` — user create, `cannot_connect`, `no_mac`, duplicate,
  reconfigure `wrong_device`.
- `test_platforms.py` — gain/trim numbers (+ range rejection), power & mute
  switches, diagnostic sensors, unused-channel skip, unload closes client.

## Live (opt-in, read-only)

`tests/test_live_readonly.py` talks to a real amp — **read-only** (only
getFWinfo/getDanteInfo/cfgget). Excluded by default.

```bash
export WISDOM_AMP_HOST=192.168.30.75   # management IP
make test-live
```
