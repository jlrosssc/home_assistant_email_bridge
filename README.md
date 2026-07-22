# Home Assistant Email Bridge

Home Assistant Email Bridge is a small local SMTP bridge for tools that can only send email notifications.
It receives fake/local email such as `dad@ha-notify.local`, parses the subject and body, and forwards the message to a Home Assistant webhook.

The bridge is intended for LAN/local use. Do not expose it to the public internet.

## How Recipient Mapping Works

Home Assistant does not automatically know that `dad@ha-notify.local` means a specific Home Assistant user.
The mapping is explicit:

1. A tool sends mail to `dad@ha-notify.local`.
2. The bridge extracts the local part, `dad`.
3. The bridge posts JSON to Home Assistant:

   ```json
   {
     "to": "dad",
     "source": "dad",
     "from": "container-monitor@dad.local",
     "subject": "Container offline",
     "message": "tng-test-web is offline",
     "severity": "normal"
   }
   ```

4. A Home Assistant webhook automation maps `to: dad` to the actual action, for example:
   - `notify.mobile_app_dads_iphone`
   - `persistent_notification.create`
   - both mobile push and persistent notification

This keeps the fake email address separate from Home Assistant users and devices.

## Example Email Settings

For a tool running on the same host:

```text
SMTP server: 127.0.0.1
SMTP port: 2525
Security: none
Authentication: none
To: dad@ha-notify.local
```

By default the Docker example binds to `127.0.0.1`, which means only programs running on the same host can connect.
That is the safest default.

For a Docker container or another LAN host, you must deliberately make the listener reachable, for example by changing the bridge host from `127.0.0.1` to a Docker-network address or to `0.0.0.0`.
Only do this on a trusted network with firewall rules that keep port `2525` off the internet.

If enabled for LAN/container access:

```text
SMTP server: <bridge-host-ip>
SMTP port: 2525
Security: none
Authentication: none
To: dad@ha-notify.local
```

## Home Assistant Integration

The repo includes a real Home Assistant custom integration under:

```text
custom_components/home_assistant_email_bridge/
```

Install it by copying that folder into your Home Assistant config:

```bash
sudo cp -a custom_components/home_assistant_email_bridge /opt/homeassistant/config/custom_components/
```

Restart Home Assistant, then add it from:

```text
Settings > Devices & services > Add integration > Home Assistant Email Bridge
```

The integration asks for:

- `webhook_id`: the local webhook path the SMTP bridge posts to.
- `default_notify_service`: fallback notify service.
- `recipients`: JSON mapping fake email endpoint/users to HA notify services.

After setup, the integration creates one diagnostic sensor per endpoint/user, such as:

```text
sensor.home_assistant_email_bridge_dad
sensor.home_assistant_email_bridge_critical
```

Each endpoint/user entity shows the local fake email address, configured aliases, notify services, and title prefix. This makes established endpoints visible in Home Assistant instead of hiding all of them only inside one settings list.

Notifications include the bridge source in the title, such as `[hross] Container offline` or `[dad] Backup complete`, so messages from multiple servers are easy to tell apart.

After setup, open:

```text
Settings > Devices & services > Home Assistant Email Bridge > Configure
```

Available actions:

- `View local email addresses`: shows which fake email address a server or service should use.
- `Add endpoint/user`: creates one endpoint and lets you pick an active notify service from a dropdown.
- `Edit endpoint/user`: chooses one existing endpoint first, then edits its email aliases and notification targets.
- `Test endpoint/user`: chooses one endpoint first, then opens a full test-message form prefilled with that endpoint's destination email.
- `Remove endpoint/user`: deletes one mapping.
- `Edit raw JSON`: advanced bulk editing.

Enable `Keep full message in Home Assistant` on an endpoint if you want phone pushes to keep a matching Home Assistant notification copy. Phone operating systems can truncate popup text; the HA copy keeps the full message available after opening Home Assistant.

Example recipient mapping:

```json
{
  "dad": {
    "notify_service": "notify.mobile_app_dads_iphone",
    "title_prefix": "",
    "create_persistent_copy": true
  },
  "critical": {
    "notify_service": "notify.mobile_app_dads_iphone",
    "title_prefix": "Critical: ",
    "create_persistent_copy": true
  }
}
```

With that mapping:

```text
dad@ha-notify.local
```

is translated by the SMTP bridge into:

```json
{"to": "dad"}
```

and the Home Assistant integration sends it through:

```text
notify.mobile_app_dads_iphone
```

The Home Assistant webhook is registered as `local_only`, so Home Assistant will reject non-local webhook calls. Keep the SMTP bridge local too unless you intentionally need LAN/container access.

## Optional YAML Setup

You can also configure the receiver in `configuration.yaml`:

```yaml
home_assistant_email_bridge:
  webhook_id: ha_email_bridge_dad
  default_notify_service: persistent_notification.create
  recipients:
    dad:
      notify_services:
        - notify.mobile_app_joe_ross_iphone
        - notify.mobile_app_joe_ross_iphone_2
        - persistent_notification.create
      title_prefix: ""
    critical:
      notify_services:
        - notify.mobile_app_joe_ross_iphone
        - notify.mobile_app_joe_ross_iphone_2
        - persistent_notification.create
      title_prefix: "Critical: "
```

`notify_services` are tried in order. This is useful when Home Assistant has duplicate or renamed Companion App devices.

## Install

Create the app directory:

```bash
sudo mkdir -p /opt/home-assistant-email-bridge
sudo cp ha_email_bridge.py /opt/home-assistant-email-bridge/
sudo cp examples/config.json /opt/home-assistant-email-bridge/config.json
sudo cp examples/docker/docker-compose.yml /opt/home-assistant-email-bridge/docker-compose.yml
sudo chmod 755 /opt/home-assistant-email-bridge/ha_email_bridge.py
sudo chmod 600 /opt/home-assistant-email-bridge/config.json
```

Edit `/opt/home-assistant-email-bridge/config.json`:

```json
{
  "source": "dad",
  "webhook_url": "http://127.0.0.1:8125/api/webhook/ha_email_bridge_dad",
  "default_recipient": "dad",
  "recipients": {
    "dad": {
      "address": "dad@ha-notify.local",
      "severity": "normal"
    },
    "critical": {
      "address": "critical@ha-notify.local",
      "severity": "critical"
    }
  }
}
```

Install the Home Assistant package:

```bash
sudo cp examples/homeassistant/ha_email_bridge_package.yaml /opt/homeassistant/config/packages/ha_email_bridge.yaml
```

Restart Home Assistant so the webhook automation loads.

Start the bridge:

```bash
cd /opt/home-assistant-email-bridge
sudo docker compose up -d
```

## Test

```bash
python3 - <<'PY'
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["From"] = "container-monitor@server.local"
msg["To"] = "dad@ha-notify.local"
msg["Subject"] = "Bridge test"
msg.set_content("This message was delivered through Home Assistant Email Bridge.")

with smtplib.SMTP("127.0.0.1", 2525, timeout=10) as smtp:
    smtp.send_message(msg)
PY
```

Check logs:

```bash
sudo docker logs --tail 50 home-assistant-email-bridge
```

Expected:

```text
delivered to=dad rcpt=dad@ha-notify.local subject='Bridge test'
```

## Security Notes

- Keep this listener on a trusted LAN or localhost.
- Do not port-forward SMTP port `2525` to the internet.
- Use a firewall if the host is on an untrusted network.
- Treat the Home Assistant webhook ID as a secret.

## License

GPL-3.0-or-later
