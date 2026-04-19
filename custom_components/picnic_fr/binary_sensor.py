"""Binary sensors: pending-delivery live state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_CURRENT_DELIVERY, DOMAIN
from .coordinator import PicnicFRCoordinator

# Any status other than these means something is actively happening.
_COMPLETED_STATUSES = {"COMPLETED", "CANCELLED"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PicnicDeliveryInProgressBinarySensor(coord, entry),
            PicnicCanEditOrderBinarySensor(coord, entry),
        ]
    )


class _Base(CoordinatorEntity[PicnicFRCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PicnicFRCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": "Picnic",
            "model": self._entry.data.get("country", "FR"),
        }


class PicnicDeliveryInProgressBinarySensor(_Base):
    """On whenever there is a pending (non-completed, non-cancelled) delivery."""

    _key = "delivery_in_progress"
    _attr_name = "Livraison en cours"
    _attr_device_class = BinarySensorDeviceClass.MOVING
    _attr_icon = "mdi:truck-fast"

    @property
    def is_on(self) -> bool:
        d = self.coordinator.data.get(DATA_CURRENT_DELIVERY)
        if not d:
            return False
        status = (d.get("status") or "").upper()
        return status not in _COMPLETED_STATUSES


class PicnicCanEditOrderBinarySensor(_Base):
    """On while `now < slot.cut_off_time` — the pending order can still be edited."""

    _key = "can_edit_order"
    _attr_name = "Modification de la commande possible"
    _attr_icon = "mdi:pencil-circle"

    @property
    def is_on(self) -> bool:
        d = self.coordinator.data.get(DATA_CURRENT_DELIVERY)
        if not d:
            return False
        cutoff = (d.get("slot") or {}).get("cut_off_time")
        if not cutoff:
            return False
        try:
            deadline = datetime.fromisoformat(cutoff)
        except (TypeError, ValueError):
            return False
        return datetime.now(tz=timezone.utc) < deadline
