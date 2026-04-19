"""Base class for domain services."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..session import PicnicSession


class BaseDomain:
    def __init__(self, session: "PicnicSession"):
        self._s = session
