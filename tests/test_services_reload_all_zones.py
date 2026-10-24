"""Tests for the domain-wide reload_all_zones action."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.services import reload_all_zones
from custom_components.polygonal_zones.services.errors import RateLimited


def _entry(entry_id: str, source=None, *, runtime_data=True):
    data = SimpleNamespace(source=source) if runtime_data else None
    return SimpleNamespace(entry_id=entry_id, runtime_data=data)


def _hass(*entries) -> SimpleNamespace:
    return SimpleNamespace(
        config_entries=SimpleNamespace(async_loaded_entries=MagicMock(return_value=list(entries)))
    )


async def test_reloads_every_loaded_entry_once() -> None:
    first, second = AsyncMock(), AsyncMock()
    hass = _hass(_entry("a", first), _entry("b", second))

    with patch(
        "custom_components.polygonal_zones.services.reload_all_zones.enforce_mutation_rate_limit"
    ):
        await reload_all_zones.action_builder(hass)(SimpleNamespace())

    first.async_reload.assert_awaited_once_with(hass)
    second.async_reload.assert_awaited_once_with(hass)
    hass.config_entries.async_loaded_entries.assert_called_once_with(DOMAIN)


async def test_skips_an_entry_without_a_source() -> None:
    source = AsyncMock()
    hass = _hass(_entry("a", source), _entry("b", None, runtime_data=False))

    with patch(
        "custom_components.polygonal_zones.services.reload_all_zones.enforce_mutation_rate_limit"
    ):
        await reload_all_zones.action_builder(hass)(SimpleNamespace())

    source.async_reload.assert_awaited_once_with(hass)


async def test_a_rate_limited_entry_is_skipped_not_failed() -> None:
    """The add-on calls this after every save; one entry inside its budget must
    not stop the others reloading."""
    allowed, skipped = AsyncMock(), AsyncMock()
    hass = _hass(_entry("a", allowed), _entry("b", skipped))

    def limit(entry_id: str) -> None:
        if entry_id == "a":
            raise RateLimited("busy")

    with patch(
        "custom_components.polygonal_zones.services.reload_all_zones.enforce_mutation_rate_limit",
        side_effect=limit,
    ):
        await reload_all_zones.action_builder(hass)(SimpleNamespace())

    allowed.async_reload.assert_not_awaited()
    skipped.async_reload.assert_awaited_once_with(hass)
