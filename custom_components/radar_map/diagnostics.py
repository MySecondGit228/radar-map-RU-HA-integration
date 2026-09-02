"""Diagnostics support for RadarMap."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import RadarMapConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: RadarMapConfigEntry,
) -> dict[str, Any]:
    """Return compact diagnostics with no cookies, tokens, or raw payload."""
    coordinator = entry.runtime_data.coordinator
    snapshot = coordinator.data
    selected_state: list[dict[str, Any]] = []
    for selected in coordinator.selected_objects:
        current = coordinator.get_object(selected.object_id)
        semantic_event = coordinator.get_last_event(selected.object_id)
        selected_state.append(
            {
                "object_id": current.object_id,
                "object_type": current.object_type,
                "name": current.name,
                "region": current.region,
                "flags": dict(current.flags),
                "last_event_ts": current.last_event_ts,
                "last_event_type": semantic_event.code if semantic_event else None,
                "sources": list(current.sources),
            }
        )

    return {
        "api_status": "ok" if coordinator.last_update_success else "unavailable",
        "last_successful_update": (
            coordinator.last_successful_update.isoformat()
            if coordinator.last_successful_update
            else None
        ),
        "poll_interval_sec": (
            coordinator.update_interval.total_seconds() if coordinator.update_interval else None
        ),
        "configured_poll_interval_sec": coordinator.configured_poll_interval,
        "server_poll_interval_sec": coordinator.server_poll_interval,
        "api_version": snapshot.version if snapshot else None,
        "selected_regions": [
            item.name for item in coordinator.selected_objects if item.object_type == "region"
        ],
        "selected_cities": [
            item.name for item in coordinator.selected_objects if item.object_type == "city"
        ],
        "selected_districts": [
            item.name for item in coordinator.selected_objects if item.object_type == "district"
        ],
        "last_error": coordinator.last_error,
        "last_update_duration_sec": coordinator.last_update_duration,
        "last_semantic_event": (
            coordinator.last_event.as_attributes() if coordinator.last_event else None
        ),
        "selected_state": selected_state,
    }
