"""Shared helpers used by all action types."""

import re

import frappe
from frappe.utils import sanitize_html

TRIGGER_DOCTYPE_FIELD = "__trigger_doctype__"
_TRIGGER_TOKEN_RE = re.compile(r"\{\{trigger\.(\w+)\}\}")
_ENV_TOKEN_RE = re.compile(r"\{\{env\.(\w+)\}\}")


def _resolve_env_token(name):
    """Resolve a single {{env.name}} token from Automation Global Variable.

    Missing variables resolve to an empty string rather than raising —
    the same lenient behaviour as trigger tokens on shared nodes.
    """
    try:
        return frappe.db.get_value(
            "Automation Global Variable", {"variable_name": name}, "value"
        ) or ""
    except Exception:
        return ""


def resolve_value(raw_value, context):
    """Resolve token placeholders in *raw_value* against the trigger context.

    Supported tokens:
        {{trigger.fieldname}}  ->  doc.get("fieldname") on the triggering document
        {{env.varname}}        ->  value of the Automation Global Variable "varname"

    When ``context["trigger_doctype_select"]`` is ``"any"``, the node operates
    on whatever document actually triggered this run. Tokens referencing fields
    that don't exist on that particular doctype resolve to an empty string
    rather than raising an error. This supports shared downstream nodes that
    receive documents from different trigger doctypes via converging branches.

    Static strings (no tokens) pass through unchanged.
    Non-string values are returned as-is.

    Token values are sanitized via frappe.utils.sanitize_html() to prevent
    XSS injection when substituted into HTML email bodies or message fields.
    """
    if not isinstance(raw_value, str) or "{{" not in raw_value:
        return raw_value

    doc = context.get("doc")

    def _replace(match):
        field = match.group(1)
        # Special case: __trigger_doctype__ resolves from context, not the document
        if field == TRIGGER_DOCTYPE_FIELD:
            return str(context.get("trigger_doctype", "") or "")
        if doc is None:
            return ""
        try:
            val = doc.get(field)
        except (AttributeError, TypeError):
            # Doc doesn't support .get() or field access — resolve to empty
            return ""
        if val is None:
            return ""
        val_str = str(val)
        # Sanitize to prevent XSS when token values are rendered as HTML
        return sanitize_html(val_str)

    def _replace_env(match):
        val = _resolve_env_token(match.group(1))
        if val is None:
            return ""
        return sanitize_html(str(val))

    resolved = _TRIGGER_TOKEN_RE.sub(_replace, raw_value)
    return _ENV_TOKEN_RE.sub(_replace_env, resolved)
