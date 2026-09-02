"""DataUpdateCoordinator for RadarMap."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class RadarMapSemanticEvent:
    """One observed semantic state transition for a selected object."""

    object_type: str
    object_id: str
    name: str
    region: str | None
    alert_type: str
    state: str
    observed_at: str
    api_last_event_ts: int | None
    source_text: str | None
    sources: tuple[str, ...]

    @property
    def code(self) -> str:
        """Return a stable machine-readable event code."""
        suffix = "started" if self.state == "on" else "ended"
        return f"{self.alert_type}_{suffix}"

    def as_attributes(self) -> dict[str, object]:
        """Return compact Home Assistant state attributes."""
        return {
            "event_code": self.code,
            "alert_type": self.alert_type,
            "state": self.state,
            "transition": self.state,
            "event_timestamp": self.observed_at,
            "api_last_event_ts": self.api_last_event_ts,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "name": self.name,
            "region": self.region,
            "source_text": self.source_text,
            "sources": list(self.sources),
        }


class RadarMapCoordinator(DataUpdateCoordinator[RadarMapSnapshot]):
    """Poll one full RadarMap snapshot for all selected entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client,
        selected_objects: tuple[RadarMapObject, ...],
        configured_poll_interval: float = DEFAULT_POLL_INTERVAL,
        config_entry=None,
    ) -> None:
        self.configured_poll_interval = max(
            MIN_POLL_INTERVAL,
            min(configured_poll_interval, MAX_POLL_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name="RadarMap",
            config_entry=config_entry,
            update_interval=timedelta(seconds=self.configured_poll_interval),
        )
        self.client = client
        self.selected_objects = selected_objects
        self._selected_by_id = {item.object_id: item for item in selected_objects}
        self._last_flags: dict[str, dict[str, bool | None]] | None = None
        self._resolved_objects: dict[str, RadarMapObject] = {}
        self.last_successful_update: datetime | None = None
        self.last_error: str | None = None
        self.last_update_duration: float | None = None
        self.server_poll_interval: float | None = None
        self.last_events: dict[str, RadarMapSemanticEvent] = {}
        self.last_event: RadarMapSemanticEvent | None = None

    def get_object(self, object_id: str) -> RadarMapObject:
        """Return selected object state from the latest successful snapshot."""
        selected = self._selected_by_id[object_id]
        if self.data is None:
            return selected.safe_copy()
        return self._resolved_objects.get(object_id, selected.safe_copy())

    def get_last_event(self, object_id: str) -> RadarMapSemanticEvent | None:
        """Return the latest semantic transition observed for one object."""
        return self.last_events.get(object_id)

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
        server_interval = max(
            MIN_POLL_INTERVAL,
            min(snapshot.poll_interval, MAX_POLL_INTERVAL),
        )
        self.server_poll_interval = server_interval
        # Never poll faster than either the user's preference or RadarMap's
        # current server policy.
        interval = max(self.configured_poll_interval, server_interval)
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
        observed_at = datetime.now(UTC).isoformat()
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
                event = RadarMapSemanticEvent(
                    object_type=item.object_type,
                    object_id=item.object_id,
                    name=item.name,
                    region=item.region,
                    alert_type=alert_type,
                    state="on" if new else "off",
                    observed_at=observed_at,
                    api_last_event_ts=item.last_event_ts,
                    source_text=(
                        item.source_text[:MAX_SOURCE_TEXT_LENGTH] if item.source_text else None
                    ),
                    sources=item.sources,
                )
                self.last_events[item.object_id] = event
                self.last_event = event
                payload = event.as_attributes()
                payload["last_event_ts"] = item.last_event_ts
                self.hass.bus.async_fire(EVENT_ALERT, payload)
                changes += 1
        if changes:
            _LOGGER.debug("RadarMap semantic state changes: %d", changes)
