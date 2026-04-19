"""Authentication: login, logout, 2FA, phone verification."""

from __future__ import annotations

from ..session import DEFAULT_CLIENT_ID, hash_password
from ._base import BaseDomain


class AuthDomain(BaseDomain):
    def login(self, email: str, password: str, *, persist: bool = True) -> dict | None:
        """Login with email + plaintext password.

        Returns the response payload (typically user metadata).
        Auth key is captured automatically from the `x-picnic-auth` response header.
        """
        body = {
            "key": email,
            "secret": hash_password(password),
            "client_id": DEFAULT_CLIENT_ID,
        }
        result = self._s.post("/user/login", json_body=body)
        if persist and self._s.auth_key_path:
            self._s.persist_auth_key()
        return result

    def logout(self) -> None:
        self._s.post("/user/logout")
        self._s.auth_key = None
        if self._s.auth_key_path:
            self._s.persist_auth_key()

    # --- 2FA ---------------------------------------------------------------

    def generate_2fa_code(self, channel: str = "SMS") -> dict:
        """Ask Picnic to send a 2FA code via the given channel."""
        return self._s.post("/user/2fa/generate", json_body={"channel": channel})

    def verify_2fa_code(self, code: str) -> dict:
        return self._s.post("/user/2fa/verify", json_body={"otp": code})

    # --- Phone verification ------------------------------------------------

    def request_phone_verification(self, phone_number: str) -> dict:
        return self._s.post(
            "/user/phone/verification/request",
            json_body={"phone_number": phone_number},
        )

    def confirm_phone_verification(self, code: str) -> dict:
        return self._s.post(
            "/user/phone/verification/confirm",
            json_body={"code": code},
        )
