"""Shared RadarMap entity implementation."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import API_BASE_URL, DOMAIN, SUMMARY_OBJECT_ID
from .coordinator import RadarMapCoordinator
from .models import RadarMapObject


class RadarMapEntity(CoordinatorEntity[RadarMapCoordinator]):
    """Base class for an entity attached to a selected RadarMap object."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by RadarMap (radar-map.ru)"

    def __init__(self, coordinator: RadarMapCoordinator, selected: RadarMapObject) -> None:
        super().__init__(coordinator)
        self.selected = selected
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, selected.object_id)},
            name=f"RadarMap — {selected.name}",
            manufacturer="RadarMap",
            model=f"RadarMap {selected.object_type}",
            configuration_url=API_BASE_URL,
        )

    @property
    def current(self) -> RadarMapObject:
        """Return state from the coordinator's latest successful snapshot."""
        return self.coordinator.get_object(self.selected.object_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose compact source metadata, never a raw API tree."""
        sources = list(self.current.sources)
        return {
            "source": sources[0] if len(sources) == 1 else None,
            "sources": sources,
        }


class RadarMapSummaryEntity(CoordinatorEntity[RadarMapCoordinator]):
    """Base class for entities aggregating every selected RadarMap object."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by RadarMap (radar-map.ru)"

    def __init__(self, coordinator: RadarMapCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, SUMMARY_OBJECT_ID)},
            name="RadarMap — Summary",
            manufacturer="RadarMap",
            model="RadarMap summary",
            configuration_url=API_BASE_URL,
        )
