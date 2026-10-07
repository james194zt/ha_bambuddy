# Bambuddy Panel for Home Assistant

Adds the [Bambuddy](https://github.com/maziggy/bambuddy) web app to the Home Assistant sidebar, shown full size in the main window.

## Why there's a proxy

Bambuddy sends `X-Frame-Options: SAMEORIGIN` and `Content-Security-Policy: frame-ancestors 'none'`, so browsers refuse to show it inside another page. The integration therefore runs a small reverse proxy on the Home Assistant host (port **8001** by default). The proxy forwards everything to Bambuddy, including live streams and websockets, and removes only those two restrictions. The sidebar panel loads Bambuddy through the proxy.

Set the proxy port to `0` to load Bambuddy directly (only works if Bambuddy is changed to allow framing).

Notes:

- The proxy listens on the LAN only, with the same access as Bambuddy itself (no Home Assistant login in front of it).
- If you open Home Assistant over `https://`, the browser blocks an `http://` panel. The panel only works when Home Assistant is opened over `http://` on the LAN, unless the proxy is put behind TLS.

## Install

1. HACS → ⋮ → Custom repositories → add `https://github.com/james194zt/ha_bambuddy`, type **Integration**.
2. Download **Bambuddy Panel**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **Bambuddy Panel**.
4. Check the URL (default `http://192.168.1.1:8000`), title, icon and proxy port, then submit.

To change these settings later, open the integration and click **Configure**.
