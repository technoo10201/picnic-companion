# Contributing

## Branching

- `main` is protected; **no direct pushes**.
- Create a feature branch off `main`: `git switch -c <kebab-case-name>`.
- Open a Pull Request targeting `main` when ready.

Suggested branch prefixes: `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`.

## Commit messages

Keep commits focused. One logical change per commit. Format:

```
<short imperative subject, 50-72 chars>

<optional body — explain the why, not the what>
<wrap at 72 chars>
```

Examples:

```
Fix recipe button adds 11 items instead of 5

recipes.ingredients() was matching every product ID in the PML tree,
including VARIATION and CUPBOARD items. Added _INGREDIENT_BINDING_RE
to extract the type tag and filter to CORE + CORE_STOCKABLE by default.
```

```
Add Portuguese translation
```

## Code layout

- `homeassistant/custom_components/picnic_fr/` — the Home Assistant
  integration (config flow, platforms, coordinator, services).
- `homeassistant/custom_components/picnic_fr/lib/` — the internal client
  that talks to Picnic's API. Kept separate from HA glue for testability
  and to mirror the canonical HA structure (integration root =
  platform files, helpers under their own package).

## Code style

- Python: PEP 8 + 4-space indents, type hints where useful.
- No new runtime dependencies without discussion (HA already pulls a lot).
- Use `homeassistant` imports only from the integration root; the `lib/`
  subpackage must remain HA-agnostic.
- User-facing strings live under `translations/<lang>.json` — do not
  hard-code UI text in Python.

## Translations

UI strings for the integration live in
`homeassistant/custom_components/picnic_fr/translations/`. Languages
currently shipped: `en`, `fr`, `nl`, `de`, `es`, `pt`. To add a new
language, copy `en.json`, translate the values (keep keys unchanged),
and commit as `<lang>.json` (2-letter ISO-639 code).

## Local testing with Home Assistant in Docker

See [installation.md](installation.md#1-run-home-assistant-docker) for the
full recipe. Short loop:

```bash
cp -r homeassistant/custom_components/picnic_fr \
      homeassistant/config/custom_components/
docker restart homeassistant
docker logs --since 30s homeassistant 2>&1 | grep -iE 'picnic_fr|error' | tail
```

## PR checklist

- [ ] Python files compile (`python3 -m py_compile <changed>.py`)
- [ ] JSON files parse (`python3 -c "import json; json.load(open('…'))"`)
- [ ] No real credentials, tokens, or personal info in the diff
  (`grep -iE '<your-account-email>|eyJ[A-Za-z0-9]+\.'`)
- [ ] New user-facing strings added to all 6 language files
- [ ] The HA integration starts cleanly (no traceback in logs) after the
  change is deployed
- [ ] A short changelog entry in the PR description (not a file)
