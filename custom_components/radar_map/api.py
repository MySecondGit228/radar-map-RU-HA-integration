"""Asynchronous HTTP client for the public RadarMap endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping, Sequence
from urllib.parse import urljoin

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    API_BASE_URL,
    API_STATE_PATH,
    CITIES_CATALOG_PATHS,
    DISTRICTS_MANIFEST_PATH,
    OBJECT_CITY,
    OBJECT_DISTRICT,
    OBJECT_REGION,
    REGIONS_CATALOG_PATH,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from .models import (
    RadarMapCatalog,
    RadarMapObject,
    RadarMapSchemaError,
    RadarMapSnapshot,
    city_key,
    normalize_region_id,
    object_id,
)

_LOGGER = logging.getLogger(__name__)


class RadarMapError(Exception):
    """Base RadarMap client error."""


class RadarMapConnectionError(RadarMapError):
    """Network or timeout error."""


class RadarMapHttpError(RadarMapError):
    """Unexpected HTTP response."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        super().__init__(f"RadarMap returned HTTP {status}")
        self.status = status
        self.retry_after = retry_after


class RadarMapInvalidResponseError(RadarMapError):
    """Malformed JSON or incompatible response schema."""


class RadarMapNotReadyError(RadarMapError):
    """Server returned a transient wait/not-ready state."""


class RadarMapClient:
    """Client that uses Home Assistant's shared aiohttp session."""

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str = API_BASE_URL,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/") + "/"

    async def async_get_state(self) -> RadarMapSnapshot:
        """Fetch a full state snapshot without the large message feed."""
        payload = await self._async_get_json(API_STATE_PATH, params={"nofeed": "1"})
        if isinstance(payload, Mapping) and payload.get("type") == "wait":
            raise RadarMapNotReadyError("RadarMap state is not ready")
        try:
            snapshot = RadarMapSnapshot.from_api(payload)
        except RadarMapSchemaError as err:
            raise RadarMapInvalidResponseError(str(err)) from err
        if not snapshot.startup_ready or not snapshot.state_ready:
            raise RadarMapNotReadyError("RadarMap state is not ready")
        return snapshot

    async def async_get_catalog(self) -> RadarMapCatalog:
        """Fetch base location catalogs used by the config flow."""
        state_task = self.async_get_state()
        regions_task = self._async_get_json(REGIONS_CATALOG_PATH)
        cities_tasks = [self._async_get_json(path) for path in CITIES_CATALOG_PATHS]
        manifest_task = self._async_get_json(DISTRICTS_MANIFEST_PATH)
        snapshot, regions_raw, *rest = await asyncio.gather(
            state_task,
            regions_task,
            *cities_tasks,
            manifest_task,
        )
        city_parts = rest[:-1]
        manifest_raw = rest[-1]

        regions = _parse_region_catalog(regions_raw)
        cities = _parse_city_catalog(city_parts)
        # Include any currently observed object if a static catalog lags behind.
        for item in snapshot.objects.values():
            if item.object_type == OBJECT_REGION:
                regions.setdefault(item.object_id, item.safe_copy())
            elif item.object_type == OBJECT_CITY:
                cities.setdefault(item.object_id, item.safe_copy())

        if not isinstance(manifest_raw, Mapping):
            raise RadarMapInvalidResponseError("District manifest is not an object")
        manifest_regions = manifest_raw.get("regions", {})
        if not isinstance(manifest_regions, Mapping):
            raise RadarMapInvalidResponseError("District manifest regions is not an object")
        district_manifest = {
            str(region): str(filename)
            for region, filename in manifest_regions.items()
            if region and filename
        }
        district_base = str(manifest_raw.get("base") or "/static/data/districts_by_region/")
        return RadarMapCatalog(
            regions=regions,
            cities=cities,
            district_manifest=district_manifest,
            district_base=district_base,
        )

    async def async_get_districts(
        self,
        catalog: RadarMapCatalog,
        region_names: Sequence[str],
    ) -> dict[str, RadarMapObject]:
        """Load only the district catalogs explicitly requested by the user."""
        semaphore = asyncio.Semaphore(4)

        async def load(region_name: str) -> object:
            filename = catalog.district_manifest.get(region_name)
            if not filename:
                return None
            path = urljoin(catalog.district_base.rstrip("/") + "/", filename)
            async with semaphore:
                return await self._async_get_json(path)

        payloads = await asyncio.gather(*(load(name) for name in region_names))
        result: dict[str, RadarMapObject] = {}
        city_names = {(item.name, item.region) for item in catalog.cities.values()}
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            features = payload.get("features", [])
            if not isinstance(features, Sequence) or isinstance(features, (str, bytes)):
                continue
            for feature in features:
                if not isinstance(feature, Mapping):
                    continue
                props = feature.get("properties")
                if not isinstance(props, Mapping):
                    continue
                gid = props.get("gid_2")
                name = props.get("name_ru")
                region = props.get("region_ru")
                if not gid or not name or not region:
                    continue
                # RadarMap district GeoJSON also contains city polygons. Those
                # places are already selectable from the richer city catalog.
                if (str(name), str(region)) in city_names:
                    continue
                oid = object_id(OBJECT_DISTRICT, str(gid))
                result[oid] = RadarMapObject(
                    object_id=oid,
                    object_type=OBJECT_DISTRICT,
                    key=str(gid),
                    name=str(name),
                    region=str(region),
                ).safe_copy()
        return result

    async def _async_get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> object:
        url = urljoin(self._base_url, path.lstrip("/"))
        started = time.monotonic()
        _LOGGER.debug("RadarMap API request: GET %s params=%s", url, params or {})
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                ) as response:
                    _LOGGER.debug(
                        "RadarMap API response: status=%s duration=%.3fs",
                        response.status,
                        time.monotonic() - started,
                    )
                    if response.status < 200 or response.status >= 300:
                        raise RadarMapHttpError(
                            response.status,
                            _retry_after(response),
                        )
                    try:
                        return await response.json(content_type=None)
                    except (json.JSONDecodeError, ValueError, TypeError) as err:
                        raise RadarMapInvalidResponseError("Malformed JSON") from err
        except RadarMapError:
            raise
        except (TimeoutError, ClientError) as err:
            raise RadarMapConnectionError(str(err)) from err


