"""Shared fixtures for RadarMap tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.radar_map.const import ALERT_FIELDS
from custom_components.radar_map.models import (
    RadarMapCatalog,
    RadarMapObject,
    RadarMapSnapshot,
    city_key,
    normalize_region_id,
    object_id,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def state_payload() -> dict:
    """Return a fresh shortened payload derived from real RadarMap structures."""
    path = Path(__file__).parent / "fixtures" / "state.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def snapshot(state_payload: dict) -> RadarMapSnapshot:
    """Return a normalized snapshot."""
    return RadarMapSnapshot.from_api(state_payload)


@pytest.fixture
def selected_region() -> RadarMapObject:
    """Return selected metadata for Moscow Oblast."""
    name = "Московская область"
    key = normalize_region_id(name)
    return RadarMapObject(
        object_id=object_id("region", key),
        object_type="region",
        key=key,
        name=name,
        region=name,
        flags={field: False for field in ALERT_FIELDS},
    )


@pytest.fixture
def catalog(selected_region: RadarMapObject) -> RadarMapCatalog:
    """Return small base catalogs for config-flow tests."""
    city_key_value = city_key("Москва", "Москва")
    city = RadarMapObject(
        object_id=object_id("city", city_key_value),
        object_type="city",
        key=city_key_value,
        name="Москва",
        region="Москва",
        latitude=55.75204,
        longitude=37.61781,
    ).safe_copy()
    return RadarMapCatalog(
        regions={selected_region.object_id: selected_region},
        cities={city.object_id: city},
        district_manifest={"Московская область": "r_687a3cb54481.geojson"},
        district_base="/static/data/districts_by_region/",
    )


@pytest.fixture
def selected_district() -> RadarMapObject:
    """Return metadata using the real current Ruzsky district gid_2."""
    return RadarMapObject(
        object_id="district:RUS.44.57_1",
        object_type="district",
        key="RUS.44.57_1",
        name="Рузский район",
        region="Московская область",
    ).safe_copy()
