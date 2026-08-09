<img src="custom_components/aircore/brand/logo.png" alt="AirCore" width="420">

**English** · [Русский](README.ru.md)

[![Checks](https://github.com/maxmirazh33/aircore/actions/workflows/validate.yml/badge.svg)](https://github.com/maxmirazh33/aircore/actions/workflows/validate.yml)
[![HACS custom](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Release](https://img.shields.io/github/v/release/maxmirazh33/aircore?display_name=tag&sort=semver)](https://github.com/maxmirazh33/aircore/releases)
[![Coverage](https://img.shields.io/endpoint?url=https://maxmirazh33.github.io/aircore/coverage.json)](https://github.com/maxmirazh33/aircore/actions/workflows/validate.yml)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.8%2B-41BDF5.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# AirCore

**Broadlink air conditioners in Home Assistant**

Direct control of air conditioners with a built-in Broadlink WiFi module: no cloud, no
MQTT broker, no intermediate bridge. Home Assistant talks to the unit over its own UDP
protocol.

**Supported brands:** AUX, Zanussi, Ballu, Rovex, Tornado, Electrolux, Dunham, Rcool,
Akai, Kenwood, Hyundai, Centek, Roda, Shivaki — any unit built on the Broadlink module
of type `0x4E2A`.

## What it reads beyond the settings

Alongside mode, temperature and fan the integration reports the state of the
refrigeration circuit:

- **whether the compressor is actually running** — not «is the unit switched on»;
- **compressor output** as a percentage;
- **coil temperature**.

That makes real compressor starts visible. Starts are what wears the unit down and drives
electricity consumption, yet from air temperature alone you can only guess about them.

Mode, setpoint, fan speed and both swings are exposed as sensors on top of the climate
entity as well, because Home Assistant draws no history for climate attributes beyond
temperature.

## Installation

**Via HACS:** add this repository as a custom one, install the integration, restart Home
Assistant.

**Manually:** copy `custom_components/aircore` into your configuration's
`custom_components` folder and restart Home Assistant.

## Setup

Settings → Devices & services → Add integration → **AirCore**.

Units are discovered on the network automatically — pick yours from the list and give it
a name. If a unit stays silent (different subnet, router filtering broadcasts), enter its
address by hand: the probe aimed at a single address gets through, and the MAC is read
from the device itself.

### Options

The «Configure» button on the integration:

| option | default | why |
|---|---|---|
| Settings poll, seconds | 30 | mode, target and fan change rarely |
| Sensor poll, seconds | 30 | temperature and compressor come in a separate request |
| Compressor and coil sensors | on | turn off if you only need climate |
| Response timeout, seconds | 5 | raise it if the unit sits far from the access point |
| Debug mode | off | writes raw packets to the log |

## Entities

One device per air conditioner:

- **climate** — modes (cool, heat, dry, fan, auto), target temperature in 0.5° steps, fan
  speeds (auto, low, medium, high, mute, turbo), vertical louvres (7 positions) and
  horizontal swing (on/off);
- **sensors** — air temperature, coil temperature, compressor output;
- **binary sensor** — compressor running;
- **switches** — display, sleep mode, ionizer, self-clean, dry after shutdown, remote
  thermometer (iFeel).

## Examples

Entity names below are placeholders: Home Assistant builds them from the name you gave
the unit. Check the entity list for the exact ones.

### Count compressor starts per day

Wear and electricity are driven not by the air conditioner running, but by frequent
compressor starts. The unit has no such counter, but it is easy to assemble:

```yaml
sensor:
  - platform: history_stats
    name: Compressor starts today
    entity_id: binary_sensor.<your_unit>_compressor
    state: "on"
    type: count
    start: "{{ today_at('00:00') }}"
    end: "{{ now() }}"
```

The same helper in `time` mode shows how many hours the compressor actually worked —
a direct proxy for consumption.

### Warn about a freezing coil

A coil staying below zero usually means a clogged filter or low refrigerant:

```yaml
automation:
  - alias: Air conditioner is freezing up
    triggers:
      - trigger: numeric_state
        entity_id: sensor.<your_unit>_coil_temperature
        below: 0
        for: "00:15:00"
    actions:
      - action: notify.persistent_notification
        data:
          message: >-
            Coil below zero for over 15 minutes.
            Check the filter and refrigerant level.
```

### Quiet night mode

The unit beeps on every fan speed change, so at night those are worth minimising:

```yaml
automation:
  - alias: Air conditioner for the night
    triggers:
      - trigger: time
        at: "23:00:00"
    actions:
      - action: climate.set_fan_mode
        target:
          entity_id: climate.<your_unit>
        data:
          fan_mode: mute
      - action: switch.turn_off
        target:
          entity_id: switch.<your_unit>_display
```

## Removal

Settings → Devices & services → **AirCore** → three dots next to the unit → «Delete».
Entities and the device disappear along with the entry. The unit itself loses nothing:
the integration stores no settings on it and requires no unpairing.

To remove the integration entirely, delete `custom_components/aircore` (or remove it
in HACS) and restart Home Assistant.

## Known limitations

**Timers** are not exposed by the unit: the protocol structure has the fields, but no
data block ever carries a timer value. The app most likely implements timers in the
cloud rather than in the appliance.

**iFeel** can be switched on and off, but feeding the unit your own sensor readings is
impossible — the protocol has no command for writing an external temperature. With iFeel
on, the unit takes temperature from its remote.

**Readings outside physically possible bounds** (coil beyond −40…80 °C) are discarded:
occasionally the unit sends a corrupted packet where several values jump at once and
return a second later. The bounds are generous on purpose — a freezing coil goes below
zero, heating pushes it past fifty, and an idle unit simply mirrors the room.

**Horizontal louvres** have only two states — swinging or not. Intermediate positions are
not reported, even though the remote can stop them anywhere.

**Compressor fields** are read from a byte layout that may differ between brands. When a
reading contradicts the unit's state, it is dropped and the sensor stays empty rather
than showing a plausible but wrong number.

## Protocol

Communication runs over UDP port 80; the payload is encrypted with AES-128-CBC using a
key issued during authentication. Request structure:

```
bb 00 06 80 00 00 | CODE | 00 | SELECTOR | 01 | data
```

| code / selector | operation |
|---|---|
| `0x02` / `0x11` | read settings |
| `0x02` / `0x21` | read sensor |
| `0x0f` / `0x01` | write settings, 13 bytes of data |

The selector is closer to a register address than to «what to read»: some of them
(`0x08`–`0x0e`) move the louvres instead of returning data.

Replies start with `bb 00 07` on success and `bb 00 01` on refusal. The unit serves one
request at a time and refuses concurrent ones, so the integration retries.

## License

MIT
