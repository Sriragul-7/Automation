"""Action type registry — the plug-and-play system for automation actions.

Each action type is a small, isolated module registered into a central dict.
Dispatcher/executor only needs to look up the registry and call execute().

Branching logic types (IF/Switch) are also registered here with node_category="logic".
They don't have side effects — they determine which edge to follow next.

To add a new action type:
    1. Create automation_builder/action_types/my_action.py
    2. Import and register it here, or use register_action_type() directly.

To add a new logic/branching type:
    1. Create automation_builder/action_types/my_logic.py
    2. Register with node_category="logic" and provide evaluate_branch function.
"""

ACTION_TYPES = {}


def register_action_type(
    key,
    label,
    config_schema,
    execute_fn=None,
    node_category="action",
    output_handles=None,
    evaluate_branch=None,
    get_output_handles=None,
):
    """Register an action or logic type into the global registry.

    For action types (node_category="action"):
        execute_fn is required — called with (context, config) -> result dict.

    For logic types (node_category="logic"):
        evaluate_branch is required — called with (config, context) -> (handle, log_msg).
        output_handles: static list [{"id": ..., "label": ...}] or "dynamic" for
        types whose handles depend on config (use get_output_handles).
    """
    entry = {
        "key": key,
        "label": label,
        "config_schema": config_schema,
        "node_category": node_category,
    }
    if execute_fn is not None:
        entry["execute"] = execute_fn
    if output_handles is not None:
        entry["output_handles"] = output_handles
    if evaluate_branch is not None:
        entry["evaluate_branch"] = evaluate_branch
    if get_output_handles is not None:
        entry["get_output_handles"] = get_output_handles
    ACTION_TYPES[key] = entry


def get_action_type(key):
    """Return the action/logic type dict for *key*, or None."""
    return ACTION_TYPES.get(key)


def get_all_action_types():
    """Return metadata for every registered type (no execute/evaluate_branch functions).

    Returns a dict keyed by type key, with label, config_schema, and node_category.
    """
    return {
        k: {
            "key": v["key"],
            "label": v["label"],
            "config_schema": v["config_schema"],
            "node_category": v["node_category"],
        }
        for k, v in ACTION_TYPES.items()
    }


# Import built-in types so they register on first import of this package.
from automation_builder.action_types import create_document  # noqa: E402, F401
from automation_builder.action_types import send_email  # noqa: E402, F401
from automation_builder.action_types import http_request  # noqa: E402, F401
from automation_builder.action_types import telegram  # noqa: E402, F401
from automation_builder.action_types import update_field  # noqa: E402, F401
from automation_builder.action_types import if_condition  # noqa: E402, F401
from automation_builder.action_types import switch_case  # noqa: E402, F401
from automation_builder.action_types import slack  # noqa: E402, F401
from automation_builder.action_types import assign_to  # noqa: E402, F401
from automation_builder.action_types import workflow_transition  # noqa: E402, F401
from automation_builder.action_types import generate_pdf  # noqa: E402, F401
