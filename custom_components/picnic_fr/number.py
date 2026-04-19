"""Number entity: tune the Picnic polling interval from the HA UI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL_MIN,
    DOMAIN,
    MAX_POLL_INTERVAL_MIN,
    MIN_POLL_INTERVAL_MIN,
)
from .coordinator import PicnicFRCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicnicPollIntervalNumber(coord, entry)])


class PicnicPollIntervalNumber(NumberEntity):
    """Slider to control coordinator poll frequency (minutes)."""

    _attr_has_entity_name = True
    _attr_name = "Intervalle de rafraîchissement"
    _attr_native_min_value = MIN_POLL_INTERVAL_MIN
    _attr_native_max_value = MAX_POLL_INTERVAL_MIN
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:timer-sync-outline"

    def __init__(self, coordinator: PicnicFRCoordinator, entry: ConfigEntry) -> None:
        self._coord = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_poll_interval"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": "Picnic",
            "model": self._entry.data.get("country", "FR"),
        }

    @property
    def native_value(self) -> float:
        return float(
            (self._entry.options or {}).get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MIN)
        )

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(max(MIN_POLL_INTERVAL_MIN, min(MAX_POLL_INTERVAL_MIN, value)))
        new_options = {**(self._entry.options or {}), CONF_POLL_INTERVAL: minutes}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self._coord.set_poll_interval(minutes)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
