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

        result = await _async_dispatch_message(hass, entry, payload)
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return True


async def _async_dispatch_message(
    hass: HomeAssistant,
    entry: ConfigEntry,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a received bridge payload to the mapped notify target."""
    config = {**entry.data, **entry.options}
    recipient_key = str(payload.get("to") or "").strip().lower()
    recipients = config.get(CONF_RECIPIENTS, {})
    recipient = recipients.get(recipient_key)

    if recipient is None:
        _LOGGER.warning("Unknown email bridge recipient: %s", recipient_key)
        await _async_persistent(
            hass,
            "Unknown email bridge recipient",
            f"Recipient '{recipient_key}' is not mapped.\n\n{_format_message(payload)}",
            "home_assistant_email_bridge_unknown_recipient",
        )
        return {"ok": False, "error": "unknown_recipient", "to": recipient_key}

    notify_service = recipient.get("notify_service") or config.get(
        CONF_DEFAULT_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE
    )
    title_prefix = recipient.get("title_prefix", "")
    subject = str(payload.get("subject") or "Server notification")
    message = _format_message(payload)

    if notify_service == "persistent_notification.create":
        await _async_persistent(
            hass,
            f"{title_prefix}{subject}",
            message,
            f"home_assistant_email_bridge_{recipient_key}",
        )
    else:
        domain, service = notify_service.split(".", 1)
        await hass.services.async_call(
            domain,
            service,
            {
                "title": f"{title_prefix}{subject}",
                "message": message,
            },
            blocking=True,
        )

    _LOGGER.info(
        "Delivered email bridge message to %s via %s: %s",
        recipient_key,
        notify_service,
        subject,
    )
    return {"ok": True, "to": recipient_key, "notify_service": notify_service}


def _format_message(payload: dict[str, Any]) -> str:
    """Format a bridge payload for notification delivery."""
    source = payload.get("source", "unknown")
    sender = payload.get("from", "unknown")
    severity = payload.get("severity", "normal")
    body = payload.get("message", "")
    return f"Source: {source}\nFrom: {sender}\nSeverity: {severity}\n\n{body}"


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
