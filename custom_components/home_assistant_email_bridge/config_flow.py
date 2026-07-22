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


def _notify_service_options(hass) -> list[str]:
    services = hass.services.async_services()
    notify_services = [
        f"notify.{service}"
        for service in sorted(services.get("notify", {}))
    ]
    if "persistent_notification.create" not in notify_services:
        notify_services.append("persistent_notification.create")
    return notify_services or ["persistent_notification.create"]


def _recipient_address_summary(recipients: dict[str, Any]) -> str:
    if not recipients:
        return "No recipients are configured."
    lines = []
    for key in sorted(recipients):
        recipient = recipients[key]
        emails = recipient.get("emails") or [f"{key}@ha-notify.local"]
        if isinstance(emails, str):
            emails = [emails]
        services = recipient.get("notify_services") or [recipient.get("notify_service", "")]
        lines.append(
            f"{key}: {', '.join(str(email) for email in emails)} -> "
            f"{', '.join(str(service) for service in services if service)}"
        )
    return "\n".join(lines)


def _recipient_defaults(
    recipient_key: str,
    recipient: dict[str, Any],
) -> dict[str, Any]:
    """Return form defaults for a recipient."""
    emails = recipient.get("emails") or [f"{recipient_key}@ha-notify.local"]
    if isinstance(emails, str):
        emails = [emails]
    notify_services = recipient.get("notify_services") or [
        recipient.get("notify_service", "")
    ]
    notify_services = [str(service) for service in notify_services if service]
    return {
        "emails": ",".join(str(email) for email in emails),
        "notify_service": notify_services[0] if notify_services else "",
        "fallback_services": ",".join(notify_services[1:]),
        "title_prefix": str(recipient.get("title_prefix", "")),
        "create_persistent_copy": bool(recipient.get("create_persistent_copy")),
    }


