"""Recipient sensors for Home Assistant Email Bridge."""

from __future__ import annotations
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_RECIPIENTS, DOMAIN


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
        return {
            "recipient": self._recipient_key,
            "local_email_addresses": self._emails,
            "notify_services": self._notify_services,
            "title_prefix": self._recipient.get("title_prefix", ""),
            "create_persistent_copy": bool(
                self._recipient.get("create_persistent_copy")
            ),
        }

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
