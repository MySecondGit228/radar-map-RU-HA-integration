"""Tests for RadarMap normalization and mappings."""

from __future__ import annotations

from custom_components.radar_map.const import ALERT_FIELDS
from custom_components.radar_map.models import RadarMapSnapshot, aggregate_alert


def test_successful_api_response(snapshot: RadarMapSnapshot) -> None:
    """A shortened real response maps all three object types."""
    assert snapshot.version == 23
    assert snapshot.poll_interval == 25.0
    assert "region:московская_область" in snapshot.objects
    assert "district:RUS.44.57_1" in snapshot.objects
    assert "city:москва|москва" in snapshot.objects
    assert snapshot.objects["city:москва|москва"].sources == ("vrv_radar",)


def test_binary_sensor_mapping(snapshot: RadarMapSnapshot) -> None:
    """Semantic booleans are mapped independently of fill/UI state."""
    city = snapshot.objects["city:москва|москва"]
    assert city.flags["bpla"] is True
    assert city.flags["fpv"] is True
    assert city.flags["danger"] is False
    assert city.active_alert_types == ("bpla", "fpv")


def test_alert_aggregation() -> None:
    """Attention and PVO are not actual-danger aggregate inputs."""
    flags = {field: False for field in ALERT_FIELDS}
    flags["attention"] = True
    flags["pvo"] = True
    assert aggregate_alert(flags) is False
    flags["rocket_level"] = True
    assert aggregate_alert(flags) is True


def test_schema_change_missing_field_is_unknown(state_payload: dict) -> None:
    """A missing field on a present row cannot silently become safe."""
    del state_payload["regions"]["Московская область"]["bpla"]
    snapshot = RadarMapSnapshot.from_api(state_payload)
    region = snapshot.objects["region:московская_область"]
    assert region.flags["bpla"] is None
    assert region.alert is None


def test_missing_collection_is_tolerated(state_payload: dict) -> None:
    """A partial compatible schema remains usable when one collection is absent."""
    del state_payload["districts"]
    snapshot = RadarMapSnapshot.from_api(state_payload)
    assert "region:московская_область" in snapshot.objects
    assert not any(key.startswith("district:") for key in snapshot.objects)
