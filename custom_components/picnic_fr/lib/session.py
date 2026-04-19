"""HTTP session layer for the Picnic API.

Handles:
- Base URL construction per country code
- Password hashing (MD5, as used by the official mobile app)
- Auth header injection (`x-picnic-auth`)
- Persistence of the auth key on disk (optional)
- Centralized error mapping
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import requests

from .exceptions import (
    PicnicAuthError,
    PicnicCountryNotSupportedError,
    PicnicError,
    PicnicNotFoundError,
    PicnicRateLimitError,
)

log = logging.getLogger(__name__)

DEFAULT_API_VERSION = "15"
DEFAULT_CLIENT_ID = 30100  # observed in mobile app traffic
DEFAULT_CLIENT_VERSION = "1.15.232"
SUPPORTED_COUNTRIES = {"NL", "DE", "BE", "FR"}  # FR untested upstream
URL_TEMPLATE = "https://storefront-prod.{cc}.picnicinternational.com/api/{version}"

DEFAULT_HEADERS = {
    "User-Agent": "okhttp/4.12.0",  # mimic the Android app
    "Content-Type": "application/json; charset=UTF-8",
    "x-picnic-agent": f"30100;{DEFAULT_CLIENT_VERSION};",
    "x-picnic-did": "3C417201548B2E3B",  # device id; arbitrary but stable
}


def hash_password(password: str) -> str:
    """Picnic hashes passwords with MD5 before sending."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


class PicnicSession:
    """Thin wrapper around `requests.Session` with Picnic-specific concerns."""

    def __init__(
        self,
        country_code: str = "NL",
        api_version: str = DEFAULT_API_VERSION,
        auth_key: str | None = None,
        auth_key_path: str | Path | None = None,
        base_url: str | None = None,
        timeout: float = 15.0,
    ):
        cc = country_code.upper()
        if cc not in SUPPORTED_COUNTRIES:
            raise PicnicCountryNotSupportedError(
                f"Country '{cc}' is not in the known list {sorted(SUPPORTED_COUNTRIES)}. "
                f"FR is supported but untested upstream — pass it explicitly if you accept the risk."
            )
        self.country_code = cc
        self.api_version = api_version
        self.timeout = timeout
        self.base_url = base_url or URL_TEMPLATE.format(cc=cc.lower(), version=api_version)
        self.auth_key_path = Path(auth_key_path) if auth_key_path else None

        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

        # Resolve auth key precedence: explicit > file
        if auth_key:
            self.auth_key = auth_key
        elif self.auth_key_path and self.auth_key_path.exists():
            self.auth_key = self._load_auth_key()
        else:
            self.auth_key = None

    # --- Auth key persistence ----------------------------------------------

    @property
    def auth_key(self) -> str | None:
        return self._auth_key

    @auth_key.setter
    def auth_key(self, value: str | None) -> None:
        self._auth_key = value
        if value:
            self._session.headers["x-picnic-auth"] = value
        else:
            self._session.headers.pop("x-picnic-auth", None)

    def _load_auth_key(self) -> str | None:
        try:
            data = json.loads(self.auth_key_path.read_text())
            return data.get(self.country_code)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load auth key from %s: %s", self.auth_key_path, exc)
            return None

    def persist_auth_key(self) -> None:
        """Write the current auth key to disk (keyed by country code).

        If the in-memory key has been cleared (logout), remove the entry.
        """
        if not self.auth_key_path:
            return
        data: dict[str, str] = {}
        if self.auth_key_path.exists():
            try:
                data = json.loads(self.auth_key_path.read_text())
            except json.JSONDecodeError:
                data = {}
        if self._auth_key:
            data[self.country_code] = self._auth_key
        else:
            data.pop(self.country_code, None)
        self.auth_key_path.parent.mkdir(parents=True, exist_ok=True)
        self.auth_key_path.write_text(json.dumps(data, indent=2))
        try:
            self.auth_key_path.chmod(0o600)
        except OSError:
            pass

    @property
    def authenticated(self) -> bool:
        return bool(self._auth_key)

    # --- HTTP --------------------------------------------------------------

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an HTTP request and return parsed JSON (or raw text on non-JSON)."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)

        log.debug("%s %s", method, url)
        resp = self._session.request(method, url, **kwargs)

        # Capture rotated auth key, if Picnic returns one
        new_key = resp.headers.get("x-picnic-auth")
        if new_key and new_key != self._auth_key:
            self.auth_key = new_key
            if self.auth_key_path:
                self.persist_auth_key()

        self._raise_for_status(resp)

        if not resp.content:
            return None
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct:
            return resp.json()
        return resp.text

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.ok:
            return
        try:
            payload = resp.json()
        except ValueError:
            payload = resp.text

        msg = f"HTTP {resp.status_code} on {resp.request.method} {resp.request.url}: {payload}"
        if resp.status_code in (401, 403):
            raise PicnicAuthError(msg, resp.status_code, payload)
        if resp.status_code == 404:
            raise PicnicNotFoundError(msg, resp.status_code, payload)
        if resp.status_code == 429:
            raise PicnicRateLimitError(msg, resp.status_code, payload)
        raise PicnicError(msg, resp.status_code, payload)

    # Convenience verbs
    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json_body: Any = None, **kwargs):
        if json_body is not None:
            kwargs["json"] = json_body
        return self.request("POST", path, **kwargs)

    def put(self, path: str, json_body: Any = None, **kwargs):
        if json_body is not None:
            kwargs["json"] = json_body
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)
