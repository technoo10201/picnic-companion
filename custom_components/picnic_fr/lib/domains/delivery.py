"""Delivery history, live tracking, ratings, invoices."""

from __future__ import annotations

from ._base import BaseDomain


class DeliveryDomain(BaseDomain):
    def list(self, statuses: list[str] | None = None) -> list[dict]:
        """List deliveries. Empty list = all; ["CURRENT"] = ongoing only.

        Picnic removed the unsummarized variant; only the POST summary endpoint
        remains (the body is a list of status filters).
        """
        return self._s.post("/deliveries/summary", json_body=statuses or [])

    def current(self) -> list[dict]:
        return self.list(statuses=["CURRENT"])

    def get(self, delivery_id: str) -> dict:
        return self._s.get(f"/deliveries/{delivery_id}")

    def order_history(self, max_deliveries: int | None = None) -> list[dict]:
        """Return a flat list of ORDER_ARTICLE items across all past deliveries.

        Items include: id, name, unit_quantity, image_ids, quantity, delivery_id.
        Duplicates are NOT deduplicated — see `product_frequency` for that.
        """
        deliveries = self.list()
        if max_deliveries:
            deliveries = deliveries[:max_deliveries]

        items: list[dict] = []
        for d in deliveries:
            detail = self.get(d["delivery_id"])
            for order in detail.get("orders", []):
                for line in order.get("items", []):
                    for art in line.get("items", []):
                        if art.get("type") != "ORDER_ARTICLE":
                            continue
                        qty = 1
                        for deco in art.get("decorators", []) or []:
                            if deco.get("type") == "QUANTITY":
                                qty = deco.get("quantity", 1)
                                break
                        items.append({
                            "id": art.get("id"),
                            "name": art.get("name"),
                            "unit_quantity": art.get("unit_quantity"),
                            "image_ids": art.get("image_ids") or [],
                            "quantity": qty,
                            "delivery_id": d["delivery_id"],
                            "delivery_time": (d.get("delivery_time") or {}).get("start"),
                        })
        return items

    def product_frequency(self, max_deliveries: int | None = None) -> dict[str, dict]:
        """Aggregate past orders into a map {product_id: {count, name, ...}}.

        `count` is the total units ordered across all past deliveries.
        `orders` is the number of distinct deliveries in which it appeared.
        Sorted by count, descending, when iterated via items().
        """
        items = self.order_history(max_deliveries=max_deliveries)
        bucket: dict[str, dict] = {}
        deliveries_per_id: dict[str, set[str]] = {}
        for it in items:
            pid = it["id"]
            if not pid:
                continue
            cur = bucket.setdefault(pid, {
                "id": pid,
                "name": it["name"],
                "unit_quantity": it["unit_quantity"],
                "image_ids": it["image_ids"],
                "count": 0,
                "orders": 0,
            })
            cur["count"] += it.get("quantity") or 1
            deliveries_per_id.setdefault(pid, set()).add(it["delivery_id"])
        for pid, dset in deliveries_per_id.items():
            bucket[pid]["orders"] = len(dset)
        return dict(sorted(bucket.items(), key=lambda kv: kv[1]["count"], reverse=True))

    def position(self, delivery_id: str) -> dict:
        """Live driver position for an in-progress delivery."""
        return self._s.get(f"/deliveries/{delivery_id}/position")

    def rate(self, delivery_id: str, rating: int) -> dict:
        """Rate a delivery (typically 0-10)."""
        return self._s.post(
            f"/deliveries/{delivery_id}/rating",
            json_body={"rating": rating},
        )

    def invoice(self, delivery_id: str) -> bytes | str:
        """PDF invoice (returned as bytes if Content-Type is application/pdf)."""
        return self._s.get(f"/deliveries/{delivery_id}/invoice")

    def cancel(self, delivery_id: str) -> dict:
        return self._s.post(f"/deliveries/{delivery_id}/cancel")
