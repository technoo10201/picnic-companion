"""Recipes — backed by Picnic FR's selling-group pages.

Picnic FR exposes recipes as "selling groups" via PML endpoints. There is no
dedicated /recipes/* endpoint that works on FR; we use:

  - /pages/see-more-recipes-page?segmentType=SAVED_RECIPES   → liked/favorite list
  - /pages/selling-group-details-page?selling_group_id=...   → ingredients + meta
  - /pages/selling-group-header?...                          → name, default_portions, is_saved
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from ._base import BaseDomain

_RECIPE_ID_RE = re.compile(r"selling_group_id=([0-9a-f]{24})")
_PRODUCT_ID_RE = re.compile(r"\b(s\d{6,7})\b")
_NAME_RE = re.compile(r'"sellable_name":\s*"([^"]+)"')
_PORTIONS_RE = re.compile(r'"default_portions":\s*(\d+)')
_IS_SAVED_RE = re.compile(r'"is_saved":\s*(true|false)')

# Ingredient binding pattern found embedded (escaped JSON) inside selling-group
# content PML. Each match gives (type, product_id).
#
#   "630c58a8…", "PIM", 0, "CORE", "<ingredient-uuid>", null, "s1034023", …
#
# We want CORE + CORE_STOCKABLE only (the actual recipe ingredients). The
# CUPBOARD type marks pantry items (salt, oil, pepper…) and VARIATION marks
# optional swaps — neither should be auto-added.
_INGREDIENT_BINDING_RE = re.compile(
    r'\\"(?P<type>CORE|CORE_STOCKABLE|CUPBOARD|VARIATION)\\",\s*'
    r'\\"[0-9a-f-]{36}\\",\s*null,\s*'
    r'\\"(?P<pid>s\d{6,7})\\"'
)
_CORE_TYPES = ("CORE", "CORE_STOCKABLE")
_MARKDOWN_RE = re.compile(r'"markdown"\s*:\s*"([^"\\]{4,120})"')

# Skip markdown strings that are clearly not recipe titles
_META_MARKERS = (
    "min", "Pour ", "portion", "Temps", "kcal", "cuisson",
    "préparation", "€", "Ajouter", "Aimer", "#(",
)


def _extract_title_from_markdown(text: str) -> str | None:
    """First markdown string in a header PML that looks like a recipe title."""
    for m in _MARKDOWN_RE.finditer(text):
        s = m.group(1)
        if any(marker in s for marker in _META_MARKERS):
            continue
        if s[:1].islower():  # titles start uppercase in French
            continue
        return s
    return None


class RecipesDomain(BaseDomain):
    # --- Saved (Aimées) ----------------------------------------------------

    def list_saved(self) -> list[str]:
        """Return the selling_group_ids the user has liked (★ favoris).

        Mirrors the in-app 'Recettes enregistrées' tab. Ordering follows
        Picnic's response (most recent like first).
        """
        page = self._s.get(
            "/pages/see-more-recipes-page"
            f"?segmentName={quote('Aimées')}&segmentType=SAVED_RECIPES"
        )
        text = json.dumps(page, ensure_ascii=False)
        seen: list[str] = []
        for m in _RECIPE_ID_RE.finditer(text):
            if m.group(1) not in seen:
                seen.append(m.group(1))
        return seen

    # --- Ordered (Commandées / Historique) --------------------------------

    def list_ordered(self) -> list[str]:
        """Return the selling_group_ids of recipes the user has ordered.

        Mirrors the in-app 'Recettes commandées / Historique' tab.
        """
        page = self._s.get("/pages/meals-purchase-page-root")
        text = json.dumps(page, ensure_ascii=False)
        seen: list[str] = []
        for m in _RECIPE_ID_RE.finditer(text):
            if m.group(1) not in seen:
                seen.append(m.group(1))
        return seen

    # --- Detail ------------------------------------------------------------

    def details(self, recipe_id: str) -> dict:
        """Return the raw selling-group-details PML page for a recipe."""
        return self._s.get(
            f"/pages/selling-group-details-page?selling_group_id={recipe_id}"
        )

    def info(self, recipe_id: str) -> dict:
        """Lightweight info (name, default_portions, is_saved).

        Tries the small `selling-group-header` sub-page first. The recipe title
        lives in a `markdown` node there (not in a structured field), so we
        extract it heuristically.
        """
        page = self._s.get(
            f"/pages/selling-group-header?selling_group_id={recipe_id}"
        )
        text = json.dumps(page, ensure_ascii=False)
        name = None
        m = _NAME_RE.search(text)
        if m:
            name = m.group(1)
        else:
            name = _extract_title_from_markdown(text)
        portions_m = _PORTIONS_RE.search(text)
        saved_m = _IS_SAVED_RE.search(text)
        return {
            "id": recipe_id,
            "name": name,
            "default_portions": int(portions_m.group(1)) if portions_m else None,
            "is_saved": (saved_m.group(1) == "true") if saved_m else None,
        }

    def ingredients(
        self,
        recipe_id: str,
        portions: int | None = None,
        *,
        include_variations: bool = False,
        include_cupboard: bool = False,
    ) -> list[str]:
        """Return only the product IDs that are actual recipe ingredients.

        By default returns CORE + CORE_STOCKABLE items — the ones the app
        pre-selects when you tap "Ajouter au panier". Use the flags to widen:
          - include_variations: alternative takes (lardons, oeuf, oignon…)
          - include_cupboard:   pantry items (huile, sel, poivre…)
        """
        params = f"selling_group_id={recipe_id}&selling_group_creator_type=PIM"
        if portions:
            params += f"&portions={portions}"
        page = self._s.get(f"/pages/selling-group-content-wrapper?{params}")
        text = json.dumps(page, ensure_ascii=False)
        wanted = set(_CORE_TYPES)
        if include_variations:
            wanted.add("VARIATION")
        if include_cupboard:
            wanted.add("CUPBOARD")
        ids: list[str] = []
        for m in _INGREDIENT_BINDING_RE.finditer(text):
            if m.group("type") in wanted and m.group("pid") not in ids:
                ids.append(m.group("pid"))
        return ids

    # --- Cart integration --------------------------------------------------

    def add_to_cart(self, recipe_id: str, portions: int | None = None) -> dict:
        """Add every ingredient of the recipe to the cart (count=1 each).

        Returns a summary {"recipe_id", "name", "added": [pids], "failed": [pids]}.
        Picnic FR has no atomic "add recipe" endpoint; we POST each ingredient.
        """
        info = self.info(recipe_id)
        if portions is None:
            portions = info.get("default_portions")
        ingredients = self.ingredients(recipe_id, portions=portions)
        added, failed = [], []
        for pid in ingredients:
            try:
                self._s.post(
                    "/cart/add_product",
                    json_body={"product_id": pid, "count": 1},
                )
                added.append(pid)
            except Exception:
                failed.append(pid)
        return {
            "recipe_id": recipe_id,
            "name": info.get("name"),
            "added": added,
            "failed": failed,
        }
