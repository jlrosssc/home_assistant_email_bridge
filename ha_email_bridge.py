#!/usr/bin/env python3
"""Local SMTP-to-Home-Assistant notification bridge."""

import argparse
import json
import re
import socketserver
import sys
import urllib.request
from email import policy
from email.parser import BytesParser


class BridgeConfig:
    def __init__(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.webhook_url = data["webhook_url"]
        self.default_recipient = data.get("default_recipient", "admin")
        self.recipients = data.get("recipients", {})
        self.source = data.get("source", "server")

    def resolve_recipient(self, address):
        local = address.split("@", 1)[0].lower()
        if local in self.recipients:
            return local
        return local or self.default_recipient

    def is_valid_recipient(self, address):
        local, _, domain = address.lower().partition("@")
        if domain and domain != "ha-notify.local":
            return False
        if not local:
            return False
        if not self.recipients:
            return True
        return local in self.recipients


class SmtpSession:
    def __init__(self):
        self.mail_from = ""
        self.rcpt_to = []
        self.data = bytearray()


class SmtpHandler(socketserver.StreamRequestHandler):
    def write_line(self, text):
        self.wfile.write((text + "\r\n").encode("utf-8"))
        self.wfile.flush()

    def handle(self):
        self.session = SmtpSession()
        self.write_line("220 home-assistant-email-bridge ready")
        while True:
            raw = self.rfile.readline(65536)
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            upper = line.upper()

            if upper.startswith("EHLO") or upper.startswith("HELO"):
                self.write_line("250-home-assistant-email-bridge")
                self.write_line("250 SIZE 1048576")
            elif upper.startswith("MAIL FROM:"):
                self.session.mail_from = extract_address(line[10:])
                self.write_line("250 OK")
            elif upper.startswith("RCPT TO:"):
                recipient = extract_address(line[8:])
                if not self.server.bridge_config.is_valid_recipient(recipient):
                    self.write_line("550 Unknown ha-notify.local recipient")
                    continue
                self.session.rcpt_to.append(recipient)
                self.write_line("250 OK")
            elif upper == "DATA":
                if not self.session.rcpt_to:
                    self.write_line("554 No valid recipients")
                    continue
                self.write_line("354 End data with <CR><LF>.<CR><LF>")
                self.read_message_data()
                try:
                    dispatch_message(self.server.bridge_config, self.session)
                    self.write_line("250 Message accepted")
                except Exception as exc:
                    print(f"dispatch failed: {exc}", file=sys.stderr, flush=True)
                    self.write_line("451 Local delivery failed")
                self.session = SmtpSession()
            elif upper == "RSET":
                self.session = SmtpSession()
                self.write_line("250 OK")
            elif upper == "NOOP":
                self.write_line("250 OK")
            elif upper == "QUIT":
                self.write_line("221 Bye")
                return
            else:
                self.write_line("502 Command not implemented")

    def read_message_data(self):
        while True:
            raw = self.rfile.readline(1048576)
            if raw in (b".\r\n", b".\n", b"."):
                return
            if raw.startswith(b".."):
                raw = raw[1:]
            self.session.data.extend(raw)


class ThreadedSmtpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler, bridge_config):
        super().__init__(server_address, handler)
        self.bridge_config = bridge_config


def extract_address(value):
    match = re.search(r"<([^>]+)>", value)
    if match:
        return match.group(1).strip()
    return value.strip()


def plain_body(message):
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                return part.get_content()
        body = message.get_body(preferencelist=("plain", "html"))
        return body.get_content() if body else ""
    return message.get_content()


def dispatch_message(config, session):
    message = BytesParser(policy=policy.default).parsebytes(bytes(session.data))
    subject = str(message.get("subject", "Server notification")).strip()
    body = plain_body(message).strip()
    rcpt = session.rcpt_to[0] if session.rcpt_to else f"{config.default_recipient}@ha-notify.local"
    to_name = config.resolve_recipient(rcpt)
    recipient = config.recipients.get(to_name, {})
    severity = recipient.get("severity", "normal")

    payload = {
        "to": to_name,
        "recipient_address": rcpt,
        "source": config.source,
        "from": session.mail_from or str(message.get("from", "")),
        "subject": subject or "Server notification",
        "message": body[:4000],
        "severity": severity,
        "dedupe_key": f"{config.source}:{to_name}:{subject or 'message'}",
    }

    request = urllib.request.Request(
        config.webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()

    print(
        f"delivered to={to_name} rcpt={rcpt} subject={payload['subject']!r}",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/app/config.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2525)
    args = parser.parse_args()

    config = BridgeConfig(args.config)
    with ThreadedSmtpServer((args.host, args.port), SmtpHandler, config) as server:
        print(f"home-assistant-email-bridge listening on {args.host}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
