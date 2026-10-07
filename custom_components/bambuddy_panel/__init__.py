"""Bambuddy Panel: shows the Bambuddy web app as a Home Assistant sidebar panel."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from homeassistant.components import frontend
from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CONF_ICON,
    CONF_PROXY_PORT,
    CONF_TITLE,
    CONF_URL,
    DEFAULT_ICON,
    DEFAULT_PROXY_PORT,
    DEFAULT_TITLE,
    DEFAULT_URL,
    PANEL_URL_PATH,
)
from .proxy import BambuddyProxy

_LOGGER = logging.getLogger(__name__)


async def _ha_host(hass: HomeAssistant) -> str:
    """Host name/IP that browsers on the LAN use to reach Home Assistant."""
    try:
        host = urlsplit(get_url(hass, allow_external=False)).hostname
        if host:
            return host
    except NoURLAvailableError:
        pass
    return await async_get_source_ip(hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start the proxy (if enabled) and register the sidebar panel."""
    conf = {**entry.data, **entry.options}
    url = conf.get(CONF_URL, DEFAULT_URL)
    port = int(conf.get(CONF_PROXY_PORT, DEFAULT_PROXY_PORT))

    proxy = None
    panel_url = url
    if port:
        proxy = BambuddyProxy(url, port)
        try:
            await proxy.start()
        except OSError as err:
            raise ConfigEntryNotReady(f"Can't listen on port {port}: {err}") from err
        panel_url = f"http://{await _ha_host(hass)}:{port}/"
    entry.runtime_data = proxy

    frontend.async_register_built_in_panel(
        hass,
        "iframe",
        sidebar_title=conf.get(CONF_TITLE, DEFAULT_TITLE),
        sidebar_icon=conf.get(CONF_ICON, DEFAULT_ICON),
        frontend_url_path=PANEL_URL_PATH,
        config={"url": panel_url},
        require_admin=False,
    )
    _LOGGER.debug("Bambuddy panel registered for %s", panel_url)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel and stop the proxy."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    if entry.runtime_data is not None:
        await entry.runtime_data.stop()
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
