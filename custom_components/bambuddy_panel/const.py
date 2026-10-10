"""Constants for the Bambuddy Panel integration."""

DOMAIN = "bambuddy_panel"

CONF_URL = "url"
CONF_TITLE = "title"
CONF_ICON = "icon"
CONF_NOTIFY_TARGETS = "notify_targets"

DEFAULT_URL = "http://192.168.1.1:8000"
DEFAULT_TITLE = "Bambuddy"
DEFAULT_ICON = "mdi:printer-3d"

PANEL_URL_PATH = "bambuddy"
PANEL_ELEMENT = "bambuddy-panel"

# Bambuddy is served through Home Assistant under this path, so it works
# wherever Home Assistant does (including https / Nabu Casa remote access).
PROXY_PATH = "/api/bambuddy_panel/proxy"
SESSION_PATH = "/api/bambuddy_panel/session"
STATIC_PATH = "/bambuddy_panel_static"

# Iframe requests can't carry Home Assistant's bearer token, so the panel
# swaps it for this signed cookie, scoped to PROXY_PATH.
COOKIE_NAME = "bambuddy_panel_session"
SESSION_TTL = 24 * 3600

# Called by Bambuddy's Home Assistant notification provider.
SERVICE_NOTIFY = "notify"
# Bambuddy's notification snapshots (unguessable filename per photo).
PHOTO_PATH = "/api/v1/notifications/photos/"
