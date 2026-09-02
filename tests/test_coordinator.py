"""Coordinator event and availability tests."""

from __future__ import annotations

from copy import deepcopy

from custom_components.radar_map.api import RadarMapConnectionError
from custom_components.radar_map.binary_sensor import (
    SENSOR_DESCRIPTIONS,
    RadarMapBinarySensor,
    RadarMapConnectionBinarySensor,
    RadarMapOverallAlertBinarySensor,
    RadarMapSummaryAlertBinarySensor,
)
from custom_components.radar_map.const import EVENT_ALERT
from custom_components.radar_map.coordinator import RadarMapCoordinator
from custom_components.radar_map.models import RadarMapSnapshot


class SequenceClient:
    """Return snapshots/errors in order."""

    def __init__(self, values):
        self.values = iter(values)

    async def async_get_state(self):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


def _with_bpla(state_payload: dict, value: bool) -> RadarMapSnapshot:
    payload = deepcopy(state_payload)
    payload["regions"]["Московская область"]["bpla"] = value
    payload["regions"]["Московская область"]["source_text"] = (
        "Начало опасности" if value else "Отбой опасности"
    )
    payload["regions"]["Московская область"]["last_event_ts"] += int(value)
    return RadarMapSnapshot.from_api(payload)


async def test_false_true_false_and_no_duplicate_events(
    hass,
    state_payload,
    selected_region,
) -> None:
    """Only real transitions emit bus events, including an end transition."""
    off = _with_bpla(state_payload, False)
    on = _with_bpla(state_payload, True)
    events = []
    hass.bus.async_listen(EVENT_ALERT, events.append)
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([off, on, on, off]),
        (selected_region,),
    )

    await coordinator.async_refresh()  # Initial state: no event.
    await coordinator.async_refresh()  # false -> true.
    await hass.async_block_till_done()
    await coordinator.async_refresh()  # unchanged: no duplicate.
    await coordinator.async_refresh()  # true -> false.
    await hass.async_block_till_done()

    bpla_events = [event for event in events if event.data["alert_type"] == "bpla"]
    assert [event.data["state"] for event in bpla_events] == ["on", "off"]
    assert bpla_events[0].data["name"] == "Московская область"


async def test_outage_keeps_data_unavailable_then_recovers(
    hass,
    state_payload,
    selected_region,
) -> None:
    """Network UNKNOWN is not safe/off and the coordinator recovers automatically."""
    on = _with_bpla(state_payload, True)
    off = _with_bpla(state_payload, False)
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([on, RadarMapConnectionError("offline"), off]),
        (selected_region,),
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.get_object(selected_region.object_id).flags["bpla"] is True
    description = next(item for item in SENSOR_DESCRIPTIONS if item.flag == "bpla")
    entity = RadarMapBinarySensor(coordinator, selected_region, description)
    connection = RadarMapConnectionBinarySensor(coordinator)
    assert entity.is_on is True
    assert entity.available is True
    assert connection.is_on is True
    assert connection.available is True

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert coordinator.get_object(selected_region.object_id).flags["bpla"] is True
    assert entity.is_on is True
    assert entity.available is False
    assert connection.is_on is False
    assert connection.available is True
    assert connection.extra_state_attributes["last_error"] == "offline"
    assert coordinator.last_error == "offline"

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.get_object(selected_region.object_id).flags["bpla"] is False
    assert entity.is_on is False
    assert entity.available is True
    assert connection.is_on is True
    assert connection.available is True
    assert connection.extra_state_attributes["last_error"] is None
    assert coordinator.last_error is None


async def test_object_removed_from_valid_snapshot_turns_off_and_keeps_last_event(
    hass,
    state_payload,
    selected_region,
) -> None:
    """Removal from a full valid snapshot is safe, unlike a failed request."""
    on = _with_bpla(state_payload, True)
    without_region_payload = deepcopy(state_payload)
    without_region_payload["regions"] = {}
    without_region = RadarMapSnapshot.from_api(without_region_payload)
    events = []
    hass.bus.async_listen(EVENT_ALERT, events.append)
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([on, without_region]),
        (selected_region,),
    )

    await coordinator.async_refresh()
    previous_timestamp = coordinator.get_object(selected_region.object_id).last_event_ts
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    current = coordinator.get_object(selected_region.object_id)
    assert current.flags["bpla"] is False
    assert current.last_event_ts == previous_timestamp
    assert [event.data["state"] for event in events if event.data["alert_type"] == "bpla"] == [
        "off"
    ]


