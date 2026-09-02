"""Binary sensor platform for RadarMap."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RadarMapConfigEntry
from .const import ALERT_FIELDS
from .entity import RadarMapEntity
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
        RadarMapBinarySensor(coordinator, selected, description)
        for selected in coordinator.selected_objects
        for description in (*SENSOR_DESCRIPTIONS, ALERT_DESCRIPTION)
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
