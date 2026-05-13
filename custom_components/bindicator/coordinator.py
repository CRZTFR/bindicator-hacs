"""Safety-net poll coordinator.

The primary data path is the SSE stream in `event_stream.py`. This
DataUpdateCoordinator wraps a periodic `/api/state` GET so that if the
SSE connection misses an event (broker blip, transient parse failure),
we still re-sync to the device's actual state within POLL_INTERVAL_SECONDS.

Entities subscribe to it for full-snapshot updates; live updates go via
dispatcher signals (see event_stream.py).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BindicatorApiError, BindicatorClient
from .const import DOMAIN, POLL_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class BindicatorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One per config entry."""

    def __init__(self, hass: HomeAssistant, client: BindicatorClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.get_state()
        except BindicatorApiError as err:
            raise UpdateFailed(str(err)) from err
