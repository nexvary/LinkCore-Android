from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from .api import RckApiError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RckCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator: RckCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.identity_prefix = entry.entry_id + "_" if getattr(coordinator.api, "direct", False) else ""
    known: set[str] = set()

    @callback
    def add_new_devices() -> None:
        entities = []
        for device in coordinator.data or []:
            mac = str(device.get("mac", ""))
            if not mac:
                continue
            outlets = device.get("visible_outlets", range(1, 5))
            for outlet in outlets:
                unique = f"{mac}_outlet_{outlet}"
                if unique in known:
                    continue
                known.add(unique)
                entities.append(RckOutletSwitch(coordinator, mac, outlet))
        if entities:
            async_add_entities(entities)

    add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_new_devices))


class RckOutletSwitch(CoordinatorEntity[RckCoordinator], SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RckCoordinator, mac: str, outlet: int) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._outlet = outlet
        self._attr_unique_id = getattr(coordinator, "identity_prefix", "") + f"{mac}_outlet_{outlet}"
        self._attr_name = f"Outlet {outlet}"

    @property
    def device_info(self) -> DeviceInfo:
        device = self.coordinator.device(self._mac) or {}
        return DeviceInfo(
            identifiers={(DOMAIN, getattr(self.coordinator, "identity_prefix", "") + self._mac)},
            name=device.get("name") or f"MTTL-W01 {self._mac}",
            manufacturer="FG Machines / compatible MTTL",
            model="MTTL-W01",
            sw_version=device.get("firmware") or None,
            suggested_area=device.get("room") or None,
        )

    @property
    def available(self) -> bool:
        device = self.coordinator.device(self._mac)
        return bool(super().available and device and device.get("connected")
                    and self._outlet in device.get("visible_outlets", range(1, 5))
                    and self._outlet in device.get("allowed_outlets", range(1, 5))
                    and device.get("control_enabled", True)
                    and not device.get("device_busy") and not device.get("pending_outlets")
                    and self.is_on is not None)

    @property
    def is_on(self) -> bool | None:
        device = self.coordinator.device(self._mac) or {}
        telemetry = device.get("telemetry") or {}
        for outlet in telemetry.get("outlets", []):
            if int(outlet.get("channel", 0)) == self._outlet:
                return outlet.get("on")
        return None

    async def _set(self, on: bool) -> None:
        try:
            await self.coordinator.api.set_outlet(self._mac, self._outlet, on)
        except RckApiError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
