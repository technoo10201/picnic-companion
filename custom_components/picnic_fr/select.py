"""Select entity: pick a Picnic delivery slot from the HA UI.

The options list is rebuilt on every coordinator update from the available
slots. Selecting an option calls `cart.set_delivery_slot` and forces a refresh
so the change is reflected both in HA and in the Picnic mobile app.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PicnicError
from .const import DATA_SLOT, DATA_SLOTS, DOMAIN
from .coordinator import PicnicFRCoordinator

_LOGGER = logging.getLogger(__name__)

_WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _format_slot_label(slot: dict) -> str:
    start: datetime = slot["start"]
    end: datetime = slot["end"]
    kind = "éco" if (end - start).total_seconds() / 60 > 65 else "normal"
    return (
        f"{_WEEKDAYS_FR[start.weekday()]} "
        f"{start.strftime('%d/%m')} "
        f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} "
        f"({kind})"
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicnicSlotSelect(coord, entry)])


class PicnicSlotSelect(CoordinatorEntity[PicnicFRCoordinator], SelectEntity):
    """Dropdown of available Picnic delivery slots."""

    _attr_has_entity_name = True
    _attr_name = "Créneau de livraison"
    _attr_icon = "mdi:truck-delivery"

    def __init__(self, coordinator: PicnicFRCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_slot_select"
        self._label_to_id: dict[str, str] = {}

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": "Picnic",
            "model": self._entry.data.get("country", "FR"),
        }

    def _build_options(self) -> tuple[list[str], dict[str, str]]:
        by_day = (self.coordinator.data or {}).get(DATA_SLOTS) or {}
        label_to_id: dict[str, str] = {}
        labels: list[str] = []
        for _day, slots in by_day.items():
            for slot in slots:
                if "start" not in slot or "end" not in slot:
                    continue
                label = _format_slot_label(slot)
                label_to_id[label] = slot["slot_id"]
                labels.append(label)
        # Make sure the currently selected slot is in the list even if
        # Picnic no longer advertises it as "available".
        current = (self.coordinator.data or {}).get(DATA_SLOT) or {}
        if current and current.get("slot_id") and current.get("start") and current.get("end"):
            label = _format_slot_label(current)
            if label not in label_to_id:
                label_to_id[label] = current["slot_id"]
                labels.insert(0, label)
        return labels, label_to_id

    @property
    def options(self) -> list[str]:
        labels, mapping = self._build_options()
        self._label_to_id = mapping
        return labels

    @property
    def current_option(self) -> str | None:
        current = (self.coordinator.data or {}).get(DATA_SLOT) or {}
        if not current or not current.get("slot_id"):
            return None
        if current.get("start") and current.get("end"):
            return _format_slot_label(current)
        return None

    async def async_select_option(self, option: str) -> None:
        # Ensure mapping is fresh
        _, self._label_to_id = self._build_options()
        slot_id = self._label_to_id.get(option)
        if not slot_id:
            raise ValueError(f"Créneau inconnu : {option!r}")
        try:
            await self.coordinator.client.book_slot(slot_id)
        except PicnicError as exc:
            _LOGGER.error("Booking failed for %s: %s", slot_id, exc)
            raise
        await self.coordinator.async_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
