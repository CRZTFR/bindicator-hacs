# Bindicator — Home Assistant integration

Local-push integration for the [Bindicator](https://bindicator.net) bin-collection reminder lamp. Auto-discovers the device on your LAN, exposes the two RGB lights, the touchpad as an event entity, and the bin schedule as a calendar. Fully local communication.

## Install

### HACS (recommended)

1. In HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/CRZTFR/bindicator` as type **Integration**
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
- Bindicator firmware v13 or newer (V1 hardware) / v24 or newer (V2 hardware). Check for updates in the Bindicator app's settings.
- HA and the Bindicator on the same LAN, with multicast reachability

## What you get

| Entity | Type | Notes |
|---|---|---|
| `light.<id>_top` | Light | RGB, brightness. Authoritative live state of the upper light segment. |
| `light.<id>_bottom` | Light | RGB, brightness. Authoritative live state of the lower light segment. |
| `event.<id>_touchpad` | Event | `press` / `hold` event types from the physical touchpad. |
| `calendar.<id>` | Calendar | Every scheduled bin event over a time window. Multiple concurrent schedules surface as overlapping events; state is "on" while any bin is currently out. |
| `sensor.<id>_rssi` | Sensor | Wi-Fi signal strength (dBm), diagnostic. |
| `sensor.<id>_firmware` | Sensor | Firmware version, diagnostic. |

Live updates arrive via a Server-Sent Events stream from the device (touchpad press → HA event within ~50ms). The calendar entity additionally pulls a per-window event list from `/api/schedule` whenever Lovelace renders the calendar card — so concurrent and far-future schedules are never lossy.

The calendar event `summary` is the schedule's name as set in the Bindicator app ("General waste", "Recycling", etc.) — see the **TrashCard** section below for using this with the popular bin-tracking Lovelace card.

## TrashCard (recommended dashboard card)

The [TrashCard](https://github.com/idaho/hassio-trash-card) custom card pairs perfectly with the Bindicator's calendar — it reads any calendar entity and renders a tidy "next collection" view on your dashboard. The Bindicator integration deliberately writes the schedule's app-defined name as each event's summary so TrashCard's pattern matching is as simple as typing your bin names.

### Install TrashCard

1. HACS → Frontend → ⋮ → **Custom repositories** (or search the default HACS list for "TrashCard").
2. Install **TrashCard**, refresh the browser.
3. Add a new card to your dashboard → **Custom: TrashCard**.

### Wire it to the Bindicator

In the card editor, set the entity to `calendar.<your_bindicator>` and define one pattern per bin name. Example YAML for a household with three weekly bins named "General waste", "Recycling", and "Garden waste" in the Bindicator app:

```yaml
type: custom:trash-card
entities:
  - calendar.bindicator      # use whatever your device's calendar entity is
next_days: 14
day_style: counter
card_style: card
color_mode: background
with_label: true
pattern:
  - label: General waste
    pattern: General waste   # substring-matched against the calendar event summary
    type: waste
    icon: mdi:trash-can
    color: dark-grey
  - label: Recycling
    pattern: Recycling
    type: recycle
    icon: mdi:recycle-variant
    color: amber
  - label: Garden waste
    pattern: Garden waste
    type: organic
    icon: mdi:leaf
    color: light-green
```

The `pattern` field is matched as a case-insensitive substring against the event summary, so the names in your card config just need to be contained in the names you used in the Bindicator app. If a schedule on the device has no name (typically one saved with an older app or firmware), the calendar falls back to the colour hex as the summary. You can match on `#ff0000` etc. as a temporary workaround until you re-save the schedule in the app.

For the full set of TrashCard options (chip layout, all-day filtering, custom pictures, etc.) see the [TrashCard README](https://github.com/idaho/hassio-trash-card).

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
