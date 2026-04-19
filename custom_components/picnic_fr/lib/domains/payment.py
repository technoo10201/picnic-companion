"""Payment profile and wallet."""

from __future__ import annotations

from ._base import BaseDomain


class PaymentDomain(BaseDomain):
    def profile(self) -> dict:
        return self._s.get("/user/payment_profile")

    def wallet_transactions(self) -> list[dict]:
        return self._s.get("/wallet/transactions")

    def add_payment_method(self, method_type: str, **details) -> dict:
        body = {"type": method_type, **details}
        return self._s.post("/user/payment_methods", json_body=body)
