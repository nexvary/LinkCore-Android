from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RckApi, RckApiError
from .direct_api import DirectAuthError
from homeassistant.exceptions import ConfigEntryAuthFailed

_LOGGER = logging.getLogger(__name__)


class RckCoordinator(DataUpdateCoordinator[list[dict]]):
    def __init__(self, hass: HomeAssistant, api: RckApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="FG Machines RCK",
            update_interval=timedelta(seconds=10),
        )
        self.api = api

    async def _async_update_data(self) -> list[dict]:
        try:
            return await self.api.devices()
        except DirectAuthError as err:
            raise ConfigEntryAuthFailed("Direct VPS credentials rejected") from err
        except RckApiError as err:
            raise UpdateFailed(str(err)) from err

    def device(self, mac: str) -> dict | None:
        for device in self.data or []:
            if str(device.get("mac", "")).upper() == mac.upper():
                return device
        return None
