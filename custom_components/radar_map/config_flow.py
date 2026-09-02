"""UI config and options flows for RadarMap."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    RadarMapClient,
    RadarMapConnectionError,
    RadarMapError,
    RadarMapInvalidResponseError,
)
from .const import (
    CONF_CITIES,
    CONF_DISTRICT_REGIONS,
    CONF_DISTRICTS,
    CONF_OBJECTS,
    CONF_REGIONS,
    DOMAIN,
    NAME,
)
from .models import RadarMapCatalog, RadarMapObject


def _selector(options: Sequence[SelectOptionDict]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=list(options),
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _base_schema(
    catalog: RadarMapCatalog,
    defaults: Mapping[str, Sequence[str]],
) -> vol.Schema:
    region_options = [
        SelectOptionDict(value=item.object_id, label=item.name)
        for item in sorted(catalog.regions.values(), key=lambda item: item.name.casefold())
    ]
    city_options = [
        SelectOptionDict(
            value=item.object_id,
            label=f"{item.name} — {item.region}",
        )
        for item in sorted(
            catalog.cities.values(),
            key=lambda item: ((item.region or "").casefold(), item.name.casefold()),
        )
    ]
    district_region_options = [
        SelectOptionDict(value=name, label=name)
        for name in sorted(catalog.district_manifest, key=str.casefold)
    ]
    return vol.Schema(
        {
            vol.Required(CONF_REGIONS, default=list(defaults.get(CONF_REGIONS, []))): _selector(
                region_options
            ),
            vol.Required(CONF_CITIES, default=list(defaults.get(CONF_CITIES, []))): _selector(
                city_options
            ),
            vol.Required(
                CONF_DISTRICT_REGIONS,
                default=list(defaults.get(CONF_DISTRICT_REGIONS, [])),
            ): _selector(district_region_options),
        }
    )


def _district_schema(
    districts: Mapping[str, RadarMapObject],
    defaults: Sequence[str],
) -> vol.Schema:
    options = [
        SelectOptionDict(
            value=item.object_id,
            label=f"{item.name} — {item.region}",
        )
        for item in sorted(
            districts.values(),
            key=lambda item: ((item.region or "").casefold(), item.name.casefold()),
        )
    ]
    return vol.Schema({vol.Required(CONF_DISTRICTS, default=list(defaults)): _selector(options)})


class _RadarMapFlowMixin:
    """Shared implementation for config and options flows."""

    hass: Any
    _catalog: RadarMapCatalog | None = None
    _districts: dict[str, RadarMapObject]
    _pending: dict[str, list[str]]

    def _init_flow_state(self) -> None:
        self._catalog = None
        self._districts = {}
        self._pending = {}

    @property
    def _client(self) -> RadarMapClient:
        return RadarMapClient(async_get_clientsession(self.hass))

    async def _load_catalog(self) -> RadarMapCatalog:
        if self._catalog is None:
            self._catalog = await self._client.async_get_catalog()
        return self._catalog

    async def _load_districts(self) -> None:
        catalog = await self._load_catalog()
        regions = self._pending.get(CONF_DISTRICT_REGIONS, [])
        self._districts = await self._client.async_get_districts(catalog, regions)

    def _settings(self, district_ids: Sequence[str]) -> dict[str, Any]:
        assert self._catalog is not None
        region_ids = self._pending.get(CONF_REGIONS, [])
        city_ids = self._pending.get(CONF_CITIES, [])
        selected: list[RadarMapObject] = []
        selected.extend(
            self._catalog.regions[oid] for oid in region_ids if oid in self._catalog.regions
        )
        selected.extend(
            self._catalog.cities[oid] for oid in city_ids if oid in self._catalog.cities
        )
        selected.extend(self._districts[oid] for oid in district_ids if oid in self._districts)
        return {
            CONF_REGIONS: region_ids,
            CONF_CITIES: city_ids,
            CONF_DISTRICT_REGIONS: self._pending.get(CONF_DISTRICT_REGIONS, []),
            CONF_DISTRICTS: list(district_ids),
            CONF_OBJECTS: [item.as_selection_dict() for item in selected],
        }

    @staticmethod
    def _error_key(err: RadarMapError) -> str:
        if isinstance(err, RadarMapConnectionError):
            return "cannot_connect"
        if isinstance(err, RadarMapInvalidResponseError):
            return "invalid_response"
        return "api_error"


class RadarMapConfigFlow(_RadarMapFlowMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a RadarMap config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._init_flow_state()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Validate RadarMap and select regions/cities/district scopes."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        try:
            catalog = await self._load_catalog()
        except RadarMapError as err:
            errors["base"] = self._error_key(err)
            # Empty selectors keep the flow usable for a retry.
            catalog = RadarMapCatalog({}, {}, {}, "/")

        if user_input is not None and not errors:
            self._pending = {
                CONF_REGIONS: list(user_input.get(CONF_REGIONS, [])),
                CONF_CITIES: list(user_input.get(CONF_CITIES, [])),
                CONF_DISTRICT_REGIONS: list(user_input.get(CONF_DISTRICT_REGIONS, [])),
            }
            if self._pending[CONF_DISTRICT_REGIONS]:
                return await self.async_step_districts()
            settings = self._settings([])
            if not settings[CONF_OBJECTS]:
                errors["base"] = "no_selection"
            else:
                return self.async_create_entry(
                    title=NAME,
                    data={},
                    options=settings,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_base_schema(catalog, {}),
            errors=errors,
        )

    async def async_step_districts(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select districts only from explicitly requested region catalogs."""
        errors: dict[str, str] = {}
        if not self._districts:
            try:
                await self._load_districts()
            except RadarMapError as err:
                errors["base"] = self._error_key(err)
        if user_input is not None and not errors:
            district_ids = list(user_input.get(CONF_DISTRICTS, []))
            settings = self._settings(district_ids)
            if not settings[CONF_OBJECTS]:
                errors["base"] = "no_selection"
            else:
                return self.async_create_entry(
                    title=NAME,
                    data={},
                    options=settings,
                )
        return self.async_show_form(
            step_id="districts",
            data_schema=_district_schema(self._districts, []),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RadarMapOptionsFlow:
        """Return an options flow that reloads the entry once."""
        return RadarMapOptionsFlow()


class RadarMapOptionsFlow(_RadarMapFlowMixin, OptionsFlowWithReload):
    """Change selected RadarMap objects."""

    def __init__(self) -> None:
        self._init_flow_state()

    def _stored(self) -> Mapping[str, Any]:
        return self.config_entry.options or self.config_entry.data

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select regions/cities and district catalog regions."""
        errors: dict[str, str] = {}
        stored = self._stored()
        try:
            catalog = await self._load_catalog()
        except RadarMapError as err:
            errors["base"] = self._error_key(err)
            catalog = RadarMapCatalog({}, {}, {}, "/")

        if user_input is not None and not errors:
            self._pending = {
                CONF_REGIONS: list(user_input.get(CONF_REGIONS, [])),
                CONF_CITIES: list(user_input.get(CONF_CITIES, [])),
                CONF_DISTRICT_REGIONS: list(user_input.get(CONF_DISTRICT_REGIONS, [])),
            }
            if self._pending[CONF_DISTRICT_REGIONS]:
                return await self.async_step_districts()
            settings = self._settings([])
            if not settings[CONF_OBJECTS]:
                errors["base"] = "no_selection"
            else:
                return self.async_create_entry(title="", data=settings)

        defaults = {
            CONF_REGIONS: list(stored.get(CONF_REGIONS, [])),
            CONF_CITIES: list(stored.get(CONF_CITIES, [])),
            CONF_DISTRICT_REGIONS: list(stored.get(CONF_DISTRICT_REGIONS, [])),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=_base_schema(catalog, defaults),
            errors=errors,
        )

    async def async_step_districts(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select districts and persist all options."""
        errors: dict[str, str] = {}
        if not self._districts:
            try:
                await self._load_districts()
            except RadarMapError as err:
                errors["base"] = self._error_key(err)
        defaults = list(self._stored().get(CONF_DISTRICTS, []))
        if user_input is not None and not errors:
            district_ids = list(user_input.get(CONF_DISTRICTS, []))
            settings = self._settings(district_ids)
            if not settings[CONF_OBJECTS]:
                errors["base"] = "no_selection"
            else:
                return self.async_create_entry(title="", data=settings)
        return self.async_show_form(
            step_id="districts",
            data_schema=_district_schema(self._districts, defaults),
            errors=errors,
        )
