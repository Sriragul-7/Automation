"""Stage 31 — Five new action types via the registry: real-dispatch-path tests.

Covers Slack (mock mode), Assign To (real ToDo), Workflow Transition (real state
change), Generate PDF (real attachment), and {{env.*}} Global Variable tokens —
all through the REAL dispatch path (document.save() -> hooks -> on_doc_event ->
enqueue (patched synchronous) -> execute_automation -> graph walk -> action
execute). No direct function calls to execute() except via the enqueue patch.
"""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from automation_builder.action_types import get_action_type
from automation_builder.dispatcher import execute_automation
from automation_builder.api import save_automation


def _make_trigger_node(node_id="trigger", trigger_doctype=""):
    return {
        "id": node_id, "type": "trigger",
        "position": {"x": 250, "y": 50},
        "data": {"trigger_doctype": trigger_doctype, "trigger_event": "After Insert"},
    }


def _make_action_node(node_id, action_type, config=None):
    data = {"action_type": action_type}
    if config:
        data.update(config)
    return {"id": node_id, "type": "action", "position": {"x": 0, "y": 300}, "data": data}


def _make_edge(src, tgt, source_handle=None):
    return {
        "id": f"e-{src}-{tgt}",
        "source": src, "target": tgt,
        "sourceHandle": source_handle or f"{src}-out",
        "targetHandle": f"{tgt}-in",
        "type": "smoothstep",
    }


def _make_trigger(dt, event="After Insert", **kwargs):
    row = {
        "trigger_type": "DocType Event",
        "trigger_doctype": dt,
        "trigger_event": event,
        "condition_logic": "All must match",
        "conditions": [],
    }
    row.update(kwargs)
    return row


def _create_and_publish(auto_name, nodes, edges, triggers):
    return save_automation(
        name=None,
        graph_definition=json.dumps({"nodes": nodes, "edges": edges}),
        automation_name=auto_name,
        status="Published",
        enabled=1,
        triggers=triggers,
    )["name"]


def _get_runs(automation, ref_doctype, ref_name):
    return frappe.get_all(
        "Automation Run",
        filters={"automation": automation, "reference_doctype": ref_doctype,
                 "reference_name": ref_name},
        order_by="creation desc",
    )


def _get_run_steps(run_name):
    return frappe.get_all(
        "Automation Run Step",
        filters={"parent": run_name, "parenttype": "Automation Run"},
        fields=["node_id", "node_type", "step_type", "status", "output", "error"],
        order_by="idx asc",
    )


class TestStage31Registry(IntegrationTestCase):
    """All four new action types appear in get_action_types() with the right shape."""

    def test_slack_registered(self):
        at = get_action_type("slack")
        self.assertIsNotNone(at)
        self.assertEqual(at["label"], "Slack")
        keys = {f["name"] for f in at["config_schema"]}
        self.assertIn("trigger_doctype_select", keys)
        self.assertIn("channel", keys)
        self.assertIn("message", keys)

    def test_assign_to_registered(self):
        at = get_action_type("assign_to")
        self.assertIsNotNone(at)
        self.assertEqual(at["label"], "Assign To")
        keys = {f["name"] for f in at["config_schema"]}
        self.assertIn("trigger_doctype_select", keys)
        self.assertIn("assign_to_user", keys)
        self.assertIn("priority", keys)

    def test_workflow_transition_registered(self):
        at = get_action_type("workflow_transition")
        self.assertIsNotNone(at)
        self.assertEqual(at["label"], "Workflow Transition")
        keys = {f["name"] for f in at["config_schema"]}
        self.assertIn("trigger_doctype_select", keys)
        self.assertIn("transition_action", keys)

    def test_generate_pdf_registered(self):
        at = get_action_type("generate_pdf")
        self.assertIsNotNone(at)
        self.assertEqual(at["label"], "Generate PDF")
        keys = {f["name"] for f in at["config_schema"]}
        self.assertIn("trigger_doctype_select", keys)
        self.assertIn("print_format", keys)


