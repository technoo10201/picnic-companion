"""Smart shopping helper: match a shopping list against past orders.

Given a free-text query (e.g. "bananes") and a user's order history, pick the
product the user is most likely to actually want — usually the one they've
bought most often, cross-referenced with the current catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class MatchResult:
    query: str
    product_id: str
    name: str
    unit_quantity: str | None
    price_cents: int | None
    source: str  # "history" | "catalog"
    past_count: int
    past_orders: int

    def __str__(self) -> str:
        origin = "★ habituel" if self.source == "history" else "⊕ nouveau"
        price = f"{self.price_cents / 100:.2f} €" if self.price_cents else "—"
        qty = f" {self.unit_quantity}" if self.unit_quantity else ""
        suffix = f" (acheté {self.past_count}× en {self.past_orders} commandes)" if self.source == "history" else ""
        return f"{origin}  {self.product_id}  {price}{qty}  {self.name}{suffix}"


def match_query(
    query: str,
    *,
    catalog_results: list[dict],
    history: dict[str, dict],
    min_history_count: int = 1,
) -> MatchResult | None:
    """Pick the best product for `query`.

    Strategy: among the top catalog hits for `query`, return the one with the
    highest past purchase count (if any); otherwise fall back to the first
    catalog hit.

    Parameters
    ----------
    catalog_results : output of `CatalogDomain.search_flat(query)`.
    history : output of `DeliveryDomain.product_frequency()`.
    """
    if not catalog_results:
        return None

    best = None
    for prod in catalog_results:
        pid = prod.get("id") or prod.get("sole_article_id")
        if not pid:
            continue
        hist = history.get(pid)
        if hist and hist["count"] >= min_history_count:
            if best is None or hist["count"] > best[1]["count"]:
                best = (prod, hist)

    if best is not None:
        prod, hist = best
        return MatchResult(
            query=query,
            product_id=prod["id"],
            name=prod.get("name") or hist["name"],
            unit_quantity=prod.get("unit_quantity") or hist.get("unit_quantity"),
            price_cents=prod.get("display_price") or prod.get("price"),
            source="history",
            past_count=hist["count"],
            past_orders=hist["orders"],
        )

    fallback = catalog_results[0]
    return MatchResult(
        query=query,
        product_id=fallback.get("id") or fallback.get("sole_article_id") or "?",
        name=fallback.get("name", "<unknown>"),
        unit_quantity=fallback.get("unit_quantity"),
        price_cents=fallback.get("display_price") or fallback.get("price"),
        source="catalog",
        past_count=0,
        past_orders=0,
    )


def _search_with_fallback(client, query: str, max_attempts: int = 4) -> list[dict]:
    """Search, and if empty, progressively drop trailing tokens until we hit."""
    tokens = query.split()
    for _ in range(min(max_attempts, len(tokens))):
        attempt = " ".join(tokens)
        hits = client.catalog.search_flat(attempt)
        if hits:
            return hits
        if len(tokens) <= 1:
            break
        tokens.pop()
    return []


def match_shopping_list(
    items: Iterable[tuple[str, int]],
    *,
    client,
) -> list[tuple[MatchResult | None, int]]:
    """Resolve an entire shopping list to concrete products.

    `items` is an iterable of (query, quantity). Returns `[(match, qty), ...]`
    preserving input order; `match` is None when the query had zero catalog hits.
    Caller decides what to do with the results (print, add to cart, etc.).
    """
    history = client.delivery.product_frequency()
    resolved: list[tuple[MatchResult | None, int]] = []
    for query, qty in items:
        catalog = _search_with_fallback(client, query)
        resolved.append((match_query(query, catalog_results=catalog, history=history), qty))
    return resolved
