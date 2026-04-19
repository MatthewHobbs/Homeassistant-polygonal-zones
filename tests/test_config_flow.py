"""Tests for the ConfigFlow / OptionsFlowHandler classes."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.polygonal_zones.config_flow import (
    ConfigFlow,
    OptionsFlowHandler,
    build_create_flow,
    build_options_flow,
)


def _hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


def test_build_create_flow_has_all_required_keys() -> None:
    schema = build_create_flow()
    keys = {str(k) for k in schema.schema}
    assert "zone_urls" in keys
    assert "entities" in keys


def test_build_create_flow_download_zones_defaults_true_for_new_entries() -> None:
    """New installs default download_zones to True so mutation services work out of the box."""
    schema = build_create_flow()
    download_key = next(k for k in schema.schema if str(k) == "download_zones")
    assert download_key.default() is True


def test_build_create_flow_preserves_existing_download_zones_false() -> None:
    """A reconfigure flow on an entry with download_zones=False preserves that choice."""
    schema = build_create_flow({"download_zones": False})
    download_key = next(k for k in schema.schema if str(k) == "download_zones")
    assert download_key.default() is False


def test_build_options_flow_has_zone_urls_and_priority() -> None:
    schema = build_options_flow()
    keys = {str(k) for k in schema.schema}
    assert "zone_urls" in keys
    assert "prioritize_zone_files" in keys


async def test_config_flow_first_step_renders_form(tmp_path) -> None:
    flow = ConfigFlow()
    flow.hass = _hass(tmp_path)
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    result = await flow.async_step_user(None)
    assert result == {"type": "form"}
    flow.async_create_entry.assert_not_called()


async def test_config_flow_invalid_url_renders_form_with_errors(tmp_path) -> None:
    flow = ConfigFlow()
    flow.hass = _hass(tmp_path)
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    result = await flow.async_step_user({"zone_urls": ["ftp://nope"], "entities": []})
    assert result == {"type": "form"}
    args = flow.async_show_form.call_args.kwargs
    assert args["errors"] == {"zone_urls": "invalid_url"}


async def test_config_flow_valid_input_creates_entry(tmp_path) -> None:
    flow = ConfigFlow()
    flow.hass = _hass(tmp_path)
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    result = await flow.async_step_user(
        {"zone_urls": ["https://example.com/x.json"], "entities": ["device_tracker.x"]}
    )

    assert result == {"type": "create_entry"}
    flow.async_create_entry.assert_called_once()


async def test_options_flow_invalid_url_renders_form(tmp_path) -> None:
    flow = OptionsFlowHandler()
    flow.hass = _hass(tmp_path)
    fake_entry = SimpleNamespace(data={"zone_urls": [], "entities": []})

    with patch.object(OptionsFlowHandler, "config_entry", new=fake_entry, create=True):
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        result = await flow.async_step_init({"zone_urls": ["ftp://nope"]})
        assert result == {"type": "form"}


async def test_options_flow_valid_input_merges_data(tmp_path) -> None:
    """Successful options save merges into entry.data instead of replacing it."""
    flow = OptionsFlowHandler()
    flow.hass = _hass(tmp_path)
    update_mock = MagicMock()
    flow.hass.config_entries = SimpleNamespace(async_update_entry=update_mock)
    fake_entry = SimpleNamespace(
        data={
            "zone_urls": ["https://old"],
            "entities": ["device_tracker.alice"],
            "download_zones": True,
        }
    )

    with patch.object(OptionsFlowHandler, "config_entry", new=fake_entry, create=True):
        flow.async_create_entry = MagicMock(return_value={"type": "options"})
        result = await flow.async_step_init(
            {"zone_urls": ["https://new"], "prioritize_zone_files": True}
        )

    assert result == {"type": "options"}
    update_mock.assert_called_once()
    merged = update_mock.call_args.kwargs["data"]
    # User-supplied keys override; CONF_ENTITIES from existing data is preserved
    assert merged["zone_urls"] == ["https://new"]
    assert merged["prioritize_zone_files"] is True
    assert merged["entities"] == ["device_tracker.alice"]
    assert merged["download_zones"] is True


async def test_reconfigure_flow_first_render_uses_entry_defaults(tmp_path) -> None:
    """The reconfigure step on initial render shows the form with current entry data."""
    flow = ConfigFlow()
    flow.hass = _hass(tmp_path)
    fake_entry = SimpleNamespace(
        data={
            "zone_urls": ["https://existing"],
            "entities": ["device_tracker.alice"],
            "prioritize_zone_files": False,
        }
    )
    flow._get_reconfigure_entry = MagicMock(return_value=fake_entry)
    flow.async_show_form = MagicMock(return_value={"type": "form"})

    result = await flow.async_step_reconfigure(None)
    assert result == {"type": "form"}
    flow.async_show_form.assert_called_once()


async def test_reconfigure_flow_invalid_url_renders_form_with_errors(tmp_path) -> None:
    flow = ConfigFlow()
    flow.hass = _hass(tmp_path)
    flow._get_reconfigure_entry = MagicMock(return_value=SimpleNamespace(data={}))
    flow.async_show_form = MagicMock(return_value={"type": "form"})

    result = await flow.async_step_reconfigure({"zone_urls": ["ftp://nope"], "entities": []})
    assert result == {"type": "form"}
    args = flow.async_show_form.call_args.kwargs
    assert args["errors"] == {"zone_urls": "invalid_url"}


async def test_reconfigure_flow_valid_input_calls_update_reload_and_abort(tmp_path) -> None:
    flow = ConfigFlow()
    flow.hass = _hass(tmp_path)
    fake_entry = SimpleNamespace(data={"zone_urls": [], "entities": []})
    flow._get_reconfigure_entry = MagicMock(return_value=fake_entry)
    flow.async_update_reload_and_abort = MagicMock(return_value={"type": "reload"})

    result = await flow.async_step_reconfigure(
        {
            "zone_urls": ["https://example.com/x.json"],
            "entities": ["device_tracker.bob"],
        }
    )
    assert result == {"type": "reload"}
    flow.async_update_reload_and_abort.assert_called_once()
