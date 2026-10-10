"""Config flow for Bambuddy Panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ICON,
    CONF_NOTIFY_TARGETS,
    CONF_TITLE,
    CONF_URL,
    DEFAULT_ICON,
    DEFAULT_TITLE,
    DEFAULT_URL,
    DOMAIN,
)

# Generic notify services that aren't a device to push to.
_NOT_TARGETS = {"notify", "send_message", "persistent_notification"}


def _notify_targets(hass: HomeAssistant) -> list[str]:
    return sorted(
        f"notify.{name}"
        for name in hass.services.async_services_for_domain("notify")
        if name not in _NOT_TARGETS
    )


def _schema(hass: HomeAssistant, defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=defaults.get(CONF_URL, DEFAULT_URL)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            ),
            vol.Required(CONF_TITLE, default=defaults.get(CONF_TITLE, DEFAULT_TITLE)): str,
            vol.Required(CONF_ICON, default=defaults.get(CONF_ICON, DEFAULT_ICON)): selector.IconSelector(),
            vol.Optional(
                CONF_NOTIFY_TARGETS, default=defaults.get(CONF_NOTIFY_TARGETS, [])
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_notify_targets(hass),
                    multiple=True,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class BambuddyPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-step setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_TITLE], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(self.hass, {}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BambuddyPanelOptionsFlow()


class BambuddyPanelOptionsFlow(OptionsFlow):
    """Change URL, title, icon or notification phones after setup."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(self.hass, current))
