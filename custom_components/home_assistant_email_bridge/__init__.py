"""Home Assistant Email Bridge integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from homeassistant.components import persistent_notification, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEFAULT_NOTIFY_SERVICE,
    CONF_RECIPIENTS,
    CONF_WEBHOOK_ID,
    DEFAULT_NOTIFY_SERVICE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Home Assistant Email Bridge from YAML."""
    yaml_config = config.get(DOMAIN)
    if not yaml_config:
        return True

    webhook_id = yaml_config[CONF_WEBHOOK_ID]

    async def handle_webhook(
        hass: HomeAssistant,
        webhook_id: str,
        request: web.Request,
    ) -> web.Response:
        try:
            payload = await request.json()
        except Exception as err:  # noqa: BLE001 - return clean webhook response
            _LOGGER.warning("Invalid email bridge payload: %s", err)
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        result = await _async_dispatch_message(hass, yaml_config, payload)
        return web.json_response(result)

    webhook.async_register(
        hass,
        DOMAIN,
        "Home Assistant Email Bridge",
        webhook_id,
        handle_webhook,
        local_only=True,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Assistant Email Bridge from a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    async def handle_webhook(
        hass: HomeAssistant,
        webhook_id: str,
        request: web.Request,
    ) -> web.Response:
        try:
            payload = await request.json()
        except Exception as err:  # noqa: BLE001 - return clean webhook response
            _LOGGER.warning("Invalid email bridge payload: %s", err)
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        result = await _async_dispatch_message(hass, {**entry.data, **entry.options}, payload)
        return web.json_response(result)

    webhook.async_register(
        hass,
        DOMAIN,
        "Home Assistant Email Bridge",
        webhook_id,
        handle_webhook,
        local_only=True,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return True


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload recipient entities after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_dispatch_message(
    hass: HomeAssistant,
    config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a received bridge payload to the mapped notify target."""
    recipient_key = str(payload.get("to") or "").strip().lower()
    recipient_address = str(payload.get("recipient_address") or "").strip().lower()
    recipients = config.get(CONF_RECIPIENTS, {})
    recipient_key, recipient = _find_recipient(
        recipients,
        recipient_key,
        recipient_address,
    )

    if recipient is None:
        _LOGGER.warning("Unknown email bridge recipient: %s", recipient_key)
        await _async_persistent(
            hass,
            "Unknown email bridge recipient",
            f"Recipient '{recipient_key}' is not mapped.\n\n{_format_message(payload)}",
            "home_assistant_email_bridge_unknown_recipient",
        )
        return {"ok": False, "error": "unknown_recipient", "to": recipient_key}

    notify_services = recipient.get("notify_services")
    if not notify_services:
        notify_services = [
            recipient.get("notify_service")
            or config.get(CONF_DEFAULT_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
        ]
    title_prefix = recipient.get("title_prefix", "")
    subject = str(payload.get("subject") or "Server notification")
    message = _format_message(payload)

    delivered_service = None
    last_error = None
    for notify_service in notify_services:
        if notify_service == "persistent_notification.create":
            await _async_persistent(
                hass,
                f"{title_prefix}{subject}",
                message,
                f"home_assistant_email_bridge_{recipient_key}",
            )
            delivered_service = notify_service
            break

        domain, service = notify_service.split(".", 1)
        if not hass.services.has_service(domain, service):
            last_error = f"service_not_found:{notify_service}"
            continue
        try:
            await hass.services.async_call(
                domain,
                service,
                {
                    "title": f"{title_prefix}{subject}",
                    "message": message,
                },
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - try fallback services
            last_error = str(err)
            continue
        delivered_service = notify_service
        break

    if delivered_service is None:
        await _async_persistent(
            hass,
            f"Email bridge delivery failed: {subject}",
            f"Recipient: {recipient_key}\nError: {last_error}\n\n{message}",
            f"home_assistant_email_bridge_failed_{recipient_key}",
        )
        return {"ok": False, "error": last_error, "to": recipient_key}

    _LOGGER.info(
        "Delivered email bridge message to %s via %s: %s",
        recipient_key,
        delivered_service,
        subject,
    )
    return {"ok": True, "to": recipient_key, "notify_service": delivered_service}


def _format_message(payload: dict[str, Any]) -> str:
    """Format a bridge payload for notification delivery."""
    source = payload.get("source", "unknown")
    sender = payload.get("from", "unknown")
    severity = payload.get("severity", "normal")
    body = payload.get("message", "")
    return f"Source: {source}\nFrom: {sender}\nSeverity: {severity}\n\n{body}"


def _find_recipient(
    recipients: dict[str, Any],
    recipient_key: str,
    recipient_address: str,
) -> tuple[str, dict[str, Any] | None]:
    """Find a recipient by alias or configured email address."""
    if recipient_key in recipients:
        return recipient_key, recipients[recipient_key]

    normalized_address = recipient_address.strip().lower()
    normalized_local = normalized_address.split("@", 1)[0]
    for key, recipient in recipients.items():
        emails = recipient.get("emails", [])
        if isinstance(emails, str):
            emails = [emails]
        normalized_emails = [str(item).strip().lower() for item in emails]
        if normalized_address in normalized_emails or normalized_local in normalized_emails:
            return key, recipient

    return recipient_key, None


async def _async_persistent(
    hass: HomeAssistant,
    title: str,
    message: str,
    notification_id: str,
) -> None:
    """Create a persistent notification."""
    persistent_notification.async_create(
        hass,
        message,
        title=title,
        notification_id=notification_id,
    )
