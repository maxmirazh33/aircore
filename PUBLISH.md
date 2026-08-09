# Publishing checklist

## 1. Repository

Name: `aircore` — the brand alone. Searching by protocol and by appliance make
relies on the description and the topics below, so keep both filled in.

**Repository description** (HACS searches it):

```
AirCore — Broadlink air conditioners in Home Assistant, directly, without cloud or MQTT.
AUX, Zanussi, Ballu, Rovex, Tornado, Electrolux, Dunham, Rcool, Akai, Kenwood.
Compressor state, output and coil temperature.
```

**Repository topics** — also used for search:

```
home-assistant  homeassistant  hacs  hacs-integration  custom-component
broadlink  air-conditioner  climate  aux  zanussi  ballu  rovex  tornado
electrolux  hvac  smart-home
```

## 2. Checks before publishing

```bash
ruff check custom_components tests
ruff format --check custom_components tests
pytest --cov=custom_components.aircore
```

GitHub Actions runs the same on every commit, plus `hassfest` and HACS requirements.

## 3. Release

HACS shows the five latest releases. The version in `manifest.json` must match the tag:

```bash
git tag v1.0.0
git push --tags
```

Tag only after the checks are green.

## 4. Adding to HACS

Until the repository is accepted into the default catalogue it installs as a custom one:
HACS → three dots → «Custom repositories» → repository URL, category «Integration».

To get into the default catalogue, submit a request to `hacs/default`: the repository
must be public and have a description, topics, `hacs.json` and brand assets.

## 5. Brand in Home Assistant

For the icon to appear in the interface, images go in a separate pull request to
`home-assistant/brands`: directory `custom_integrations/aircore/` with `icon.png` and
`logo.png`. Ready-made ones live in `custom_components/aircore/brand/`.
