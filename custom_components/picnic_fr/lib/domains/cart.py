"""Cart: list, add, remove, clear, delivery slots, checkout."""

from __future__ import annotations

from ._base import BaseDomain


class CartDomain(BaseDomain):
    def get(self) -> dict:
        """Get the current cart."""
        return self._s.get("/cart")

    def add_product(self, product_id: str | int, count: int = 1) -> dict:
        return self._s.post(
            "/cart/add_product",
            json_body={"product_id": str(product_id), "count": count},
        )

    def add_products(self, items: list[tuple[str | int, int]]) -> list[dict]:
        """Convenience: add multiple products in sequence.

        `items` is a list of (product_id, count) tuples.
        Returns the list of cart states after each add.
        """
        results = []
        for pid, count in items:
            results.append(self.add_product(pid, count))
        return results

    def remove_product(self, product_id: str | int, count: int = 1) -> dict:
        return self._s.post(
            "/cart/remove_product",
            json_body={"product_id": str(product_id), "count": count},
        )

    def clear(self) -> dict:
        return self._s.post("/cart/clear")

    # --- Delivery slots ----------------------------------------------------

    def delivery_slots(self) -> dict:
        return self._s.get("/cart/delivery_slots")

    def selected_slot(self) -> dict | None:
        """Return the currently selected delivery slot, enriched with its full
        details, or None if nothing is selected.

        The returned dict contains all the raw slot fields plus:
        - `state`: "EXPLICIT" (chosen by the user) or "IMPLICIT" (auto-suggested)
        - `start` / `end`: parsed datetimes
        """
        from datetime import datetime

        raw = self.delivery_slots()
        sel = (raw or {}).get("selected_slot")
        if not sel or not sel.get("slot_id"):
            return None
        slot_id = sel["slot_id"]
        full = next((s for s in raw.get("delivery_slots", []) if s.get("slot_id") == slot_id), None)
        if not full:
            return {"slot_id": slot_id, "state": sel.get("state")}
        try:
            start = datetime.fromisoformat(full["window_start"])
            end = datetime.fromisoformat(full["window_end"])
        except (KeyError, ValueError):
            start = end = None
        return {**full, "state": sel.get("state"), "start": start, "end": end}

    def available_slots_by_day(self, only_available: bool = True) -> dict[str, list[dict]]:
        """Group delivery slots by ISO date (YYYY-MM-DD).

        Each slot keeps its raw fields plus parsed `start` / `end` datetimes.
        Days are sorted chronologically; within a day, slots are sorted by start time.
        """
        from datetime import datetime

        raw = self.delivery_slots()
        slots = (raw or {}).get("delivery_slots", [])
        by_day: dict[str, list[dict]] = {}
        for s in slots:
            if only_available and not s.get("is_available"):
                continue
            try:
                start = datetime.fromisoformat(s["window_start"])
                end = datetime.fromisoformat(s["window_end"])
            except (KeyError, ValueError):
                continue
            day = start.date().isoformat()
            by_day.setdefault(day, []).append({**s, "start": start, "end": end})
        for day in by_day:
            by_day[day].sort(key=lambda x: x["start"])
        return dict(sorted(by_day.items()))

    def set_delivery_slot(self, slot_id: str) -> dict:
        return self._s.post(
            "/cart/set_delivery_slot",
            json_body={"slot_id": slot_id},
        )

    # --- Checkout ----------------------------------------------------------

    def checkout(self) -> dict:
        """Place the order. Cart MUST already have a delivery slot set."""
        return self._s.post("/cart/checkout/order")

    def checkout_summary(self) -> dict:
        return self._s.get("/cart/checkout/summary")
