"""Diagnostic sensors — Wi-Fi signal strength + firmware version.

We deliberately don't expose a "current bin colour" sensor: the two light
entities are the authoritative live state, and a single-value sensor can't
faithfully represent a device that may have multiple concurrent schedules
out at once.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .const import SIGNAL_RSSI, SIGNAL_STATE
from .entity import BindicatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BindicatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            BindicatorRssiSensor(runtime),
            BindicatorFirmwareSensor(runtime),
        ]
    )


class BindicatorRssiSensor(BindicatorEntity, SensorEntity):
    _attr_translation_key = "rssi"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = "measurement"
    _attr_device_class = "signal_strength"

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_rssi"
        snapshot = runtime.stream.snapshot or runtime.coordinator.data or {}
        rssi = snapshot.get("rssi")
        if isinstance(rssi, (int, float)):
            self._attr_native_value = int(rssi)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RSSI.format(id=self._device_id),
                self._handle_rssi,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE.format(id=self._device_id),
                self._handle_state,
            )
        )

    @callback
    def _handle_rssi(self, payload: Any) -> None:
        try:
            self._attr_native_value = int(payload)
        except (TypeError, ValueError):
            return
        self.async_write_ha_state()

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        rssi = (payload or {}).get("rssi")
        if isinstance(rssi, (int, float)):
            self._attr_native_value = int(rssi)
            self.async_write_ha_state()


class BindicatorFirmwareSensor(BindicatorEntity, SensorEntity):
    """Firmware version as a diagnostic sensor. The device card also picks
    this up via DeviceInfo.sw_version; the sensor form makes it easy to
    template against in automations (e.g. "if firmware == 22")."""

    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_firmware"
        info = runtime.stream.snapshot or runtime.coordinator.data or {}
        version = info.get("sw_version") or info.get("version")
        if version is not None:
            self._attr_native_value = str(version)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Firmware is pushed in the snapshot, which arrives via both the SSE
        # snapshot event and the safety-net coordinator poll (both fire
        # SIGNAL_STATE with the same payload shape).
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE.format(id=self._device_id),
                self._handle_state,
            )
        )

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        version = (payload or {}).get("sw_version") or (payload or {}).get("version")
        if version is not None:
            self._attr_native_value = str(version)
            self.async_write_ha_state()
