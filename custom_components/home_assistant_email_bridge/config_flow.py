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
        notify_services = recipient.get("notify_services")
        if notify_services is not None:
            if not isinstance(notify_services, list) or not notify_services:
                raise ValueError(f"recipient {key} notify_services must be a non-empty list")
            if not all(isinstance(item, str) and "." in item for item in notify_services):
                raise ValueError(f"recipient {key} notify_services need service names like notify.mobile_app_phone")
        elif not isinstance(notify_service, str) or "." not in notify_service:
            raise ValueError(f"recipient {key} needs notify_service like notify.mobile_app_phone")
    return parsed


def _csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _current_config(config_entry: config_entries.ConfigEntry) -> dict[str, Any]:
    return {
        CONF_DEFAULT_NOTIFY_SERVICE: config_entry.options.get(
            CONF_DEFAULT_NOTIFY_SERVICE,
            config_entry.data.get(CONF_DEFAULT_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
        ),
        CONF_RECIPIENTS: config_entry.options.get(
            CONF_RECIPIENTS,
            config_entry.data.get(CONF_RECIPIENTS, DEFAULT_RECIPIENTS),
        ),
    }


class ConfigFlow(
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
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_recipient",
                "remove_recipient",
                "edit_json",
            ],
        )

    async def async_step_add_recipient(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Add or update a recipient mapping."""
        errors: dict[str, str] = {}
        current = _current_config(self.config_entry)
        recipients = dict(current.get(CONF_RECIPIENTS, {}))

        if user_input is not None:
            recipient_key = user_input["recipient"].strip().lower()
            emails = _csv_to_list(user_input["emails"])
            notify_services = _csv_to_list(user_input["notify_services"])

            if not recipient_key:
                errors["recipient"] = "required"
            elif not emails:
                errors["emails"] = "required"
            elif not notify_services or not all("." in item for item in notify_services):
                errors["notify_services"] = "invalid_notify_services"
            else:
                recipients[recipient_key] = {
                    "emails": emails,
                    "notify_services": notify_services,
                    "title_prefix": user_input.get("title_prefix", ""),
                }
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_DEFAULT_NOTIFY_SERVICE: current[
                            CONF_DEFAULT_NOTIFY_SERVICE
                        ],
                        CONF_RECIPIENTS: recipients,
                    },
                )

        return self.async_show_form(
            step_id="add_recipient",
            data_schema=vol.Schema(
                {
                    vol.Required("recipient"): str,
                    vol.Required("emails", default="dad@ha-notify.local,dad"): str,
                    vol.Required(
                        "notify_services",
                        default="notify.mobile_app_joe_ross_iphone,persistent_notification.create",
                    ): str,
                    vol.Optional("title_prefix", default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_remove_recipient(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Remove a recipient mapping."""
        current = _current_config(self.config_entry)
        recipients = dict(current.get(CONF_RECIPIENTS, {}))
        recipient_names = sorted(recipients)

        if user_input is not None:
            recipient = user_input["recipient"]
            recipients.pop(recipient, None)
            return self.async_create_entry(
                title="",
                data={
                    CONF_DEFAULT_NOTIFY_SERVICE: current[CONF_DEFAULT_NOTIFY_SERVICE],
                    CONF_RECIPIENTS: recipients,
                },
            )

        if not recipient_names:
            return self.async_show_form(
                step_id="remove_recipient",
                data_schema=vol.Schema({}),
                errors={"base": "no_recipients"},
            )

        return self.async_show_form(
            step_id="remove_recipient",
            data_schema=vol.Schema(
                {
                    vol.Required("recipient"): vol.In(recipient_names),
                }
            ),
        )

    async def async_step_edit_json(self, user_input: dict[str, Any] | None = None):
        """Edit raw JSON options."""
        errors: dict[str, str] = {}
        current = _current_config(self.config_entry)

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
            step_id="edit_json",
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