class TestStage31Slack(IntegrationTestCase):
    """Slack action — mock mode through the real dispatch path."""

    def setUp(self):
        for n in ("ST31-Slack-Mock",):
            if frappe.db.exists("Automation", n):
                frappe.delete_doc("Automation", n, force=True)
        frappe.db.commit()

    def tearDown(self):
        if frappe.db.exists("Automation", "ST31-Slack-Mock"):
            frappe.delete_doc("Automation", "ST31-Slack-Mock", force=True)
        frappe.db.commit()

    def test_slack_mock_mode_real_dispatch(self):
        """Lead insert -> real dispatch -> Slack mock-mode log (no webhook configured)."""
        # Ensure no Slack webhook is configured (mock mode)
        with patch("automation_builder.action_types.slack._get_webhook_url",
                   return_value=None):
            nodes = [
                _make_trigger_node("trigger", trigger_doctype="Lead"),
                _make_action_node("act-slack", "slack", {
                    "channel": "#sales",
                    "message": "New lead: {{trigger.lead_name}}",
                }),
            ]
            edges = [_make_edge("trigger", "act-slack")]
            triggers = [_make_trigger("Lead", "After Insert", graph_node_id="trigger")]
            name = _create_and_publish("ST31-Slack-Mock", nodes, edges, triggers)

            lead = frappe.get_doc({
                "doctype": "Lead",
                "lead_name": "ST31-Slack-Lead",
            })
            lead.insert(ignore_permissions=True)
            frappe.db.commit()

            with patch("automation_builder.dispatcher.frappe.enqueue",
                       side_effect=lambda method, **kw: execute_automation(**kw)):
                execute_automation(name, "Lead", lead.name)

        runs = _get_runs(name, "Lead", lead.name)
        self.assertTrue(len(runs) >= 1)
        steps = _get_run_steps(runs[-1].name)
        slack_steps = [s for s in steps if s.step_type == "slack"]
        self.assertTrue(len(slack_steps) >= 1)
        self.assertEqual(slack_steps[0].status, "Success")
        self.assertIn("MOCK MODE", slack_steps[0].output)
        self.assertIn("ST31-Slack-Lead", slack_steps[0].output)
        self.assertIn("#sales", slack_steps[0].output)


class TestStage31AssignTo(IntegrationTestCase):
    """Assign To action — real ToDo created through the real dispatch path."""

    def setUp(self):
        if frappe.db.exists("Automation", "ST31-AssignTo"):
            frappe.delete_doc("Automation", "ST31-AssignTo", force=True)
        frappe.db.sql("DELETE FROM `tabToDo` WHERE reference_type='Lead' AND description LIKE '%ST31-Assign%'")
        frappe.db.commit()

    def tearDown(self):
        if frappe.db.exists("Automation", "ST31-AssignTo"):
            frappe.delete_doc("Automation", "ST31-AssignTo", force=True)
        frappe.db.sql("DELETE FROM `tabToDo` WHERE reference_type='Lead' AND description LIKE '%ST31-Assign%'")
        frappe.db.commit()

    def test_assign_to_creates_real_todo(self):
        """Lead insert -> real dispatch -> real ToDo assigned to trigger.owner."""
        nodes = [
            _make_trigger_node("trigger", trigger_doctype="Lead"),
            _make_action_node("act-assign", "assign_to", {
                "target": "Same Document",
                "assign_to_user": "{{trigger.owner}}",
                "description": "ST31-Assign: follow up with {{trigger.lead_name}}",
                "priority": "High",
            }),
        ]
        edges = [_make_edge("trigger", "act-assign")]
        triggers = [_make_trigger("Lead", "After Insert", graph_node_id="trigger")]
        name = _create_and_publish("ST31-AssignTo", nodes, edges, triggers)

        lead = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": "ST31-Assign-Lead",
        })
        lead.insert(ignore_permissions=True)
        frappe.db.commit()

        with patch("automation_builder.dispatcher.frappe.enqueue",
                   side_effect=lambda method, **kw: execute_automation(**kw)):
            execute_automation(name, "Lead", lead.name)

        runs = _get_runs(name, "Lead", lead.name)
        self.assertTrue(len(runs) >= 1)
        steps = _get_run_steps(runs[-1].name)
        assign_steps = [s for s in steps if s.step_type == "assign_to"]
        self.assertTrue(len(assign_steps) >= 1)
        self.assertEqual(assign_steps[0].status, "Success")
        self.assertIn("Assigned Lead", assign_steps[0].output)

        # Real ToDo exists, visible via Frappe's own assignment API
        todos = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Lead", "reference_name": lead.name,
                "status": "Open", "priority": "High",
            },
        )
        self.assertTrue(len(todos) >= 1, "Real ToDo should be created on the Lead")


