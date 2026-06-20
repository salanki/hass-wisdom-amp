"""Config flow for the Wisdom SA-3 amplifier integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .const import DEFAULT_PORT, DOMAIN
from .pywisdomamp import WisdomClient, WisdomError


def _schema(host: str = "", port: int = DEFAULT_PORT) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Optional(CONF_PORT, default=port): vol.All(
                int, vol.Range(min=1, max=65535)
            ),
        }
    )


class WisdomConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _probe(self, host: str, port: int) -> tuple[str, str]:
        """Connect and return ``(normalized_mac, title)``; raises on failure."""
        client = WisdomClient(host, port, async_get_clientsession(self.hass))
        try:
            await client.async_connect()
            fw = await client.async_get_fwinfo()
            mac = fw.get("MAC")
            if not mac:
                raise WisdomError("no_mac")
            title = host
            try:
                dante = await client.async_get_dante_info()
                cfg = await client.async_cfgget()
            except WisdomError:
                dante, cfg = {}, {}
            name = None
            if isinstance(dante, dict):
                name = dante.get("friendlyName") or dante.get("name")
            elif isinstance(dante, str):
                name = dante
            name = name or cfg.get("network", {}).get("hostname")
            return format_mac(mac), (name or title)
        finally:
            await client.async_close()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                mac, title = await self._probe(host, port)
            except WisdomError as err:
                errors["base"] = "no_mac" if str(err) == "no_mac" else "cannot_connect"
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PORT: port}
                )
                return self.async_create_entry(
                    title=title, data={CONF_HOST: host, CONF_PORT: port}
                )

        return self.async_show_form(
            step_id="user", data_schema=_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                mac, _ = await self._probe(host, port)
            except WisdomError as err:
                errors["base"] = "no_mac" if str(err) == "no_mac" else "cannot_connect"
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host, CONF_PORT: port}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(
                entry.data.get(CONF_HOST, ""),
                entry.data.get(CONF_PORT, DEFAULT_PORT),
            ),
            errors=errors,
        )
