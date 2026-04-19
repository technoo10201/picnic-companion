"""Todo platform: HA ↔ Picnic cart mirror.

Semantics
---------
- The entity shows the *actual* Picnic cart. Each todo item == a cart line.
  Items added from the mobile app appear here after the next coordinator poll
  (default: 2 min), or immediately if you call the `picnic_fr.refresh_history`
  service or trigger a manual refresh.
- Adding an item (free text like "farine" or "oeufs x3"):
    1. Matcher resolves query × catalog × past-order frequency.
    2. The picked product is added to the Picnic cart.
    3. An immediate coordinator refresh updates the list so the item appears
       with the resolved product's real name, price, and quantity.
- Deleting an item removes the corresponding product entirely from the cart.
- Quantity changes via the UI aren't supported (the summary is recomputed
  from the cart on each refresh). Re-add or edit from the Picnic app.

Quantity input: "bananes x3", "bananes ×3", "bananes (3)" → count=3.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PicnicError
from .const import DATA_CART, DATA_HISTORY, DOMAIN
from .coordinator import PicnicFRCoordinator

_LOGGER = logging.getLogger(__name__)

QTY_RE = re.compile(r"\s*[x×*]\s*(\d+)\s*$|\s*\((\d+)\)\s*$", re.IGNORECASE)
MULTI_SEP = "//"


def parse_query_and_qty(text: str) -> tuple[str, int]:
    if not text:
        return text, 1
    m = QTY_RE.search(text)
    if m:
        qty = int(m.group(1) or m.group(2) or 1)
        return QTY_RE.sub("", text).strip(), max(1, qty)
    return text.strip(), 1


def parse_multi_items(text: str) -> list[tuple[str, int]]:
    """Split a free-text input on `//` into multiple (query, qty) tuples.

    Whitespace and empty fragments are ignored. Each fragment is then run
    through `parse_query_and_qty` so per-item quantity suffixes still work,
    e.g. "bananes // oeufs x3 // sucre" → [(bananes,1), (oeufs,3), (sucre,1)].
    """
    if not text:
        return []
    parts = [p.strip() for p in text.split(MULTI_SEP)]
    out: list[tuple[str, int]] = []
    for p in parts:
        if not p:
            continue
        out.append(parse_query_and_qty(p))
    return out


def _extract_cart_lines(cart: dict | None) -> list[dict]:
    """Flatten cart.items[].items[] into a list of product lines."""
    if not cart:
        return []
    lines: list[dict] = []
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
            lines.append({
                "id": line["id"],
                "name": line.get("name", "?"),
                "count": int(count or 1),
                "price_cents": line.get("display_price") or line.get("price"),
                "unit_quantity": line.get("unit_quantity"),
            })
    return lines


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicnicShoppingList(coord, entry)])


class PicnicShoppingList(CoordinatorEntity[PicnicFRCoordinator], TodoListEntity):
    """Cart-mirrored shopping list."""

    _attr_has_entity_name = True
    _attr_name = "Nombre article dans liste de courses"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
    )

    def __init__(self, coordinator: PicnicFRCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_shopping_list"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": "Picnic",
            "model": self._entry.data.get("country", "FR"),
        }

    @property
    def todo_items(self) -> list[TodoItem]:
        cart = (self.coordinator.data or {}).get(DATA_CART) or {}
        lines = _extract_cart_lines(cart)
        out: list[TodoItem] = []
        for line in lines:
            qty_prefix = f"(x{line['count']}) "
            price_txt = (
                f"  {line['price_cents'] / 100:.2f} €"
                if isinstance(line["price_cents"], int) else ""
            )
            unit_txt = f" [{line['unit_quantity']}]" if line.get("unit_quantity") else ""
            summary = f"{qty_prefix}{line['name']}{unit_txt}{price_txt}"
            out.append(
                TodoItem(
                    uid=line["id"],
                    summary=summary,
                    status=TodoItemStatus.NEEDS_ACTION,
                )
            )
        return out

    # --- Mutations --------------------------------------------------------

    async def async_create_todo_item(self, item: TodoItem) -> None:
        items = parse_multi_items(item.summary or "")
        if not items:
            raise ValueError("Saisie vide.")

        history = (self.coordinator.data or {}).get(DATA_HISTORY) or {}
        added: list[str] = []
        failed: list[str] = []

        for query, qty in items:
            try:
                match = await self.coordinator.client.resolve_query(query, history)
            except PicnicError as exc:
                _LOGGER.warning("Resolve failed for %r: %s", query, exc)
                failed.append(query)
                continue
            if match is None:
                _LOGGER.warning("No match for %r — skipped.", query)
                failed.append(query)
                continue
            try:
                await self.coordinator.client.add_product(match.product_id, count=qty)
                added.append(f"{match.name} x{qty}")
            except PicnicError as exc:
                _LOGGER.error("Cart add failed for %s: %s", match.product_id, exc)
                failed.append(query)

        # Single refresh after all adds, so the cart-mirrored list updates once.
        await self.coordinator.async_refresh()

        if not added and failed:
            raise ValueError(
                f"Aucun produit ajouté. Échecs : {', '.join(failed)}"
            )
        if failed:
            _LOGGER.warning("Items added but with %d failure(s): %s", len(failed), failed)

    async def _remove_line(self, product_id: str) -> None:
        """Fully remove a cart line, using the actual count if known."""
        cart = (self.coordinator.data or {}).get(DATA_CART) or {}
        count = 99
        for line in _extract_cart_lines(cart):
            if line["id"] == product_id:
                count = line["count"]
                break
        try:
            await self.coordinator.client.remove_product(product_id, count=count)
            _LOGGER.info("Removed %sx%d from Picnic cart", product_id, count)
        except PicnicError as exc:
            _LOGGER.warning("Cart remove failed for %s (count=%d): %s", product_id, count, exc)
            raise

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        _LOGGER.debug("async_delete_todo_items called with uids=%s", uids)
        for uid in uids:
            try:
                await self._remove_line(uid)
            except PicnicError:
                pass
        await self.coordinator.async_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Some HA frontends delete by updating status to COMPLETED instead of
        calling delete. Treat a completion transition as a removal."""
        _LOGGER.debug(
            "async_update_todo_item called uid=%s status=%s summary=%s",
            item.uid, item.status, item.summary,
        )
        if item.uid and item.status == TodoItemStatus.COMPLETED:
            try:
                await self._remove_line(item.uid)
            except PicnicError:
                pass
            await self.coordinator.async_refresh()