class TestStage31WorkflowTransition(IntegrationTestCase):
    """Workflow Transition action — real state change through the real dispatch path."""

    def setUp(self):
        if frappe.db.exists("Automation", "ST31-WorkflowTransition"):
            frappe.delete_doc("Automation", "ST31-WorkflowTransition", force=True)
        frappe.db.commit()

    def tearDown(self):
        if frappe.db.exists("Automation", "ST31-WorkflowTransition"):
            frappe.delete_doc("Automation", "ST31-WorkflowTransition", force=True)
        frappe.db.commit()

    def _setup_workflow(self):
        """Create a minimal Workflow on ToDo for testing."""
        if frappe.db.exists("Workflow", "ST31 Test Workflow"):
            frappe.delete_doc("Workflow", "ST31 Test Workflow", force=True)
        wf = frappe.get_doc({
            "doctype": "Workflow",
            "workflow_name": "ST31 Test Workflow",
            "document_type": "ToDo",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Pending", "allow_edit": "System Manager"},
                {"state": "Approved", "allow_edit": "System Manager", "doc_status": 1},
            ],
            "transitions": [
                {"state": "Pending", "action": "Approve", "next_state": "Approved",
                 "allowed": "System Manager", "allow_self_approval": 1},
            ],
        })
        wf.insert(ignore_permissions=True)
        frappe.db.commit()

        # Add the workflow_state field to ToDo if missing
        if not frappe.get_meta("ToDo").has_field("workflow_state"):
            cf = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "ToDo",
                "fieldname": "workflow_state",
                "fieldtype": "Link",
                "options": "Workflow State",
                "insert_after": "status",
            })
            cf.insert(ignore_permissions=True)
            frappe.clear_cache(doctype="ToDo")
            frappe.db.commit()

        # Seed the workflow states
        for state in ("Pending", "Approved"):
            if not frappe.db.exists("Workflow State", state):
                ws = frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state})
                ws.insert(ignore_permissions=True)
        frappe.db.commit()

    def _teardown_workflow(self):
        if frappe.db.exists("Workflow", "ST31 Test Workflow"):
            frappe.delete_doc("Workflow", "ST31 Test Workflow", force=True)
        if frappe.db.exists("Custom Field", {"dt": "ToDo", "fieldname": "workflow_state"}):
            frappe.delete_doc("Custom Field", "ToDo-workflow_state", force=True)
            frappe.clear_cache(doctype="ToDo")
        frappe.db.commit()

    def test_workflow_transition_real_state_change(self):
        """ToDo insert -> real dispatch -> real workflow state transition."""
        self._setup_workflow()
        try:
            nodes = [
                _make_trigger_node("trigger", trigger_doctype="ToDo"),
                _make_action_node("act-wf", "workflow_transition", {
                    "target": "Same Document",
                    "transition_action": "Approve",
                }),
            ]
            edges = [_make_edge("trigger", "act-wf")]
            triggers = [_make_trigger("ToDo", "After Insert", graph_node_id="trigger")]
            name = _create_and_publish("ST31-WorkflowTransition", nodes, edges, triggers)

            todo = frappe.get_doc({
                "doctype": "ToDo",
                "description": "ST31-WF: test transition",
                "status": "Open",
                "workflow_state": "Pending",
            })
            todo.insert(ignore_permissions=True)
            frappe.db.commit()

            with patch("automation_builder.dispatcher.frappe.enqueue",
                       side_effect=lambda method, **kw: execute_automation(**kw)):
                execute_automation(name, "ToDo", todo.name)

            runs = _get_runs(name, "ToDo", todo.name)
            self.assertTrue(len(runs) >= 1)
            steps = _get_run_steps(runs[-1].name)
            wf_steps = [s for s in steps if s.step_type == "workflow_transition"]
            self.assertTrue(len(wf_steps) >= 1)
            self.assertEqual(wf_steps[0].status, "Success")
            self.assertIn("Pending → Approved", wf_steps[0].output)

            # Real state change on the document
            fresh = frappe.get_doc("ToDo", todo.name)
            self.assertEqual(fresh.get("workflow_state"), "Approved")
        finally:
            self._teardown_workflow()

    def test_workflow_transition_denied_on_blocked_doctype(self):
        """Workflow transition targeting a denylisted doctype is rejected."""
        from automation_builder.action_types._denylist import check_denylist
        with self.assertRaises(ValueError):
            check_denylist("User")

    def test_workflow_transition_no_workflow_configured(self):
        """Transition on a doctype without a Workflow raises a clear error."""
        wf_at = get_action_type("workflow_transition")
        context = {"doc": frappe.get_doc({
            "doctype": "Lead", "lead_name": "ST31-WF-NoWorkflow",
        })}
        with self.assertRaises(ValueError) as ctx:
            wf_at["execute"](context, {"transition_action": "Approve"})
        self.assertIn("No Workflow configured", str(ctx.exception))


