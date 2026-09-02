"""Constants for the RadarMap integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "radar_map"
NAME: Final = "RadarMap"

API_BASE_URL: Final = "https://radar-map.ru"
API_STATE_PATH: Final = "/api/state"
REGIONS_CATALOG_PATH: Final = "/static/data/russia_regions.geojson"
CITIES_CATALOG_PATHS: Final = (
    "/static/data/cities_ru.json",
    "/static/data/cities_user.json",
)
DISTRICTS_MANIFEST_PATH: Final = "/static/data/districts_by_region/manifest.json"

DEFAULT_POLL_INTERVAL: Final = 30.0
MIN_POLL_INTERVAL: Final = 15.0
MAX_POLL_INTERVAL: Final = 300.0
REQUEST_TIMEOUT: Final = 15.0
USER_AGENT: Final = "HomeAssistant-RadarMap/1.0"
MAX_SOURCE_TEXT_LENGTH: Final = 2048

CONF_REGIONS: Final = "regions"
CONF_CITIES: Final = "cities"
CONF_DISTRICTS: Final = "districts"
CONF_DISTRICT_REGIONS: Final = "district_regions"
CONF_OBJECTS: Final = "objects"

OBJECT_REGION: Final = "region"
OBJECT_DISTRICT: Final = "district"
OBJECT_CITY: Final = "city"

# Fields exported as individual binary sensors. Missing fields on an object are
# represented as unknown, not silently coerced to safe/off.
ALERT_FIELDS: Final = (
    "bpla",
    "attention",
    "danger",
    "uab",
    "fpv",
    "rocket",
    "rocket_level",
    "aviation",
    "pvo",
)

# Attention is deliberately a separate warning. PVO is an observed defensive
# event, not itself an active threat. rocket_level is included because the
# RadarMap frontend treats it as rocket/aviation danger.
AGGREGATE_ALERT_FIELDS: Final = (
    "bpla",
    "danger",
    "uab",
    "fpv",
    "rocket",
    "rocket_level",
    "aviation",
)

EVENT_ALERT: Final = "radar_map_alert"
PLATFORMS: Final = ("binary_sensor", "sensor")
