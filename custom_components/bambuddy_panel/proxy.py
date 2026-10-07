"""Reverse proxy that serves Bambuddy under a sub-path of Home Assistant.

Bambuddy expects to live at the root of its own host: it uses absolute paths
(``/assets/...``, ``/api/v1/...``, ``/fonts/...``) and a router without a base
path. It also refuses to be framed (``X-Frame-Options`` / ``frame-ancestors``).
To show it inside a Home Assistant panel this proxy:

* forwards HTTP, streams and websockets to Bambuddy;
* drops the framing restrictions;
* rewrites absolute paths in HTML and CSS, and gives the router a base path;
* injects ``shim.js``, which prefixes URLs the app builds at runtime;
* gzips the rewritten text (Bambuddy's 10 MB bundle is sent uncompressed,
  which hurts over remote access).

This module has no Home Assistant imports so it can be exercised on its own.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import gzip
import logging
import re
from urllib.parse import urlsplit

import aiohttp
from aiohttp import WSMsgType, web
from multidict import CIMultiDict

_LOGGER = logging.getLogger(__name__)

# Hop-by-hop headers (RFC 7230 6.1) plus ones aiohttp sets itself.
_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
_REQUEST_DROP = _HOP_HEADERS | {"cookie", "authorization", "referer", "accept-encoding"}
_WS_HANDSHAKE = {
    "sec-websocket-key",
    "sec-websocket-version",
    "sec-websocket-extensions",
    "sec-websocket-protocol",
    "sec-websocket-accept",
}

_HTML_ATTR = re.compile(r"""(\s(?:src|href)=["'])/(?!/)""")
_SW_REGISTER = re.compile(r"<script[^>]*sw-register\.js[^>]*>\s*</script>\s*", re.I)
_HEAD = re.compile(r"<head[^>]*>", re.I)
_CSS_URL = re.compile(r"""url\((["']?)/(?!/)""")
# React Router's <Router basename="/"> default (minified). The shim sets
# window.__BB_BASE__ so the router works under the proxy path.
_ROUTER_BASENAME = re.compile(r"basename:(\w+)=`/`,children:(\w+)=null,location:")

_CACHE_SIZE = 8


def rewrite_html(text: str, prefix: str, shim_url: str) -> str:
    """Prefix absolute src/href, drop the service worker, inject the shim."""
    # A service worker registered from here would control Home Assistant's
    # whole origin, so Bambuddy's is never registered.
    text = _SW_REGISTER.sub("", text)
    text = _HTML_ATTR.sub(lambda m: m[1] + prefix + "/", text)
    tag = f'<script src="{shim_url}"></script>'
    text, found = _HEAD.subn(lambda m: m[0] + tag, text, count=1)
    return text if found else tag + text


def rewrite_css(text: str, prefix: str) -> str:
    """Prefix absolute url(...) references."""
    return _CSS_URL.sub(lambda m: f"url({m[1]}{prefix}/", text)


def rewrite_js(text: str) -> str:
    """Make React Router's default basename come from the shim."""
    return _ROUTER_BASENAME.sub(
        lambda m: f"basename:{m[1]}=(window.__BB_BASE__||`/`),children:{m[2]}=null,location:",
        text,
    )


def strip_frame_ancestors(csp: str) -> str:
    """Remove the frame-ancestors directive from a CSP header value."""
    directives = [d.strip() for d in csp.split(";")]
    return "; ".join(
        d for d in directives if d and not d.lower().startswith("frame-ancestors")
    )


def _rewrite_kind(content_type: str) -> str | None:
    ctype = content_type.split(";")[0].strip().lower()
    if ctype == "text/html":
        return "html"
    if ctype == "text/css":
        return "css"
    if ctype in ("application/javascript", "text/javascript"):
        return "js"
    return None


class BambuddyProxy:
    """Forwards requests under ``prefix`` to the Bambuddy server."""

    def __init__(
        self, upstream: str, prefix: str, shim_url: str, cookie_name: str
    ) -> None:
        parts = urlsplit(upstream)
        self._upstream = f"{parts.scheme}://{parts.netloc}"
        self._prefix = prefix
        self._shim_url = shim_url
        self._cookie_name = cookie_name
        self._session: aiohttp.ClientSession | None = None
        # Rewritten hashed assets (immutable), so the 10 MB bundle is only
        # rewritten and compressed once. Derived data; safe to lose.
        self._cache: OrderedDict[str, tuple[bytes, bytes, CIMultiDict]] = OrderedDict()

    async def start(self) -> None:
        """Open the upstream session."""
        # auto_decompress=False: binary bodies pass through untouched.
        self._session = aiohttp.ClientSession(
            auto_decompress=False,
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
        )

    async def stop(self) -> None:
        """Close the upstream session."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._cache.clear()

    async def handle(self, request: web.Request, path: str) -> web.StreamResponse:
        """Proxy ``request``; ``path`` is the upstream path + query string."""
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._handle_ws(request, path)
        return await self._handle_http(request, path)

    # -- headers -----------------------------------------------------------

    def _request_headers(self, request: web.Request, *, websocket: bool) -> dict:
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in _REQUEST_DROP
            and not (websocket and k.lower() in _WS_HANDSHAKE)
        }
        # Present requests as same-origin to Bambuddy (websocket/CSRF checks).
        if "Origin" in headers:
            headers["Origin"] = self._upstream
        # Text is rewritten here, so ask for it uncompressed (LAN hop).
        headers["Accept-Encoding"] = "identity"
        cookies = [
            f"{k}={v}" for k, v in request.cookies.items() if k != self._cookie_name
        ]
        if cookies:
            headers["Cookie"] = "; ".join(cookies)
        return headers

    def _location(self, value: str) -> str:
        if value.startswith(self._upstream):
            value = value[len(self._upstream) :] or "/"
        if value.startswith("/") and not value.startswith("//"):
            value = self._prefix + value
        return value

    def _response_headers(self, upstream: aiohttp.ClientResponse, *, rewritten: bool) -> CIMultiDict:
        headers: CIMultiDict = CIMultiDict()
        for key, value in upstream.headers.items():
            lower = key.lower()
            if lower in _HOP_HEADERS or lower == "x-frame-options":
                continue
            if rewritten and lower in ("content-encoding", "etag", "last-modified"):
                continue
            if lower == "content-security-policy":
                value = strip_frame_ancestors(value)
            elif lower == "location":
                value = self._location(value)
            headers.add(key, value)
        return headers

    # -- http --------------------------------------------------------------

    async def _handle_http(self, request: web.Request, path: str) -> web.StreamResponse:
        assert self._session is not None
        try:
            upstream = await self._session.request(
                request.method,
                self._upstream + path,
                headers=self._request_headers(request, websocket=False),
                data=request.content if request.body_exists else None,
                allow_redirects=False,
            )
        except aiohttp.ClientError as err:
            return web.Response(status=502, text=f"Bambuddy unreachable: {err}")

        async with upstream:
            kind = None
            if upstream.status == 200 and "Content-Encoding" not in upstream.headers:
                kind = _rewrite_kind(upstream.headers.get("Content-Type", ""))

            if kind is None:
                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=self._response_headers(upstream, rewritten=False),
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_any():
                    await response.write(chunk)
                await response.write_eof()
                return response

            cacheable = "/assets/" in path and request.method == "GET"
            cached = self._cache.get(path) if cacheable else None
            if cached is None:
                body = await upstream.read()
                cached = await asyncio.get_running_loop().run_in_executor(
                    None, self._rewrite, kind, body
                ) + (self._response_headers(upstream, rewritten=True),)
                if cacheable:
                    self._cache[path] = cached
                    while len(self._cache) > _CACHE_SIZE:
                        self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(path)

        raw, gz, headers = cached
        headers = CIMultiDict(headers)
        headers["Vary"] = "Accept-Encoding"
        if "gzip" in request.headers.get("Accept-Encoding", ""):
            headers["Content-Encoding"] = "gzip"
            return web.Response(status=200, body=gz, headers=headers)
        return web.Response(status=200, body=raw, headers=headers)

    def _rewrite(self, kind: str, body: bytes) -> tuple[bytes, bytes]:
        """Rewrite and gzip a text body (runs in an executor)."""
        text = body.decode("utf-8", "surrogateescape")
        if kind == "html":
            text = rewrite_html(text, self._prefix, self._shim_url)
        elif kind == "css":
            text = rewrite_css(text, self._prefix)
        else:
            text = rewrite_js(text)
        raw = text.encode("utf-8", "surrogateescape")
        return raw, gzip.compress(raw, 6)

    # -- websocket ---------------------------------------------------------

    async def _handle_ws(self, request: web.Request, path: str) -> web.StreamResponse:
        assert self._session is not None
        protocols = [
            p.strip()
            for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
            if p.strip()
        ]
        url = "ws" + self._upstream[len("http") :] + path
        try:
            upstream = await self._session.ws_connect(
                url,
                headers=self._request_headers(request, websocket=True),
                protocols=protocols,
            )
        except aiohttp.ClientError as err:
            return web.Response(status=502, text=f"Bambuddy unreachable: {err}")

        client = web.WebSocketResponse(
            protocols=[upstream.protocol] if upstream.protocol else ()
        )
        await client.prepare(request)

        async def pump(src, dst) -> None:
            async for msg in src:
                if msg.type == WSMsgType.TEXT:
                    await dst.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await dst.send_bytes(msg.data)
                else:
                    break

        tasks = [
            asyncio.create_task(pump(client, upstream)),
            asyncio.create_task(pump(upstream, client)),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await upstream.close()
            await client.close()
        return client
