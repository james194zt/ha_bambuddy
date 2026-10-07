"""Fixtures: a fake Bambuddy server for the proxy to talk to."""

from __future__ import annotations

import asyncio

from aiohttp import WSMsgType, web
import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="manifest" href="/manifest.json" />
    <script type="module" crossorigin src="/assets/index-abc.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-abc.css">
  </head>
  <body>
    <div id="root"></div>
    <script src="/sw-register.js"></script>
  </body>
</html>"""
APP_JS = "function jr({basename:e=`/`,children:t=null,location:n,navigationType:r=`POP`}){}"
APP_CSS = "@font-face{src:url(/fonts/inter-latin.woff2)}"
CSP = "default-src 'self'; frame-src 'self' http: https:; frame-ancestors 'none';"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ from this repo."""
    yield


@pytest.fixture
async def bambuddy(socket_enabled):
    """Fake Bambuddy on a local port; yields (base URL, what it saw)."""
    seen: dict[str, object] = {}

    async def index(request: web.Request) -> web.Response:
        seen["index_headers"] = dict(request.headers)
        return web.Response(
            text=INDEX,
            content_type="text/html",
            headers={"X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": CSP},
        )

    async def js(request: web.Request) -> web.Response:
        return web.Response(text=APP_JS, content_type="application/javascript")

    async def css(request: web.Request) -> web.Response:
        return web.Response(text=APP_CSS, content_type="text/css")

    async def printers(request: web.Request) -> web.Response:
        seen["api_cookie"] = request.headers.get("Cookie")
        return web.json_response([{"name": "My Printer"}])

    async def redirect(request: web.Request) -> web.Response:
        return web.Response(status=302, headers={"Location": "/setup"})

    async def stream(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"})
        await resp.prepare(request)
        for i in range(3):
            await resp.write(f"--frame\r\nframe{i}\r\n".encode())
            await asyncio.sleep(0.01)
        await resp.write_eof()
        return resp

    async def ws(request: web.Request) -> web.WebSocketResponse:
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        async for msg in sock:
            if msg.type == WSMsgType.TEXT:
                await sock.send_str("echo:" + msg.data)
        return sock

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/assets/index-abc.js", js)
    app.router.add_get("/assets/index-abc.css", css)
    app.router.add_get("/api/v1/printers/", printers)
    app.router.add_get("/old", redirect)
    app.router.add_get("/api/v1/printers/2/camera/stream", stream)
    app.router.add_get("/api/v1/ws", ws)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", seen
    finally:
        await runner.cleanup()
