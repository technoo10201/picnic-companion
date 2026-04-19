"""Picnic Companion integration setup, services, and repair scheduling."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import issue_registry as ir

from .api import PicnicAsyncClient, PicnicError
from .const import (
    CONF_AUTH_KEY,
    CONF_COUNTRY,
    CONF_TOKEN_EXP,
    DEFAULT_COUNTRY,
    DOMAIN,
    ISSUE_TOKEN_EXPIRED,
    ISSUE_TOKEN_EXPIRING,
    SERVICE_ADD_RECIPE,
    SERVICE_BOOK_SLOT,
    SERVICE_CHECKOUT,
    SERVICE_CLEAR_CART,
    SERVICE_PUSH_LIST,
    SERVICE_REFRESH_HISTORY,
    TOKEN_RENEWAL_WARNING_DAYS,
)
from .coordinator import PicnicFRCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TODO,
]

PUSH_LIST_SCHEMA = vol.Schema(
    {
        vol.Required("items"): vol.All(
            cv.ensure_list,
            [
                vol.Any(
                    cv.string,
                    vol.Schema(
                        {
                            vol.Required("query"): cv.string,
                            vol.Optional("count", default=1): vol.All(int, vol.Range(min=1, max=99)),
                        }
                    ),
                )
            ],
        ),
        vol.Optional("clear_first", default=False): cv.boolean,
    }
)

BOOK_SLOT_SCHEMA = vol.Schema({vol.Required("slot_id"): cv.string})

ADD_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required("recipe_id"): cv.string,
        vol.Optional("portions"): vol.All(int, vol.Range(min=1, max=12)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Picnic Companion from a config entry."""
    country = entry.data.get(CONF_COUNTRY, DEFAULT_COUNTRY)
    auth_key = entry.data.get(CONF_AUTH_KEY)

    client = PicnicAsyncClient(hass, country=country, auth_key=auth_key)

    coordinator = PicnicFRCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)

    # Periodic token-expiry check (once a day)
    async def _check_token(_now: datetime) -> None:
        await _evaluate_token_expiry(hass, entry)

    entry.async_on_unload(
        async_track_time_interval(hass, _check_token, timedelta(hours=24))
    )
    await _evaluate_token_expiry(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


# --- Token expiry watcher ---------------------------------------------------


async def _evaluate_token_expiry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    exp = entry.data.get(CONF_TOKEN_EXP)
    if not exp:
        return
    now = datetime.now(tz=timezone.utc).timestamp()
    seconds_left = exp - now

    if seconds_left <= 0:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_TOKEN_EXPIRED,
            is_fixable=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_TOKEN_EXPIRED,
            data={"entry_id": entry.entry_id},
        )
        return

    days_left = seconds_left / 86400
    if days_left <= TOKEN_RENEWAL_WARNING_DAYS:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_TOKEN_EXPIRING,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_TOKEN_EXPIRING,
            translation_placeholders={"days": str(int(days_left))},
            data={"entry_id": entry.entry_id},
        )
    else:
        # Far enough — clear any stale issue
        ir.async_delete_issue(hass, DOMAIN, ISSUE_TOKEN_EXPIRING)
        ir.async_delete_issue(hass, DOMAIN, ISSUE_TOKEN_EXPIRED)


# --- Services ---------------------------------------------------------------


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_PUSH_LIST):
        return

    def _coordinator_for_entry_id(entry_id: str | None) -> PicnicFRCoordinator | None:
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            return hass.data[DOMAIN][entry_id]
        # No entry_id given: pick the first one
        coords = hass.data.get(DOMAIN, {})
        return next(iter(coords.values()), None)

    async def push_list(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        if call.data.get("clear_first"):
            await coord.client.clear_cart()
        items = call.data["items"]
        history = (coord.data or {}).get("history", {})
        for raw in items:
            if isinstance(raw, str):
                query, count = raw, 1
            else:
                query, count = raw["query"], int(raw.get("count", 1))
            try:
                match = await coord.client.resolve_query(query, history)
            except PicnicError as exc:
                _LOGGER.warning("resolve failed for %s: %s", query, exc)
                continue
            if not match:
                _LOGGER.warning("no match for %r", query)
                continue
            try:
                await coord.client.add_product(match.product_id, count=count)
                _LOGGER.info("pushed %s x%d (%s, %s)", match.product_id, count, match.name, match.source)
            except PicnicError as exc:
                _LOGGER.error("add failed for %s: %s", match.product_id, exc)
        await coord.async_request_refresh()

    async def clear_cart(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        await coord.client.clear_cart()
        await coord.async_request_refresh()

    async def book_slot(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        await coord.client.book_slot(call.data["slot_id"])
        await coord.async_request_refresh()

    async def checkout(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        try:
            await coord.client.checkout()
        except PicnicError as exc:
            _LOGGER.error("checkout failed: %s", exc)
            raise
        await coord.async_request_refresh()

    async def refresh_history(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        await coord.async_force_history_refresh()
        await coord.async_request_refresh()

    async def arm_clear_cart(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        coord.arm_clear_cart()

    async def confirm_clear_cart(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        await coord.confirm_clear_cart()

    async def add_recipe_to_cart(call: ServiceCall) -> None:
        coord = _coordinator_for_entry_id(call.data.get("entry_id"))
        if coord is None:
            return
        recipe_id = call.data["recipe_id"]
        portions = call.data.get("portions")
        try:
            result = await coord.client.add_recipe_to_cart(recipe_id, portions=portions)
        except PicnicError as exc:
            _LOGGER.error("add_recipe_to_cart failed: %s", exc)
            raise
        _LOGGER.info(
            "Recipe %s (%s) — added: %d, failed: %d",
            recipe_id, result.get("name"), len(result["added"]), len(result["failed"]),
        )
        await coord.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_PUSH_LIST, push_list, schema=PUSH_LIST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_CART, clear_cart)
    hass.services.async_register(DOMAIN, SERVICE_BOOK_SLOT, book_slot, schema=BOOK_SLOT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CHECKOUT, checkout)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH_HISTORY, refresh_history)
    hass.services.async_register(DOMAIN, "arm_clear_cart", arm_clear_cart)
    hass.services.async_register(DOMAIN, "confirm_clear_cart", confirm_clear_cart)
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_RECIPE, add_recipe_to_cart, schema=ADD_RECIPE_SCHEMA
    )
