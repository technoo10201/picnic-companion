"""Config flow for Picnic Companion: login → 2FA SMS → confirmation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import PicnicAsyncClient, PicnicAuthError, PicnicError, decode_token_exp
from .const import (
    CONF_AUTH_KEY,
    CONF_COUNTRY,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TOKEN_EXP,
    CONF_TOKEN_IAT,
    DEFAULT_COUNTRY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_COUNTRY, default=DEFAULT_COUNTRY): vol.In(["FR", "NL", "DE", "BE"]),
    }
)

STEP_2FA_SCHEMA = vol.Schema({vol.Required("code"): str})


class PicnicFRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the multi-step Picnic Companion login."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._country: str = DEFAULT_COUNTRY
        self._client: PicnicAsyncClient | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    # --- Step 1: email + password -----------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._country = user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY)

            await self.async_set_unique_id(f"{self._country}:{self._email.lower()}")
            if not self._reauth_entry:
                self._abort_if_unique_id_configured()

            self._client = PicnicAsyncClient(self.hass, country=self._country)
            try:
                result = await self._client.login(self._email, user_input[CONF_PASSWORD])
            except PicnicAuthError as exc:
                _LOGGER.warning("Picnic auth error: %s", exc)
                errors["base"] = "invalid_auth"
            except PicnicError as exc:
                _LOGGER.exception("Picnic API error during login")
                errors["base"] = "cannot_connect"
            else:
                requires_2fa = bool(
                    isinstance(result, dict)
                    and result.get("second_factor_authentication_required")
                )
                if requires_2fa:
                    try:
                        await self._client.generate_2fa("SMS")
                    except PicnicError:
                        _LOGGER.exception("Could not trigger 2FA SMS")
                        errors["base"] = "sms_failed"
                    else:
                        return await self.async_step_two_factor()
                else:
                    return await self._finalize()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    # --- Step 2: SMS code -------------------------------------------------

    async def async_step_two_factor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._client is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._client.verify_2fa(user_input["code"].strip())
            except PicnicAuthError:
                errors["base"] = "invalid_2fa"
            except PicnicError:
                _LOGGER.exception("2FA verification failed")
                errors["base"] = "cannot_connect"
            else:
                return await self._finalize()

        return self.async_show_form(
            step_id="two_factor",
            data_schema=STEP_2FA_SCHEMA,
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    # --- Final: persist entry ---------------------------------------------

    async def _finalize(self) -> FlowResult:
        assert self._client is not None
        auth_key = self._client.auth_key or ""
        iat, exp = decode_token_exp(auth_key)

        data = {
            CONF_EMAIL: self._email,
            CONF_COUNTRY: self._country,
            CONF_AUTH_KEY: auth_key,
            CONF_TOKEN_IAT: iat,
            CONF_TOKEN_EXP: exp,
        }

        if self._reauth_entry:
            self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        title = f"Picnic Companion ({self._email})"
        exp_human = (
            datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%d/%m/%Y")
            if exp
            else "—"
        )
        return self.async_create_entry(
            title=title,
            data=data,
            description=f"Token valide jusqu'au {exp_human}",
        )

    # --- Re-auth flow -----------------------------------------------------

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reauth_entry:
            self._email = self._reauth_entry.data.get(CONF_EMAIL)
            self._country = self._reauth_entry.data.get(CONF_COUNTRY, DEFAULT_COUNTRY)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={"email": self._email or ""},
            )
        return await self.async_step_user()
