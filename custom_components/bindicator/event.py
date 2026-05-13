"""Touchpad event entity.

Fires `press` and `hold` event types as the device pushes them via SSE.
HA exposes these as event entities (HA 2023.8+), which is the correct
shape for "user did a thing on the device" — distinct from buttons,
which represent "HA tells the device to do a thing".
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .const import SIGNAL_TOUCHPAD
from .entity import BindicatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BindicatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BindicatorTouchpadEvent(entry.runtime_data)])


class BindicatorTouchpadEvent(BindicatorEntity, EventEntity):
    _attr_event_types = ["press", "hold"]
    _attr_translation_key = "touchpad"

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_touchpad"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_TOUCHPAD.format(id=self._device_id),
                self._handle_touchpad,
            )
        )

    @callback
    def _handle_touchpad(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        event_type = payload.get("type")
        if event_type in self._attr_event_types:
            self._trigger_event(event_type)
            self.async_write_ha_state()
