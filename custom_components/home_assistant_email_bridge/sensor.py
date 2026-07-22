"""Recipient sensors for Home Assistant Email Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import CONF_RECIPIENTS, DOMAIN, SIGNAL_MESSAGE_RECEIVED


def _entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return config entry data with options overriding setup values."""
    return {**entry.data, **entry.options}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one sensor for each configured recipient."""
    recipients = _entry_config(entry).get(CONF_RECIPIENTS, {})
    async_add_entities([
        EmailBridgeRecipientSensor(entry, recipient_key, recipient)
        for recipient_key, recipient in sorted(recipients.items())
    ])


class EmailBridgeRecipientSensor(SensorEntity):
    """Expose a configured fake-email recipient as a Home Assistant entity."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:email-fast-outline"
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        recipient_key: str,
        recipient: dict[str, Any],
    ) -> None:
        self._entry = entry
        self._recipient_key = recipient_key
        self._recipient = recipient
        self._attr_unique_id = f"{entry.entry_id}_recipient_{recipient_key}"
        self._attr_name = recipient_key

    async def async_added_to_hass(self) -> None:
        """Subscribe to message updates for this endpoint."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_MESSAGE_RECEIVED,
                self._handle_message_received,
            )
        )

    @callback
    def _handle_message_received(
        self,
        entry_id: str,
        recipient_key: str,
    ) -> None:
        """Refresh state when this endpoint receives a message."""
        if entry_id == self._entry.entry_id and recipient_key == self._recipient_key:
            self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return the primary fake email address."""
        emails = self._emails
        if emails:
            return emails[0]
        return f"{self._recipient_key}@ha-notify.local"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return recipient details."""
        attrs = {
            "recipient": self._recipient_key,
            "local_email_addresses": self._emails,
            "notify_services": self._notify_services,
            "title_prefix": self._recipient.get("title_prefix", ""),
            "create_persistent_copy": bool(
                self._recipient.get("create_persistent_copy")
            ),
        }
        last_message = self._last_message
        if last_message:
            attrs.update(
                {
                    "last_title": last_message.get("title"),
                    "last_subject": last_message.get("subject"),
                    "last_message": last_message.get("message"),
                    "last_source": last_message.get("source"),
                    "last_from": last_message.get("from"),
                    "last_severity": last_message.get("severity"),
                    "last_recipient_address": last_message.get("recipient_address"),
                    "last_received_at": last_message.get("received_at"),
                }
            )
        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        """Group recipient entities under the bridge device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Home Assistant Email Bridge",
            "manufacturer": "Home Assistant Email Bridge",
        }

    @property
    def _emails(self) -> list[str]:
        emails = self._recipient.get("emails") or [
            f"{self._recipient_key}@ha-notify.local"
        ]
        if isinstance(emails, str):
            return [emails]
        return [str(email) for email in emails]

    @property
    def _notify_services(self) -> list[str]:
        services = self._recipient.get("notify_services")
        if services:
            return [str(service) for service in services]
        service = self._recipient.get("notify_service")
        return [str(service)] if service else []

    @property
    def _last_message(self) -> dict[str, Any]:
        return (
            self.hass.data.get(DOMAIN, {})
            .get(self._entry.entry_id, {})
            .get("messages", {})
            .get(self._recipient_key, {})
        )
