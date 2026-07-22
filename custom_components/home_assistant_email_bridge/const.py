DOMAIN = "home_assistant_email_bridge"

CONF_WEBHOOK_ID = "webhook_id"
CONF_RECIPIENTS = "recipients"
CONF_DEFAULT_NOTIFY_SERVICE = "default_notify_service"
CONF_CREATE_PERSISTENT = "create_persistent_notification"
SIGNAL_MESSAGE_RECEIVED = "home_assistant_email_bridge_message_received"

DEFAULT_WEBHOOK_ID = "ha_email_bridge"
DEFAULT_NOTIFY_SERVICE = "persistent_notification.create"
DEFAULT_RECIPIENTS = {
    "dad": {
        "emails": ["dad@ha-notify.local", "dad"],
        "notify_services": ["persistent_notification.create"],
        "title_prefix": "",
    },
    "critical": {
        "emails": ["critical@ha-notify.local", "critical"],
        "notify_services": ["persistent_notification.create"],
        "title_prefix": "Critical: ",
    },
}
