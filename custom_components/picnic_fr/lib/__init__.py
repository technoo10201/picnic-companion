"""picnic_fr — Unofficial Python wrapper for the Picnic API (NL/DE/BE/FR).

Not affiliated with Picnic. Use at your own risk.
"""

from .client import PicnicClient
from .exceptions import (
    PicnicError,
    PicnicAuthError,
    PicnicRateLimitError,
    PicnicNotFoundError,
)

__version__ = "0.1.0"
__all__ = [
    "PicnicClient",
    "PicnicError",
    "PicnicAuthError",
    "PicnicRateLimitError",
    "PicnicNotFoundError",
]
