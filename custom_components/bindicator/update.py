"""Firmware-version `update` entity.

Read-only — this integration doesn't push OTAs. The Bindicator app
handles OTA via AWS IoT. We surface the installed version so HA's
device card shows it, and could expose a "latest" version pulled from
a static endpoint later. For now we just report `installed_version`
and leave `latest_version` equal so HA doesn't flag an update.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .const import SIGNAL_STATE
from .entity import BindicatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BindicatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BindicatorUpdate(entry.runtime_data)])


class BindicatorUpdate(BindicatorEntity, UpdateEntity):
    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_supported_features = 0  # No HA-driven install action

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_update"
        snapshot = runtime.stream.snapshot or {}
        version = snapshot.get("sw_version") or snapshot.get("version")
        if version is not None:
            self._attr_installed_version = str(version)
            self._attr_latest_version = str(version)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
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
            self._attr_installed_version = str(version)
            self._attr_latest_version = str(version)
            self.async_write_ha_state()
