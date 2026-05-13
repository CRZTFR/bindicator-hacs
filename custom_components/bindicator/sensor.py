"""Sensor entities — current bin colour, Wi-Fi signal strength, firmware version."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .const import SIGNAL_RSSI, SIGNAL_SCHEDULE, SIGNAL_STATE
from .entity import BindicatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BindicatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            BindicatorCurrentBinSensor(runtime),
            BindicatorRssiSensor(runtime),
            BindicatorFirmwareSensor(runtime),
        ]
    )


class BindicatorCurrentBinSensor(BindicatorEntity, SensorEntity):
    """Current bin colour, or 'none' when no schedule is active."""

    _attr_translation_key = "current_bin"

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_current_bin"
        snapshot = runtime.stream.snapshot or {}
        self._apply(snapshot.get("current_bin"))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SCHEDULE.format(id=self._device_id),
                self._handle_schedule,
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
    def _handle_schedule(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        self._apply(payload.get("current"))
        self.async_write_ha_state()

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        self._apply((payload or {}).get("current_bin"))
        self.async_write_ha_state()

    def _apply(self, entry: dict[str, Any] | None) -> None:
        if not entry:
            self._attr_native_value = "none"
        else:
            self._attr_native_value = entry.get("color") or "none"


class BindicatorRssiSensor(BindicatorEntity, SensorEntity):
    _attr_translation_key = "rssi"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = "measurement"
    _attr_device_class = "signal_strength"

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_rssi"
        snapshot = runtime.stream.snapshot or {}
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
    """Firmware version as a separate diagnostic sensor. Mirrors the
    `update` entity's installed-version field, but easier to template
    against in automations ('if firmware == 22')."""

    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_firmware"
        info = runtime.stream.snapshot or {}
        version = info.get("sw_version") or info.get("version")
        if version is not None:
            self._attr_native_value = str(version)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Firmware is pushed in the snapshot, which comes through both the
        # SSE snapshot event and the poll coordinator.
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
