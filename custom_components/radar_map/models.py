"""Schema-tolerant data models for RadarMap."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from .const import (
    AGGREGATE_ALERT_FIELDS,
    ALERT_FIELDS,
    DEFAULT_POLL_INTERVAL,
    OBJECT_CITY,
    OBJECT_DISTRICT,
    OBJECT_REGION,
)

ObjectType = Literal["region", "district", "city"]
FlagValue = bool | None


class RadarMapSchemaError(ValueError):
    """Raised when a RadarMap payload cannot safely be interpreted."""


def normalize_text(value: object) -> str:
    """Normalize text in the same way RadarMap city keys are formed."""
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return re.sub(r"\s+", " ", text)


def normalize_region_id(name: str) -> str:
    """Return a stable, readable identifier for a region name."""
    normalized = normalize_text(name)
    return re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")


def city_key(name: str, region: str) -> str:
    """Build the stable city key used by the current RadarMap API."""
    return f"{normalize_text(name)}|{normalize_text(region)}"


def object_id(object_type: ObjectType, key: str) -> str:
    """Build a namespaced stable object identifier."""
    return f"{object_type}:{key}"


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_timestamp(value: object) -> int | None:
    number = _optional_number(value)
    if number is None or number <= 0:
        return None
    return int(number)


def _flags(row: Mapping[str, Any]) -> dict[str, FlagValue]:
    """Parse flags without treating a missing/changed field as safe."""
    return {
        name: value if isinstance((value := row.get(name)), bool) else None for name in ALERT_FIELDS
    }


def aggregate_alert(flags: Mapping[str, FlagValue]) -> FlagValue:
    """Aggregate actual danger while keeping attention/PVO separate."""
    values = [flags.get(name) for name in AGGREGATE_ALERT_FIELDS]
    if any(value is True for value in values):
        return True
    if any(value is None for value in values):
        return None
    return False


@dataclass(frozen=True, slots=True)
class RadarMapObject:
    """Normalized state and metadata for one selectable map object."""

    object_id: str
    object_type: ObjectType
    key: str
    name: str
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    flags: Mapping[str, FlagValue] = field(default_factory=dict)
    last_event_ts: int | None = None
    source_text: str | None = None
    sources: tuple[str, ...] = ()

    @property
    def active_alert_types(self) -> tuple[str, ...]:
        """Return only currently active, semantic flags."""
        return tuple(name for name in ALERT_FIELDS if self.flags.get(name) is True)

    @property
    def alert(self) -> FlagValue:
        """Return the aggregate threat state."""
        return aggregate_alert(self.flags)

    def with_sources(self, sources: Iterable[str]) -> RadarMapObject:
        """Return a copy with contributing source identifiers."""
        return replace(self, sources=tuple(dict.fromkeys(sources)))

    def as_selection_dict(self) -> dict[str, Any]:
        """Return JSON-serializable metadata suitable for config options."""
        return {
            "object_id": self.object_id,
            "object_type": self.object_type,
            "key": self.key,
            "name": self.name,
            "region": self.region,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    @classmethod
    def from_selection_dict(cls, data: Mapping[str, Any]) -> RadarMapObject:
        """Restore object metadata stored by a config/options flow."""
        object_type_value = str(data.get("object_type", ""))
        if object_type_value not in {OBJECT_REGION, OBJECT_DISTRICT, OBJECT_CITY}:
            raise RadarMapSchemaError(f"Unknown object type: {object_type_value}")
        return cls(
            object_id=str(data["object_id"]),
            object_type=object_type_value,  # type: ignore[arg-type]
            key=str(data["key"]),
            name=str(data["name"]),
            region=str(data["region"]) if data.get("region") else None,
            latitude=_optional_number(data.get("latitude")),
            longitude=_optional_number(data.get("longitude")),
            flags={name: False for name in ALERT_FIELDS},
        )

    def safe_copy(self) -> RadarMapObject:
        """Represent an object omitted from a successful full snapshot as safe."""
        return replace(
            self,
            flags={name: False for name in ALERT_FIELDS},
            last_event_ts=None,
            source_text=None,
            sources=(),
        )

    def inactive_copy(self) -> RadarMapObject:
        """Clear flags while retaining useful last-event context."""
        return replace(
            self,
            flags={name: False for name in ALERT_FIELDS},
            sources=(),
        )


@dataclass(frozen=True, slots=True)
class RadarMapCatalog:
    """Selectable RadarMap locations and lazy district manifest."""

    regions: Mapping[str, RadarMapObject]
    cities: Mapping[str, RadarMapObject]
    district_manifest: Mapping[str, str]
    district_base: str


@dataclass(frozen=True, slots=True)
class RadarMapSnapshot:
    """Normalized result of one full state poll."""

    version: int | str | None
    poll_interval: float
    objects: Mapping[str, RadarMapObject]
    source_labels: Mapping[str, str]
    startup_ready: bool
    state_ready: bool

    def object_or_safe(self, selected: RadarMapObject) -> RadarMapObject:
        """Return current state or safe state for an omitted location."""
        return self.objects.get(selected.object_id, selected.safe_copy())

    @classmethod
    def from_api(cls, payload: object) -> RadarMapSnapshot:
        """Normalize a `/api/state` response."""
        if not isinstance(payload, Mapping):
            raise RadarMapSchemaError("Root payload is not an object")
        if payload.get("type") != "state":
            raise RadarMapSchemaError(f"Unexpected payload type: {payload.get('type')!r}")

        regions = payload.get("regions", {})
        cities = payload.get("cities", [])
        districts = payload.get("districts", {})
        if not isinstance(regions, Mapping):
            raise RadarMapSchemaError("regions is not an object")
        if not isinstance(cities, Sequence) or isinstance(cities, (str, bytes)):
            raise RadarMapSchemaError("cities is not an array")
        if not isinstance(districts, Mapping):
            raise RadarMapSchemaError("districts is not an object")
        if not any(key in payload for key in ("regions", "cities", "districts")):
            raise RadarMapSchemaError("State contains no supported object collections")

        source_labels: dict[str, str] = {}
        raw_sources = payload.get("sources", [])
        if isinstance(raw_sources, Sequence) and not isinstance(raw_sources, (str, bytes)):
            for source in raw_sources:
                if not isinstance(source, Mapping) or not source.get("id"):
                    continue
                source_id = str(source["id"])
                source_labels[source_id] = str(source.get("label") or source_id)

        objects: dict[str, RadarMapObject] = {}
        for name, row in regions.items():
            if not isinstance(name, str) or not isinstance(row, Mapping):
                continue
            key = normalize_region_id(name)
            item = _object_from_row(OBJECT_REGION, key, name, row, region=name)
            objects[item.object_id] = item

        for row in districts.values():
            if not isinstance(row, Mapping):
                continue
            gid = row.get("gid_2")
            name = row.get("name_ru")
            if not gid or not name:
                continue
            item = _object_from_row(
                OBJECT_DISTRICT,
                str(gid),
                str(name),
                row,
                region=str(row["region_ru"]) if row.get("region_ru") else None,
            )
            objects[item.object_id] = item

        for row in cities:
            if not isinstance(row, Mapping) or not row.get("name") or not row.get("region"):
                continue
            key = str(row.get("key") or city_key(str(row["name"]), str(row["region"])))
            item = _object_from_row(
                OBJECT_CITY,
                key,
                str(row["name"]),
                row,
                region=str(row["region"]),
            )
            objects[item.object_id] = item

        _attach_sources(objects, payload.get("states"))

        poll_interval = payload.get("poll_interval_sec")
        live = payload.get("client_live")
        if isinstance(live, Mapping) and isinstance(live.get("poll_interval_sec"), (int, float)):
            poll_interval = live["poll_interval_sec"]
        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or poll_interval <= 0
        ):
            poll_interval = DEFAULT_POLL_INTERVAL

        version = payload.get("version")
        return cls(
            version=version if isinstance(version, (int, str)) else None,
            poll_interval=float(poll_interval),
            objects=objects,
            source_labels=source_labels,
            startup_ready=payload.get("startup_ready") is not False,
            state_ready=payload.get("state_ready") is not False,
        )


def _object_from_row(
    object_type_value: ObjectType,
    key: str,
    name: str,
    row: Mapping[str, Any],
    *,
    region: str | None,
) -> RadarMapObject:
    source_text = row.get("source_text")
    return RadarMapObject(
        object_id=object_id(object_type_value, key),
        object_type=object_type_value,
        key=key,
        name=name,
        region=region,
        latitude=_optional_number(row.get("lat")),
        longitude=_optional_number(row.get("lon")),
        flags=_flags(row),
        last_event_ts=_optional_timestamp(row.get("last_event_ts")),
        source_text=str(source_text) if isinstance(source_text, str) and source_text else None,
    )


def _attach_sources(objects: dict[str, RadarMapObject], raw_states: object) -> None:
    """Annotate aggregate objects with source IDs that currently mention them."""
    if not isinstance(raw_states, Mapping):
        return
    sources_by_object: dict[str, list[str]] = {}
    for source_id, state in raw_states.items():
        if source_id == "__all__" or not isinstance(state, Mapping):
            continue
        source = str(source_id)
        source_regions = state.get("regions", {})
        if isinstance(source_regions, Mapping):
            for name in source_regions:
                oid = object_id(OBJECT_REGION, normalize_region_id(str(name)))
                if oid in objects:
                    sources_by_object.setdefault(oid, []).append(source)
        source_districts = state.get("districts", {})
        if isinstance(source_districts, Mapping):
            for gid in source_districts:
                oid = object_id(OBJECT_DISTRICT, str(gid))
                if oid in objects:
                    sources_by_object.setdefault(oid, []).append(source)
        source_cities = state.get("cities", [])
        if isinstance(source_cities, Sequence) and not isinstance(source_cities, (str, bytes)):
            for row in source_cities:
                if not isinstance(row, Mapping) or not row.get("name") or not row.get("region"):
                    continue
                key = str(row.get("key") or city_key(str(row["name"]), str(row["region"])))
                oid = object_id(OBJECT_CITY, key)
                if oid in objects:
                    sources_by_object.setdefault(oid, []).append(source)
    for oid, sources in sources_by_object.items():
        objects[oid] = objects[oid].with_sources(sources)


def selected_objects_from_mapping(data: Mapping[str, Any]) -> tuple[RadarMapObject, ...]:
    """Restore selected objects from config entry data/options."""
    raw_objects = data.get("objects", [])
    if not isinstance(raw_objects, Sequence) or isinstance(raw_objects, (str, bytes)):
        return ()
    result: list[RadarMapObject] = []
    for item in raw_objects:
        if not isinstance(item, Mapping):
            continue
        try:
            result.append(RadarMapObject.from_selection_dict(item))
        except (KeyError, RadarMapSchemaError, TypeError, ValueError):
            continue
    return tuple(result)