def _primary_email(recipient_key: str, recipient: dict[str, Any]) -> str:
    """Return the primary fake email address for a recipient."""
    emails = recipient.get("emails") or [f"{recipient_key}@ha-notify.local"]
    if isinstance(emails, str):
        return emails
    return str(emails[0]) if emails else f"{recipient_key}@ha-notify.local"


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
        self._config_entry = config_entry
        self._edit_recipient_key: str | None = None
        self._test_recipient_key: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "view_addresses",
                "add_recipient",
                "edit_recipient",
                "send_test",
                "remove_recipient",
                "edit_json",
            ],
        )

    async def async_step_view_addresses(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Show currently configured local email addresses."""
        current = _current_config(self._config_entry)
        if user_input is not None:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="view_addresses",
            data_schema=vol.Schema({}),
            description_placeholders={
                "smtp_host": "127.0.0.1",
                "smtp_port": "2525",
                "addresses": _recipient_address_summary(
                    current.get(CONF_RECIPIENTS, {})
                ),
            },
        )

    async def async_step_add_recipient(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Add an endpoint/user mapping."""
        errors: dict[str, str] = {}
        current = _current_config(self._config_entry)
        recipients = dict(current.get(CONF_RECIPIENTS, {}))

        if user_input is not None:
            recipient_key = user_input["recipient"].strip().lower()
            emails = _csv_to_list(user_input["emails"])
            notify_services = [user_input["notify_service"]]
            notify_services.extend(_csv_to_list(user_input.get("fallback_services", "")))

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
                    "create_persistent_copy": user_input.get(
                        "create_persistent_copy",
                        False,
                    ),
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
                        "notify_service",
                        default=_notify_service_options(self.hass)[0],
                    ): vol.In(_notify_service_options(self.hass)),
                    vol.Optional(
                        "fallback_services",
                        default="persistent_notification.create",
                    ): str,
                    vol.Optional("title_prefix", default=""): str,
                    vol.Optional("create_persistent_copy", default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_edit_recipient(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Choose an existing recipient to edit."""
        current = _current_config(self._config_entry)
        recipients = current.get(CONF_RECIPIENTS, {})
        recipient_names = sorted(recipients)

        if user_input is not None:
            self._edit_recipient_key = user_input["recipient"]
            return await self.async_step_edit_selected_recipient()

        if not recipient_names:
            return self.async_show_form(
                step_id="edit_recipient",
                data_schema=vol.Schema({}),
                errors={"base": "no_recipients"},
            )

        return self.async_show_form(
            step_id="edit_recipient",
            data_schema=vol.Schema(
                {
                    vol.Required("recipient"): vol.In(recipient_names),
                }
            ),
        )

    async def async_step_edit_selected_recipient(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Edit a selected recipient mapping."""
        errors: dict[str, str] = {}
        current = _current_config(self._config_entry)
        recipients = dict(current.get(CONF_RECIPIENTS, {}))
        recipient_key = self._edit_recipient_key

        if not recipient_key or recipient_key not in recipients:
            return await self.async_step_edit_recipient()

        if user_input is not None:
            emails = _csv_to_list(user_input["emails"])
            notify_services = [user_input["notify_service"]]
            notify_services.extend(_csv_to_list(user_input.get("fallback_services", "")))

            if not emails:
                errors["emails"] = "required"
            elif not notify_services or not all("." in item for item in notify_services):
                errors["notify_services"] = "invalid_notify_services"
            else:
                recipients[recipient_key] = {
                    "emails": emails,
                    "notify_services": notify_services,
                    "title_prefix": user_input.get("title_prefix", ""),
                    "create_persistent_copy": user_input.get(
                        "create_persistent_copy",
                        False,
                    ),
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

        defaults = _recipient_defaults(recipient_key, recipients[recipient_key])
        notify_options = _notify_service_options(self.hass)
        notify_default = defaults["notify_service"]
        if notify_default not in notify_options:
            notify_options = [notify_default, *notify_options]

        return self.async_show_form(
            step_id="edit_selected_recipient",
            data_schema=vol.Schema(
                {
                    vol.Required("emails", default=defaults["emails"]): str,
                    vol.Required(
                        "notify_service",
                        default=notify_default,
                    ): vol.In(notify_options),
                    vol.Optional(
                        "fallback_services",
                        default=defaults["fallback_services"],
                    ): str,
                    vol.Optional(
                        "title_prefix",
                        default=defaults["title_prefix"],
                    ): str,
                    vol.Optional(
                        "create_persistent_copy",
                        default=defaults["create_persistent_copy"],
                    ): bool,
                }
            ),
            errors=errors,
            description_placeholders={"recipient": recipient_key},
        )

    async def async_step_remove_recipient(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Remove a recipient mapping."""
        current = _current_config(self._config_entry)
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
        current = _current_config(self._config_entry)

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

    async def async_step_send_test(self, user_input: dict[str, Any] | None = None):
        """Choose an endpoint/user for a fully formed test message."""
        current = _current_config(self._config_entry)
        recipients = current.get(CONF_RECIPIENTS, {})
        recipient_names = sorted(recipients)

        if not recipient_names:
            return self.async_show_form(
                step_id="send_test",
                data_schema=vol.Schema({}),
                errors={"base": "no_recipients"},
            )

        if user_input is not None:
            self._test_recipient_key = user_input["recipient"]
            return await self.async_step_send_test_message()

        return self.async_show_form(
            step_id="send_test",
            data_schema=vol.Schema(
                {
                    vol.Required("recipient"): vol.In(recipient_names),
                }
            ),
        )

    async def async_step_send_test_message(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Send a fully formed test message through the normal dispatch path."""
        errors: dict[str, str] = {}
        current = _current_config(self._config_entry)
        recipients = current.get(CONF_RECIPIENTS, {})
        recipient_name = self._test_recipient_key

        if not recipient_name or recipient_name not in recipients:
            return await self.async_step_send_test()

        recipient = recipients[recipient_name]
        if user_input is not None:
            from . import _async_dispatch_message

            result = await _async_dispatch_message(
                self.hass,
                current,
                {
                    "to": recipient_name,
                    "recipient_address": user_input["recipient_address"],
                    "source": user_input["source"],
                    "from": user_input["from_address"],
                    "severity": user_input["severity"],
                    "subject": user_input["subject"],
                    "message": user_input["message"],
                    "dedupe_key": (
                        f"ha-ui-test:{recipient_name}:{user_input['subject']}"
                    ),
                },
            )
            if result.get("ok"):
                return self.async_create_entry(title="", data=current)
            errors["base"] = "no_notify_service"

        default_address = _primary_email(recipient_name, recipient)
        return self.async_show_form(
            step_id="send_test_message",
            data_schema=vol.Schema(
                {
                    vol.Required("recipient_address", default=default_address): str,
                    vol.Required("source", default="home_assistant_ui"): str,
                    vol.Required(
                        "from_address",
                        default="home-assistant-email-bridge@test.local",
                    ): str,
                    vol.Required("severity", default="normal"): vol.In(
                        ["normal", "critical"]
                    ),
                    vol.Required(
                        "subject",
                        default="Home Assistant Email Bridge test",
                    ): str,
                    vol.Required(
                        "message",
                        default=(
                            "This is a fully formed test message from "
                            "Home Assistant Email Bridge."
                        ),
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={"recipient": recipient_name},
        )
