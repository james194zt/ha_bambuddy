"""Bambuddy Panel set up in a real (test) Home Assistant."""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bambuddy_panel.const import (
    COOKIE_NAME,
    DOMAIN,
    PANEL_URL_PATH,
    PROXY_PATH,
    SESSION_PATH,
)


async def _setup(hass: HomeAssistant, url: str) -> MockConfigEntry:
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bambuddy",
        data={"url": url, "title": "Bambuddy", "icon": "mdi:printer-3d"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_panel_registered(hass, bambuddy) -> None:
    await _setup(hass, bambuddy[0])
    panel = hass.data["frontend_panels"][PANEL_URL_PATH]
    custom = panel.config["_panel_custom"]
    assert custom["name"] == "bambuddy-panel"
    assert custom["module_url"].startswith("/bambuddy_panel_static/panel.js?v=")
    assert panel.sidebar_title == "Bambuddy"


async def test_brand_icon(hass, bambuddy, hass_client) -> None:
    """HA serves the integration icon from custom_components/.../brand/."""
    await _setup(hass, bambuddy[0])
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    icon = Path(__file__).parents[1] / "custom_components" / DOMAIN / "brand" / "icon.png"
    for image in ("icon.png", "dark_icon.png", "logo.png"):
        resp = await client.get(f"/api/brands/integration/{DOMAIN}/{image}")
        assert resp.status == 200, image
        assert await resp.read() == icon.read_bytes(), image


async def test_proxy_needs_session(hass, bambuddy, hass_client_no_auth) -> None:
    await _setup(hass, bambuddy[0])
    client = await hass_client_no_auth()
    resp = await client.get(PROXY_PATH + "/")
    assert resp.status == 401
    client.session.cookie_jar.update_cookies({COOKIE_NAME: "123.abc.forged"})
    resp = await client.get(PROXY_PATH + "/")
    assert resp.status == 401
    # The session endpoint itself needs a Home Assistant login.
    resp = await client.post(SESSION_PATH)
    assert resp.status == 401


async def test_proxy_end_to_end(hass, bambuddy, hass_client) -> None:
    url, seen = bambuddy
    await _setup(hass, url)
    client = await hass_client()

    resp = await client.post(SESSION_PATH)
    assert resp.status == 200
    assert (await resp.json())["url"] == PROXY_PATH + "/"

    resp = await client.get(PROXY_PATH)
    assert resp.status == 200  # redirected to PROXY_PATH + "/"

    resp = await client.get(PROXY_PATH + "/")
    html = await resp.text()
    assert f'src="{PROXY_PATH}/assets/index-abc.js"' in html
    assert f'href="{PROXY_PATH}/assets/index-abc.css"' in html
    assert "/bambuddy_panel_static/shim.js" in html
    assert "sw-register" not in html
    assert "frame-ancestors" not in resp.headers.get("Content-Security-Policy", "")
    assert resp.headers.get("X-Frame-Options", "SAMEORIGIN") == "SAMEORIGIN"
    # Our session cookie is not forwarded to Bambuddy.
    assert COOKIE_NAME not in seen["index_headers"].get("Cookie", "")

    resp = await client.get(PROXY_PATH + "/assets/index-abc.js")
    assert "basename:e=(window.__BB_BASE__||`/`)" in await resp.text()
    resp = await client.get(PROXY_PATH + "/assets/index-abc.css")
    assert f"url({PROXY_PATH}/fonts/inter-latin.woff2)" in await resp.text()

    resp = await client.get(PROXY_PATH + "/api/v1/printers/")
    assert (await resp.json())[0]["name"] == "My Printer"

    resp = await client.get(PROXY_PATH + "/old", allow_redirects=False)
    assert resp.status == 302
    assert resp.headers["Location"] == PROXY_PATH + "/setup"

    resp = await client.get(PROXY_PATH + "/api/v1/printers/2/camera/stream")
    body = await resp.read()
    assert b"frame0" in body and b"frame2" in body

    async with client.ws_connect(PROXY_PATH + "/api/v1/ws") as ws:
        await ws.send_str("hi")
        assert (await ws.receive_str()) == "echo:hi"

    resp = await client.get("/bambuddy_panel_static/shim.js")
    assert resp.status == 200


async def test_unload(hass, bambuddy, hass_client) -> None:
    entry = await _setup(hass, bambuddy[0])
    client = await hass_client()
    await client.post(SESSION_PATH)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_URL_PATH not in hass.data["frontend_panels"]
    resp = await client.get(PROXY_PATH + "/")
    assert resp.status == 404
    # Reload works (views/static paths are only registered once).
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_URL_PATH in hass.data["frontend_panels"]
