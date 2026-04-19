"""Tests for services.__init__.register_services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.polygonal_zones.services import register_services


async def test_register_services_loads_each_module_and_registers() -> None:
    """Each named service module is imported and its action_builder result is registered."""
    register_mock = MagicMock()
    hass = SimpleNamespace(
        services=SimpleNamespace(async_register=register_mock),
        async_add_executor_job=AsyncMock(side_effect=lambda fn, *a: fn(*a)),
    )

    await register_services(hass, ["add_new_zone"])

    assert register_mock.call_count == 1
    domain, name, callback = register_mock.call_args.args
    assert domain == "polygonal_zones"
    assert name == "add_new_zone"
    assert callable(callback)
