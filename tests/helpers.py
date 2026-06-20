"""Shared test data and an in-memory fake Wisdom client."""

from __future__ import annotations

import copy
import re
from typing import Any

MAC = "DE:AD:BE:EF:00:01"

FWINFO: dict[str, Any] = {
    "app_ver": "03.02.71",
    "app_type": 2,
    "app_date": "Mar  9 2026",
    "app_plfm": "RP2040",
    "MAC": MAC,
}

DANTE_INFO: dict[str, Any] = {"friendlyName": "Wisdom-East-Deck"}

# East Deck snapshot: 1 active channel + 1 unused (empty name); 1 speaker on
# jacks 1/2/3. Channel 0 carries an EQ band we assert survives a trim write.
EAST_DECK_CFG: dict[str, Any] = {
    "network": {"hostname": "Wisdom-East-Deck", "ipaddr": "192.168.1.50"},
    "gain": -10,
    "MainsOnAction": 1,
    "PowerSave": 0,
    "inputs": [{"label": f"In {i}", "physicalport": i} for i in range(1, 12)],
    "channels": [
        {
            "name": "East Deck L150",
            "trim": 0,
            "delay": 0,
            "isSubwoofer": False,
            "source": [4],
            "equalizers": [{"type": "peq", "fc": 60, "Q": 1.0, "gain": 8, "bypass": False}],
        },
        {"name": "", "trim": 0, "delay": 0, "isSubwoofer": False, "source": [0]},
    ],
    "speakers": [
        {
            "name": "East Deck Speaker",
            "source": 0,
            "definition": {
                "drivers": [
                    {"name": "LF1", "jack": 2, "trim": 0, "delay": 0},
                    {"name": "LF2", "jack": 3, "trim": 0, "delay": 0},
                    {"name": "HF", "jack": 1, "trim": 0, "delay": 0},
                ]
            },
        }
    ],
}


class FakeClient:
    """In-memory Wisdom client: serves cfg/fwinfo, records writes."""

    def __init__(
        self,
        cfg: dict[str, Any] | None = None,
        fw: dict[str, Any] | None = None,
        dante: Any = None,
        **_: Any,
    ) -> None:
        self.cfg = copy.deepcopy(cfg if cfg is not None else EAST_DECK_CFG)
        self.fw = fw if fw is not None else dict(FWINFO)
        self.dante = dante if dante is not None else dict(DANTE_INFO)
        self.power = "off"
        self.cfgsets: list[dict[str, Any]] = []
        self.mutes: list[int] = []
        self.powers: list[bool] = []
        self.closed = False
        self._power_cb = None
        self._cfg_changed_cb = None
        self._reconnect_cb = None

    async def async_connect(self) -> None:
        pass

    async def async_get_fwinfo(self) -> dict[str, Any]:
        return dict(self.fw)

    async def async_get_dante_info(self) -> Any:
        return copy.deepcopy(self.dante)

    async def async_cfgget(self) -> dict[str, Any]:
        return copy.deepcopy(self.cfg)

    async def async_cfgset(self, partial: dict[str, Any]) -> None:
        self.cfgsets.append(copy.deepcopy(partial))
        # Mirror device semantics: an indexed key channels[N] updates that one
        # channel in place; other top-level keys merge.
        for key, val in copy.deepcopy(partial).items():
            m = re.fullmatch(r"channels\[(\d+)\]", key)
            if m:
                i = int(m.group(1))
                chs = self.cfg.setdefault("channels", [])
                while len(chs) <= i:
                    chs.append({})
                chs[i] = val
            elif key == "channels":
                # Faithfully model the device's destructive behavior: the
                # whole-array form does NOT replace — it clears the channel list.
                # This guards against any regression reintroducing it.
                self.cfg["channels"] = []
            else:
                self.cfg[key] = val

    async def async_power(self, on: bool) -> None:
        self.powers.append(on)
        self.power = "on" if on else "off"
        if self._power_cb is not None:
            self._power_cb(self.power)

    async def async_setmutes(self, mask: int) -> None:
        self.mutes.append(int(mask))

    def set_power_callback(self, cb) -> None:
        self._power_cb = cb

    def set_cfg_changed_callback(self, cb) -> None:
        self._cfg_changed_cb = cb

    def set_reconnect_callback(self, cb) -> None:
        self._reconnect_cb = cb

    async def async_close(self) -> None:
        self.closed = True