async def test_unknown_schema_value_does_not_emit_false_event(
    hass,
    state_payload,
    selected_region,
) -> None:
    """A changed/missing flag becomes unknown without a false-clear event."""
    on = _with_bpla(state_payload, True)
    changed_payload = deepcopy(state_payload)
    del changed_payload["regions"]["Московская область"]["bpla"]
    changed = RadarMapSnapshot.from_api(changed_payload)
    events = []
    hass.bus.async_listen(EVENT_ALERT, events.append)
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([on, changed]),
        (selected_region,),
    )

    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.get_object(selected_region.object_id).flags["bpla"] is None
    assert not [event for event in events if event.data["alert_type"] == "bpla"]


async def test_overall_alert_aggregates_every_selected_object(
    hass,
    state_payload,
    selected_region,
    selected_district,
) -> None:
    """The summary reports on/off/unknown across regions, districts and cities."""
    on = RadarMapSnapshot.from_api(state_payload)
    selected_city = on.objects["city:москва|москва"].safe_copy()

    off_payload = deepcopy(state_payload)
    off_payload["cities"][0]["bpla"] = False
    off_payload["cities"][0]["fpv"] = False
    off = RadarMapSnapshot.from_api(off_payload)

    unknown_payload = deepcopy(off_payload)
    del unknown_payload["regions"]["Московская область"]["bpla"]
    unknown = RadarMapSnapshot.from_api(unknown_payload)

    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([on, off, unknown]),
        (selected_region, selected_district, selected_city),
    )
    entity = RadarMapOverallAlertBinarySensor(coordinator)

    await coordinator.async_refresh()
    assert entity.is_on is True
    assert entity.extra_state_attributes == {
        "selected_object_count": 3,
        "active_object_count": 1,
        "active_objects": ["Москва"],
        "active_object_ids": ["city:москва|москва"],
        "active_alert_types": ["bpla", "fpv"],
        "active_objects_truncated": False,
    }

    await coordinator.async_refresh()
    assert entity.is_on is False
    assert entity.extra_state_attributes["active_object_count"] == 0

    await coordinator.async_refresh()
    assert entity.is_on is None


async def test_per_type_summary_alerts_aggregate_every_selected_object(
    hass,
    state_payload,
    selected_region,
    selected_district,
) -> None:
    """Each summary flag reports matching objects across all object types."""
    snapshot = RadarMapSnapshot.from_api(state_payload)
    selected_city = snapshot.objects["city:москва|москва"].safe_copy()
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([snapshot]),
        (selected_region, selected_district, selected_city),
    )
    await coordinator.async_refresh()

    descriptions = {item.flag: item for item in SENSOR_DESCRIPTIONS}
    bpla = RadarMapSummaryAlertBinarySensor(coordinator, descriptions["bpla"])
    attention = RadarMapSummaryAlertBinarySensor(coordinator, descriptions["attention"])
    danger = RadarMapSummaryAlertBinarySensor(coordinator, descriptions["danger"])

    assert bpla.is_on is True
    assert bpla.extra_state_attributes == {
        "alert_type": "bpla",
        "selected_object_count": 3,
        "active_object_count": 1,
        "active_objects": ["Москва"],
        "active_object_ids": ["city:москва|москва"],
        "active_objects_truncated": False,
    }
    assert attention.is_on is True
    assert attention.extra_state_attributes["active_objects"] == ["Рузский район"]
    assert danger.is_on is False


async def test_per_type_summary_preserves_unknown(
    hass,
    state_payload,
    selected_region,
) -> None:
    """A missing source flag makes its summary unknown instead of falsely safe."""
    del state_payload["regions"]["Московская область"]["rocket"]
    snapshot = RadarMapSnapshot.from_api(state_payload)
    coordinator = RadarMapCoordinator(
        hass,
        SequenceClient([snapshot]),
        (selected_region,),
    )
    await coordinator.async_refresh()
    description = next(item for item in SENSOR_DESCRIPTIONS if item.flag == "rocket")

    entity = RadarMapSummaryAlertBinarySensor(coordinator, description)

    assert entity.is_on is None
    assert entity.extra_state_attributes["active_object_count"] == 0


async def test_configured_poll_interval_never_exceeds_server_rate(
    hass,
    snapshot,
    selected_region,
) -> None:
    """User preference can slow polling but cannot violate the server interval."""
    slower = RadarMapCoordinator(
        hass,
        SequenceClient([snapshot]),
        (selected_region,),
        configured_poll_interval=60,
    )
    await slower.async_refresh()
    assert slower.configured_poll_interval == 60
    assert slower.server_poll_interval == 25
    assert slower.update_interval.total_seconds() == 60

    faster = RadarMapCoordinator(
        hass,
        SequenceClient([snapshot]),
        (selected_region,),
        configured_poll_interval=15,
    )
    await faster.async_refresh()
    assert faster.configured_poll_interval == 15
    assert faster.server_poll_interval == 25
    assert faster.update_interval.total_seconds() == 25
