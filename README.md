<p align="center">
  <img src="custom_components/picnic_fr/icon.png" alt="Picnic Companion" width="128" />
</p>

# Picnic Companion

An **unofficial** Home Assistant custom integration for the
[Picnic](https://picnic.app) online supermarket, validated against the French
storefront. Mirror your cart, push shopping lists, re-order favourite recipes
in one click, pick delivery slots, and monitor basket weight — all from HA.

> ⚠️ Not affiliated with Picnic. Uses the mobile app API obtained by community
> reverse-engineering. It can break at any time. Use at your own risk.

## Highlights

- 🔑 **Login + SMS 2FA** handled end-to-end (token is a 180-day JWT,
  auto-renewed while the integration is polling).
- 🛒 **Cart mirror** — a Home Assistant `todo` entity that reflects your real
  Picnic cart. Add from HA → added in the mobile app. Add from the mobile
  app → appears in HA.
- 🧠 **Smart shopping matcher** — type `"banane"` in the todo list, the
  integration looks at your **purchase history** and adds the exact banana
  you usually buy.
- 🍳 **One-click recipes** — every recipe you've liked (*Recettes
  enregistrées*) or ordered (*Recettes commandées*) becomes a button. One
  press = all CORE ingredients added to the cart.
- 🕐 **Delivery slots** — list, select, and swap your slot from HA (⚡ normal
  vs 🌱 eco windows).
- ⚖️ **Cart weight** — a sensor estimates the total weight of your cart based
  on each line's `unit_quantity`.

## Installation

### Option 1 — HACS (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=technoo10201&repository=picnic-companion&category=integration)

1. In Home Assistant open **HACS** (install HACS first if you haven't —
   see [hacs.xyz/docs/use/download](https://www.hacs.xyz/docs/use/download/)).
2. Click the **⋮ menu** (top right) → **Custom repositories**.
3. Paste the URL of this repository, choose category **Integration**, click
   **Add**.
4. The repository now appears in the HACS integrations list. Click it, then
   **Download**.
5. **Restart Home Assistant** when prompted.
6. Go to **Settings → Devices & services → Add integration** and search for
   **Picnic Companion**. Sign in with your Picnic email + password (+ SMS
   code on first login from this "device").

Once this repository reaches the default HACS store, steps 2–3 disappear and
users can just search "Picnic Companion" directly in HACS.

### Option 2 — Manual

1. Copy the folder `custom_components/picnic_fr/` from this repository into
   your Home Assistant configuration directory:

   ```bash
   cp -r custom_components/picnic_fr <HA-config>/custom_components/
   ```

2. **Restart Home Assistant**.
3. **Settings → Devices & services → Add integration → Picnic Companion**.

## Repository layout

```
.
├── custom_components/picnic_fr/       # the Home Assistant integration
│   ├── lib/                           # internal Picnic API client
│   ├── translations/                  # en, fr, nl, de, es, pt
│   ├── manifest.json
│   ├── config_flow.py                 # 3-step login + SMS 2FA + reauth
│   ├── coordinator.py                 # polling, cart/slot/history cache
│   ├── __init__.py                    # setup, services, repair flow
│   ├── sensor.py / select.py /
│   │   number.py / button.py /
│   │   todo.py                        # HA platforms
│   └── services.yaml + strings.json
├── hacs.json                          # HACS metadata
└── docs/
    ├── installation.md                # HACS and manual install walk-through
    ├── home-assistant.md              # entities, sensors, services
    ├── architecture.md                # storefront, JWT, PML, endpoints
    ├── security.md                    # credentials, JWT, rotation
    └── contributing.md                # branching, commits, translations
```

## License & trademarks

Code: MIT — see [LICENSE](LICENSE).

The Picnic name and logo are trademarks of Picnic International B.V. and are
used here solely for identification under nominative fair use. See
[TRADEMARKS.md](TRADEMARKS.md).

## Getting the logo into Home Assistant's integrations UI

HACS picks up `custom_components/picnic_fr/icon.png` for its own list
automatically. For the logo to also appear on the Home Assistant
*Settings → Devices & services* tile, the domain has to be registered in
the [home-assistant/brands](https://github.com/home-assistant/brands) repo
under `custom_integrations/picnic_fr/`. That step requires a separate PR
there and upstream review — on roadmap, not shipped yet.
