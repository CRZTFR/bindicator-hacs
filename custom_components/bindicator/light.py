"""Two RGB light entities (top, bottom) backed by the device's REST API
for commands and the SSE stream for state. Brightness is the max channel."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .const import SIGNAL_LIGHTS, SIGNAL_STATE
from .entity import BindicatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BindicatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            BindicatorLight(runtime, which="top", translation_key="top"),
            BindicatorLight(runtime, which="bottom", translation_key="bottom"),
        ]
    )


class BindicatorLight(BindicatorEntity, LightEntity):
    """One side of the lamp. Calls the device's REST API on turn_on /
    turn_off; reflects pushed updates from the `lights` SSE event."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(self, runtime, *, which: str, translation_key: str) -> None:
        super().__init__(runtime)
        self._which = which
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{self._device_id}_{which}"
        # Seed from the latest snapshot so HA doesn't render "unknown" on
        # restart while we wait for the first push.
        self._apply_state(runtime.stream.snapshot.get("lights", {}).get(which, {}))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Live updates.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LIGHTS.format(id=self._device_id),
                self._handle_lights,
            )
        )
        # Backstop: full snapshots from the SSE snapshot event or the
        # safety-net poll. Same signal carries both.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE.format(id=self._device_id),
                self._handle_state,
            )
        )

    @callback
    def _handle_lights(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        entry = payload.get(self._which)
        if entry:
            self._apply_state(entry)
            self.async_write_ha_state()

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        lights = (payload or {}).get("lights", {})
        entry = lights.get(self._which)
        if entry:
            self._apply_state(entry)
            self.async_write_ha_state()

    def _apply_state(self, entry: dict[str, Any]) -> None:
        if not entry:
            return
        self._attr_is_on = bool(entry.get("on", False))
        r = int(entry.get("r", 0))
        g = int(entry.get("g", 0))
        b = int(entry.get("b", 0))
        self._attr_rgb_color = (r, g, b)
        # Brightness mirrors the max channel — consistent with how the
        # firmware applies HA's brightness slider back to RGB.
        self._attr_brightness = max(r, g, b)

    async def async_turn_on(self, **kwargs: Any) -> None:
        # HA's slider sends brightness separately; combine with current or
        # newly-supplied RGB to drive the device. The firmware scales RGB
        # by brightness/255 server-side, so we just forward both.
        rgb = kwargs.get(ATTR_RGB_COLOR) or self._attr_rgb_color or (255, 255, 255)
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
        await self._runtime.client.set_light(
            self._which,
            on=True,
            r=int(rgb[0]),
            g=int(rgb[1]),
            b=int(rgb[2]),
            brightness=int(brightness),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._runtime.client.set_light(self._which, on=False)
