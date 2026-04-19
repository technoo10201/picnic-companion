"""GDPR consent settings."""

from __future__ import annotations

from ._base import BaseDomain


class ConsentDomain(BaseDomain):
    def settings(self) -> dict:
        return self._s.get("/user/consent_settings")

    def update_settings(self, **flags: bool) -> dict:
        return self._s.put("/user/consent_settings", json_body=flags)

    def declarations(self) -> list[dict]:
        return self._s.get("/user/consent_declarations")
