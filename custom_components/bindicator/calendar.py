"""Calendar entity for the Bindicator's bin schedule.

Two data paths, by design:

  - SSE `schedule` event + REST snapshot — push the *currently active* event
    so the entity's `state` flips to "on" the instant a bin starts and back
    to "off" the moment it ends. Falls back to the next upcoming event when
    nothing is active, so the entity's `event` attribute always points at
    something useful.

  - REST `GET /api/schedule?from&to` — pull *every* occurrence overlapping a
    window. Called from `async_get_events` whenever Lovelace renders the
    calendar card. This is the path that supports multiple concurrent
    schedules in a day, weeks of upcoming events, and arbitrary scrolling.

The split matters because Lovelace's calendar card and most automations ask
"give me events between X and Y", and a one-event-at-a-time entity drops
data on the floor. The REST endpoint is the source of truth for *what's
scheduled*; the SSE feed is the source of truth for *what's happening now*.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BindicatorConfigEntry
from .api import BindicatorApiError
from .const import SIGNAL_SCHEDULE, SIGNAL_STATE
from .entity import BindicatorEntity

_LOGGER = logging.getLogger(__name__)


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
        # Currently active (or next upcoming) event — what the entity's
        # `state` and `event` attribute report. Lovelace's per-window query
        # goes through async_get_events instead.
        self._active_event: CalendarEvent | None = None
        snapshot = runtime.stream.snapshot or runtime.coordinator.data or {}
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
        return self._active_event

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Pull every occurrence in [start_date, end_date] from the device.

        The device's `/api/schedule` endpoint runs each occurrence through
        the same activationCheck the LEDs use, so bi-weekly inactive weeks
        and future-anchored schedules are filtered out for us. We just
        translate epoch → tz-aware datetime and hand the list to HA."""
        try:
            entries = await self._runtime.client.get_schedule(
                int(start_date.timestamp()), int(end_date.timestamp())
            )
        except BindicatorApiError as err:
            _LOGGER.debug("Bindicator schedule fetch failed: %s", err)
            return []
        events: list[CalendarEvent] = []
        for entry in entries:
            start = entry.get("start")
            end = entry.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            color = entry.get("color") or "unknown"
            # Name is the human-readable schedule label ("General waste",
            # "Recycling", …). Falls back to the colour hex if the device
            # didn't send one — older firmware or an empty label in the
            # app. The summary is what cards like TrashCard pattern-match
            # against, so a real name is much more useful than #ff0000.
            summary = entry.get("name") or color
            events.append(
                CalendarEvent(
                    start=datetime.fromtimestamp(start, tz=timezone.utc),
                    end=datetime.fromtimestamp(end, tz=timezone.utc),
                    summary=summary,
                    description=f"Color {color}",
                )
            )
        return events

    @callback
    def _handle_schedule(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        # Prefer the currently-active occurrence so the entity's state
        # flips to "on" while the bin is out. Fall back to the next
        # upcoming occurrence when nothing is active so we still have
        # something to surface as the "next event".
        self._apply_event(payload.get("current") or payload.get("next"))
        self.async_write_ha_state()

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        self._apply_snapshot(payload or {})
        self.async_write_ha_state()

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._apply_event(
            snapshot.get("current_bin") or snapshot.get("next_bin")
        )

    def _apply_event(self, entry: dict[str, Any] | None) -> None:
        if not entry:
            self._active_event = None
            return
        start_epoch = entry.get("start")
        end_epoch = entry.get("end") or (
            start_epoch + 3600 if start_epoch else None
        )
        if not start_epoch or not end_epoch:
            self._active_event = None
            return
        color = entry.get("color", "unknown")
        summary = entry.get("name") or color
        self._active_event = CalendarEvent(
            start=datetime.fromtimestamp(start_epoch, tz=timezone.utc),
            end=datetime.fromtimestamp(end_epoch, tz=timezone.utc),
            summary=summary,
            description=f"Color {color}",
        )
