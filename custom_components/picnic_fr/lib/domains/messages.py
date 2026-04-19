"""Customer messages, reminders, parcels."""

from __future__ import annotations

from ._base import BaseDomain


class MessagesDomain(BaseDomain):
    def inbox(self) -> list[dict]:
        return self._s.get("/messages")

    def reminders(self) -> list[dict]:
        return self._s.get("/reminders")

    def parcels(self) -> list[dict]:
        return self._s.get("/parcels")

    def contact_info(self) -> dict:
        return self._s.get("/contact/info")
