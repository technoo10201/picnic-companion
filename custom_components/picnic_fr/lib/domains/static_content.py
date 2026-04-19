"""Static content pages (FAQ, search empty state, terms)."""

from __future__ import annotations

from ._base import BaseDomain


class StaticContentDomain(BaseDomain):
    def page(self, page_id: str) -> dict:
        return self._s.get(f"/pages/{page_id}")

    def faq(self) -> dict:
        return self._s.get("/pages/faq")

    def terms(self) -> dict:
        return self._s.get("/pages/terms-and-conditions")
