"""Async wrapper around the vendored picnic_fr library.

The lib is synchronous (uses `requests`). Every call goes through HA's executor
so we don't block the event loop.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from .lib import PicnicAuthError, PicnicClient, PicnicError  # type: ignore[attr-defined]
from .lib.shopping import MatchResult, match_query  # type: ignore[attr-defined]

_LOGGER = logging.getLogger(__name__)


def decode_token_exp(auth_key: str) -> tuple[int | None, int | None]:
    """Return (iat, exp) in epoch seconds from a Picnic JWT, or (None, None)."""
    if not auth_key or auth_key.count(".") != 2:
        return (None, None)
    payload = auth_key.split(".")[1]
    pad = payload + "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(pad))
    except (ValueError, json.JSONDecodeError):
        return (None, None)
    return (data.get("iat"), data.get("exp"))


def token_expires_at(auth_key: str) -> datetime | None:
    _, exp = decode_token_exp(auth_key)
    if exp is None:
        return None
    return datetime.fromtimestamp(exp, tz=timezone.utc)


class PicnicAsyncClient:
    """Asyncio-friendly facade around `PicnicClient`.

    All blocking calls are run via `hass.async_add_executor_job`. The underlying
    client is *not* thread-safe; we serialize calls implicitly by awaiting them.
    """

    def __init__(self, hass: HomeAssistant, *, country: str = "FR", auth_key: str | None = None):
        self.hass = hass
        self._client = PicnicClient(country_code=country, auth_key=auth_key)

    # --- Properties --------------------------------------------------------

    @property
    def authenticated(self) -> bool:
        return self._client.authenticated

    @property
    def auth_key(self) -> str | None:
        return self._client.auth_key

    @property
    def base_url(self) -> str:
        return self._client.base_url

    @property
    def country_code(self) -> str:
        return self._client.country_code

    # --- Auth --------------------------------------------------------------

    async def login(self, email: str, password: str) -> dict[str, Any] | None:
        return await self.hass.async_add_executor_job(self._client.auth.login, email, password)

    async def generate_2fa(self, channel: str = "SMS") -> Any:
        return await self.hass.async_add_executor_job(
            self._client.auth.generate_2fa_code, channel
        )

    async def verify_2fa(self, code: str) -> Any:
        return await self.hass.async_add_executor_job(self._client.auth.verify_2fa_code, code)

    async def whoami(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._client.user.me)

    # --- Cart --------------------------------------------------------------

    async def get_cart(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._client.cart.get)

    async def add_product(self, product_id: str, count: int = 1) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(
            self._client.cart.add_product, product_id, count
        )

    async def remove_product(self, product_id: str, count: int = 1) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(
            self._client.cart.remove_product, product_id, count
        )

    async def clear_cart(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._client.cart.clear)

    async def get_slots_by_day(self) -> dict[str, list[dict]]:
        return await self.hass.async_add_executor_job(
            self._client.cart.available_slots_by_day
        )

    async def get_selected_slot(self) -> dict[str, Any] | None:
        return await self.hass.async_add_executor_job(self._client.cart.selected_slot)

    async def book_slot(self, slot_id: str) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(
            self._client.cart.set_delivery_slot, slot_id
        )

    async def checkout(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._client.cart.checkout)

    # --- History -----------------------------------------------------------

    async def product_frequency(self) -> dict[str, dict]:
        return await self.hass.async_add_executor_job(
            self._client.delivery.product_frequency
        )

    async def deliveries(self) -> list[dict]:
        return await self.hass.async_add_executor_job(self._client.delivery.list)

    async def current_delivery(self) -> dict[str, Any] | None:
        """Return the single pending delivery, or None if there's nothing in
        flight. Picnic allows only one pending order per household."""
        items = await self.hass.async_add_executor_job(self._client.delivery.current)
        return items[0] if items else None

    # --- Catalog -----------------------------------------------------------

    async def search_flat(self, query: str) -> list[dict]:
        return await self.hass.async_add_executor_job(self._client.catalog.search_flat, query)

    # --- Recipes -----------------------------------------------------------

    async def saved_recipe_ids(self) -> list[str]:
        return await self.hass.async_add_executor_job(self._client.recipes.list_saved)

    async def ordered_recipe_ids(self) -> list[str]:
        return await self.hass.async_add_executor_job(self._client.recipes.list_ordered)

    async def recipe_info(self, recipe_id: str) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._client.recipes.info, recipe_id)

    async def add_recipe_to_cart(self, recipe_id: str, portions: int | None = None) -> dict:
        if portions is None:
            return await self.hass.async_add_executor_job(
                self._client.recipes.add_to_cart, recipe_id
            )
        return await self.hass.async_add_executor_job(
            self._client.recipes.add_to_cart, recipe_id, portions
        )

    async def resolve_query(
        self, query: str, history: dict[str, dict]
    ) -> MatchResult | None:
        """Run the smart matcher: prefer history hits over fresh catalog matches."""
        # Try search with progressive simplification, like in shopping.py
        tokens = query.split()
        catalog: list[dict] = []
        for _ in range(min(4, len(tokens))):
            attempt = " ".join(tokens)
            catalog = await self.search_flat(attempt)
            if catalog:
                break
            if len(tokens) <= 1:
                break
            tokens.pop()
        return match_query(query, catalog_results=catalog, history=history)


__all__ = [
    "PicnicAsyncClient",
    "PicnicAuthError",
    "PicnicError",
    "MatchResult",
    "decode_token_exp",
    "token_expires_at",
]
