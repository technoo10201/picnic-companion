"""Custom exceptions for the Picnic wrapper."""


class PicnicError(Exception):
    """Base exception for all Picnic API errors."""

    def __init__(self, message: str, status_code: int | None = None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class PicnicAuthError(PicnicError):
    """Raised on auth failures (401, 403, invalid credentials, expired token)."""


class PicnicRateLimitError(PicnicError):
    """Raised on 429 responses."""


class PicnicNotFoundError(PicnicError):
    """Raised on 404 responses."""


class PicnicCountryNotSupportedError(PicnicError):
    """Raised when the requested country has no Picnic storefront."""
