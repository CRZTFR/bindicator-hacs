"""Constants for the Bindicator integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "bindicator"

# Platforms registered by __init__.py via async_forward_entry_setups.
# We deliberately omit Platform.UPDATE — the device only OTAs via AWS IoT,
# never via HA, so an update entity has no actionable state and just
# duplicates sensor.firmware.
PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.EVENT,
    Platform.CALENDAR,
    Platform.SENSOR,
]

# Dispatcher signal names. The event stream pushes payloads via
# async_dispatcher_send; entities subscribe with async_dispatcher_connect.
# Each signal is suffixed with the device's unique id so two Bindicators on
# one HA instance don't cross-wire.
SIGNAL_AVAILABILITY = "bindicator_availability_{id}"
SIGNAL_LIGHTS = "bindicator_lights_{id}"
SIGNAL_TOUCHPAD = "bindicator_touchpad_{id}"
SIGNAL_SCHEDULE = "bindicator_schedule_{id}"
SIGNAL_RSSI = "bindicator_rssi_{id}"
SIGNAL_STATE = "bindicator_state_{id}"  # full snapshot from REST poll

# How often to do the safety-net REST poll. SSE is the primary source of
# truth; this is a backstop for missed events (e.g. brief network blip).
POLL_INTERVAL_SECONDS = 60

# How long the event stream can go without any traffic from the device
# (data event or :ping comment) before we mark the device unavailable.
# Device sends a keepalive every 15s; 45s = 3 missed heartbeats.
SSE_LIVENESS_TIMEOUT_SECONDS = 45

# Reconnect backoff for the SSE stream.
SSE_RECONNECT_INITIAL_SECONDS = 2
SSE_RECONNECT_MAX_SECONDS = 60

MANUFACTURER = "Bindicator"
