"""RadarMap custom integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RadarMapClient
from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, PLATFORMS
from .coordinator import RadarMapCoordinator
from .models import selected_objects_from_mapping


@dataclass(slots=True)
class RadarMapRuntimeData:
    """Non-persisted runtime data for one config entry."""

    client: RadarMapClient
    coordinator: RadarMapCoordinator


type RadarMapConfigEntry = ConfigEntry[RadarMapRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarMapConfigEntry,
) -> bool:
    """Set up RadarMap from a config entry."""
    settings = entry.options or entry.data
    selected = selected_objects_from_mapping(settings)
    client = RadarMapClient(async_get_clientsession(hass))
    coordinator = RadarMapCoordinator(
        hass,
        client,
        selected,
        configured_poll_interval=float(settings.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)),
        config_entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RadarMapRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: RadarMapConfigEntry,
) -> bool:
    """Unload a RadarMap config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
