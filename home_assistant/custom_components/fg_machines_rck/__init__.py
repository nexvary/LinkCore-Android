from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RckApi
from .direct_api import DirectVpsApi
from .const import CONF_HOST, CONF_TOKEN, DOMAIN, PLATFORMS
from .coordinator import RckCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get("mode") == "direct":
        api = DirectVpsApi(async_get_clientsession(hass), entry.data[CONF_HOST],
                           entry.data["username"], entry.data["password"])
    else:
        api = RckApi(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    coordinator = RckCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator and getattr(coordinator.api, "direct", False):
            await coordinator.api.logout()
    return unloaded
