"""Device tracker: live GPS position of the Picnic driver during delivery.

The coordinator polls `/deliveries/{id}/position` only while the current
delivery is in a transit-ish state (`CURRENT`, `TRANSPORTING`, `EN_ROUTE`,
`AT_DOOR`). The endpoint returns `null` before the driver has started the
run; the tracker surfaces that as `available=False` so the map entity
degrades gracefully.

Picnic's position payload is not formally documented and field names have
varied over time. We probe several common spellings (`latitude`/`lat`,
`longitude`/`lng`/`lon`). Unknown extra fields get passed through as
attributes so new fields are visible even before the wrapper learns about
them.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_CURRENT_DELIVERY, DATA_DELIVERY_POSITION, DOMAIN
from .coordinator import PicnicFRCoordinator


def _pick(position: dict, *keys: str) -> Any:
    for k in keys:
        if k in position and position[k] is not None:
            return position[k]
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicnicDriverTracker(coord, entry)])


class PicnicDriverTracker(
    CoordinatorEntity[PicnicFRCoordinator], TrackerEntity
):
    """Real-time location of the Picnic driver handling your delivery."""

    _attr_has_entity_name = True
    _attr_name = "Livreur Picnic"
    _attr_icon = "mdi:truck-fast"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: PicnicFRCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_driver_tracker"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": "Picnic",
            "model": self._entry.data.get("country", "FR"),
        }

    @property
    def _position(self) -> dict | None:
        data = self.coordinator.data or {}
        pos = data.get(DATA_DELIVERY_POSITION)
        return pos if isinstance(pos, dict) else None

    @property
    def available(self) -> bool:
        return self._position is not None and self.latitude is not None

    @property
    def latitude(self) -> float | None:
        pos = self._position
        if not pos:
            return None
        val = _pick(pos, "latitude", "lat")
        return float(val) if val is not None else None

    @property
    def longitude(self) -> float | None:
        pos = self._position
        if not pos:
            return None
        val = _pick(pos, "longitude", "lng", "lon")
        return float(val) if val is not None else None

    @property
    def location_accuracy(self) -> int:
        pos = self._position or {}
        val = _pick(pos, "accuracy", "location_accuracy", "horizontal_accuracy")
        try:
            return int(val) if val is not None else 0
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        delivery = (self.coordinator.data or {}).get(DATA_CURRENT_DELIVERY) or {}
        pos = self._position or {}
        out: dict[str, Any] = {
            "delivery_id": delivery.get("delivery_id"),
            "delivery_status": delivery.get("status"),
        }
        # Commonly-seen fields we surface explicitly when present
        for key in ("heading", "speed", "bearing", "timestamp", "eta_start", "eta_end"):
            val = pos.get(key)
            if val is not None:
                out[key] = val
        # Passthrough anything else unknown so new fields become visible
        passthrough = {
            k: v
            for k, v in pos.items()
            if k not in {"latitude", "lat", "longitude", "lng", "lon",
                         "accuracy", "location_accuracy", "horizontal_accuracy",
                         "heading", "speed", "bearing", "timestamp",
                         "eta_start", "eta_end"}
            and not isinstance(v, (dict, list))
        }
        if passthrough:
            out["raw_extra"] = passthrough
        return out
