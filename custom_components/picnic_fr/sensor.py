"""Sensors: cart total, items count, weight, selected slot, token expiry, deliveries."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_WEIGHT_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<mult>\d+)\s*[x×*]\s*)?      # optional leading "N x"
    (?P<val>\d+(?:[.,]\d+)?)\s*
    (?P<unit>kg|g|l|cl|ml)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_UNIT_TO_GRAMS = {"kg": 1000.0, "g": 1.0, "l": 1000.0, "cl": 10.0, "ml": 1.0}


def parse_weight_grams(unit_quantity: str | None) -> float | None:
    """Convert a Picnic `unit_quantity` string to grams (approx).

    Handles: "1 Kg", "375 g", "1,25 L", "70 cl", "12 x 60 g".
    Returns None for non-weighable units (pièces, unités, rouleaux, …).
    Liquids are approximated 1 L ≈ 1000 g (water-equivalent).
    """
    if not unit_quantity:
        return None
    m = _WEIGHT_RE.match(unit_quantity)
    if not m:
        return None
    mult = int(m.group("mult") or 1)
    val = float(m.group("val").replace(",", "."))
    unit = m.group("unit").lower()
    return mult * val * _UNIT_TO_GRAMS[unit]

from .const import (
    CONF_TOKEN_EXP,
    DATA_CART,
    DATA_DELIVERIES,
    DATA_HISTORY,
    DATA_SLOT,
    DOMAIN,
)
from .coordinator import PicnicFRCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PicnicCartTotalSensor(coord, entry),
            PicnicCartProductsCountSensor(coord, entry),
            PicnicCartItemsSensor(coord, entry),
            PicnicCartWeightSensor(coord, entry),
            PicnicCartListSensor(coord, entry),
            PicnicSelectedSlotSensor(coord, entry),
            PicnicTokenExpirySensor(coord, entry),
            PicnicHistoryProductsSensor(coord, entry),
            PicnicDeliveriesCountSensor(coord, entry),
        ]
    )


def _flatten_cart_lines(cart: dict | None) -> list[dict]:
    if not cart:
        return []
    out: list[dict] = []
    for group in cart.get("items", []) or []:
        if not isinstance(group, dict):
            continue
        for line in group.get("items", []) or []:
            if not isinstance(line, dict) or not line.get("id"):
                continue
            count = line.get("count")
            if count is None:
                for deco in line.get("decorators", []) or []:
                    if deco.get("type") == "QUANTITY":
                        count = deco.get("quantity", 1)
                        break
            out.append(
                {
                    "id": line["id"],
                    "name": line.get("name", "?"),
                    "count": int(count or 1),
                    "unit_quantity": line.get("unit_quantity"),
                    "price_cents": line.get("display_price") or line.get("price"),
                }
            )
    return out


def _format_line(line: dict) -> str:
    price = line.get("price_cents")
    unit = line.get("unit_quantity")
    unit_txt = f" [{unit}]" if unit else ""
    price_txt = f"  {price / 100:.2f} €" if isinstance(price, int) else ""
    return f"(x{line['count']}) {line['name']}{unit_txt}{price_txt}"


class _PicnicSensorBase(CoordinatorEntity[PicnicFRCoordinator], SensorEntity):
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


class PicnicCartTotalSensor(_PicnicSensorBase):
    _key = "cart_total"
    _attr_name = "Total panier"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY_EURO
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        cart = self.coordinator.data.get(DATA_CART) or {}
        total = cart.get("total_price")
        if total is None:
            return None
        return round(total / 100, 2)


class PicnicCartProductsCountSensor(_PicnicSensorBase):
    """Number of distinct products in the cart (unique product_ids)."""

    _key = "cart_products_count"
    _attr_name = "Nombre de produits"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:shape-outline"

    @property
    def native_value(self) -> int:
        return len(_flatten_cart_lines(self.coordinator.data.get(DATA_CART)))


class PicnicCartItemsSensor(_PicnicSensorBase):
    """Total number of articles (sum of quantities)."""

    _key = "cart_items"
    _attr_name = "Nombre d'articles"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cart"

    @property
    def native_value(self) -> int:
        lines = _flatten_cart_lines(self.coordinator.data.get(DATA_CART))
        return sum(line["count"] for line in lines)


class PicnicCartWeightSensor(_PicnicSensorBase):
    """Estimated total weight of the cart, computed from each line's
    `unit_quantity` × count. Liquids use a water-equivalent approximation
    (1 L ≈ 1 kg). Items sold by piece (œufs, rouleaux de PQ…) ne contribuent
    pas — listés dans l'attribut `unweighted_lines`."""

    _key = "cart_weight"
    _attr_name = "Poids du panier"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_icon = "mdi:weight"
    _attr_suggested_display_precision = 2

    def _compute(self) -> tuple[float, list[dict], list[dict]]:
        lines = _flatten_cart_lines(self.coordinator.data.get(DATA_CART))
        total_grams = 0.0
        weighted, unweighted = [], []
        for line in lines:
            grams = parse_weight_grams(line.get("unit_quantity"))
            if grams is None:
                unweighted.append(
                    {
                        "id": line["id"],
                        "name": line["name"],
                        "count": line["count"],
                        "unit_quantity": line.get("unit_quantity"),
                    }
                )
                continue
            line_total = grams * line["count"]
            total_grams += line_total
            weighted.append(
                {
                    "id": line["id"],
                    "name": line["name"],
                    "count": line["count"],
                    "unit_quantity": line.get("unit_quantity"),
                    "weight_g": round(line_total, 1),
                }
            )
        return total_grams, weighted, unweighted

    @property
    def native_value(self) -> float:
        total_grams, _, _ = self._compute()
        return round(total_grams / 1000.0, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        total_grams, weighted, unweighted = self._compute()
        return {
            "total_grams": round(total_grams, 1),
            "weighted_lines": weighted,
            "unweighted_lines": unweighted,
        }


class PicnicCartListSensor(_PicnicSensorBase):
    """State = comma-separated product names (truncated 255). Full list in attrs."""

    _key = "cart_list"
    _attr_name = "Liste des articles"
    _attr_icon = "mdi:format-list-bulleted"

    @property
    def native_value(self) -> str:
        lines = _flatten_cart_lines(self.coordinator.data.get(DATA_CART))
        if not lines:
            return "Panier vide"
        chunks = [
            (f"(x{l['count']}) {l['name']}" if l["count"] > 1 else l["name"])
            for l in lines
        ]
        joined = ", ".join(chunks)
        if len(joined) <= 255:
            return joined
        # Truncate and indicate how many more products exist
        truncated = ""
        kept = 0
        for chunk in chunks:
            candidate = (truncated + ", " + chunk) if truncated else chunk
            remaining = len(lines) - (kept + 1)
            suffix = f" (+{remaining})" if remaining > 0 else ""
            if len(candidate) + len(suffix) > 255:
                break
            truncated = candidate
            kept += 1
        remaining = len(lines) - kept
        if remaining > 0:
            truncated += f" (+{remaining})"
        return truncated

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lines = _flatten_cart_lines(self.coordinator.data.get(DATA_CART))
        formatted = [_format_line(l) for l in lines]
        return {
            "lines": lines,
            "names": [l["name"] for l in lines],
            "items_text": "\n".join(formatted) if formatted else "(panier vide)",
            "items_markdown": "\n".join(f"- {t}" for t in formatted) if formatted else "_Panier vide_",
        }


class PicnicSelectedSlotSensor(_PicnicSensorBase):
    _key = "selected_slot"
    _attr_name = "Créneau de livraison"
    _attr_icon = "mdi:truck-delivery"

    @property
    def native_value(self) -> str | None:
        slot = self.coordinator.data.get(DATA_SLOT)
        if not slot:
            return "Aucun"
        start = slot.get("start")
        end = slot.get("end")
        if isinstance(start, datetime) and isinstance(end, datetime):
            return f"{start.strftime('%a %d/%m %H:%M')} – {end.strftime('%H:%M')}"
        return slot.get("slot_id", "?")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        slot = self.coordinator.data.get(DATA_SLOT) or {}
        if not slot:
            return {}
        start = slot.get("start")
        end = slot.get("end")
        duration_min = (
            (end - start).total_seconds() / 60
            if isinstance(start, datetime) and isinstance(end, datetime)
            else None
        )
        return {
            "slot_id": slot.get("slot_id"),
            "state": slot.get("state"),
            "start": start.isoformat() if isinstance(start, datetime) else None,
            "end": end.isoformat() if isinstance(end, datetime) else None,
            "kind": "eco" if duration_min and duration_min > 65 else "normal",
            "duration_min": duration_min,
        }


class PicnicTokenExpirySensor(_PicnicSensorBase):
    _key = "token_expiry"
    _attr_name = "Expiration du token"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:key-alert"

    @property
    def native_value(self) -> datetime | None:
        exp = self._entry.data.get(CONF_TOKEN_EXP)
        if not exp:
            return None
        return datetime.fromtimestamp(exp, tz=timezone.utc)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        exp = self._entry.data.get(CONF_TOKEN_EXP)
        if not exp:
            return {}
        days_left = (exp - datetime.now(tz=timezone.utc).timestamp()) / 86400
        return {"days_left": round(days_left, 1)}


class PicnicHistoryProductsSensor(_PicnicSensorBase):
    _key = "history_unique_products"
    _attr_name = "Produits distincts achetés"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:history"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get(DATA_HISTORY) or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        history = self.coordinator.data.get(DATA_HISTORY) or {}
        top = list(history.values())[:10]
        return {
            "top_10": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "count": p["count"],
                    "orders": p["orders"],
                }
                for p in top
            ]
        }


class PicnicDeliveriesCountSensor(_PicnicSensorBase):
    _key = "deliveries_total"
    _attr_name = "Livraisons reçues"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:package-variant-closed"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get(DATA_DELIVERIES) or [])


