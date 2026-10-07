# Bambuddy Panel for Home Assistant

Adds the [Bambuddy](https://github.com/maziggy/bambuddy) web app to the Home Assistant sidebar, shown full size in the main window. Home Assistant serves Bambuddy itself, so it works everywhere Home Assistant does, including the Companion app over Nabu Casa / https remote access. This is useful for printers in LAN mode, where Bambu Handy can't reach them.

## How it works

- Home Assistant proxies Bambuddy under `/api/bambuddy_panel/proxy/`: pages, API, live websocket updates and camera streams.
- **Login:** the panel exchanges your Home Assistant login for a signed, HTTP-only session cookie scoped to that path. Without the cookie the proxy returns 401, so Bambuddy is never exposed without a Home Assistant login. The signing key is kept in `.storage/bambuddy_panel.secret`.
- **Path rewriting:** Bambuddy expects to run at the root of its own server. The proxy rewrites absolute paths in its HTML and CSS, gives its router a base path, and injects `shim.js` to redirect URLs the app builds at runtime. It also removes Bambuddy's "don't frame me" headers.
- **Service worker:** Bambuddy's offline service worker is disabled inside Home Assistant, because it would take over Home Assistant's own address.
- **Compression:** text is gzipped by the proxy. Bambuddy's ~10 MB app bundle is otherwise sent uncompressed, which matters on mobile data.

**Known limits:** a few Bambuddy actions do a full page navigation, such as the "Projects" link in the archive menu. On browsers without the Navigation API (older Safari), these can land on Home Assistant instead of Bambuddy. Re-open the panel from the sidebar if that happens. Camera pop-out windows that open in an external browser won't have the session cookie.

## Install

1. HACS → ⋮ → Custom repositories → add `https://github.com/james194zt/ha_bambuddy`, type **Integration**.
2. Download **Bambuddy Panel**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **Bambuddy Panel**.
4. Check the URL (default `http://192.168.1.1:8000`), title and icon, then submit.

To change these settings later, open the integration and click **Configure**.
