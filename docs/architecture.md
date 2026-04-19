# Architecture

## Storefront & auth

Base URL: `https://storefront-prod.<cc>.picnicinternational.com/api/15` with
`cc ∈ {fr, nl, de, be}`. Validated against FR in April 2026.

Login: `POST /user/login`
```json
{ "key": "<email>", "secret": "<md5(password)>", "client_id": 30100 }
```

The response sets an `x-picnic-auth` header — a JWT (RS256) with:

```
sub, pc:clid=30100, pc:logints, pc:pv:enabled, pc:pv:verified, pc:2fa,
pc:role=STANDARD_USER, pc:loc (household), pc:did (device), iat, exp, jti
```

`exp - iat = 15 552 000 s = 180 days`.

A fresh "device" (unknown `pc:did`) triggers an SMS 2FA flow:
1. `POST /user/2fa/generate` with `{channel: "SMS"}`
2. `POST /user/2fa/verify` with `{otp: "<6 digits>"}`

Subsequent calls authenticate via `x-picnic-auth: <jwt>`. Picnic sometimes
includes a refreshed JWT in response headers; the session layer captures
and persists those automatically, so a long-lived actively-used integration
never needs to re-auth until 180 days of inactivity.

## PML (Picnic Markup Language)

Modern Picnic endpoints return **PML** — a declarative UI-tree JSON. A search
no longer returns a flat product list; it returns a screen description with
embedded product tiles (`SELLING_UNIT_TILE` nodes) plus analytics contexts,
initialization expressions, and nested suspense sub-pages.

The integration deals with PML in three ways (all code in
`homeassistant/custom_components/picnic_fr/lib/`):

1. **Pattern extraction** — regex on the serialized JSON, for simple lookups
   (e.g. `selling_group_id=([0-9a-f]{24})` inside a deeplink to list the
   recipes in a cookbook section).
2. **Node walking** — `find_nodes_by_content()` in `lib/domains/catalog.py`
   walks the tree looking for a structural match (e.g. every `SELLING_UNIT_TILE`
   with a non-empty `sellingUnit`).
3. **Typed-binding extraction** — recipes embed ingredient type info as
   escaped JS tuples (`"…PIM…, 0, \"CORE\", \"<uuid>\", null, \"s1034023\", …"`).
   `_INGREDIENT_BINDING_RE` in `lib/domains/recipes.py` pulls those out
   to distinguish CORE vs VARIATION vs CUPBOARD.

## Validated endpoints (FR)

### Auth
- `POST /user/login` — MD5-hashed password, `client_id=30100`
- `POST /user/2fa/generate` — SMS channel
- `POST /user/2fa/verify` — OTP

### Catalog
- `GET /pages/search-page-results?search_term=<q>` — PML screen w/ tiles
- `GET /pages/product-details-page-root?id=<sid>&show_category_action=true`

### Cart
- `GET /cart`
- `POST /cart/add_product` — `{product_id, count}`
- `POST /cart/remove_product` — `{product_id, count}`
- `POST /cart/clear`
- `GET /cart/delivery_slots`
- `POST /cart/set_delivery_slot` — `{slot_id}`
- `POST /cart/checkout/order`

### User
- `GET /user` — profile, household, feature toggles

### Deliveries (history)
- `POST /deliveries/summary` — body `[]` or `["CURRENT"]`
- `GET /deliveries/<id>` — orders with ORDER_ARTICLE items

### Recipes
- `GET /pages/see-more-recipes-page?segmentType=SAVED_RECIPES&segmentName=…`
  → liked / saved recipes (aka *Recettes enregistrées*)
- `GET /pages/meals-purchase-page-root`
  → previously-ordered recipes (aka *Recettes commandées / Historique*)
- `GET /pages/selling-group-header?selling_group_id=<id>` — recipe metadata
- `GET /pages/selling-group-content-wrapper?selling_group_id=<id>&selling_group_creator_type=PIM[&portions=N]`
  → ingredient bindings (see PML section 3)

## Home Assistant integration

```
ConfigEntry ──┬─▶ PicnicAsyncClient (hass executor wrapper)
              │      └─▶ PicnicClient ──▶ PicnicSession (requests.Session)
              │
              ├─▶ PicnicFRCoordinator (DataUpdateCoordinator)
              │      - polls cart, slots, history, saved + ordered recipes
              │      - captures rotated x-picnic-auth on each response
              │      - exposes arm/confirm/request_clear_cart helpers
              │
              ├─ Platform: todo     → Cart mirror with matcher on create
              ├─ Platform: sensor   → 9 sensors (cart/total/weight/history/…)
              ├─ Platform: select   → Slot picker
              ├─ Platform: number   → Poll-interval slider
              └─ Platform: button   → Refresh / clear-cart / per-recipe buttons
                                      (latter: dynamic via RecipeButtonsManager
                                       syncing on every coordinator update)
```

The shopping matcher (`lib/shopping.py :: match_query`) prefers a historical
match over a fresh catalog hit: for each product returned by the catalog
search, it checks whether the ID appears in the frequency map built from
past orders, and picks the highest-count match. Falls back to the first
catalog result if nothing matches.
