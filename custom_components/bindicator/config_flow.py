"""Config flow for Bindicator: zeroconf discovery + manual IP fallback.

Zeroconf is the happy path — the device advertises `_bindicator._tcp`
with a TXT `id=<mac-derived>`. We treat that id as the unique key for
the config entry so DHCP renewals don't strand the device. Manual flow
exists for networks that filter mDNS (guest VLANs, some Mesh systems).
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import BindicatorApiError, BindicatorClient, DEFAULT_PORT
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_DEVICE_ID = "device_id"


class BindicatorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two entry points: zeroconf (auto) or user (manual IP)."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_id: str | None = None
        self._discovered_name: str | None = None

    # ----- Manual entry -----

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await self._probe(host, DEFAULT_PORT)
            except BindicatorApiError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_response"
            else:
                device_id = info.get("id")
                if not device_id:
                    errors["base"] = "invalid_response"
                else:
                    await self.async_set_unique_id(device_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    return self.async_create_entry(
                        title=info.get("name") or "Bindicator",
                        data={
                            CONF_HOST: host,
                            CONF_PORT: DEFAULT_PORT,
                            CONF_DEVICE_ID: device_id,
                            CONF_NAME: info.get("name") or "Bindicator",
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    # ----- Zeroconf -----

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        # TXT id is authoritative; falls back to mDNS instance name. The IP
        # comes from the discovery_info host field, which HA normalises from
        # whichever A record was advertised.
        properties = discovery_info.properties or {}
        device_id = properties.get("id")
        if not device_id:
            # Old/buggy firmware that didn't advertise id — bail rather than
            # creating an entry we can't identify.
            return self.async_abort(reason="no_devices_found")

        self._discovered_host = discovery_info.host
        self._discovered_port = discovery_info.port or DEFAULT_PORT
        self._discovered_id = device_id
        self._discovered_name = properties.get("name") or "Bindicator"

        await self.async_set_unique_id(device_id)
        # IMPORTANT: also update host on existing entries — DHCP renewals
        # would otherwise leave the integration pointing at a dead IP.
        # Pattern lifted from the Shelly integration.
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: self._discovered_host}
        )

        self.context["title_placeholders"] = {
            "name": self._discovered_name,
            "host": self._discovered_host,
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered_id is not None
        if user_input is None:
            return self.async_show_form(
                step_id="zeroconf_confirm",
                description_placeholders={
                    "name": self._discovered_name or "Bindicator",
                    "host": self._discovered_host or "",
                },
            )
        # User confirmed — create the entry. No need to probe; zeroconf
        # already gave us enough to identify the device.
        return self.async_create_entry(
            title=self._discovered_name or "Bindicator",
            data={
                CONF_HOST: self._discovered_host,
                CONF_PORT: self._discovered_port,
                CONF_DEVICE_ID: self._discovered_id,
                CONF_NAME: self._discovered_name,
            },
        )

    # ----- Helpers -----

    async def _probe(self, host: str, port: int) -> dict[str, Any]:
        """Hit /api/info to confirm the host actually speaks our protocol.
        Raises BindicatorApiError on transport errors, ValueError on a
        response that doesn't look like a Bindicator."""
        session = async_get_clientsession(self.hass)
        client = BindicatorClient(session, host, port)
        info = await client.get_info()
        if not isinstance(info, dict) or "id" not in info or "name" not in info:
            raise ValueError("response does not look like a Bindicator")
        return info
