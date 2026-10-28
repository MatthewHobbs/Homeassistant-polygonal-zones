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


def _info(*, config: dict | None = None, uuid: str = "discovery-1") -> HassioServiceInfo:
    payload = {
        "host": "local-polygonal-zones",
        "port": 8000,
        "path": "/zones.json",
        "token": "generated-token",
    }
    payload.update(config or {})
    return HassioServiceInfo(
        config=payload,
        name="Polygonal Zones",
        slug="local_polygonal_zones",
        uuid=uuid,
    )


async def _start(hass: HomeAssistant, info: HassioServiceInfo):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=info
    )


async def _create(hass: HomeAssistant, info: HassioServiceInfo):
    started = await _start(hass, info)
    assert started["type"] == FlowResultType.FORM
    created = await hass.config_entries.flow.async_configure(started["flow_id"], {})
    assert created["type"] == FlowResultType.CREATE_ENTRY
    return hass.config_entries.async_get_entry(created["result"].entry_id)


async def test_discovery_asks_once_then_creates_the_entry(hass: HomeAssistant) -> None:
    result = await _start(hass, _info())

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "hassio_confirm"
    assert result["description_placeholders"] == {
        "url": "http://local-polygonal-zones:8000/zones.json"
    }

    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert created["type"] == FlowResultType.CREATE_ENTRY
    # The address is part of the title so two entries are told apart in Settings.
    assert created["title"] == "Polygonal Zones (local-polygonal-zones:8000)"
    assert created["data"]["zone_urls"] == ["http://local-polygonal-zones:8000/zones.json"]
    assert created["data"]["zone_source_token"] == "generated-token"
    assert created["data"]["allow_private_urls"] is True
    assert created["data"]["download_zones"] is False
    assert created["data"]["entities"] == []
    # The add-on's hostname is neither an IP literal nor `.local`, so this flag
    # and the announced URL let the fetch carry the token there and nowhere else.
    assert created["data"]["discovered_by_addon"] is True
    assert created["data"]["addon_url"] == "http://local-polygonal-zones:8000/zones.json"
    # Explicit, or the entry counts as legacy and exposes coordinates by default.
    assert created["data"]["expose_coordinates"] is False


async def test_a_second_discovery_rotates_the_token_and_keeps_the_user_settings(
    hass: HomeAssistant,
) -> None:
    """The add-on re-posts on every start with a fresh token. That must update
    the address and token, and leave the trackers and choices alone."""
    entry = await _create(hass, _info())
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            "entities": ["device_tracker.phone"],
            "download_zones": True,
            "allow_private_urls": False,
            "home_zone_id": "Home",
        },
    )

    second = await _start(hass, _info(config={"token": "rotated"}))

    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "already_configured"
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.data["zone_source_token"] == "rotated"
    assert updated.data["entities"] == ["device_tracker.phone"]
    assert updated.data["download_zones"] is True
    assert updated.data["allow_private_urls"] is False
    assert updated.data["home_zone_id"] == "Home"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize("missing", ["host"])
