"""Semantic last-event sensor tests."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, patch

from homeassistant.core import State
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.radar_map.coordinator import RadarMapCoordinator
from custom_components.radar_map.models import RadarMapSnapshot
from custom_components.radar_map.sensor import (
    RadarMapLastSemanticEventSensor,
    RadarMapSummaryLastSemanticEventSensor,
)


class SequenceClient:
    """Return snapshots in order."""

    def __init__(self, values):
        self.values = iter(values)

    async def async_get_state(self):
        return next(self.values)


def _snapshot_with_bpla(state_payload: dict, value: bool) -> RadarMapSnapshot:
    payload = deepcopy(state_payload)
    payload["regions"]["Московская область"]["bpla"] = value
    payload["regions"]["Московская область"]["source_text"] = (
        "Начало угрозы БПЛА" if value else "Отбой угрозы БПЛА"
    )
    return RadarMapSnapshot.from_api(payload)


async def test_semantic_event_sensors_report_actual_transition(
    hass,
    state_payload,
    selected_region,
) -> None:
    """Object and summary sensors expose a stable code and structured context."""
    off = _snapshot_with_bpla(state_payload, False)
    on = _snapshot_with_bpla(state_payload, True)
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([off, on]),
        (selected_region,),
    )
    object_sensor = RadarMapLastSemanticEventSensor(coordinator, selected_region)
    summary_sensor = RadarMapSummaryLastSemanticEventSensor(coordinator)

    await coordinator.async_refresh()
    assert object_sensor.native_value is None
    assert summary_sensor.native_value is None

    await coordinator.async_refresh()

    assert object_sensor.native_value == "bpla_started"
    assert summary_sensor.native_value == "bpla_started"
    assert object_sensor.extra_state_attributes["alert_type"] == "bpla"
    assert object_sensor.extra_state_attributes["state"] == "on"
    assert object_sensor.extra_state_attributes["object_id"] == selected_region.object_id
    assert object_sensor.extra_state_attributes["source_text"] == "Начало угрозы БПЛА"
    assert object_sensor.extra_state_attributes["event_timestamp"]


async def test_semantic_event_sensor_restores_previous_event(
    hass,
    snapshot,
    selected_region,
) -> None:
    """The last structured event survives a Home Assistant restart."""
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([snapshot]),
        (selected_region,),
    )
    await coordinator.async_refresh()
    entity = RadarMapLastSemanticEventSensor(coordinator, selected_region)
    assert isinstance(entity, RestoreEntity)
    entity.hass = hass
    entity.entity_id = "sensor.radar_map_restore_test"
    restored = State(
        entity.entity_id,
        "rocket_ended",
        {
            "event_code": "rocket_ended",
            "alert_type": "rocket",
            "state": "off",
            "transition": "off",
            "event_timestamp": "2026-09-02T12:00:00+00:00",
            "object_id": selected_region.object_id,
            "source_text": "Отбой ракетной угрозы",
        },
    )

    with patch.object(entity, "async_get_last_state", AsyncMock(return_value=restored)):
        await entity.async_added_to_hass()

    assert entity.native_value == "rocket_ended"
    assert entity.extra_state_attributes["alert_type"] == "rocket"
    assert entity.extra_state_attributes["source_text"] == "Отбой ракетной угрозы"
    await entity.async_will_remove_from_hass()
