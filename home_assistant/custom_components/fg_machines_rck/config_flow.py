from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RckApi, RckApiError
from .direct_api import DirectVpsApi, DirectAuthError, normalize_origin
from homeassistant.helpers import selector
from .const import CONF_HOST, CONF_TOKEN, DOMAIN


async def _validate(hass: HomeAssistant, host: str, token: str) -> None:
    api = RckApi(async_get_clientsession(hass), host, token)
    await api.health()
    await api.devices()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["direct", "local"])

    async def async_step_direct(self, user_input=None):
        errors = {}
        if user_input:
            api = None
            try:
                host = normalize_origin(user_input[CONF_HOST])
                api = DirectVpsApi(async_get_clientsession(self.hass), host,
                                   user_input["username"], user_input["password"])
                await api.devices()
            except ValueError:
                errors["base"] = "invalid_host"
            except DirectAuthError:
                errors["base"] = "invalid_auth"
            except RckApiError:
                errors["base"] = "cannot_connect"
            finally:
                if api:
                    await api.logout()
            if not errors:
                username = user_input["username"].strip().lower()
                await self.async_set_unique_id(host.lower() + "|" + username)
                data = {CONF_HOST: host, "mode": "direct", "username": username, "password": user_input["password"]}
                if self.context.get("source") == "reauth":
                    entry = self._get_reauth_entry()
                    if entry.data[CONF_HOST] != host or entry.data["username"] != username:
                        return self.async_abort(reason="account_mismatch")
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"FG Link Direct VPS · {username}", data=data)
        return self.async_show_form(step_id="direct", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST, default="https://link.fgmachines.org"): str,
            vol.Required("username"): str,
            vol.Required("password"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }))

    async def async_step_reauth(self, entry_data):
        return await self.async_step_direct()

    async def async_step_local(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].rstrip("/")
            token = user_input[CONF_TOKEN].strip()
            try:
                await _validate(self.hass, host, token)
            except RckApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"FG Machines RCK · {host}",
                    data={CONF_HOST: host, CONF_TOKEN: token},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="http://192.168.1.2:18086"): str,
                vol.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="local", data_schema=schema, errors=errors)
