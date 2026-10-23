"""The service schemas match services.yaml and refuse what the handlers cannot take.

The real-hass suite also calls the services, but it is not a required check; this one
runs in every job, so dropping or loosening a schema cannot merge green.
"""

from pathlib import Path

import pytest
import yaml

from custom_components.polygonal_zones.services import schemas
from custom_components.polygonal_zones.services.schemas import SERVICE_SCHEMAS

_YAML = yaml.safe_load(
    (Path(__file__).parent.parent / "custom_components/polygonal_zones/services.yaml").read_text()
)


def _documented(name: str) -> dict:
    return {f: "device-1" if f == "device_id" else "x" for f in _YAML[name]["fields"]}


@pytest.mark.parametrize("name", SERVICE_SCHEMAS)
def test_schema_accepts_the_documented_fields(name: str) -> None:
    fields = _YAML[name]["fields"]
    assert all(spec.get("required") for spec in fields.values())
    assert SERVICE_SCHEMAS[name](_documented(name)) == _documented(name)


def test_every_documented_service_has_a_schema() -> None:
    editing = {name for name, spec in _YAML.items() if "fields" in spec}
    assert editing == set(SERVICE_SCHEMAS)


@pytest.mark.parametrize("name", SERVICE_SCHEMAS)
def test_schema_refuses_a_missing_extra_empty_or_structured_value(name: str) -> None:
    schema = SERVICE_SCHEMAS[name]
    for field in _YAML[name]["fields"]:
        missing = _documented(name)
        del missing[field]
        with pytest.raises(schemas.vol.Invalid):
            schema(missing)
    with pytest.raises(schemas.vol.Invalid):
        schema({**_documented(name), "entity_id": "device_tracker.x"})
    for field in set(_YAML[name]["fields"]) - {"device_id"}:
        for bad in ("", {"type": "Feature"}):
            with pytest.raises(schemas.vol.Invalid):
                schema({**_documented(name), field: bad})


def test_device_id_may_be_a_list() -> None:
    assert SERVICE_SCHEMAS["delete_zone"]({"device_id": ["a", "b"], "zone_name": "x"})
