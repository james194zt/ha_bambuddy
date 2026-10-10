"""``bambuddy_panel.notify``: forwards Bambuddy notifications to phones.

Bambuddy's Home Assistant notification provider calls this service. It sends
the notification to the notify services chosen in the integration's options,
with two changes that make it work away from home:

* the camera snapshot link (built from Bambuddy's LAN "External URL") is
  rewritten to a relative path through the proxy; the Companion app fetches
  relative links from Home Assistant with the user's login;
* tapping the notification opens the Bambuddy panel.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_NOTIFY_TARGETS,
    DOMAIN,
    PANEL_URL_PATH,
    PHOTO_PATH,
    PROXY_PATH,
    SERVICE_NOTIFY,
)

NOTIFY_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional("data"): dict,
    }
)


def rewrite_image(image: str) -> str:
    """Point a Bambuddy snapshot link at the proxy (relative, HA-authenticated)."""
    parts = urlsplit(image)
    if parts.path.startswith(PHOTO_PATH):
        return PROXY_PATH + parts.path
    return image


def build_data(data: dict | None) -> dict:
    """Service data for each notify target."""
    data = dict(data or {})
    if isinstance(data.get("image"), str):
        data["image"] = rewrite_image(data["image"])
    panel = "/" + PANEL_URL_PATH
    data.setdefault("clickAction", panel)  # Android
    data.setdefault("url", panel)  # iOS
    data.setdefault("group", "bambuddy")
    return data


def async_register(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the notify service for the loaded entry."""

    async def handle(call: ServiceCall) -> None:
        targets = {**entry.data, **entry.options}.get(CONF_NOTIFY_TARGETS) or []
        if not targets:
            raise ServiceValidationError(
                "No phones selected: open Bambuddy Panel → Configure and pick notify targets."
            )
        payload = {"message": call.data["message"], "data": build_data(call.data.get("data"))}
        if "title" in call.data:
            payload["title"] = call.data["title"]
        for target in targets:
            domain, service = target.split(".", 1)
            await hass.services.async_call(domain, service, payload, blocking=True)

    hass.services.async_register(DOMAIN, SERVICE_NOTIFY, handle, schema=NOTIFY_SCHEMA)


def async_unregister(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_NOTIFY)
