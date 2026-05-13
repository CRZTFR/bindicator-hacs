"""Thin REST client for the Bindicator device's local HTTP API.

Endpoints are documented in [local_api.h](../../../ESP/Bindicator/src/local_api.h);
this client is the Python counterpart. It's intentionally dumb — just
async HTTP calls — so the event stream and coordinator can be tested
against a fake easily.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 80
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


class BindicatorApiError(Exception):
    """Raised when a REST call fails. Distinguishes from aiohttp.ClientError so
    callers can decide whether to surface user-friendly messages or to retry."""


class BindicatorClient:
    """Async REST client for one Bindicator device.

    The host can be updated at runtime (e.g. when zeroconf rediscovers the
    device at a new DHCP-assigned IP) without reconstructing the client —
    callers just assign to .host.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._session = session
        self.host = host
        self.port = port

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def get_info(self) -> dict[str, Any]:
        """`GET /api/info` — identity + version. Cheap and used during
        config-flow validation to confirm the host is actually a Bindicator."""
        return await self._get("/api/info")

    async def get_state(self) -> dict[str, Any]:
        """`GET /api/state` — full snapshot. Used by the safety-net poll and
        as the initial sync after a fresh config entry setup."""
        return await self._get("/api/state")

    async def set_light(
        self,
        which: str,
        *,
        on: bool = True,
        r: int = 255,
        g: int = 255,
        b: int = 255,
        brightness: int = 255,
    ) -> None:
        """`POST /api/lights/{top|bottom}` with RGB + brightness. Sets the
        device's manualOverride so the schedule won't fight us."""
        if which not in {"top", "bottom"}:
            raise ValueError(f"unknown light {which!r}")
        await self._post(
            f"/api/lights/{which}",
            {"on": on, "r": r, "g": g, "b": b, "brightness": brightness},
        )

    async def clear_light_override(self) -> None:
        """`POST /api/lights/clear` — release manual override, schedule resumes."""
        await self._post("/api/lights/clear", None)

    async def preview(self) -> None:
        """`POST /api/preview` — equivalent of a touchpad short press."""
        await self._post("/api/preview", None)

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with self._session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise BindicatorApiError(f"GET {path} failed: {err}") from err

    async def _post(self, path: str, body: dict[str, Any] | None) -> None:
        url = f"{self.base_url}{path}"
        try:
            async with self._session.post(
                url,
                json=body if body is not None else {},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise BindicatorApiError(f"POST {path} failed: {err}") from err
