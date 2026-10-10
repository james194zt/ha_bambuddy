"""Home Assistant HTTP views: session cookie and the Bambuddy proxy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import time

from aiohttp import web

from homeassistant.components.http import (
    KEY_AUTHENTICATED,
    KEY_HASS_USER,
    HomeAssistantView,
)
from homeassistant.core import HomeAssistant

from .const import COOKIE_NAME, DOMAIN, PROXY_PATH, SESSION_PATH, SESSION_TTL
from .proxy import BambuddyProxy


class SessionSigner:
    """Issues and checks ``<expiry>.<user id>.<hmac>`` session tokens."""

    def __init__(self, secret: str) -> None:
        self._key = bytes.fromhex(secret)

    def _sig(self, payload: str) -> str:
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()

    def issue(self, user_id: str) -> str:
        payload = f"{int(time.time()) + SESSION_TTL}.{user_id}"
        return f"{payload}.{self._sig(payload)}"

    def verify(self, token: str) -> str | None:
        """Return the user id if the token is valid and unexpired."""
        try:
            expiry, user_id, sig = token.split(".")
            if int(expiry) < time.time():
                return None
        except ValueError:
            return None
        if not hmac.compare_digest(sig, self._sig(f"{expiry}.{user_id}")):
            return None
        return user_id


@dataclass
class PanelRuntime:
    """Live objects for the loaded config entry (in hass.data[DOMAIN])."""

    proxy: BambuddyProxy
    signer: SessionSigner


class BambuddySessionView(HomeAssistantView):
    """Swap the caller's Home Assistant login for a proxy cookie."""

    url = SESSION_PATH
    name = "api:bambuddy_panel:session"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        runtime: PanelRuntime | None = self.hass.data.get(DOMAIN)
        if runtime is None:
            return self.json_message("Bambuddy Panel is not loaded", 404)
        user = request[KEY_HASS_USER]
        response = self.json({"url": PROXY_PATH + "/"})
        response.set_cookie(
            COOKIE_NAME,
            runtime.signer.issue(user.id),
            path=PROXY_PATH,
            max_age=SESSION_TTL,
            httponly=True,
            samesite="Strict",
            secure=request.secure,
        )
        return response


class BambuddyProxyView(HomeAssistantView):
    """Bambuddy, served through Home Assistant (HA login or session cookie)."""

    url = PROXY_PATH + "/{path:.*}"
    extra_urls = [PROXY_PATH]
    name = "api:bambuddy_panel:proxy"
    # Iframe requests can't send the bearer token, so auth is checked in
    # _handle: the session cookie, or a normal Home Assistant login (e.g. the
    # Companion app fetching a notification snapshot).
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def _user(self, request: web.Request, runtime: PanelRuntime):
        if request.get(KEY_AUTHENTICATED):
            return request.get(KEY_HASS_USER)
        user_id = runtime.signer.verify(request.cookies.get(COOKIE_NAME, ""))
        return await self.hass.auth.async_get_user(user_id) if user_id else None

    async def _handle(self, request: web.Request, path: str = "") -> web.StreamResponse:
        runtime: PanelRuntime | None = self.hass.data.get(DOMAIN)
        if runtime is None:
            return web.Response(status=404, text="Bambuddy Panel is not loaded")
        user = await self._user(request, runtime)
        if user is None or not user.is_active:
            return web.Response(
                status=401, text="Open Bambuddy from the Home Assistant sidebar."
            )

        upstream_path = request.raw_path[len(PROXY_PATH) :]
        if not upstream_path or upstream_path.startswith("?"):
            return web.Response(
                status=302, headers={"Location": PROXY_PATH + "/" + upstream_path}
            )
        return await runtime.proxy.handle(request, upstream_path)

    get = post = put = patch = delete = head = options = _handle
