"""Assign To action type — creates a real Frappe ToDo/assignment.

Uses Frappe's own native assignment mechanism (frappe.desk.form.assign_to.add)
rather than reinventing ToDo creation — the assignment shows up with the
standard badge in Frappe's own document UI, honours duplicate-assignment
suppression, document sharing, and assignment notifications.

Target document resolution follows the same "Same Document / Linked Document"
pattern as update_field.py.
"""

import frappe
from frappe.desk.form.assign_to import add as assign_to_add

from automation_builder.action_types import register_action_type
from automation_builder.action_types._denylist import check_denylist
from automation_builder.action_types._helpers import resolve_value

CONFIG_SCHEMA = [
    {
        "name": "trigger_doctype_select",
        "type": "trigger_doctype_select",
        "label": "Trigger DocType",
        "description": "Which trigger's document to use for field tokens. Only shown when automation has multiple triggers.",
    },
    {
        "name": "target",
        "type": "select",
        "label": "Target",
        "options": ["Same Document", "Linked Document"],
        "default": "Same Document",
        "description": "Which document to attach the assignment to.",
    },
    {
        "name": "link_fieldname",
        "type": "link_field_select",
        "label": "Via Link Field",
        "description": "Field on the trigger doc that links to the target document. Only shown when Target = Linked Document.",
        "depends_on": "target",
        "depends_on_value": "Linked Document",
    },
    {
        "name": "assign_to_user",
        "type": "data",
        "label": "Assign To User",
        "description": "User to assign (e.g. a static user ID or {{trigger.owner}} to assign dynamically from a field).",
    },
    {
        "name": "description",
        "type": "textarea",
        "label": "Description",
        "description": "Assignment description. Supports {{trigger.fieldname}} and {{env.varname}} tokens.",
    },
    {
        "name": "priority",
        "type": "select",
        "label": "Priority",
        "options": ["Low", "Medium", "High"],
        "default": "Medium",
    },
    {
        "name": "due_date",
        "type": "data",
        "label": "Due Date",
        "description": "Optional due date (YYYY-MM-DD). Supports {{trigger.fieldname}} tokens. Defaults to today.",
    },
]


def execute(context, config):
    """Create a Frappe assignment (ToDo) on the target document.

    config format::

        {
            "target": "Same Document",
            "link_fieldname": "",
            "assign_to_user": "{{trigger.owner}}",
            "description": "Follow up with {{trigger.lead_name}}",
            "priority": "High",
            "due_date": "2026-10-01"
        }

    Calls frappe.desk.form.assign_to.add — the real Frappe assignment API,
    which creates a visible ToDo, handles duplicates, sharing, and notifications.
    """
    target_mode = config.get("target", "Same Document")

    doc = context.get("doc")
    if doc is None:
        raise ValueError("No trigger document available in context")

    if target_mode == "Linked Document":
        link_fieldname = resolve_value(config.get("link_fieldname", ""), context)
        if not link_fieldname:
            raise ValueError("No link_fieldname specified for Linked Document target")
        linked_name = doc.get(link_fieldname)
        if not linked_name:
            raise ValueError(
                f"Link field '{link_fieldname}' is empty on the trigger document"
            )
        meta = frappe.get_meta(doc.doctype)
        link_field = meta.get_field(link_fieldname)
        if not link_field:
            raise ValueError(f"Field '{link_fieldname}' not found on {doc.doctype}")
        linked_doctype = link_field.options
        if not linked_doctype:
            raise ValueError(f"Field '{link_fieldname}' has no linked DocType configured")
        target_doctype = linked_doctype
        target_name = linked_name
    else:
        target_doctype = doc.doctype
        target_name = doc.name

    # Security: refuse to target sensitive core/governance doctypes
    check_denylist(target_doctype)

    user_raw = resolve_value(config.get("assign_to_user", ""), context)
    assign_to_user = (user_raw or "").strip()
    if not assign_to_user:
        raise ValueError("No assign_to_user specified in assign_to action config")

    description = resolve_value(config.get("description", ""), context)
    priority = config.get("priority", "Medium") or "Medium"
    due_date = resolve_value(config.get("due_date", ""), context)

    # Real Frappe assignment — creates a ToDo visible in the desk UI
    # add() returns the open assignment list: [{owner, name}, ...]
    assign_to_add({
        "assign_to": frappe.parse_json([assign_to_user]),
        "doctype": target_doctype,
        "name": str(target_name),
        "description": description or None,
        "priority": priority,
        "date": due_date or None,
        "assigned_by": frappe.session.user,
    })

    return {
        "step_type": "assign_to",
        "status": "Success",
        "output": (
            f"Assigned {target_doctype} {target_name} to {assign_to_user} "
            f"(priority: {priority})"
        ),
    }


register_action_type(
    key="assign_to",
    label="Assign To",
    config_schema=CONFIG_SCHEMA,
    execute_fn=execute,
)
