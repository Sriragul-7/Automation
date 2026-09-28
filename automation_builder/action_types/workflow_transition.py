"""Workflow Transition action type — advances a document through a Frappe Workflow.

Calls frappe.model.workflow.apply_workflow against the target document, reusing
the "Same Document / Linked Document" target pattern from update_field.py.

Role enforcement is respected: apply_workflow only applies transitions whose
``allowed`` role is held by the current session user, and each Workflow's own
configured transitions/gates apply unchanged. The denylist check prevents
targeting sensitive core/governance doctypes (the Workflow doctype itself is
also on the denylist — automations cannot reconfigure workflows, only drive
them on allowed business documents).
"""

import frappe
from frappe.model.workflow import apply_workflow, get_workflow_name

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
        "description": "Which document to transition.",
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
        "name": "transition_action",
        "type": "workflow_transition_select",
        "label": "Transition Action",
        "description": "Workflow transition to apply (populated from the target doctype's configured Workflow).",
    },
]


def execute(context, config):
    """Apply a workflow transition to the target document.

    config format::

        {
            "target": "Linked Document",
            "link_fieldname": "purchase_order",
            "transition_action": "Approve"
        }

    Raises on failure — the exception propagates to the dispatcher which
    marks the Automation Run as Failed with the real traceback.
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

    transition_action = (config.get("transition_action") or "").strip()
    if not transition_action:
        raise ValueError("No transition_action specified in workflow_transition action config")

    if not get_workflow_name(target_doctype):
        raise ValueError(
            f"No Workflow configured for {target_doctype} — "
            f"configure a Workflow on this DocType first"
        )

    target_doc = frappe.get_doc(target_doctype, target_name)
    previous_state = target_doc.get(
        frappe.get_cached_doc("Workflow", get_workflow_name(target_doctype)).workflow_state_field
    )

    # Real Frappe workflow transition — respects role/allowed configuration
    apply_workflow(target_doc, transition_action)

    new_state = frappe.get_cached_doc(target_doctype, target_name).get(
        frappe.get_cached_doc("Workflow", get_workflow_name(target_doctype)).workflow_state_field
    )

    return {
        "step_type": "workflow_transition",
        "status": "Success",
        "output": (
            f"Workflow transition '{transition_action}' applied to "
            f"{target_doctype} {target_name}: {previous_state} → {new_state}"
        ),
    }


register_action_type(
    key="workflow_transition",
    label="Workflow Transition",
    config_schema=CONFIG_SCHEMA,
    execute_fn=execute,
)
