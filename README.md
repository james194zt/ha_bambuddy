# Bambuddy Panel for Home Assistant

Adds the [Bambuddy](https://github.com/maziggy/bambuddy) web app to the Home Assistant sidebar, shown full size in the main window. Home Assistant serves Bambuddy itself, so it works everywhere Home Assistant does, including the Companion app over Nabu Casa / https remote access. This is useful for printers in LAN mode, where Bambu Handy can't reach them.

## How it works

- Home Assistant proxies Bambuddy under `/api/bambuddy_panel/proxy/`: pages, API, live websocket updates and camera streams.
- **Login:** the panel exchanges your Home Assistant login for a signed, HTTP-only session cookie scoped to that path. Without the cookie the proxy returns 401, so Bambuddy is never exposed without a Home Assistant login. The signing key is kept in `.storage/bambuddy_panel.secret`.
- **Path rewriting:** Bambuddy expects to run at the root of its own server. The proxy rewrites absolute paths in its HTML and CSS, gives its router a base path, and injects `shim.js` to redirect URLs the app builds at runtime. It also removes Bambuddy's "don't frame me" headers.
- **Service worker:** Bambuddy's offline service worker is disabled inside Home Assistant, because it would take over Home Assistant's own address.
- **Compression:** text is gzipped by the proxy. Bambuddy's ~10 MB app bundle is otherwise sent uncompressed, which matters on mobile data.

**Known limits:** a few Bambuddy actions do a full page navigation, such as the "Projects" link in the archive menu. On browsers without the Navigation API (older Safari), these can land on Home Assistant instead of Bambuddy. Re-open the panel from the sidebar if that happens. Camera pop-out windows that open in an external browser won't have the session cookie.

## Notifications on your phone

Bambuddy has a built-in Home Assistant notification provider. Point it at this integration's `bambuddy_panel.notify` service to get Bambuddy's alerts as Companion app push notifications, including the camera snapshot, even away from home.

The service forwards each notification to the phones you pick, with two changes:
- **Snapshot:** the link, which Bambuddy builds from its LAN "External URL", is rewritten to load through Home Assistant with your login.
- **Tap action:** tapping the notification opens the Bambuddy panel.

1. Home Assistant: Bambuddy Panel → **Configure** → **Notification phones**, then pick your phone(s) (e.g. `notify.mobile_app_my_phone`).
2. Bambuddy: Settings → Notifications → **Add provider** → **Home Assistant**.
   - **Service:** `bambuddy_panel.notify`
   - Leave **Attach photo** on, and tick the events you want.
   - Bambuddy needs its Home Assistant connection set up (Settings → Network → Home Assistant), and its **External URL** set (any value works, e.g. its LAN address) or it won't attach snapshots.
3. Press **Test** on the provider.

Any extra **Data** you set on the provider (e.g. `{"priority": "high", "ttl": 0}`) is passed to the phone unchanged.

## Install

1. HACS → ⋮ → Custom repositories → add `https://github.com/james194zt/ha_bambuddy`, type **Integration**.
2. Download **Bambuddy Panel**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **Bambuddy Panel**.
4. Check the URL (default `http://192.168.1.1:8000`), title and icon, then submit.

To change these settings later, open the integration and click **Configure**.
