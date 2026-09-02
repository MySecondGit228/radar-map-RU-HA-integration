"""DataUpdateCoordinator for RadarMap."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RadarMapError, RadarMapHttpError
from .const import (
    ALERT_FIELDS,
    DEFAULT_POLL_INTERVAL,
    EVENT_ALERT,
    MAX_POLL_INTERVAL,
    MAX_SOURCE_TEXT_LENGTH,
    MIN_POLL_INTERVAL,
)
from .models import RadarMapObject, RadarMapSnapshot

_LOGGER = logging.getLogger(__name__)


class RadarMapCoordinator(DataUpdateCoordinator[RadarMapSnapshot]):
    """Poll one full RadarMap snapshot for all selected entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client,
        selected_objects: tuple[RadarMapObject, ...],
        config_entry=None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="RadarMap",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.client = client
        self.selected_objects = selected_objects
        self._selected_by_id = {item.object_id: item for item in selected_objects}
        self._last_flags: dict[str, dict[str, bool | None]] | None = None
        self._resolved_objects: dict[str, RadarMapObject] = {}
        self.last_successful_update: datetime | None = None
        self.last_error: str | None = None
        self.last_update_duration: float | None = None

    def get_object(self, object_id: str) -> RadarMapObject:
        """Return selected object state from the latest successful snapshot."""
        selected = self._selected_by_id[object_id]
        if self.data is None:
            return selected.safe_copy()
        return self._resolved_objects.get(object_id, selected.safe_copy())

    async def _async_update_data(self) -> RadarMapSnapshot:
        started = time.monotonic()
        try:
            snapshot = await self.client.async_get_state()
        except RadarMapHttpError as err:
            self.last_error = str(err)
            self.last_update_duration = time.monotonic() - started
            if err.status == 429:
                raise UpdateFailed(
                    str(err),
                    retry_after=err.retry_after or DEFAULT_POLL_INTERVAL * 2,
                ) from err
            raise UpdateFailed(str(err)) from err
        except RadarMapError as err:
            self.last_error = str(err)
            self.last_update_duration = time.monotonic() - started
            raise UpdateFailed(str(err)) from err

        self.last_update_duration = time.monotonic() - started
        self.last_successful_update = datetime.now(UTC)
        self.last_error = None
        interval = max(
            MIN_POLL_INTERVAL,
            min(snapshot.poll_interval, MAX_POLL_INTERVAL),
        )
        self.update_interval = timedelta(seconds=interval)

        resolved_objects: dict[str, RadarMapObject] = {}
        for selected in self.selected_objects:
            current = snapshot.objects.get(selected.object_id)
            if current is None:
                previous = self._resolved_objects.get(selected.object_id, selected)
                current = previous.inactive_copy()
            resolved_objects[selected.object_id] = current
        self._resolved_objects = resolved_objects
        current_flags = {
            object_id: dict(item.flags) for object_id, item in resolved_objects.items()
        }
        if self._last_flags is not None:
            self._fire_state_change_events(self._last_flags, current_flags)
        self._last_flags = current_flags

        _LOGGER.debug(
            "RadarMap update completed: duration=%.3fs objects=%d selected=%d poll_interval=%.1fs",
            self.last_update_duration,
            len(snapshot.objects),
            len(self.selected_objects),
            interval,
        )
        return snapshot

    def _fire_state_change_events(
        self,
        previous: dict[str, dict[str, bool | None]],
        current: dict[str, dict[str, bool | None]],
    ) -> None:
        changes = 0
        for selected in self.selected_objects:
            old_flags = previous.get(selected.object_id, {})
            new_flags = current[selected.object_id]
            item = self._resolved_objects[selected.object_id]
            for alert_type in ALERT_FIELDS:
                old = old_flags.get(alert_type)
                new = new_flags.get(alert_type)
                # Unknown due to a schema change is not equivalent to safe.
                if not isinstance(old, bool) or not isinstance(new, bool) or old == new:
                    continue
                payload = {
                    "object_type": item.object_type,
                    "object_id": item.object_id,
                    "name": item.name,
                    "region": item.region,
                    "alert_type": alert_type,
                    "state": "on" if new else "off",
                    "last_event_ts": item.last_event_ts,
                    "source_text": (
                        item.source_text[:MAX_SOURCE_TEXT_LENGTH] if item.source_text else None
                    ),
                    "sources": list(item.sources),
                }
                self.hass.bus.async_fire(EVENT_ALERT, payload)
                changes += 1
        if changes:
            _LOGGER.debug("RadarMap semantic state changes: %d", changes)
