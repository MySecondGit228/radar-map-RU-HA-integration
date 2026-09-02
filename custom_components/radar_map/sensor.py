"""Sensor platform for RadarMap."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import RadarMapConfigEntry
from .const import EVENT_CODES, MAX_SOURCE_TEXT_LENGTH, SUMMARY_OBJECT_ID
from .coordinator import RadarMapSemanticEvent
from .entity import RadarMapEntity, RadarMapSummaryEntity
from .models import RadarMapObject


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarMapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up last-event sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            *(
                RadarMapLastEventSensor(coordinator, selected)
                for selected in coordinator.selected_objects
            ),
            *(
                RadarMapLastSemanticEventSensor(coordinator, selected)
                for selected in coordinator.selected_objects
            ),
            RadarMapSummaryLastSemanticEventSensor(coordinator),
        ]
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
        semantic_event = self.coordinator.get_last_event(self.selected.object_id)
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
            "last_event_type": semantic_event.code if semantic_event else None,
        }


class _RadarMapSemanticEventSensorMixin:
    """Shared restore and attribute behavior for semantic event sensors."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:message-alert-outline"
    _attr_options = EVENT_CODES
    _restored_value: str | None = None
    _restored_attributes: dict[str, object] = {}

    @property
    def event(self) -> RadarMapSemanticEvent | None:
        """Return the current coordinator event in concrete subclasses."""
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Restore the last event until a new semantic transition arrives."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
            return
        if last_state.state not in EVENT_CODES:
            return
        self._restored_value = last_state.state
        keys = {
            "event_code",
            "alert_type",
            "state",
            "transition",
            "event_timestamp",
            "api_last_event_ts",
            "object_type",
            "object_id",
            "name",
            "region",
            "source_text",
            "sources",
        }
        self._restored_attributes = {
            key: value for key, value in last_state.attributes.items() if key in keys
        }

    @property
    def native_value(self) -> str | None:
        """Return a stable event code suitable for automations."""
        if self.event is not None:
            return self.event.code
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return structured context for the observed transition."""
        if self.event is not None:
            return self.event.as_attributes()
        return dict(self._restored_attributes)


class RadarMapLastSemanticEventSensor(
    _RadarMapSemanticEventSensorMixin,
    RadarMapEntity,
    RestoreEntity,
    SensorEntity,
):
    """Latest semantic transition for one selected RadarMap object."""

    _attr_translation_key = "last_event_type"

    def __init__(self, coordinator, selected: RadarMapObject) -> None:
        super().__init__(coordinator, selected)
        self._attr_unique_id = f"{selected.object_id}:last_event_type"
        self._restored_attributes = {}

    @property
    def event(self) -> RadarMapSemanticEvent | None:
        """Return this object's latest transition."""
        return self.coordinator.get_last_event(self.selected.object_id)


class RadarMapSummaryLastSemanticEventSensor(
    _RadarMapSemanticEventSensorMixin,
    RadarMapSummaryEntity,
    RestoreEntity,
    SensorEntity,
):
    """Latest semantic transition across every selected object."""

    _attr_translation_key = "last_event_type"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{SUMMARY_OBJECT_ID}:last_event_type"
        self._restored_attributes = {}

    @property
    def event(self) -> RadarMapSemanticEvent | None:
        """Return the latest transition across the integration."""
        return self.coordinator.last_event
