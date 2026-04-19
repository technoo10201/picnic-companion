# Home Assistant integration

Domain: `picnic_fr`. Default name: **Picnic Companion**.

## Config flow

Three steps:

1. **user** — email + password + country (defaults FR).
2. **two_factor** — only shown if Picnic's `/user/login` returns
   `second_factor_authentication_required: true`. The integration triggers
   an SMS via `/user/2fa/generate` and prompts for the 6-digit code.
3. **finalize** — success screen mentions the 180-day validity.

The JWT is decoded client-side to store `iat` and `exp` in the config entry.

## Entities

### Todo

| Entity | Description |
|---|---|
| `todo.nombre_article_dans_liste_de_courses` | **Cart mirror.** Each line is a Picnic cart line displayed as `(xN) <name> [<unit_quantity>]  <price €>`. Adding a free-text item (`"farine"` or `"bananes x3"`) runs the matcher, then calls `/cart/add_product`. Multi-add supported with `//`: `"a // b x2 // c"` = 3 distinct items. Deleting a todo item removes that product from the cart. |

### Sensors

| Entity | State |
|---|---|
| `sensor.total_panier` | Cart subtotal in € |
| `sensor.nombre_de_produits` | Distinct product IDs in cart |
| `sensor.nombre_d_articles` | Total quantity (sum of counts) |
| `sensor.liste_des_articles` | Comma-joined product names (truncated 255). Attributes: `lines`, `names`, `items_text`, `items_markdown` |
| `sensor.poids_du_panier` | Total weight in kg — parsed from each line's `unit_quantity` (`1 Kg`, `375 g`, `12 x 60 g`, `1,25 L`…). Attributes: `weighted_lines`, `unweighted_lines` (pieces, rolls, units) |
| `sensor.creneau_de_livraison` | Currently selected delivery slot (readable form). Attributes: `slot_id`, `kind` (`eco`/`normal`), `state` (EXPLICIT/IMPLICIT), `start`, `end`, `duration_min` |
| `sensor.expiration_du_token` | Timestamp, `days_left` attribute |
| `sensor.produits_distincts_achetes` | Unique products across all past deliveries. Attribute `top_10` for the matcher |
| `sensor.livraisons_recues` | Historical delivery count |

### Select

| Entity | Description |
|---|---|
| `select.creneau_de_livraison` | Dropdown listing every available slot as `lundi 20/04 14:10–15:45 (éco)`. Selecting an option calls `/cart/set_delivery_slot` and refreshes. The currently-selected slot is always included even if no longer advertised as available. |

### Number

| Entity | Description |
|---|---|
| `number.intervalle_de_rafraichissement` | Coordinator poll interval (1-60 min, default 5). Persisted in `ConfigEntry.options`. Changes apply immediately (reschedules the next refresh). |

### Buttons

| Entity | Description |
|---|---|
| `button.synchroniser_maintenant` | Forces a coordinator refresh |
| `button.rafraichir_l_historique` | Re-fetches the order history used by the matcher |
| `button.vider_le_panier` | Empties the cart. **Two-click confirmation** within 10s, or long-press + tap via dashboard `tap_action`/`hold_action` + services |
| `button.enregistree_<recipe_name>` | Dynamic — one per "Recette enregistrée" (★ liked). Press = add all CORE ingredients to cart |
| `button.commandee_<recipe_name>` | Dynamic — one per "Recette commandée" (previously ordered). Same behaviour |

The recipe buttons are added/removed automatically on each coordinator refresh.

## Services

| Service | Schema | Purpose |
|---|---|---|
| `picnic_fr.push_list` | `{items: [str or {query, count}], clear_first?: bool, entry_id?: str}` | Push a shopping list in one call |
| `picnic_fr.clear_cart` | `{entry_id?}` | Empty cart (no confirmation) |
| `picnic_fr.arm_clear_cart` | `{entry_id?}` | Arm the 10-second confirmation window |
| `picnic_fr.confirm_clear_cart` | `{entry_id?}` | Confirm (no-op if not armed) |
| `picnic_fr.book_slot` | `{slot_id, entry_id?}` | Reserve a slot |
| `picnic_fr.checkout` | `{entry_id?}` | **Place the order.** Irreversible — use with care |
| `picnic_fr.refresh_history` | `{entry_id?}` | Force order-history re-fetch |
| `picnic_fr.add_recipe_to_cart` | `{recipe_id, portions?, entry_id?}` | Add a recipe's CORE ingredients to the cart |

## Token lifecycle

- Picnic issues a 180-day JWT signed with RS256.
- The integration decodes `iat` / `exp` into the config entry.
- On every API call, Picnic may include a rotated `x-picnic-auth` response
  header — the session captures it and the coordinator persists the new
  token on the entry. **Active use = indefinite session.**
- A daily scheduled check raises:
  - `token_expiring` (WARNING) at 7 days left
  - `token_expired` (ERROR) past expiry
  Both are Repair issues that re-open the reauth config flow.

## Example automations

### Weekly grocery run (Friday 9 am)

```yaml
automation:
  - alias: Picnic weekly basket
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: time
        weekday: [fri]
    action:
      - service: picnic_fr.push_list
        data:
          clear_first: true
          items:
            - bananes
            - { query: "fromage blanc 0% paturages", count: 2 }
            - { query: "oeufs label rouge", count: 3 }
            - pain de mie complet
      # Pick a slot from sensor.creneau_de_livraison or book a specific one
      # - service: picnic_fr.checkout    # uncomment to fully automate
```

### Long-press clear-cart tile card

```yaml
type: tile
entity: button.vider_le_panier
name: Vider le panier
tap_action:
  action: call-service
  service: picnic_fr.confirm_clear_cart
hold_action:
  action: call-service
  service: picnic_fr.arm_clear_cart
```

### Markdown card — full cart list

```yaml
type: markdown
title: Panier
content: |
  **{{ states('sensor.nombre_de_produits') }} produits**,
  total **{{ states('sensor.total_panier') }} €**
  ({{ states('sensor.poids_du_panier') }} kg)

  {{ state_attr('sensor.liste_des_articles', 'items_markdown') }}
```
