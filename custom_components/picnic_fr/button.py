"""Buttons: refresh + clear-cart (confirmation) + one-per-liked-recipe.

The recipe buttons are created dynamically from the coordinator's saved-recipe
list on each update: new likes → new buttons, unliked recipes → entity removal.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PicnicError
from .const import DATA_ORDERED_RECIPES, DATA_SAVED_RECIPES, DOMAIN
from .coordinator import PicnicFRCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: PicnicFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PicnicRefreshButton(coord, entry),
            PicnicRefreshHistoryButton(coord, entry),
            PicnicClearCartButton(coord, entry),
        ]
    )

    # Dynamic buttons — one per saved (★ enregistrée) + one per ordered recipe
    saved_mgr = RecipeButtonsManager(
        hass, entry, coord, async_add_entities,
        data_key=DATA_SAVED_RECIPES,
        prefix="Enregistrée",
        icon="mdi:heart",
        unique_suffix="saved",
    )
    ordered_mgr = RecipeButtonsManager(
        hass, entry, coord, async_add_entities,
        data_key=DATA_ORDERED_RECIPES,
        prefix="Commandée",
        icon="mdi:chef-hat",
        unique_suffix="ordered",
    )
    entry.async_on_unload(coord.async_add_listener(saved_mgr.sync))
    entry.async_on_unload(coord.async_add_listener(ordered_mgr.sync))
    saved_mgr.sync()
    ordered_mgr.sync()


class _BaseButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PicnicFRCoordinator, entry: ConfigEntry) -> None:
        self._coord = coordinator
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


class PicnicRefreshButton(_BaseButton):
    """Force an immediate cart/slot refresh."""

    _key = "refresh_now"
    _attr_name = "Synchroniser maintenant"
    _attr_icon = "mdi:cart-arrow-down"

    async def async_press(self) -> None:
        await self._coord.async_refresh()


class PicnicRefreshHistoryButton(_BaseButton):
    """Force an order-history refresh (rebuilds the matcher cache)."""

    _key = "refresh_history"
    _attr_name = "Rafraîchir l'historique"
    _attr_icon = "mdi:history"

    async def async_press(self) -> None:
        await self._coord.async_force_history_refresh()
        await self._coord.async_refresh()


class PicnicRecipeButton(_BaseButton):
    """One-click button to add a recipe's ingredients to the cart."""

    def __init__(
        self,
        coordinator: PicnicFRCoordinator,
        entry: ConfigEntry,
        recipe: dict[str, Any],
        *,
        prefix: str,
        icon: str,
        unique_suffix: str,
    ) -> None:
        self._recipe = recipe
        self._attr_icon = icon
        # `_key` feeds the unique_id; tag with saved/ordered so HA doesn't
        # clash if a recipe appears in both lists.
        self._key = f"recipe_{unique_suffix}_{recipe['id']}"
        name = recipe.get("name") or recipe["id"]
        self._attr_name = f"{prefix} · {name}"
        super().__init__(coordinator, entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "recipe_id": self._recipe["id"],
            "recipe_name": self._recipe.get("name"),
            "default_portions": self._recipe.get("default_portions"),
        }

    async def async_press(self) -> None:
        rid = self._recipe["id"]
        try:
            result = await self._coord.client.add_recipe_to_cart(rid)
        except PicnicError as exc:
            _LOGGER.error("add recipe %s failed: %s", rid, exc)
            raise
        _LOGGER.info(
            "Recette '%s' : %d ingrédient(s) ajouté(s), %d échec(s)",
            self._recipe.get("name") or rid,
            len(result["added"]),
            len(result["failed"]),
        )
        await self._coord.async_refresh()


class RecipeButtonsManager:
    """Sync one PicnicRecipeButton per recipe in a given list."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: PicnicFRCoordinator,
        async_add_entities: AddEntitiesCallback,
        *,
        data_key: str,
        prefix: str,
        icon: str,
        unique_suffix: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coord = coordinator
        self.add = async_add_entities
        self.data_key = data_key
        self.prefix = prefix
        self.icon = icon
        self.unique_suffix = unique_suffix
        self._entities: dict[str, PicnicRecipeButton] = {}

    def sync(self) -> None:
        recipes = (self.coord.data or {}).get(self.data_key) or []
        current_ids = {r["id"] for r in recipes if r.get("id")}
        new_entities = []
        for r in recipes:
            rid = r.get("id")
            if not rid or rid in self._entities:
                continue
            ent = PicnicRecipeButton(
                self.coord, self.entry, r,
                prefix=self.prefix, icon=self.icon,
                unique_suffix=self.unique_suffix,
            )
            self._entities[rid] = ent
            new_entities.append(ent)
        if new_entities:
            self.add(new_entities)
        to_remove = [rid for rid in self._entities if rid not in current_ids]
        for rid in to_remove:
            ent = self._entities.pop(rid)
            self.hass.async_create_task(ent.async_remove(force_remove=True))


class PicnicClearCartButton(_BaseButton):
    """Clear the entire cart with double-click confirmation.

    Also wired to the `picnic_fr.arm_clear_cart` and `picnic_fr.confirm_clear_cart`
    services, so you can bind long-press (arm) + tap (confirm) on a dashboard
    tile card via `hold_action` / `tap_action`.
    """

    _key = "clear_cart"
    _attr_name = "Vider le panier"
    _attr_icon = "mdi:cart-remove"

    @property
    def icon(self) -> str:
        return "mdi:cart-off" if self._coord.is_clear_cart_armed() else "mdi:cart-remove"

    async def async_press(self) -> None:
        await self._coord.request_clear_cart()
        self.async_write_ha_state()