async def test_a_malformed_discovery_aborts_cleanly(hass: HomeAssistant, missing: str) -> None:
    info = _info()
    payload = dict(info.config)
    del payload[missing]
    broken = HassioServiceInfo(
        config=payload, name="Polygonal Zones", slug="local_polygonal_zones", uuid="x"
    )

    result = await _start(hass, broken)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_an_entry_already_pointing_at_the_addon_is_not_duplicated(
    hass: HomeAssistant,
) -> None:
    """A hand-configured entry with the same URL must not get a twin."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(
        domain=DOMAIN,
        entry_id="manual",
        data={
            "zone_urls": ["http://local-polygonal-zones:8000/zones.json"],
            "entities": [],
        },
    ).add_to_hass(hass)

    result = await _start(hass, _info())

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reconfigure_keeps_the_token_trust(hass: HomeAssistant) -> None:
    """Reconfigure rebuilds the data from the form, which cannot carry the
    discovery flag. Losing it stopped the token being sent to the app's
    hostname, so every zone load was refused with 403."""
    entry = await _create(hass, _info())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
        data=None,
    )
    assert result["type"] == FlowResultType.FORM
    assert "consent" in {str(k) for k in result["data_schema"].schema}
    submitted = {
        key: value
        for key, value in entry.data.items()
        if key not in ("addon_url", "consent_confirmed_at", "discovered_by_addon")
    }
    submitted["entities"] = ["device_tracker.phone"]
    done = await hass.config_entries.flow.async_configure(result["flow_id"], submitted)
    assert done["type"] == FlowResultType.FORM  # the consent step
    assert done["errors"] == {"consent": "consent_required"}
    done = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**submitted, "consent": True}
    )
    assert done["type"] == FlowResultType.ABORT

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.data["discovered_by_addon"] is True
    assert updated.data["addon_url"] == "http://local-polygonal-zones:8000/zones.json"
    assert updated.data["entities"] == ["device_tracker.phone"]

    # Adding another tracker with consent ticked on the first submit succeeds immediately.
    second = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
        data=None,
    )
    done = await hass.config_entries.flow.async_configure(
        second["flow_id"],
        {
            **submitted,
            "entities": ["device_tracker.phone", "device_tracker.tablet"],
            "consent": True,
        },
    )
    assert done["type"] == FlowResultType.ABORT
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.data["entities"] == ["device_tracker.phone", "device_tracker.tablet"]


async def test_a_pending_discovery_card_is_replaced_when_the_addon_restarts(
    hass: HomeAssistant,
) -> None:
    """If the add-on restarts before the user confirms the Discovered card,
    confirming the pending card must store the new token and address."""
    await _start(hass, _info(config={"token": "token-a"}))
    second = await _start(hass, _info(config={"host": "172.30.32.2", "token": "token-b"}))

    assert second["type"] == FlowResultType.FORM
    progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["flow_id"] for flow in progress] == [second["flow_id"]]

    created = await hass.config_entries.flow.async_configure(second["flow_id"], {})
    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["data"]["zone_source_token"] == "token-b"
    assert created["data"]["zone_urls"] == ["http://172.30.32.2:8000/zones.json"]
    assert created["data"]["addon_url"] == "http://172.30.32.2:8000/zones.json"


async def test_reconfigure_extra_url_survives_rediscovery_and_receives_no_token(
    hass: HomeAssistant,
) -> None:
    """A second URL added through Reconfigure survives rediscovery, and the
    add-on token is sent only to the URL the add-on announced."""
    from unittest.mock import MagicMock

    from custom_components.polygonal_zones import _build_zone_source

    entry = await _create(hass, _info())
    extra_url = "https://example.org/z.json"

    with patch(
        "custom_components.polygonal_zones.config_flow.validate_zone_urls",
        new=AsyncMock(return_value={}),
    ):
        reconf = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=None,
        )
        submitted = {
            key: value
            for key, value in entry.data.items()
            if key not in ("addon_url", "consent_confirmed_at", "discovered_by_addon")
        }
        submitted["zone_urls"] = [entry.data["addon_url"], extra_url]
        done = await hass.config_entries.flow.async_configure(reconf["flow_id"], submitted)
        assert done["type"] == FlowResultType.ABORT

    await _start(hass, _info(config={"host": "172.30.32.2", "token": "rotated"}))
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    new_addon_url = "http://172.30.32.2:8000/zones.json"
    assert updated.data["zone_urls"] == [new_addon_url, extra_url]
    assert updated.data["addon_url"] == new_addon_url

    calls: dict[str, dict | None] = {}

    class _FakeResp:
        status = 200
        content_length = 43
        charset = "utf-8"

        def raise_for_status(self) -> None:
            return None

        @property
        def content(self):
            async def _iter(_n: int):
                yield b'{"type":"FeatureCollection","features":[]}'

            return MagicMock(iter_chunked=_iter)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _FakeSession:
        def get(self, uri: str, **kwargs):
            calls[uri] = kwargs.get("headers")
            return _FakeResp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    source = _build_zone_source(updated)
    with (
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.ClientSession",
            return_value=_FakeSession(),
        ),
        patch(
            "custom_components.polygonal_zones.utils.general._PublicOnlyResolver",
            return_value=MagicMock(),
        ),
    ):
        await source.async_reload(hass)

    assert calls == {
        new_addon_url: {"X-Save-Token": "rotated"},
        extra_url: None,
    }
