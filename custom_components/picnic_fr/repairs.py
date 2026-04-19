"""Repair flow: re-trigger config flow when token is expiring or expired."""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, ISSUE_TOKEN_EXPIRED, ISSUE_TOKEN_EXPIRING


class TokenRepairFlow(RepairsFlow):
    """Open the reauth flow."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry:
                entry.async_start_reauth(self.hass)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="confirm", data_schema=None)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    if issue_id in (ISSUE_TOKEN_EXPIRING, ISSUE_TOKEN_EXPIRED) and data:
        return TokenRepairFlow(entry_id=data["entry_id"])
    return ConfirmRepairFlow()
