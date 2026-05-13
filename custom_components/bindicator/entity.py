"""Shared entity base that wires every platform to the stream's availability
signal and assembles a consistent DeviceInfo block. Each platform module
subclasses this rather than duplicating boilerplate."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import BindicatorRuntimeData
from .const import DOMAIN, MANUFACTURER, SIGNAL_AVAILABILITY


class BindicatorEntity(Entity):
    """Base class for all entities. Pulls availability from the SSE stream
    rather than from the safety-net coordinator — SSE liveness is the
    authoritative signal."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime: BindicatorRuntimeData) -> None:
        self._runtime = runtime
        self._device_id = runtime.device_id
        # Initial availability reflects the stream's current state. The
        # dispatcher will overwrite it on the next transition.
        self._attr_available = runtime.stream.connected
        snapshot = runtime.stream.snapshot or runtime.coordinator.data or {}
        sw_version = None
        # The poll snapshot from /api/state doesn't include firmware, but
        # the SSE snapshot has gone through /api/info during config flow.
        # We pick whichever is available; the update entity refreshes this.
        if isinstance(snapshot, dict):
            sw_version = snapshot.get("version") or snapshot.get("sw_version")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=runtime.coordinator.config_entry.title if runtime.coordinator.config_entry else "Bindicator",  # type: ignore[union-attr]
            manufacturer=MANUFACTURER,
            sw_version=sw_version,
            configuration_url=f"http://{runtime.client.host}/api/state",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_AVAILABILITY.format(id=self._device_id),
                self._handle_availability,
            )
        )

    @callback
    def _handle_availability(self, available: bool) -> None:
        self._attr_available = available
        self.async_write_ha_state()
