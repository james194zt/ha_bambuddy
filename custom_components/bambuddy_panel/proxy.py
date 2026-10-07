"""Tiny reverse proxy that lets Bambuddy be shown in an iframe.

Bambuddy sends ``X-Frame-Options: SAMEORIGIN`` and ``frame-ancestors 'none'``,
which stop browsers framing it inside Home Assistant. This proxy forwards
everything (HTTP, streams, websockets) to Bambuddy unchanged except for
dropping those two restrictions. It serves at the root path so Bambuddy's
absolute asset URLs keep working.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit

import aiohttp
from aiohttp import WSMsgType, web

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
_WS_HANDSHAKE_HEADERS = {
    "sec-websocket-key",
    "sec-websocket-version",
    "sec-websocket-extensions",
    "sec-websocket-protocol",
    "sec-websocket-accept",
}


def _strip_frame_ancestors(csp: str) -> str:
    """Remove the frame-ancestors directive from a CSP header value."""
    directives = [d.strip() for d in csp.split(";")]
    return "; ".join(
        d for d in directives if d and not d.lower().startswith("frame-ancestors")
    )


class BambuddyProxy:
    """Header-stripping reverse proxy bound to a local port."""

    def __init__(self, upstream: str, port: int) -> None:
        parts = urlsplit(upstream)
        self._upstream = f"{parts.scheme}://{parts.netloc}"
        self._port = port
        self._session: aiohttp.ClientSession | None = None
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        """Start listening."""
        # auto_decompress=False: pass compressed bodies through untouched.
        self._session = aiohttp.ClientSession(
            auto_decompress=False,
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
        )
        app = web.Application(client_max_size=1024**3)
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        try:
            await site.start()
        except OSError:
            await self.stop()
            raise
        _LOGGER.debug("Bambuddy proxy on :%s -> %s", self._port, self._upstream)

    async def stop(self) -> None:
        """Stop listening and close the upstream session."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _forward_headers(self, request: web.Request, *, websocket: bool) -> dict:
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in _HOP_HEADERS
            and not (websocket and k.lower() in _WS_HANDSHAKE_HEADERS)
        }
        # Present ourselves as same-origin to Bambuddy (websocket / CSRF checks).
        if "Origin" in headers:
            headers["Origin"] = self._upstream
        return headers

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._handle_ws(request)
        return await self._handle_http(request)

    async def _handle_http(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None
        try:
            upstream = await self._session.request(
                request.method,
                self._upstream + request.raw_path,
                headers=self._forward_headers(request, websocket=False),
                data=request.content if request.body_exists else None,
                allow_redirects=False,
            )
        except aiohttp.ClientError as err:
            return web.Response(status=502, text=f"Bambuddy unreachable: {err}")

        async with upstream:
            response = web.StreamResponse(status=upstream.status, reason=upstream.reason)
            for key, value in upstream.headers.items():
                lower = key.lower()
                if lower in _HOP_HEADERS or lower == "x-frame-options":
                    continue
                if lower == "content-security-policy":
                    value = _strip_frame_ancestors(value)
                elif lower == "location" and value.startswith(self._upstream):
                    value = value[len(self._upstream) :] or "/"
                response.headers.add(key, value)
            await response.prepare(request)
            async for chunk in upstream.content.iter_any():
                await response.write(chunk)
            await response.write_eof()
            return response

    async def _handle_ws(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None
        protocols = [
            p.strip()
            for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
            if p.strip()
        ]
        url = "ws" + self._upstream[len("http") :] + request.raw_path
        try:
            upstream = await self._session.ws_connect(
                url,
                headers=self._forward_headers(request, websocket=True),
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
