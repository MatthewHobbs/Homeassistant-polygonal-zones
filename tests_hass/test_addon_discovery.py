"""Discovery from the companion editor add-on (real flow manager)."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_HASSIO
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
import pytest

from custom_components.polygonal_zones.const import DOMAIN


@pytest.fixture(autouse=True)
def _no_entry_setup():
    """These tests are about the flow; a created entry would fetch a host that
    does not exist here and leave a task behind."""
    with patch(
        "custom_components.polygonal_zones.async_setup_entry", new=AsyncMock(return_value=True)
    ):
        yield


def _info(**overrides) -> HassioServiceInfo:
    config = {
        "host": "local-polygonal-zones",
        "port": 8000,
        "path": "/zones.json",
        "token": "generated-token",
    }
    config.update(overrides.pop("config", {}))
    return HassioServiceInfo(
        config=config,
        name="Polygonal Zones",
        slug="local_polygonal_zones",
        uuid="discovery-1",
    )


async def _start(hass: HomeAssistant, info: HassioServiceInfo):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=info
    )


async def test_discovery_asks_once_then_creates_the_entry(hass: HomeAssistant) -> None:
    result = await _start(hass, _info())

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "hassio_confirm"
    assert result["description_placeholders"] == {
        "url": "http://local-polygonal-zones:8000/zones.json"
    }

    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["title"] == "Polygonal Zones"
    assert created["data"]["zone_urls"] == ["http://local-polygonal-zones:8000/zones.json"]
    assert created["data"]["zone_source_token"] == "generated-token"
    assert created["data"]["allow_private_urls"] is True
    assert created["data"]["download_zones"] is False
    assert created["data"]["entities"] == []


async def test_a_second_discovery_updates_the_same_entry(hass: HomeAssistant) -> None:
    """The add-on re-posts on every start with a fresh token; that must not
    create a second entry, and the new token has to reach the stored entry."""
    first = await _start(hass, _info())
    created = await hass.config_entries.flow.async_configure(first["flow_id"], {})
    entry = hass.config_entries.async_get_entry(created["result"].entry_id)

    second = await _start(hass, _info(config={"token": "rotated"}))

    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "already_configured"
    assert entry.data["zone_source_token"] == "rotated"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
