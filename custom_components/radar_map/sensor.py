"""Sensor platform for RadarMap."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RadarMapConfigEntry
from .const import MAX_SOURCE_TEXT_LENGTH
from .entity import RadarMapEntity
from .models import RadarMapObject


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarMapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up last-event sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        RadarMapLastEventSensor(coordinator, selected) for selected in coordinator.selected_objects
    )


class RadarMapLastEventSensor(RadarMapEntity, SensorEntity):
    """Timestamp and compact context of the latest object event."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_event"
    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, coordinator, selected: RadarMapObject) -> None:
        super().__init__(coordinator, selected)
        self._attr_unique_id = f"{selected.object_id}:last_event"

    @property
    def native_value(self) -> datetime | None:
        """Return the event timestamp as a timezone-aware datetime."""
        timestamp = self.current.last_event_ts
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return the requested compact event context."""
        item = self.current
        text = item.source_text
        if text and len(text) > MAX_SOURCE_TEXT_LENGTH:
            text = text[: MAX_SOURCE_TEXT_LENGTH - 1] + "…"
        sources = list(item.sources)
        return {
            "source_text": text,
            "last_event_ts": item.last_event_ts,
            "object_type": item.object_type,
            "region": item.region,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "active_alert_types": list(item.active_alert_types),
            "source": sources[0] if len(sources) == 1 else None,
            "sources": sources,
        }
