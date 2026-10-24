"""Repair issue for two entries reading the same editor."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.zone_source import async_check_duplicate_source


@pytest.fixture(autouse=True)
def _no_entry_setup():
    """These entries point at an address that does not exist here."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "custom_components.polygonal_zones.async_setup_entry", new=AsyncMock(return_value=True)
    ):
        yield


def _entry(title: str, url: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={"zone_urls": [url], "entities": [], "download_zones": False},
    )


async def test_two_entries_on_one_editor_are_flagged(hass: HomeAssistant) -> None:
    first = _entry("Polygonal Zones (10.0.0.5:8099)", "http://10.0.0.5:8099/zones.json")
    second = _entry("Polygonal Zones (10.0.0.5:8099)", "http://10.0.0.5:8099/other.json")
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    async_check_duplicate_source(hass, second)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"duplicate_source_{second.entry_id}")
    assert issue is not None
    assert issue.translation_key == "duplicate_source"
    assert issue.translation_placeholders == {
        "entry_id": second.entry_id,
        "other_entry": first.title,
    }


async def test_a_different_editor_is_not_flagged(hass: HomeAssistant) -> None:
    first = _entry("Polygonal Zones (10.0.0.5:8099)", "http://10.0.0.5:8099/zones.json")
    second = _entry("Polygonal Zones (10.0.0.6:8099)", "http://10.0.0.6:8099/zones.json")
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    async_check_duplicate_source(hass, second)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"duplicate_source_{second.entry_id}") is None


async def test_the_issue_clears_once_the_other_entry_is_gone(hass: HomeAssistant) -> None:
    first = _entry("Polygonal Zones (10.0.0.5:8099)", "http://10.0.0.5:8099/zones.json")
    second = _entry("Polygonal Zones (10.0.0.5:8099)", "http://10.0.0.5:8099/other.json")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    async_check_duplicate_source(hass, second)

    await hass.config_entries.async_remove(first.entry_id)
    async_check_duplicate_source(hass, second)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"duplicate_source_{second.entry_id}") is None
