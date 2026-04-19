"""Tests for services.__init__.register_services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.polygonal_zones.services import register_services


async def test_register_services_loads_each_module_and_registers() -> None:
    """Each named service module is imported and its action_builder result is registered."""
    register_mock = MagicMock()
    admin_register_mock = MagicMock()
    hass = SimpleNamespace(
        services=SimpleNamespace(async_register=register_mock),
        async_add_executor_job=AsyncMock(side_effect=lambda fn, *a: fn(*a)),
    )

    with patch(
        "custom_components.polygonal_zones.services.async_register_admin_service",
        admin_register_mock,
    ):
        await register_services(hass, ["add_new_zone"])

    assert register_mock.call_count == 1
    assert admin_register_mock.call_count == 0
    domain, name, callback = register_mock.call_args.args
    assert domain == "polygonal_zones"
    assert name == "add_new_zone"
    assert callable(callback)


async def test_register_services_admin_uses_admin_register() -> None:
    """``admin=True`` routes every registration through async_register_admin_service."""
    register_mock = MagicMock()
    admin_register_mock = MagicMock()
    hass = SimpleNamespace(
        services=SimpleNamespace(async_register=register_mock),
        async_add_executor_job=AsyncMock(side_effect=lambda fn, *a: fn(*a)),
    )

    with patch(
        "custom_components.polygonal_zones.services.async_register_admin_service",
        admin_register_mock,
    ):
        await register_services(hass, ["add_new_zone", "edit_zone"], admin=True)

    assert register_mock.call_count == 0
    assert admin_register_mock.call_count == 2
    registered_names = {call.args[2] for call in admin_register_mock.call_args_list}
    assert registered_names == {"add_new_zone", "edit_zone"}
