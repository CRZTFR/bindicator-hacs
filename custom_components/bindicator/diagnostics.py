"""Diagnostics dump for bug reports.

Pulls /api/info + /api/state + the latest SSE snapshot. Anything with
PII (none in this device's surface, but defensive) would be redacted
here via async_redact_data.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import BindicatorConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BindicatorConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    out: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
        },
        "stream_connected": runtime.stream.connected,
        "snapshot": runtime.stream.snapshot,
    }
    try:
        out["info"] = await runtime.client.get_info()
    except Exception as err:  # noqa: BLE001
        out["info_error"] = str(err)
    try:
        out["state"] = await runtime.client.get_state()
    except Exception as err:  # noqa: BLE001
        out["state_error"] = str(err)
    return out
