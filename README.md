# AromaTech Ambience for Home Assistant

Local Bluetooth control of the **AromaTech Ambience** scent diffuser. No cloud,
no vendor account. It works through a local Bluetooth adapter or ESPHome
Bluetooth proxies.

> Not affiliated with or endorsed by AromaTech. "AromaTech" and "Ambience" are
> used only to identify the supported hardware.

<img src="https://raw.githubusercontent.com/subtlogic/ha-aromatech-ambience/main/examples/images/dashboard-popup.png" alt="AromaTech Ambience dashboard card" width="320">

## Why a separate integration

The community
[`ha-aromatech-scent-diffuser`](https://github.com/ttrushin/ha-aromatech-scent-diffuser)
integration supports other AromaTech models, which use a different Bluetooth
protocol (`fff0`/`fff6`). The Ambience uses service `EE01` with its own
framing, so it needs its own implementation. The full decode is in
[docs/PROTOCOL.md](docs/PROTOCOL.md).

## What you get

| Entity | Type | Notes |
|--------|------|-------|
| Scenting | switch | Master on/off: whether the diffuser scents at all |
| Light | light | RGB colour, brightness, effects Warm / Cool / Flow / Off |
| Sound | switch | The unit's audible feedback |
| Intensity | number | 1–4. Stored in the schedule, so setting it rewrites the schedule |
| Schedule enabled | switch | |
| Schedule 1 Mon … 7 Sun | switch | One per weekday |
| Schedule from / to | time | Whole hours only; the device has no minutes field |
| Schedule | sensor | Read-only summary with the raw frame as an attribute |

Schedule edits are confirmed against a fresh report from the device and retried
up to three times. If the device still holds the old value, the action fails
with an error rather than reporting success.

See [examples](examples/README.md) for the dashboard card above, the device
page, and ready-to-paste automation ideas.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/subtlogic/ha-aromatech-ambience`, category
   **Integration**.
2. Install **AromaTech Ambience** and restart Home Assistant.

### Manual

Copy `custom_components/aromatech_ambience` into your
`config/custom_components/` directory and restart Home Assistant.

## Setup

The diffuser is discovered automatically when a Bluetooth adapter or proxy
hears it. You can also add it from **Settings → Devices & services → Add
integration → AromaTech Ambience**.

The Ambience advertises intermittently. If it is not found, wait a minute and
make sure it is in range of an adapter or proxy.

### Options

**Heartbeat interval** (default 300 s, range 30–3600 s). Each poll connects,
sends a time sync, reads the device's full state and disconnects. Shorter
intervals pick up changes made in the vendor app sooner, but use one of the
proxy's connection slots more often. An ESP32 proxy has only three.

## Requirements

- Home Assistant 2026.3 or newer
- A Bluetooth adapter or an ESPHome Bluetooth proxy in range of the diffuser

## Troubleshooting

**Download diagnostics** from the device page and attach the file to your
issue. It includes the last 24 Bluetooth frames sent and received, which is
usually what it takes to tell an ignored write from one that was never sent.
The device address is redacted.

Entities show as unavailable until the first successful poll. A miss at boot is
normal; the integration retries on the next heartbeat.

## Limitations

- Tested on one Ambience unit. Other AromaTech models are not supported.
- Only one schedule slot is exposed. The app suggests the device may hold more.
- The weekday bit order (bit 0 = Sunday) is inferred. Please open an issue if
  the day switches do not match the vendor app.

## Roadmap

Planned, in no particular order and without dates:

- **Scent remaining.** Estimate how much oil is left from the device's spray
  timing and your schedule, calibrated by weighing the bottle, with a
  days-remaining sensor and a "scent low" alert you can turn into a phone
  notification (a blueprint will be included).
- **Confirm the weekday mapping.** Bit 0 = Sunday is inferred from three
  observed values; a report from another unit would settle it.
- **Multiple schedule slots.** The vendor app suggests the device holds more
  than one; only the first is exposed today.

Ideas and reports are welcome in
[issues](https://github.com/subtlogic/ha-aromatech-ambience/issues).

## Development

```
python -m unittest discover -s tests -v
```

The tests stub Home Assistant, so they run without it installed.

The brand images in `custom_components/aromatech_ambience/brand/` are drawn by
`tools/brand/draw_brand.py` (needs Pillow; pass `--font` off macOS).

## License

MIT
