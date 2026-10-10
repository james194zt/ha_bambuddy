"""bambuddy_panel.notify and snapshot fetching with a normal HA login."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bambuddy_panel.const import DOMAIN, PROXY_PATH

PHOTO = "/api/v1/notifications/photos/print_complete_abc123.jpg"


async def _setup(hass: HomeAssistant, url: str, targets: list[str]) -> list[ServiceCall]:
    assert await async_setup_component(hass, "http", {})
    sent: list[ServiceCall] = []

    async def fake_push(call: ServiceCall) -> None:
        sent.append(call)

    hass.services.async_register("notify", "mobile_app_my_phone", fake_push)
    hass.services.async_register("notify", "mobile_app_my_tablet", fake_push)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": url, "title": "Bambuddy", "icon": "mdi:printer-3d"},
        options={
            "url": url,
            "title": "Bambuddy",
            "icon": "mdi:printer-3d",
            "notify_targets": targets,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return sent


async def test_notify_forwards_and_rewrites(hass, bambuddy) -> None:
    url, _ = bambuddy
    sent = await _setup(
        hass, url, ["notify.mobile_app_my_phone", "notify.mobile_app_my_tablet"]
    )
    # What Bambuddy's HA provider sends (image from its LAN External URL).
    await hass.services.async_call(
        DOMAIN,
        "notify",
        {
            "title": "Print complete",
            "message": "Benchy finished",
            "data": {"image": f"http://192.168.1.1:8000{PHOTO}", "priority": "high"},
        },
        blocking=True,
    )
    assert [c.service for c in sent] == ["mobile_app_my_phone", "mobile_app_my_tablet"]
    data = sent[0].data["data"]
    assert sent[0].data["title"] == "Print complete"
    assert sent[0].data["message"] == "Benchy finished"
    assert data["image"] == PROXY_PATH + PHOTO
    assert data["clickAction"] == "/bambuddy"
    assert data["url"] == "/bambuddy"
    assert data["priority"] == "high"


async def test_notify_without_image_or_title(hass, bambuddy) -> None:
    sent = await _setup(hass, bambuddy[0], ["notify.mobile_app_my_phone"])
    await hass.services.async_call(DOMAIN, "notify", {"message": "Hi"}, blocking=True)
    assert "title" not in sent[0].data
    assert "image" not in sent[0].data["data"]


async def test_notify_needs_targets(hass, bambuddy) -> None:
    await _setup(hass, bambuddy[0], [])
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "notify", {"message": "Hi"}, blocking=True)


async def test_snapshot_with_ha_login(hass, bambuddy, hass_client, hass_client_no_auth) -> None:
    """The Companion app fetches the rewritten link with its HA login (no cookie)."""
    await _setup(hass, bambuddy[0], ["notify.mobile_app_my_phone"])
    client = await hass_client()
    resp = await client.get(PROXY_PATH + PHOTO)
    assert resp.status == 200
    assert await resp.read() == b"\xff\xd8JPEG"
    anon = await hass_client_no_auth()
    assert (await anon.get(PROXY_PATH + PHOTO)).status == 401


async def test_service_removed_on_unload(hass, bambuddy) -> None:
    await _setup(hass, bambuddy[0], ["notify.mobile_app_my_phone"])
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert hass.services.has_service(DOMAIN, "notify")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service(DOMAIN, "notify")
