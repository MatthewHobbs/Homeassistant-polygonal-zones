"""General helper functions for the polygonal_zones integration."""

import aiohttp

from homeassistant.core import Event, HomeAssistant, State


async def load_data(uri: str, hass: HomeAssistant) -> str:
    """Load the data from either a file or website.

    Args:
        uri: The link/path to the file to load.
        hass: The homeassistant instance.

    Returns:
        the content of the file or an error if it cant be found/reached.

    """
    if uri.startswith(("http", "https")):
        async with aiohttp.ClientSession() as session, session.get(uri) as response:
            return await response.text()
    else:
        config_dir = hass.config.config_dir
        file = await hass.async_add_executor_job(open, f"{config_dir}/{uri}", "r")
        data = file.read()
        file.close()
        return data


REQUIRED_ATTRIBUTES = {"latitude", "longitude", "gps_accuracy"}


def event_should_trigger(event: Event, entity_id: str) -> bool:
    """Decide if the event should trigger the sensor.

    Args:
        event: The event to check.
        entity_id: The entity id to check.

    Returns:
        True if the event should trigger the sensor, False otherwise.

    """
    if event.data.get("entity_id") != entity_id:
        return False

    old_state: State | None = event.data.get("old_state")
    new_state: State | None = event.data.get("new_state")

    if not (old_state and new_state):
        return False
    if not all(attr in new_state.attributes for attr in REQUIRED_ATTRIBUTES):
        return False
    # the old state is none when it is the first update of the entity
    if not all(attr in old_state.attributes for attr in REQUIRED_ATTRIBUTES):
        return True

    # Check if any location attributes changed
    return any(
        new_state.attributes[attr] != old_state.attributes[attr]
        for attr in REQUIRED_ATTRIBUTES
    )