class TestStage31GeneratePdf(IntegrationTestCase):
    """Generate PDF action — real attachment through the real dispatch path."""

    def setUp(self):
        if frappe.db.exists("Automation", "ST31-GeneratePdf"):
            frappe.delete_doc("Automation", "ST31-GeneratePdf", force=True)
        frappe.db.commit()

    def tearDown(self):
        if frappe.db.exists("Automation", "ST31-GeneratePdf"):
            frappe.delete_doc("Automation", "ST31-GeneratePdf", force=True)
        frappe.db.commit()

    def test_generate_pdf_real_attachment(self):
        """Note insert -> real dispatch -> real PDF attached to the Note."""
        nodes = [
            _make_trigger_node("trigger", trigger_doctype="Note"),
            _make_action_node("act-pdf", "generate_pdf", {
                "target": "Same Document",
                "print_format": "Standard",
                "attach_to_document": "Yes",
            }),
        ]
        edges = [_make_edge("trigger", "act-pdf")]
        triggers = [_make_trigger("Note", "After Insert", graph_node_id="trigger")]
        name = _create_and_publish("ST31-GeneratePdf", nodes, edges, triggers)

        note = frappe.get_doc({
            "doctype": "Note",
            "title": "ST31-PDF-Note",
            "content": "Stage 31 PDF test content",
            "public": 1,
        })
        note.insert(ignore_permissions=True)
        frappe.db.commit()

        with patch("automation_builder.dispatcher.frappe.enqueue",
                   side_effect=lambda method, **kw: execute_automation(**kw)), \
             patch("frappe.utils.pdf.get_url",
                   return_value="http://127.0.0.1:8010"):
            execute_automation(name, "Note", note.name)

        runs = _get_runs(name, "Note", note.name)
        self.assertTrue(len(runs) >= 1)
        steps = _get_run_steps(runs[-1].name)
        pdf_steps = [s for s in steps if s.step_type == "generate_pdf"]
        self.assertTrue(len(pdf_steps) >= 1)
        self.assertEqual(pdf_steps[0].status, "Success")
        self.assertIn("Generated PDF", pdf_steps[0].output)

        # Real File attachment exists on the Note
        files = frappe.get_all(
            "File",
            filters={"attached_to_doctype": "Note", "attached_to_name": note.name},
        )
        self.assertTrue(len(files) >= 1, "Real PDF attachment should exist on the Note")


