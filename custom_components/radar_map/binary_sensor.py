"""Binary sensor platform for RadarMap."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RadarMapConfigEntry
from .const import (
    AGGREGATE_ALERT_FIELDS,
    ALERT_FIELDS,
    MAX_SUMMARY_OBJECTS_ATTRIBUTE,
    SUMMARY_OBJECT_ID,
)
from .entity import RadarMapEntity, RadarMapSummaryEntity
from .models import FlagValue, RadarMapObject


@dataclass(frozen=True, kw_only=True)
class RadarMapBinarySensorDescription(BinarySensorEntityDescription):
    """Describe one RadarMap semantic flag."""

    flag: str


SENSOR_DESCRIPTIONS = tuple(
    RadarMapBinarySensorDescription(
        key=flag,
        flag=flag,
        translation_key=flag,
        icon={
            "bpla": "mdi:quadcopter",
            "attention": "mdi:alert-outline",
            "danger": "mdi:alert",
            "uab": "mdi:bomb",
            "fpv": "mdi:quadcopter",
            "rocket": "mdi:rocket-launch",
            "rocket_level": "mdi:rocket-launch-outline",
            "aviation": "mdi:airplane-alert",
            "pvo": "mdi:shield-check",
        }[flag],
    )
    for flag in ALERT_FIELDS
)

ALERT_DESCRIPTION = RadarMapBinarySensorDescription(
    key="alert",
    flag="alert",
    translation_key="alert",
    icon="mdi:alert-decagram",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarMapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RadarMap binary sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            *(
                RadarMapBinarySensor(coordinator, selected, description)
                for selected in coordinator.selected_objects
                for description in (*SENSOR_DESCRIPTIONS, ALERT_DESCRIPTION)
            ),
            RadarMapOverallAlertBinarySensor(coordinator),
            RadarMapConnectionBinarySensor(coordinator),
        ]
    )


class RadarMapBinarySensor(RadarMapEntity, BinarySensorEntity):
    """One semantic RadarMap alert flag."""

    entity_description: RadarMapBinarySensorDescription

    def __init__(
        self,
        coordinator,
        selected: RadarMapObject,
        description: RadarMapBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, selected)
        self.entity_description = description
        self._attr_unique_id = f"{selected.object_id}:{description.key}"

    @property
    def is_on(self) -> FlagValue:
        """Return current flag, preserving unknown schema values."""
        if self.entity_description.flag == "alert":
            return self.current.alert
        return self.current.flags.get(self.entity_description.flag)


class RadarMapOverallAlertBinarySensor(RadarMapSummaryEntity, BinarySensorEntity):
    """Aggregate alert state across every object selected in the config entry."""

    _attr_translation_key = "overall_alert"
    _attr_icon = "mdi:alert-decagram"
    _attr_unique_id = f"{SUMMARY_OBJECT_ID}:alert"

    @property
    def is_on(self) -> FlagValue:
        """Return true if any selected object has an actual active threat."""
        values = [
            self.coordinator.get_object(selected.object_id).alert
            for selected in self.coordinator.selected_objects
        ]
        if any(value is True for value in values):
            return True
        if any(value is None for value in values):
            return None
        return False

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose a bounded summary suitable for automations and dashboards."""
        objects = [
            self.coordinator.get_object(selected.object_id)
            for selected in self.coordinator.selected_objects
        ]
        active = [item for item in objects if item.alert is True]
        displayed = active[:MAX_SUMMARY_OBJECTS_ATTRIBUTE]
        active_types = [
            alert_type
            for alert_type in AGGREGATE_ALERT_FIELDS
            if any(item.flags.get(alert_type) is True for item in active)
        ]
        return {
            "selected_object_count": len(self.coordinator.selected_objects),
            "active_object_count": len(active),
            "active_objects": [item.name for item in displayed],
            "active_object_ids": [item.object_id for item in displayed],
            "active_alert_types": active_types,
            "active_objects_truncated": len(active) > len(displayed),
        }


class RadarMapConnectionBinarySensor(RadarMapSummaryEntity, BinarySensorEntity):
    """Report whether the latest RadarMap API update succeeded."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "connection"
    _attr_unique_id = f"{SUMMARY_OBJECT_ID}:connection"

    @property
    def available(self) -> bool:
        """Remain available so a connection failure is visible as off."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the latest coordinator refresh succeeded."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose compact connection diagnostics."""
        last_success = self.coordinator.last_successful_update
        interval = self.coordinator.update_interval
        return {
            "last_successful_update": last_success.isoformat() if last_success else None,
            "last_error": self.coordinator.last_error,
            "poll_interval_sec": interval.total_seconds() if interval else None,
            "last_update_duration_sec": self.coordinator.last_update_duration,
        }
