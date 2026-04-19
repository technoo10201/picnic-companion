# Installation

Two ways to install the integration:

1. **[HACS](#option-1--hacs-recommended)** — one click, auto-updates when
   new releases are tagged.
2. **[Manual copy](#option-2--manual)** — just drop the folder into your
   Home Assistant config.

## Option 1 — HACS (recommended)

### Prerequisites

HACS installed in your Home Assistant. If not, follow the official guide:
[hacs.xyz/docs/use/download](https://www.hacs.xyz/docs/use/download/).

### Add this repository as a custom HACS repository

Until the integration is accepted in the default HACS store, it must be
added as a custom repository:

1. In Home Assistant, go to **HACS** (left sidebar).
2. Click **⋮** (top-right corner) → **Custom repositories**.
3. Paste this repository's URL, e.g.
   `https://github.com/technoo10201/picnic-companion`.
4. In **Category** choose **Integration**.
5. Click **Add**.

### Download the integration

1. In HACS, search for **Picnic Companion** (it now appears in the list).
2. Click it → **Download** → confirm.
3. **Restart Home Assistant** when prompted (HACS shows a button).

### Add the integration to Home Assistant

1. **Settings → Devices & services → Add integration**.
2. Search for **Picnic Companion**.
3. Step 1: email + password + country (`FR` / `NL` / `BE` / `DE`).
4. Step 2 (only the first time from this install): enter the 6-digit
   SMS code Picnic sends to the phone on file.
5. Done. A success screen confirms the token is valid for 180 days; a
   Repair notification will fire 7 days before expiry.

### Updating

When a new release is tagged in this repo, HACS will show an **Update**
button on the integration. Click it → restart HA.

## Option 2 — Manual

```bash
cp -r custom_components/picnic_fr <HA-config>/custom_components/
```

Where `<HA-config>` is usually:

- `/config/` inside a Home Assistant OS / Container install
- `~/.homeassistant/` for a core install
- `homeassistant/config/` for a locally-mounted Docker setup

Then **restart Home Assistant** and add the integration via the UI as
described above.

### Running Home Assistant locally in Docker (for development)

```bash
mkdir -p homeassistant/config
cp -r custom_components/picnic_fr homeassistant/config/custom_components/

docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  -p 8123:8123 \
  -v $PWD/homeassistant/config:/config \
  -e TZ=Europe/Paris \
  ghcr.io/home-assistant/home-assistant:stable
```

Open http://localhost:8123 and create the admin account.

For the development channel, swap the image tag to `dev`.

After editing any file under `custom_components/picnic_fr/`, resync and
restart:

```bash
cp -r custom_components/picnic_fr homeassistant/config/custom_components/
docker restart homeassistant
docker logs --since 30s homeassistant 2>&1 | grep -iE 'picnic_fr|error' | tail
```

## What you get

Entities created (default names are in French, translations available for
EN / NL / DE / ES / PT):

| Kind | Entity | Purpose |
|---|---|---|
| todo | `todo.nombre_article_dans_liste_de_courses` | Cart mirror + smart add |
| sensor | `sensor.total_panier` | Cart subtotal (€) |
| sensor | `sensor.nombre_de_produits` | Distinct products |
| sensor | `sensor.nombre_d_articles` | Total article quantity |
| sensor | `sensor.liste_des_articles` | Comma-joined item names |
| sensor | `sensor.poids_du_panier` | Estimated total weight (kg) |
| sensor | `sensor.creneau_de_livraison` | Selected delivery slot |
| sensor | `sensor.expiration_du_token` | JWT expiry timestamp |
| sensor | `sensor.produits_distincts_achetes` | Unique past-order products |
| sensor | `sensor.livraisons_recues` | Historical delivery count |
| select | `select.creneau_de_livraison` | Pick a delivery slot |
| number | `number.intervalle_de_rafraichissement` | Poll interval (1-60 min, default 5) |
| button | `button.synchroniser_maintenant` | Force refresh |
| button | `button.rafraichir_l_historique` | Refresh order history |
| button | `button.vider_le_panier` | Clear cart (double confirmation) |
| button | `button.enregistree_*` | One per "Recette enregistrée" (liked) |
| button | `button.commandee_*` | One per "Recette commandée" (ordered) |

See [home-assistant.md](home-assistant.md) for the full reference and
example automations.

## Uninstalling

1. **Settings → Devices & services → Picnic Companion → ⋮ → Delete**.
2. In HACS, open **Picnic Companion → ⋮ → Remove** (if installed via HACS),
   or delete the folder `<HA-config>/custom_components/picnic_fr/`
   (if installed manually).
3. Restart Home Assistant.
