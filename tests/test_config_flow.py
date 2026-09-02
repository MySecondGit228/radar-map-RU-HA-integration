"""Config flow and selection tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.radar_map.api import RadarMapConnectionError
from custom_components.radar_map.const import (
    CONF_CITIES,
    CONF_DISTRICT_REGIONS,
    CONF_DISTRICTS,
    CONF_OBJECTS,
    CONF_POLL_INTERVAL,
    CONF_REGIONS,
    DOMAIN,
)


async def test_config_flow_region_city_district_selection(
    hass,
    enable_custom_integrations,
    catalog,
    selected_region,
    selected_district,
) -> None:
    """Config flow persists independent region/city/district selections."""
    city_id = "city:москва|москва"
    with (
        patch(
            "custom_components.radar_map.config_flow.RadarMapClient.async_get_catalog",
            AsyncMock(return_value=catalog),
        ),
        patch(
            "custom_components.radar_map.config_flow.RadarMapClient.async_get_districts",
            AsyncMock(return_value={selected_district.object_id: selected_district}),
        ),
        patch("custom_components.radar_map.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REGIONS: [selected_region.object_id],
                CONF_CITIES: [city_id],
                CONF_DISTRICT_REGIONS: ["Московская область"],
                CONF_POLL_INTERVAL: 60,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "districts"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_DISTRICTS: [selected_district.object_id]},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        options = result["result"].options
        assert options[CONF_REGIONS] == [selected_region.object_id]
        assert options[CONF_CITIES] == [city_id]
        assert options[CONF_DISTRICTS] == [selected_district.object_id]
        assert options[CONF_POLL_INTERVAL] == 60
        assert {item["object_type"] for item in options[CONF_OBJECTS]} == {
            "region",
            "city",
            "district",
        }


async def test_config_flow_unavailable_api(hass, enable_custom_integrations) -> None:
    """An unavailable endpoint keeps the form open with an actionable error."""
    with patch(
        "custom_components.radar_map.config_flow.RadarMapClient.async_get_catalog",
        AsyncMock(side_effect=RadarMapConnectionError("offline")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_changes_selection(
    hass,
    enable_custom_integrations,
    catalog,
    selected_region,
) -> None:
    """Options Flow replaces the stored selection and reloads the entry."""
    city_id = "city:москва|москва"
    with (
        patch(
            "custom_components.radar_map.config_flow.RadarMapClient.async_get_catalog",
            AsyncMock(return_value=catalog),
        ),
        patch("custom_components.radar_map.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REGIONS: [selected_region.object_id],
                CONF_CITIES: [],
                CONF_DISTRICT_REGIONS: [],
                CONF_POLL_INTERVAL: 45,
            },
        )
        entry = result["result"]

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_REGIONS: [],
                CONF_CITIES: [city_id],
                CONF_DISTRICT_REGIONS: [],
                CONF_POLL_INTERVAL: 120,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REGIONS] == []
    assert result["data"][CONF_CITIES] == [city_id]
    assert result["data"][CONF_POLL_INTERVAL] == 120
    assert [item["object_type"] for item in result["data"][CONF_OBJECTS]] == ["city"]
