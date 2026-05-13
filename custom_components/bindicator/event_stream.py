"""SSE consumer for the Bindicator device's `/api/events` endpoint.

This is the primary data path. The device pushes touchpad, lights,
schedule, rssi, and goodbye events here; this class parses them and
fans them out via Home Assistant's dispatcher signals so individual
entities can update themselves without us holding entity references.

Why not `DataUpdateCoordinator`? Because that's poll-shaped — `_async_update_data`
returns the latest state and entities pull from it. With SSE we have
push-shaped data, where individual events update different subsets of
state. The MQTT and Tasmota integrations use the same dispatcher pattern,
and that's what we're modelling here. `coordinator.py` still exists as a
safety-net poll for missed events.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import BindicatorClient
from .const import (
    SIGNAL_AVAILABILITY,
    SIGNAL_LIGHTS,
    SIGNAL_RSSI,
    SIGNAL_SCHEDULE,
    SIGNAL_STATE,
    SIGNAL_TOUCHPAD,
    SSE_LIVENESS_TIMEOUT_SECONDS,
    SSE_RECONNECT_INITIAL_SECONDS,
    SSE_RECONNECT_MAX_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class BindicatorEventStream:
    """Owns the long-lived SSE connection for a single device.

    Lifecycle:
      start() spawns a background task that loops forever:
        - opens an SSE connection
        - parses lines into events
        - dispatches each event
        - on disconnect, sleeps with exponential backoff and reconnects
      stop() cancels the task and closes the connection.

    The `connected` property is what entities read for `_attr_available`.
    It flips false either on stream error OR when no traffic arrives for
    SSE_LIVENESS_TIMEOUT_SECONDS (catches half-open TCP that aiohttp
    doesn't notice quickly).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        client: BindicatorClient,
        device_id: str,
    ) -> None:
        self._hass = hass
        self._session = session
        self._client = client
        self._device_id = device_id
        self._task: asyncio.Task | None = None
        self._connected = False
        self._stopping = False
        # Latest known snapshot — exposed for diagnostics and used by entities
        # to recover state after a HA restart without waiting for the next
        # push.
        self.snapshot: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = self._hass.async_create_background_task(
            self._run(), name=f"bindicator.events.{self._device_id}"
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        self._set_connected(False)

    def _set_connected(self, value: bool) -> None:
        if self._connected == value:
            return
        self._connected = value
        async_dispatcher_send(
            self._hass, SIGNAL_AVAILABILITY.format(id=self._device_id), value
        )

    async def _run(self) -> None:
        backoff = SSE_RECONNECT_INITIAL_SECONDS
        while not self._stopping:
            try:
                await self._consume()
                # Clean exit (server closed stream) — quick retry.
                backoff = SSE_RECONNECT_INITIAL_SECONDS
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "Bindicator SSE error (%s); retry in %ss",
                    err, backoff,
                )
            self._set_connected(False)
            if self._stopping:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, SSE_RECONNECT_MAX_SECONDS)

    async def _consume(self) -> None:
        url = f"{self._client.base_url}/api/events"
        # No request timeout — SSE is long-lived. We enforce liveness via the
        # per-line wait_for below.
        async with self._session.get(url, headers={"Accept": "text/event-stream"}, timeout=aiohttp.ClientTimeout(total=None, sock_connect=10)) as resp:
            resp.raise_for_status()
            self._set_connected(True)
            event_name: str | None = None
            data_lines: list[str] = []
            async for raw in self._iter_lines(resp):
                # Heartbeat comments start with ":". They're not events but
                # they DO reset our liveness clock (handled by wait_for).
                if raw.startswith(":"):
                    continue
                if raw == "":
                    # Empty line dispatches the buffered event.
                    if data_lines or event_name:
                        self._dispatch(event_name, "\n".join(data_lines))
                    event_name = None
                    data_lines = []
                    continue
                if raw.startswith("event:"):
                    event_name = raw[len("event:"):].strip()
                elif raw.startswith("data:"):
                    data_lines.append(raw[len("data:"):].lstrip())
                # id: and retry: lines are SSE-standard but we ignore them.

    async def _iter_lines(self, resp: aiohttp.ClientResponse):
        """Yield raw decoded lines, raising if nothing arrives for too long."""
        while True:
            try:
                line = await asyncio.wait_for(
                    resp.content.readline(),
                    timeout=SSE_LIVENESS_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as err:
                raise BindicatorStreamTimeout("no SSE traffic") from err
            if not line:
                # EOF — server closed the connection.
                return
            yield line.decode("utf-8", errors="replace").rstrip("\r\n")

    def _dispatch(self, event_name: str | None, data: str) -> None:
        if event_name is None:
            return
        try:
            payload = json.loads(data) if data else None
        except json.JSONDecodeError:
            _LOGGER.debug("Malformed SSE %s payload: %s", event_name, data)
            return
        signal_map = {
            "snapshot": SIGNAL_STATE,
            "touchpad": SIGNAL_TOUCHPAD,
            "lights":   SIGNAL_LIGHTS,
            "schedule": SIGNAL_SCHEDULE,
            "rssi":     SIGNAL_RSSI,
        }
        if event_name == "snapshot" and isinstance(payload, dict):
            # Cache for diagnostics and post-restart sync.
            self.snapshot = payload
        if event_name == "goodbye":
            # Device is restarting (OTA or scheduled reboot). Flip availability
            # off immediately so HA doesn't show stale online state until
            # liveness timeout expires.
            self._set_connected(False)
            return
        signal = signal_map.get(event_name)
        if signal is None:
            _LOGGER.debug("Unhandled SSE event %s", event_name)
            return
        async_dispatcher_send(
            self._hass, signal.format(id=self._device_id), payload
        )


class BindicatorStreamTimeout(Exception):
    """Raised by the SSE consumer when the device stops sending data."""