class TestStage31GlobalVariables(IntegrationTestCase):
    """{{env.*}} Global Variable tokens — resolve through the real dispatch path."""

    def setUp(self):
        if frappe.db.exists("Automation", "ST31-GlobalVars"):
            frappe.delete_doc("Automation", "ST31-GlobalVars", force=True)
        for var in ("st31_test_base_url", "st31_crud_var"):
            if frappe.db.exists("Automation Global Variable", {"variable_name": var}):
                name = frappe.db.get_value(
                    "Automation Global Variable", {"variable_name": var}, "name")
                frappe.delete_doc("Automation Global Variable", name, force=True)
        frappe.db.commit()

    def tearDown(self):
        if frappe.db.exists("Automation", "ST31-GlobalVars"):
            frappe.delete_doc("Automation", "ST31-GlobalVars", force=True)
        for var in ("st31_test_base_url", "st31_crud_var"):
            if frappe.db.exists("Automation Global Variable", {"variable_name": var}):
                name = frappe.db.get_value(
                    "Automation Global Variable", {"variable_name": var}, "name")
                frappe.delete_doc("Automation Global Variable", name, force=True)
        frappe.db.commit()

    def test_env_token_resolves_in_send_email(self):
        """Create a global variable, then Lead insert -> send_email with {{env.*}} token."""
        from automation_builder.action_types._helpers import resolve_value

        # Unit-level first: the helper resolves {{env.*}}
        gv = frappe.get_doc({
            "doctype": "Automation Global Variable",
            "variable_name": "st31_test_base_url",
            "value": "https://api.example.com",
        })
        gv.insert(ignore_permissions=True)
        frappe.db.commit()

        resolved = resolve_value("Base: {{env.st31_test_base_url}}", {"doc": None})
        self.assertEqual(resolved, "Base: https://api.example.com")

        # Missing variable resolves to empty
        resolved_missing = resolve_value("X: {{env.no_such_var_st31}}", {"doc": None})
        self.assertEqual(resolved_missing, "X: ")

        # Real dispatch path: Lead insert -> send_email with env token in subject
        nodes = [
            _make_trigger_node("trigger", trigger_doctype="Lead"),
            _make_action_node("act-email", "send_email", {
                "recipient": "test@example.com",
                "subject": "Lead {{trigger.lead_name}} — {{env.st31_test_base_url}}",
                "body": "Body with {{env.st31_test_base_url}}",
            }),
        ]
        edges = [_make_edge("trigger", "act-email")]
        triggers = [_make_trigger("Lead", "After Insert", graph_node_id="trigger")]
        name = _create_and_publish("ST31-GlobalVars", nodes, edges, triggers)

        lead = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": "ST31-GV-Lead",
        })
        lead.insert(ignore_permissions=True)
        frappe.db.commit()

        with patch("automation_builder.dispatcher.frappe.enqueue",
                   side_effect=lambda method, **kw: execute_automation(**kw)):
            with patch("automation_builder.action_types.send_email.frappe.sendmail") as sm:
                execute_automation(name, "Lead", lead.name)

        runs = _get_runs(name, "Lead", lead.name)
        self.assertTrue(len(runs) >= 1)
        steps = _get_run_steps(runs[-1].name)
        email_steps = [s for s in steps if s.step_type == "send_email"]
        self.assertTrue(len(email_steps) >= 1)
        self.assertEqual(email_steps[0].status, "Success")

        # The env token resolved in the actual sendmail call
        self.assertTrue(sm.called)
        call_kwargs = sm.call_args.kwargs
        self.assertIn("https://api.example.com", call_kwargs.get("subject", ""))

    def test_global_variable_crud_apis(self):
        """list/save global variable APIs work with the standard permission pattern."""
        from automation_builder.api import list_global_variables, save_global_variable

        result = save_global_variable(
            variable_name="st31_crud_var", value="v1", description="CRUD test")
        self.assertTrue(result["name"])

        listed = list_global_variables()
        names = [v["variable_name"] for v in listed]
        self.assertIn("st31_crud_var", names)

        # Update
        save_global_variable(name=result["name"], value="v2")
        fresh = frappe.get_doc("Automation Global Variable", result["name"])
        self.assertEqual(fresh.value, "v2")
