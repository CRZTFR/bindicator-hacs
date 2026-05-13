# Bindicator — Home Assistant integration

Local-push integration for the [Bindicator](https://bindicator.net) bin-collection reminder lamp. Auto-discovers the device on your LAN, exposes the two RGB lights, the touchpad as an event entity, and the bin schedule as a calendar — all over a direct HTTP/SSE connection to the device. No cloud, no MQTT broker.

## Install

### HACS (recommended)

1. In HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/CRZTFR/bindicator-hacs` as type **Integration**
3. Install the **Bindicator** integration
4. Restart Home Assistant
5. Your Bindicator should appear under **Settings → Devices & Services → Discovered**. Click **Add** — there's nothing to configure.

If auto-discovery doesn't find your device (some routers block mDNS across VLANs), add it manually via **Settings → Devices & Services → Add Integration → Bindicator** and enter the IP address.

### Manual

1. Copy `custom_components/bindicator/` into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Follow step 5 above

## Requirements

- Home Assistant 2025.1.0 or newer
- Bindicator firmware v23 or newer
- HA and the Bindicator on the same LAN, with multicast reachability

## What you get

| Entity | Type | Notes |
|---|---|---|
| `light.<id>_top` | Light | RGB, brightness |
| `light.<id>_bottom` | Light | RGB, brightness |
| `event.<id>_touchpad` | Event | `press` / `hold` event types |
| `calendar.<id>` | Calendar | Upcoming bin event |
| `sensor.<id>_current_bin` | Sensor | Active schedule colour or "none" |
| `sensor.<id>_rssi` | Sensor | Wi-Fi signal strength (dBm), diagnostic |
| `sensor.<id>_firmware` | Sensor | Firmware version, diagnostic |
| `update.<id>` | Update | Firmware-update entity |

All entities are driven by a single Server-Sent Events stream from the device, so updates are pushed in real time (touchpad press → HA event within ~50ms).

## Manual override

When you turn on a Bindicator light from HA, the device enters a "manual override" state: the schedule loop won't repaint the LEDs until the override clears. Override clears when:

- You call `light.turn_off` from HA, or
- The user taps the physical touchpad while LEDs are on, or
- A *new* schedule transitions in (more active schedules than before).

This matches the existing touchpad behaviour and is documented here so HA automation authors understand the precedence.

## Known limitations

- IPv4 only — `ESPmDNS` on the device is v4-only.
- LAN-trust — there's no authentication on the device's local API. Anyone on your Wi-Fi can change the LED colours. Acceptable for a typical home; consider VLAN isolation if you have untrusted devices on the same network.
- Schedules are edited in the Bindicator app, not in HA. The calendar entity is read-only.

## Reporting bugs

Please attach the diagnostic dump (Settings → Devices & Services → Bindicator → ⋮ → Download diagnostics) and link to your HA logs.
