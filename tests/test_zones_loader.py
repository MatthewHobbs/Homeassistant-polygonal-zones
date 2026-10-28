"""Tests for utils.zones.get_zones — GeoJSON parsing."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.utils.zones import (
    UnsupportedSchemaVersion,
    ZoneFileCorrupt,
    _parse_zone_document,
    get_zones,
    haversine_distances,
    load_zones,
)


async def _run_executor_job(func, *args):
    """Inline stand-in for hass.async_add_executor_job (runs the func directly)."""
    return func(*args)


def _make_hass() -> SimpleNamespace:
    """Minimal hass stub: the loader offloads parsing via async_add_executor_job."""
    return SimpleNamespace(async_add_executor_job=_run_executor_job)


def _polygon(name: str, priority: int | None = None) -> dict:
    feature = {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        },
    }
    if priority is not None:
        feature["properties"]["priority"] = priority
    return feature


async def test_get_zones_parses_feature_collection() -> None:
    """get_zones converts a single GeoJSON file into a list of Zone objects."""
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [_polygon("Home", priority=0), _polygon("Work")],
        }
    )
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        zones = await get_zones(["http://example.com/zones.json"], _make_hass(), False)

    assert len(zones) == 2
    assert {z.name for z in zones} == {"Home", "Work"}
    by_name = {z.name: z for z in zones}
    assert by_name["Home"].priority == 0


async def test_prioritize_file_index_resolves_overlapping_point_to_file_0() -> None:
    """End-to-end: two files, each with a zone that covers point (0.5, 0.5).

    Neither zone declares an explicit priority. With ``prioritize=True`` the
    loader stamps file_index on each zone's priority, and the resolver must
    then pick the zone from the first file (lower priority value wins). Before
    this test existed, the priority-stamping and resolver logic were covered
    independently but never joined end-to-end — a regression between the two
    halves would pass both isolated suites yet return the wrong zone in prod.
    """
    from custom_components.polygonal_zones.utils.zones import get_locations_zone

    # Both zones are identical squares — each standalone covers the test point.
    square = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
    }
    file_primary = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"name": "Primary"}, "geometry": square}
            ],
        }
    )
    file_backup = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"name": "Backup"}, "geometry": square}],
        }
    )

    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        return file_primary if "primary" in uri else file_backup

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        side_effect=fake_load,
    ):
        zones = await get_zones(
            ["http://example.com/primary.json", "http://example.com/backup.json"],
            _make_hass(),
            True,
        )

    # Priorities stamped from file index
    assert [(z.name, z.priority) for z in zones] == [("Primary", 0), ("Backup", 1)]

    # The resolver hands back the lower-priority-value (first-file) zone
    result = get_locations_zone(lat=0.5, lon=0.5, acc=1, zones=zones)
    assert result is not None
    assert result["name"] == "Primary"


def test_haversine_distance_known_pair() -> None:
    """London → Paris, ~344 km, accept 1% tolerance."""
    london = (51.5074, -0.1278)  # (lat, lon)
    paris = [(48.8566, 2.3522)]
    distance_m = haversine_distances(london, paris)[0]
    distance_km = distance_m / 1000.0
    assert abs(distance_km - 344) < 4


def test_haversine_distance_to_self_is_zero() -> None:
    p = (10.0, 20.0)
    distance = haversine_distances(p, [(10.0, 20.0)])[0]
    assert abs(distance) < 1e-6


def test_get_zones_empty_uri_list_returns_empty_list() -> None:
    """Edge case: zero URIs → empty list, not a crash."""

    async def _go():
        return await get_zones([], _make_hass(), False)

    zones = asyncio.run(_go())
    assert zones == []


async def test_get_zones_accepts_known_schema_version() -> None:
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 1},
            "features": [_polygon("Home")],
        }
    )
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        zones = await get_zones(["http://x"], _make_hass(), False)
    assert zones[0].name == "Home"


async def test_parse_serialize_roundtrip_preserves_extra_properties() -> None:
    """A full file → get_zones → zones_to_geojson → get_zones cycle preserves custom keys."""
    from custom_components.polygonal_zones.utils.local_zones import zones_to_geojson

    source = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 1},
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Home",
                        "priority": 2,
                        "description": "front door",
                        "polygonal_zones_ext": {"color": "#f00"},
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                    },
                }
            ],
        }
    )

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=source),
    ):
        first = await get_zones(["http://x"], _make_hass(), False)

    serialized = zones_to_geojson(first)

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=serialized),
    ):
        second = await get_zones(["http://x"], _make_hass(), False)

    assert second[0].properties["description"] == "front door"
    assert second[0].properties["polygonal_zones_ext"] == {"color": "#f00"}
    assert second[0].priority == 2


async def test_get_zones_rejects_future_schema_version() -> None:
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 99},
            "features": [_polygon("Home")],
        }
    )
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(UnsupportedSchemaVersion, match="schema_version=99"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


# ---------- Structural validation: _parse_feature via _load_zones_from_uri ----------


async def test_get_zones_rejects_top_level_not_object() -> None:
    """A JSON array at the top level is not a FeatureCollection."""
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value="[]"),
        ),
        pytest.raises(ZoneFileCorrupt, match="top-level payload is not an object"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


async def test_get_zones_rejects_non_json_body() -> None:
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value="not json {"),
        ),
        pytest.raises(ZoneFileCorrupt, match="not valid JSON"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


async def test_get_zones_rejects_missing_features_list() -> None:
    payload = json.dumps({"type": "FeatureCollection"})
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(ZoneFileCorrupt, match="'features' is missing"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


async def test_get_zones_rejects_feature_missing_geometry() -> None:
    feature = {"type": "Feature", "properties": {"name": "Home"}}
    payload = json.dumps({"type": "FeatureCollection", "features": [feature]})
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(ZoneFileCorrupt, match="no 'geometry' object"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


async def test_get_zones_rejects_feature_blank_name() -> None:
    feature = {
        "type": "Feature",
        "properties": {"name": "   "},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
    }
    payload = json.dumps({"type": "FeatureCollection", "features": [feature]})
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(ZoneFileCorrupt, match=r"properties\.name"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


async def test_get_zones_rejects_feature_unparseable_priority() -> None:
    feature = {
        "type": "Feature",
        "properties": {"name": "Home", "priority": "not-an-int"},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
    }
    payload = json.dumps({"type": "FeatureCollection", "features": [feature]})
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(ZoneFileCorrupt, match="non-integer priority"),
    ):
        await get_zones(["http://x"], _make_hass(), False)


# ---------- Per-URI partial success via load_zones ----------


async def test_load_zones_partial_success_keeps_successful_uris() -> None:
    """One URI fails, another succeeds — the successful zones survive; failure is recorded."""
    good = json.dumps({"type": "FeatureCollection", "features": [_polygon("Home")]})
    bad_exc = RuntimeError("DNS boom")

    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        if "good" in uri:
            return good
        raise bad_exc

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        side_effect=fake_load,
    ):
        result = await load_zones(["http://good", "http://bad"], _make_hass(), False)

    assert [z.name for z in result.zones] == ["Home"]
    assert len(result.failures) == 1
    failed_uri, failed_msg = result.failures[0]
    assert failed_uri == "http://bad"
    assert "DNS boom" in failed_msg


async def test_load_zones_all_fail_returns_empty_with_failures() -> None:
    """All URIs fail — load_zones returns empty zones + full failure list (never raises)."""

    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        raise RuntimeError(f"nope {uri}")

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        side_effect=fake_load,
    ):
        result = await load_zones(["http://a", "http://b"], _make_hass(), False)

    assert result.zones == []
    assert {uri for uri, _ in result.failures} == {"http://a", "http://b"}


async def test_get_zones_raises_when_all_uris_fail() -> None:
    """get_zones (the wrapper) raises ZoneFileCorrupt so retry/backoff still kicks in."""

    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        raise RuntimeError(f"down: {uri}")

    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            side_effect=fake_load,
        ),
        pytest.raises(ZoneFileCorrupt, match="All 2 zone URIs failed"),
    ):
        await get_zones(["http://a", "http://b"], _make_hass(), False)


async def test_load_zones_unsupported_schema_propagates_as_hard_error() -> None:
    """Schema-version mismatch is NOT swallowed into the failures list."""
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 99},
            "features": [],
        }
    )
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(UnsupportedSchemaVersion),
    ):
        await load_zones(["http://x"], _make_hass(), False)


_SECRET_URI = "https://user:pa55@zones.example.com/z.json?token=s3cr3t"


async def test_failed_load_logs_and_records_only_the_redacted_uri(caplog) -> None:
    """Credentials and query tokens in a zone URL must not reach the log or the failure record."""

    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        raise RuntimeError(f"boom while fetching {uri}")

    with (
        caplog.at_level("DEBUG"),
        patch("custom_components.polygonal_zones.utils.zones.load_data", side_effect=fake_load),
    ):
        result = await load_zones([_SECRET_URI], _make_hass(), False)

    everything = caplog.text + repr(result.failures)
    assert "pa55" not in everything
    assert "s3cr3t" not in everything
    assert result.failures == [
        (
            "https://zones.example.com/z.json",
            "boom while fetching https://zones.example.com/z.json",
        )
    ]
    # No traceback: it would repeat the raw exception text.
    assert all(r.exc_info is None for r in caplog.records)


async def test_real_aiohttp_error_does_not_leak_the_query_token(caplog) -> None:
    """aiohttp drops user:pass@ but keeps the query in its own message, so the
    configured string never appears in it: the case a literal replace cannot catch."""
    import aiohttp
    from yarl import URL

    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        info = aiohttp.RequestInfo(
            url=URL(uri), method="GET", headers={}, real_url=URL(uri).with_user(None)
        )
        raise aiohttp.ClientResponseError(info, (), status=401, message="Unauthorized")

    with (
        caplog.at_level("DEBUG"),
        patch("custom_components.polygonal_zones.utils.zones.load_data", side_effect=fake_load),
    ):
        result = await load_zones([_SECRET_URI], _make_hass(), False)
        with pytest.raises(ZoneFileCorrupt) as all_failed:
            await get_zones([_SECRET_URI], _make_hass(), False)

    everything = caplog.text + repr(result.failures) + str(all_failed.value)
    assert "s3cr3t" not in everything
    assert "pa55" not in everything
    assert "401" in everything  # still useful to the person debugging


async def test_get_zones_all_failed_message_is_redacted() -> None:
    async def fake_load(uri: str, _hass, **_kwargs) -> str:
        raise RuntimeError(f"nope {uri}")

    with (
        patch("custom_components.polygonal_zones.utils.zones.load_data", side_effect=fake_load),
        pytest.raises(ZoneFileCorrupt) as err,
    ):
        await get_zones([_SECRET_URI], _make_hass(), False)

    assert "pa55" not in str(err.value)
    assert "s3cr3t" not in str(err.value)


def test_unsupported_schema_version_message_is_redacted() -> None:
    data = {
        "type": "FeatureCollection",
        "polygonal_zones": {"schema_version": 999},
        "features": [],
    }
    with pytest.raises(UnsupportedSchemaVersion) as err:
        _parse_zone_document(json.dumps(data), 0, False, _SECRET_URI)

    assert "pa55" not in str(err.value)
    assert "s3cr3t" not in str(err.value)


async def test_load_zones_binds_token_and_trust_only_to_the_announced_url() -> None:
    """When addon_url is set on a discovered entry, no other URL on the entry
    receives the token or the trusted_host flag."""
    seen: list[tuple[str, str | None, bool]] = []

    async def fake_load(uri: str, _hass, *, token=None, trusted_host=False, **_kwargs) -> str:
        seen.append((uri, token, trusted_host))
        return '{"type": "FeatureCollection", "features": []}'

    addon_url = "http://local-polygonal-zones:8000/zones.json"
    extra_url = "https://example.org/z.json"
    with patch("custom_components.polygonal_zones.utils.zones.load_data", side_effect=fake_load):
        await load_zones(
            [addon_url, extra_url],
            _make_hass(),
            False,
            token="s3cr3t",
            addon_url=addon_url,
        )

    assert seen == [
        (addon_url, "s3cr3t", True),
        (extra_url, None, False),
    ]
