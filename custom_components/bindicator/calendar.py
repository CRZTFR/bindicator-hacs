"""Calendar entity exposing the next bin event.

The device only tells us about the *next* upcoming bin (a single
occurrence), so this calendar entity is intentionally simple: one event
at a time, refreshed on every `schedule` SSE push or REST poll.

Lovelace's calendar card renders this out of the box, and the entity is
queryable by automations ("if calendar.bindicator has an event in the
next 12 hours, send a notification").
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .const import SIGNAL_SCHEDULE, SIGNAL_STATE
from .entity import BindicatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BindicatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BindicatorCalendar(entry.runtime_data)])


class BindicatorCalendar(BindicatorEntity, CalendarEntity):
    _attr_translation_key = "schedule"

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{self._device_id}_calendar"
        self._next_event: CalendarEvent | None = None
        # Seed from snapshot.
        snapshot = runtime.stream.snapshot or {}
        self._apply_snapshot(snapshot)

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

    @property
    def event(self) -> CalendarEvent | None:
        return self._next_event

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        # Single-event calendar; return it if it falls inside the window.
        if self._next_event is None:
            return []
        if self._next_event.start <= end_date and self._next_event.end >= start_date:
            return [self._next_event]
        return []

    @callback
    def _handle_schedule(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        self._apply_next(payload.get("next"))
        self.async_write_ha_state()

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        self._apply_snapshot(payload or {})
        self.async_write_ha_state()

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._apply_next(snapshot.get("next_bin"))

    def _apply_next(self, entry: dict[str, Any] | None) -> None:
        if not entry:
            self._next_event = None
            return
        start_epoch = entry.get("start")
        end_epoch = entry.get("end") or (
            start_epoch + 3600 if start_epoch else None
        )
        if not start_epoch or not end_epoch:
            self._next_event = None
            return
        self._next_event = CalendarEvent(
            start=datetime.fromtimestamp(start_epoch, tz=timezone.utc),
            end=datetime.fromtimestamp(end_epoch, tz=timezone.utc),
            summary=f"Bin: {entry.get('color', 'unknown')}",
            description=f"Color {entry.get('color', 'unknown')}",
        )
