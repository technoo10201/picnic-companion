"""High-level Picnic client — entry point for users of the library."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .domains import (
    AuthDomain,
    CartDomain,
    CatalogDomain,
    ConsentDomain,
    DeliveryDomain,
    MessagesDomain,
    PaymentDomain,
    RecipesDomain,
    StaticContentDomain,
    UserDomain,
)
from .session import DEFAULT_API_VERSION, PicnicSession


class PicnicClient:
    """Main entry point. Domain services are exposed as attributes.

    Example
    -------
    >>> client = PicnicClient(country_code="FR", auth_key_path="~/.picnic/auth.json")
    >>> if not client.authenticated:
    ...     client.auth.login("me@example.com", "hunter2")
    >>> results = client.catalog.search("spaghetti")
    >>> client.cart.add_product(results[0]["items"][0]["id"], count=1)
    """

    def __init__(
        self,
        country_code: str = "NL",
        api_version: str = DEFAULT_API_VERSION,
        auth_key: str | None = None,
        auth_key_path: str | Path | None = None,
        base_url: str | None = None,
        timeout: float = 15.0,
    ):
        # Expand `~` for convenience
        if isinstance(auth_key_path, str):
            auth_key_path = Path(auth_key_path).expanduser()

        self._session = PicnicSession(
            country_code=country_code,
            api_version=api_version,
            auth_key=auth_key,
            auth_key_path=auth_key_path,
            base_url=base_url,
            timeout=timeout,
        )

        # Domain services
        self.auth = AuthDomain(self._session)
        self.catalog = CatalogDomain(self._session)
        self.cart = CartDomain(self._session)
        self.delivery = DeliveryDomain(self._session)
        self.user = UserDomain(self._session)
        self.payment = PaymentDomain(self._session)
        self.recipes = RecipesDomain(self._session)
        self.messages = MessagesDomain(self._session)
        self.consent = ConsentDomain(self._session)
        self.static = StaticContentDomain(self._session)

    # --- Convenience pass-through -----------------------------------------

    @property
    def authenticated(self) -> bool:
        return self._session.authenticated

    @property
    def auth_key(self) -> str | None:
        return self._session.auth_key

    @property
    def country_code(self) -> str:
        return self._session.country_code

    @property
    def base_url(self) -> str:
        return self._session.base_url

    def send_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Escape hatch for endpoints not yet covered by a domain."""
        return self._session.request(method, path, **kwargs)

    # --- Context manager ---------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Persist key on clean exit; do not call logout (would invalidate the key)
        if self._session.auth_key_path:
            self._session.persist_auth_key()
