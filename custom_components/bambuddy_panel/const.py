"""Constants for the Bambuddy Panel integration."""

DOMAIN = "bambuddy_panel"

CONF_URL = "url"
CONF_TITLE = "title"
CONF_ICON = "icon"
CONF_PROXY_PORT = "proxy_port"

DEFAULT_URL = "http://192.168.1.1:8000"
DEFAULT_TITLE = "Bambuddy"
DEFAULT_ICON = "mdi:printer-3d"
# Bambuddy refuses to be framed (X-Frame-Options / frame-ancestors), so by
# default the panel goes through a small header-stripping proxy on this port.
# 0 = no proxy, frame Bambuddy directly.
DEFAULT_PROXY_PORT = 8001

PANEL_URL_PATH = "bambuddy"
