"""Slack action type — sends a message via a Slack incoming webhook.

Thin wrapper over the shared HTTP request helper (http_request.make_http_request),
following the same pattern as telegram.py. The webhook URL is stored in
Automation Builder Settings as slack_webhook_url (Password field, encrypted
store) — the same convention as telegram_bot_token.

When no webhook URL is configured, the action runs in mock mode and logs what
*would* have been sent — without making any network call.
"""

import frappe
from frappe.utils import strip_html_tags

from automation_builder.action_types import register_action_type
from automation_builder.action_types._helpers import resolve_value
from automation_builder.action_types.http_request import make_http_request

CONFIG_SCHEMA = [
    {
        "name": "trigger_doctype_select",
        "type": "trigger_doctype_select",
        "label": "Trigger DocType",
        "description": "Which trigger's document to use for field tokens. Only shown when automation has multiple triggers.",
    },
    {
        "name": "channel",
        "type": "data",
        "label": "Channel",
        "description": "Optional channel override (e.g. #sales). Most incoming webhooks are pinned to one channel.",
    },
    {
        "name": "message",
        "type": "textarea",
        "label": "Message",
        "description": "Message text to send. Supports {{trigger.fieldname}} and {{env.varname}} tokens.",
    },
]


def _get_webhook_url():
    """Retrieve the Slack incoming webhook URL from Automation Builder Settings.

    Uses get_password() to retrieve from the encrypted store, not a
    plaintext field read. Returns None when not configured (mock mode).
    """
    try:
        url = frappe.get_doc("Automation Builder Settings").get_password("slack_webhook_url")
    except Exception:
        return None
    return url or None


def execute(context, config):
    """Send a Slack message, or log a mock if no webhook URL is configured.

    config format::

        {
            "channel": "#sales",
            "message": "New lead: {{trigger.lead_name}}"
        }

    Slack incoming webhooks accept a JSON payload of the form
    ``{"text": "message", "channel": "#channel"}``.
    """
    channel_raw = resolve_value(config.get("channel", ""), context)
    channel = channel_raw.strip() if isinstance(channel_raw, str) else ""
    message = strip_html_tags(resolve_value(config.get("message", ""), context))

    if not message:
        raise ValueError("No message specified in slack action config")

    webhook_url = _get_webhook_url()

    if not webhook_url:
        # Mock mode — no network call, clear log (same convention as Telegram)
        mock_line = (
            "MOCK MODE (no Slack webhook configured): "
            f"would have sent to {channel or 'default channel'}: '{message}'"
        )
        return {
            "step_type": "slack",
            "status": "Success",
            "output": mock_line,
        }

    # Real send — use the shared HTTP helper
    payload = {"text": message}
    if channel:
        payload["channel"] = channel

    result = make_http_request(
        method="POST",
        url=webhook_url,
        headers={"Content-Type": "application/json"},
        json_payload=payload,
        timeout=15,
    )

    # Slack returns a plain-text "ok" on success (status 200)
    if not result["ok"]:
        raise ValueError(
            f"Slack webhook returned status {result['status_code']}: "
            f"{result['response_body']}"
        )

    return {
        "step_type": "slack",
        "status": "Success",
        "output": (
            f"Slack message sent to {channel or 'default channel'}: {message}"
        ),
    }


register_action_type(
    key="slack",
    label="Slack",
    config_schema=CONFIG_SCHEMA,
    execute_fn=execute,
)
