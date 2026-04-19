"""User profile, addresses, push tokens, household."""

from __future__ import annotations

from ._base import BaseDomain


class UserDomain(BaseDomain):
    def me(self) -> dict:
        return self._s.get("/user")

    def info(self) -> dict:
        """User info including feature toggles."""
        return self._s.get("/user/info")

    def update(self, **fields) -> dict:
        return self._s.put("/user", json_body=fields)

    def household(self) -> dict:
        return self._s.get("/user/household_details")

    def update_household(self, **fields) -> dict:
        return self._s.put("/user/household_details", json_body=fields)

    def register_push_token(self, token: str, platform: str = "android") -> dict:
        return self._s.post(
            "/user/push_subscriptions",
            json_body={"token": token, "platform": platform},
        )

    def unregister_push_token(self, token: str) -> dict:
        return self._s.delete(f"/user/push_subscriptions/{token}")
