"""The Bindicator integration.

One config entry per device. Each entry owns a REST client, a long-lived
SSE stream task, and a backup poll coordinator. Entities live across the
five platforms declared in const.PLATFORMS.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BindicatorClient
from .config_flow import CONF_DEVICE_ID
from .const import DOMAIN, PLATFORMS
from .coordinator import BindicatorCoordinator
from .event_stream import BindicatorEventStream

_LOGGER = logging.getLogger(__name__)


@dataclass
class BindicatorRuntimeData:
    """Per-entry handles. Stored on `entry.runtime_data` (HA 2024.12+ pattern).
    Entities pull these through entry.runtime_data so platforms don't need
    to reach into hass.data."""
    client: BindicatorClient
    coordinator: BindicatorCoordinator
    stream: BindicatorEventStream
    device_id: str


type BindicatorConfigEntry = ConfigEntry[BindicatorRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: BindicatorConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, 80)
    device_id = entry.data[CONF_DEVICE_ID]

    session = async_get_clientsession(hass)
    client = BindicatorClient(session, host, port)
    coordinator = BindicatorCoordinator(hass, client, device_id)
    stream = BindicatorEventStream(hass, session, client, device_id)

    # Initial state pull — fails fast if the device is unreachable during
    # setup, giving the user a clearer error in the UI than waiting on SSE.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = BindicatorRuntimeData(
        client=client,
        coordinator=coordinator,
        stream=stream,
        device_id=device_id,
    )

    # Forward to platforms BEFORE starting the stream — entities need to be
    # registered with the dispatcher to receive the snapshot event.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Now the platforms are set up and listening, kick off the SSE consumer.
    stream.start()

    # Pick up zeroconf-driven host updates by reloading on entry-data change.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BindicatorConfigEntry) -> bool:
    runtime: BindicatorRuntimeData = entry.runtime_data
    await runtime.stream.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BindicatorConfigEntry
) -> None:
    """Re-setup the entry when the zeroconf flow updated the host. Without
    this the integration keeps its stale client/stream pointing at the old
    IP after a DHCP renewal."""
    await hass.config_entries.async_reload(entry.entry_id)
