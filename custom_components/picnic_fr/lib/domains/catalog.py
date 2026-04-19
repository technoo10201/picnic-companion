"""Catalog: search, suggestions, product details, images, categories."""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from ._base import BaseDomain

_SOLE_ARTICLE_ID_RE = re.compile(r'"sole_article_id":"(\w+)"')


def _find_nodes_by_content(node, filter_dict, max_nodes: int = 50):
    """Walk a nested PML dict/list tree and collect nodes matching filter_dict."""
    found: list[dict] = []

    def matches(n: dict, f: dict) -> bool:
        for k, v in f.items():
            if k not in n:
                return False
            if isinstance(v, dict) and isinstance(n[k], dict):
                if not matches(n[k], v):
                    return False
            elif v is not None and n[k] != v:
                return False
        return True

    def walk(n):
        if len(found) >= max_nodes:
            return
        if isinstance(n, dict):
            if matches(n, filter_dict):
                found.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return found


def extract_search_results(raw: dict) -> list[dict]:
    """Flatten Picnic's PML search response to a simple list of products.

    Returns dicts with at least: id, name, display_price (cents),
    unit_quantity, sole_article_id.
    """
    body = raw.get("body", {}) if isinstance(raw, dict) else {}
    tiles = _find_nodes_by_content(
        body.get("child", {}),
        {"type": "SELLING_UNIT_TILE", "sellingUnit": {}},
    )
    out = []
    for tile in tiles:
        su = tile.get("sellingUnit", {}) or {}
        sole_ids = _SOLE_ARTICLE_ID_RE.findall(json.dumps(tile))
        out.append({**su, "sole_article_id": sole_ids[0] if sole_ids else None})
    return out


class CatalogDomain(BaseDomain):
    def search(self, query: str) -> dict:
        """Search products by free-text query. Returns raw PML response."""
        return self._s.get(f"/pages/search-page-results?search_term={quote(query)}")

    def search_flat(self, query: str) -> list[dict]:
        """Search and return a flat list of products (parsed from PML)."""
        return extract_search_results(self.search(query))

    def suggestions(self, query: str) -> list[dict]:
        """Autocomplete-style suggestions."""
        return self._s.get(f"/suggest?search_term={quote(query)}")

    def product(self, product_id: str) -> dict:
        """Full product details (PML response)."""
        return self._s.get(
            f"/pages/product-details-page-root?id={product_id}&show_category_action=true"
        )

    def product_image_url(self, image_id: str, size: str = "medium") -> str:
        """Build a CDN URL for a product image.

        Sizes observed: 'tiny', 'small', 'medium', 'large', 'extra-large'.
        """
        return f"{self._s.base_url}/images/{image_id}/{size}.png"

    def categories(self, depth: int = 0) -> dict:
        return self._s.get(f"/my_store?depth={depth}")

    def category(self, category_id: str) -> dict:
        return self._s.get(f"/pages/category-overview-root-id-{category_id}")

    def list(self, list_id: str, sublist_id: str | None = None) -> dict:
        path = f"/lists/{list_id}"
        if sublist_id:
            path += f"?sublist={sublist_id}"
        return self._s.get(path)
