"""Polling coordinator for Picnic Companion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PicnicAsyncClient, PicnicAuthError
from datetime import timedelta

from .api import PicnicError
from .const import (
    CONF_AUTH_KEY,
    CONF_POLL_INTERVAL,
    CONF_TOKEN_EXP,
    DATA_CART,
    DATA_DELIVERIES,
    DATA_HISTORY,
    DATA_ORDERED_RECIPES,
    DATA_SAVED_RECIPES,
    DATA_SLOT,
    DATA_SLOTS,
    DEFAULT_POLL_INTERVAL_MIN,
    DOMAIN,
    HISTORY_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class PicnicFRCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Periodically refresh cart, slots and (less often) order history."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PicnicAsyncClient,
    ) -> None:
        interval_min = int(
            (entry.options or {}).get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MIN)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.title}",
            update_interval=timedelta(minutes=interval_min),
        )
        self.entry = entry
        self.client = client
        self._history_cache: dict[str, dict] | None = None
        self._history_fetched_at: datetime | None = None
        self.auth_failed = False
        self._clear_cart_armed_until: datetime | None = None
        self._cancel_disarm = None
        self._saved_recipes_cache: list[dict] | None = None
        self._ordered_recipes_cache: list[dict] | None = None

    def set_poll_interval(self, minutes: int) -> None:
        """Adjust the coordinator polling interval at runtime."""
        self.update_interval = timedelta(minutes=max(1, int(minutes)))
        # Reschedule next refresh using the new interval.
        self._schedule_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            cart = await self.client.get_cart()
            slots = await self.client.get_slots_by_day()
            selected = await self.client.get_selected_slot()
        except PicnicAuthError as exc:
            self.auth_failed = True
            raise UpdateFailed(f"Authentication failed — re-auth required: {exc}") from exc
        except PicnicError as exc:
            raise UpdateFailed(f"Picnic API error: {exc}") from exc

        if self._needs_history_refresh():
            try:
                self._history_cache = await self.client.product_frequency()
                self._history_fetched_at = datetime.now(timezone.utc)
            except PicnicError as exc:
                _LOGGER.warning("History refresh failed (keeping previous): %s", exc)

        try:
            deliveries = await self.client.deliveries()
        except PicnicError:
            deliveries = []

        # Refresh saved + ordered recipes alongside the history (same cadence)
        if self._saved_recipes_cache is None or self._needs_history_refresh():
            await self._refresh_recipe_lists()

        # Capture rotated auth key, if any
        new_key = self.client.auth_key
        if new_key and new_key != self.entry.data.get(CONF_AUTH_KEY):
            from .api import decode_token_exp
            iat, exp = decode_token_exp(new_key)
            new_data = {
                **self.entry.data,
                CONF_AUTH_KEY: new_key,
                "token_iat": iat,
                CONF_TOKEN_EXP: exp,
            }
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            _LOGGER.info("Rotated Picnic auth key (new exp: %s)", exp)

        return {
            DATA_CART: cart,
            DATA_SLOT: selected,
            DATA_SLOTS: slots,
            DATA_HISTORY: self._history_cache or {},
            DATA_DELIVERIES: deliveries,
            DATA_SAVED_RECIPES: self._saved_recipes_cache or [],
            DATA_ORDERED_RECIPES: self._ordered_recipes_cache or [],
        }

    def _needs_history_refresh(self) -> bool:
        if self._history_cache is None:
            return True
        if self._history_fetched_at is None:
            return True
        age = datetime.now(timezone.utc) - self._history_fetched_at
        return age > HISTORY_REFRESH_INTERVAL

    async def async_force_history_refresh(self) -> None:
        try:
            self._history_cache = await self.client.product_frequency()
            self._history_fetched_at = datetime.now(timezone.utc)
        except PicnicError as exc:
            _LOGGER.error("Forced history refresh failed: %s", exc)
            raise

    async def _enrich(self, ids: list[str]) -> list[dict]:
        enriched = []
        for rid in ids:
            try:
                info = await self.client.recipe_info(rid)
                enriched.append(info)
            except PicnicError:
                enriched.append({"id": rid, "name": None})
        return enriched

    async def _refresh_recipe_lists(self) -> None:
        try:
            saved_ids = await self.client.saved_recipe_ids()
            self._saved_recipes_cache = await self._enrich(saved_ids)
        except PicnicError as exc:
            _LOGGER.warning("Saved recipes fetch failed: %s", exc)
        try:
            ordered_ids = await self.client.ordered_recipe_ids()
            self._ordered_recipes_cache = await self._enrich(ordered_ids)
        except PicnicError as exc:
            _LOGGER.warning("Ordered recipes fetch failed: %s", exc)

    async def async_refresh_saved_recipes(self) -> None:
        await self._refresh_recipe_lists()

    # --- Clear cart two-step confirmation -----------------------------------

    @property
    def _clear_cart_notif_id(self) -> str:
        return f"{DOMAIN}_clear_cart_{self.entry.entry_id}"

    def is_clear_cart_armed(self) -> bool:
        return (
            self._clear_cart_armed_until is not None
            and datetime.now(timezone.utc) < self._clear_cart_armed_until
        )

    @callback
    def _disarm_clear_cart(self, *_: Any) -> None:
        self._clear_cart_armed_until = None
        if self._cancel_disarm:
            self._cancel_disarm()
            self._cancel_disarm = None
        persistent_notification.async_dismiss(self.hass, self._clear_cart_notif_id)

    def arm_clear_cart(self, window_seconds: int = 10) -> None:
        """Arm the clear-cart confirmation. Auto-disarms after the window."""
        from datetime import timedelta as _td
        self._clear_cart_armed_until = datetime.now(timezone.utc) + _td(seconds=window_seconds)
        if self._cancel_disarm:
            self._cancel_disarm()
        self._cancel_disarm = async_call_later(
            self.hass, float(window_seconds), self._disarm_clear_cart
        )
        persistent_notification.async_create(
            self.hass,
            message=(
                f"⚠️ Confirmation requise. Clique (clic court) sur **Vider le panier** "
                f"dans les {window_seconds} secondes pour valider. "
                "Sinon l'action est annulée."
            ),
            title="Picnic — Vider le panier",
            notification_id=self._clear_cart_notif_id,
        )
        _LOGGER.info("Clear cart armed (%ss window)", window_seconds)

    async def confirm_clear_cart(self) -> bool:
        """Fire the clear if armed. Returns True on success, False if not armed."""
        if not self.is_clear_cart_armed():
            persistent_notification.async_create(
                self.hass,
                message=(
                    "Aucune action à confirmer. Fais d'abord un **appui long** sur le "
                    "bouton pour armer la suppression."
                ),
                title="Picnic — Vider le panier",
                notification_id=self._clear_cart_notif_id,
            )
            return False
        self._disarm_clear_cart()
        try:
            await self.client.clear_cart()
        except PicnicError as exc:
            _LOGGER.error("Clear cart failed: %s", exc)
            persistent_notification.async_create(
                self.hass,
                message=f"Échec : {exc}",
                title="Picnic — Vider le panier",
                notification_id=self._clear_cart_notif_id,
            )
            raise
        await self.async_refresh()
        persistent_notification.async_create(
            self.hass,
            message="✅ Panier Picnic vidé.",
            title="Picnic — Vider le panier",
            notification_id=self._clear_cart_notif_id,
        )
        _LOGGER.info("Picnic cart cleared (confirmed)")
        return True

    async def request_clear_cart(self) -> None:
        """Single entry point: arm on first call, fire on second within window."""
        if self.is_clear_cart_armed():
            await self.confirm_clear_cart()
        else:
            self.arm_clear_cart()
