# AirCore

Broadlink air conditioners in Home Assistant directly — no cloud, no MQTT, no bridge.

Works with units built on the Broadlink module of type `0x4E2A`: AUX and its brands —
Zanussi, Ballu, Rovex, Tornado, Electrolux, Dunham, Rcool, Akai, Kenwood.

## Features

- climate: modes, target temperature in 0.5° steps, fan speeds, louvres
- **compressor state** — whether it actually runs and at what output
- coil and air temperature
- switches: display, sleep mode, ionizer, self-clean, dry after shutdown, iFeel

Devices are discovered on the network automatically: just pick yours from the list.
