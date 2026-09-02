"""HTTP client error-handling tests."""

from __future__ import annotations

import json

import pytest
from aiohttp import ClientConnectionError

from custom_components.radar_map.api import (
    RadarMapClient,
    RadarMapConnectionError,
    RadarMapInvalidResponseError,
    RadarMapNotReadyError,
)


class FakeResponse:
    """Small aiohttp response stand-in."""

    def __init__(self, payload=None, *, status: int = 200, error: Exception | None = None):
        self.payload = payload
        self.status = status
        self.error = error
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self, *, content_type=None):
        if self.error:
            raise self.error
        return self.payload


class FailingContext:
    """Request context that fails while opening the connection."""

    async def __aenter__(self):
        raise ClientConnectionError("offline")

    async def __aexit__(self, *args):
        return None


class FakeSession:
    """Capture request details and return a configured context manager."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


async def test_api_uses_nofeed_and_parses_state(state_payload: dict) -> None:
    """The polling request omits the unrelated message feed."""
    session = FakeSession(FakeResponse(state_payload))
    snapshot = await RadarMapClient(session).async_get_state()
    assert snapshot.version == 23
    assert session.calls[0][1]["params"] == {"nofeed": "1"}
    assert session.calls[0][1]["headers"]["User-Agent"].startswith("HomeAssistant-RadarMap/")


async def test_unavailable_api() -> None:
    """Connection failures are converted to the client error contract."""
    client = RadarMapClient(FakeSession(FailingContext()))
    with pytest.raises(RadarMapConnectionError):
        await client.async_get_state()


async def test_malformed_json() -> None:
    """Malformed JSON is explicit and never interpreted as an empty safe state."""
    malformed = json.JSONDecodeError("bad", "{", 0)
    client = RadarMapClient(FakeSession(FakeResponse(error=malformed)))
    with pytest.raises(RadarMapInvalidResponseError, match="Malformed JSON"):
        await client.async_get_state()


@pytest.mark.parametrize("field", ["startup_ready", "state_ready"])
async def test_transient_not_ready_is_not_safe(state_payload: dict, field: str) -> None:
    """A server startup/rebuild response is rejected rather than treated as safe."""
    state_payload[field] = False
    client = RadarMapClient(FakeSession(FakeResponse(state_payload)))
    with pytest.raises(RadarMapNotReadyError, match="not ready"):
        await client.async_get_state()