def _retry_after(response: ClientResponse) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(1.0, min(float(value), 3600.0))
    except ValueError:
        return None


def _parse_region_catalog(payload: object) -> dict[str, RadarMapObject]:
    if not isinstance(payload, Mapping):
        raise RadarMapInvalidResponseError("Region catalog is not an object")
    features = payload.get("features", [])
    if not isinstance(features, Sequence) or isinstance(features, (str, bytes)):
        raise RadarMapInvalidResponseError("Region catalog features is not an array")
    result: dict[str, RadarMapObject] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        props = feature.get("properties")
        if not isinstance(props, Mapping) or not props.get("name_ru"):
            continue
        name = str(props["name_ru"])
        key = normalize_region_id(name)
        oid = object_id(OBJECT_REGION, key)
        result[oid] = RadarMapObject(
            object_id=oid,
            object_type=OBJECT_REGION,
            key=key,
            name=name,
            region=name,
        ).safe_copy()
    if not result:
        raise RadarMapInvalidResponseError("Region catalog is empty")
    return result


def _parse_city_catalog(parts: Sequence[object]) -> dict[str, RadarMapObject]:
    result: dict[str, RadarMapObject] = {}
    for payload in parts:
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise RadarMapInvalidResponseError("City catalog is not an array")
        for row in payload:
            if not isinstance(row, Mapping) or not row.get("name") or not row.get("region"):
                continue
            name = str(row["name"])
            region = str(row["region"])
            key = city_key(name, region)
            oid = object_id(OBJECT_CITY, key)
            lat = row.get("lat")
            lon = row.get("lon")
            result[oid] = RadarMapObject(
                object_id=oid,
                object_type=OBJECT_CITY,
                key=key,
                name=name,
                region=region,
                latitude=(
                    float(lat)
                    if isinstance(lat, (int, float)) and not isinstance(lat, bool)
                    else None
                ),
                longitude=(
                    float(lon)
                    if isinstance(lon, (int, float)) and not isinstance(lon, bool)
                    else None
                ),
            ).safe_copy()
    if not result:
        raise RadarMapInvalidResponseError("City catalog is empty")
    return result
