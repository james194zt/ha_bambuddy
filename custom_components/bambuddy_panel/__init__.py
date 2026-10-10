"""Bambuddy Panel: shows the Bambuddy web app as a Home Assistant sidebar panel."""

from __future__ import annotations

from pathlib import Path
import secrets

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from .const import (
    CONF_ICON,
    CONF_TITLE,
    CONF_URL,
    COOKIE_NAME,
    DEFAULT_ICON,
    DEFAULT_TITLE,
    DEFAULT_URL,
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_URL_PATH,
    PROXY_PATH,
    STATIC_PATH,
)
from . import services
from .proxy import BambuddyProxy
from .views import BambuddyProxyView, BambuddySessionView, PanelRuntime, SessionSigner

_HTTP_REGISTERED = f"{DOMAIN}_http_registered"


async def _async_secret(hass: HomeAssistant) -> str:
    """Cookie signing key, kept in .storage so sessions survive restarts."""
    store: Store[dict[str, str]] = Store(hass, 1, f"{DOMAIN}.secret")
    data = await store.async_load()
    if not data or "secret" not in data:
        data = {"secret": secrets.token_hex(32)}
        await store.async_save(data)
    return data["secret"]


async def _async_register_http(hass: HomeAssistant) -> None:
    """Views and static files can't be unregistered, so add them once per run."""
    if hass.data.get(_HTTP_REGISTERED):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_PATH, str(Path(__file__).parent / "www"), False)]
    )
    hass.http.register_view(BambuddySessionView(hass))
    hass.http.register_view(BambuddyProxyView(hass))
    hass.data[_HTTP_REGISTERED] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start the proxy and register the sidebar panel."""
    conf = {**entry.data, **entry.options}
    version = (await async_get_integration(hass, DOMAIN)).version

    proxy = BambuddyProxy(
        conf.get(CONF_URL, DEFAULT_URL),
        PROXY_PATH,
        f"{STATIC_PATH}/shim.js?v={version}",
        COOKIE_NAME,
    )
    await proxy.start()
    hass.data[DOMAIN] = PanelRuntime(proxy, SessionSigner(await _async_secret(hass)))
    await _async_register_http(hass)

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=conf.get(CONF_TITLE, DEFAULT_TITLE),
        sidebar_icon=conf.get(CONF_ICON, DEFAULT_ICON),
        module_url=f"{STATIC_PATH}/panel.js?v={version}",
        require_admin=False,
    )
    services.async_register(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel and stop the proxy."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    services.async_unregister(hass)
    runtime: PanelRuntime | None = hass.data.pop(DOMAIN, None)
    if runtime is not None:
        await runtime.proxy.stop()
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
