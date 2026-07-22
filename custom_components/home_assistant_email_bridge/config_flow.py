"""Config flow for Home Assistant Email Bridge."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_DEFAULT_NOTIFY_SERVICE,
    CONF_RECIPIENTS,
    CONF_WEBHOOK_ID,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_RECIPIENTS,
    DEFAULT_WEBHOOK_ID,
    DOMAIN,
)


def _recipients_to_text(recipients: dict[str, Any]) -> str:
    return json.dumps(recipients, indent=2, sort_keys=True)


def _parse_recipients(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("recipients must be a JSON object")
    for key, recipient in parsed.items():
        if not isinstance(key, str) or not key:
            raise ValueError("recipient names must be non-empty strings")
        if not isinstance(recipient, dict):
            raise ValueError(f"recipient {key} must be an object")
        notify_service = recipient.get("notify_service")
        if not isinstance(notify_service, str) or "." not in notify_service:
            raise ValueError(f"recipient {key} needs notify_service like notify.mobile_app_phone")
    return parsed


class HomeAssistantEmailBridgeConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle a config flow for Home Assistant Email Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                recipients = _parse_recipients(user_input[CONF_RECIPIENTS])
            except (json.JSONDecodeError, ValueError):
                errors[CONF_RECIPIENTS] = "invalid_recipients"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Home Assistant Email Bridge",
                    data={
                        CONF_WEBHOOK_ID: user_input[CONF_WEBHOOK_ID],
                        CONF_DEFAULT_NOTIFY_SERVICE: user_input[
                            CONF_DEFAULT_NOTIFY_SERVICE
                        ],
                        CONF_RECIPIENTS: recipients,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WEBHOOK_ID, default=DEFAULT_WEBHOOK_ID): str,
                    vol.Required(
                        CONF_DEFAULT_NOTIFY_SERVICE,
                        default=DEFAULT_NOTIFY_SERVICE,
                    ): str,
                    vol.Required(
                        CONF_RECIPIENTS,
                        default=_recipients_to_text(DEFAULT_RECIPIENTS),
                    ): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Create the options flow."""
        return HomeAssistantEmailBridgeOptionsFlow(config_entry)


class HomeAssistantEmailBridgeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Home Assistant Email Bridge."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        errors: dict[str, str] = {}
        current = {
            **self.config_entry.data,
            **self.config_entry.options,
        }

        if user_input is not None:
            try:
                recipients = _parse_recipients(user_input[CONF_RECIPIENTS])
            except (json.JSONDecodeError, ValueError):
                errors[CONF_RECIPIENTS] = "invalid_recipients"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_DEFAULT_NOTIFY_SERVICE: user_input[
                            CONF_DEFAULT_NOTIFY_SERVICE
                        ],
                        CONF_RECIPIENTS: recipients,
                    },
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEFAULT_NOTIFY_SERVICE,
                        default=current.get(
                            CONF_DEFAULT_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE
                        ),
                    ): str,
                    vol.Required(
                        CONF_RECIPIENTS,
                        default=_recipients_to_text(
                            current.get(CONF_RECIPIENTS, DEFAULT_RECIPIENTS)
                        ),
                    ): str,
                }
            ),
            errors=errors,
        )
