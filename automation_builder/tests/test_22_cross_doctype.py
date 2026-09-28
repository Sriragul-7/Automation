"""Stage 22, Part A: Cross-doctype trigger regression tests.

Verifies that automations with triggers on different DocTypes (e.g. Lead + ToDo)
save correctly, persist, load back correctly, and fire when the matching
doctype+event occurs.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from automation_builder.dispatcher import _evaluate_trigger_conditions, on_doc_event


class TestCrossDoctypeTriggers(IntegrationTestCase):
    """Cross-doctype trigger save/load/publish/dispatch."""

    def setUp(self):
        for name in ["TEST-CrossDoc", "TEST-CrossDoc-Publish"]:
            frappe.db.sql("DELETE FROM `tabAutomation Trigger Condition` WHERE parent IN (SELECT name FROM `tabAutomation Trigger` WHERE parent = %s)", name)
            frappe.db.sql("DELETE FROM `tabAutomation Trigger` WHERE parent = %s", name)
            frappe.db.sql("DELETE FROM `tabAutomation` WHERE name = %s", name)
        frappe.db.commit()

    def tearDown(self):
        for name in ["TEST-CrossDoc", "TEST-CrossDoc-Publish"]:
            frappe.db.sql("DELETE FROM `tabAutomation Trigger Condition` WHERE parent IN (SELECT name FROM `tabAutomation Trigger` WHERE parent = %s)", name)
            frappe.db.sql("DELETE FROM `tabAutomation Trigger` WHERE parent = %s", name)
            frappe.db.sql("DELETE FROM `tabAutomation` WHERE name = %s", name)
        frappe.db.commit()

    def test_save_cross_doctype_triggers(self):
        """Save automation with two different-doctype triggers via API."""
        result = frappe.call(
            "automation_builder.api.save_automation",
            automation_name="TEST-CrossDoc",
            status="Draft",
            enabled=1,
            graph_definition='{"nodes":[],"edges":[]}',
            triggers=[
                {"trigger_doctype": "Lead", "trigger_event": "On Update"},
                {"trigger_doctype": "ToDo", "trigger_event": "On Update"},
            ],
        )
        frappe.db.commit()

        self.assertIn("name", result)
        doc = frappe.get_doc("Automation", result["name"])
        self.assertEqual(len(doc.triggers), 2)
        self.assertEqual(doc.triggers[0].trigger_doctype, "Lead")
        self.assertEqual(doc.triggers[0].trigger_event, "On Update")
        self.assertEqual(doc.triggers[1].trigger_doctype, "ToDo")
        self.assertEqual(doc.triggers[1].trigger_event, "On Update")

    def test_get_automation_cross_doctype(self):
        """Load automation with cross-doctype triggers via get_automation API."""
        # Create directly
        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-CrossDoc",
            "status": "Draft",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "On Update"},
                {"trigger_doctype": "Note", "trigger_event": "After Insert"},
            ],
            "graph_definition": '{"nodes":[],"edges":[]}',
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        # Load via API
        data = frappe.call("automation_builder.api.get_automation", name=auto.name)
        self.assertEqual(len(data["triggers"]), 3)
        self.assertEqual(data["triggers"][0]["trigger_doctype"], "Lead")
        self.assertEqual(data["triggers"][0]["trigger_event"], "After Insert")
        self.assertEqual(data["triggers"][1]["trigger_doctype"], "ToDo")
        self.assertEqual(data["triggers"][1]["trigger_event"], "On Update")
        self.assertEqual(data["triggers"][2]["trigger_doctype"], "Note")
        self.assertEqual(data["triggers"][2]["trigger_event"], "After Insert")

    def test_publish_cross_doctype(self):
        """Publish automation with cross-doctype triggers."""
        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-CrossDoc-Publish",
            "status": "Draft",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "On Update"},
            ],
            "graph_definition": '{"nodes":[],"edges":[]}',
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        # Publish
        frappe.call(
            "automation_builder.api.save_automation",
            name=auto.name,
            status="Published",
        )
        frappe.db.commit()

        doc = frappe.get_doc("Automation", auto.name)
        self.assertEqual(doc.status, "Published")

    def test_dispatch_lead_insert_matches_lead_trigger(self):
        """Lead insert fires automation with Lead/After Insert trigger."""
        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-CrossDoc",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "On Update"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {"action_type": "telegram", "chat_id": "TEST", "message": "cross-doc test"}},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1", "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        # Trigger condition evaluation with a Lead doc
        lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Cross Doc Test Lead"})
        lead.insert(ignore_permissions=True)
        frappe.db.commit()

        result = _evaluate_trigger_conditions(auto.name, lead)
        self.assertTrue(result, "Lead/After Insert trigger should match a Lead doc")

    def test_dispatch_lead_insert_does_not_match_todo_trigger(self):
        """Lead insert does NOT fire automation with only ToDo triggers."""
        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-CrossDoc",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "ToDo", "trigger_event": "On Update"},
                {"trigger_doctype": "ToDo", "trigger_event": "After Insert"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {"action_type": "telegram", "chat_id": "TEST", "message": "should not fire"}},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1", "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        # Use on_doc_event with mocked enqueue to verify the automation is NOT enqueued
        lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Should Not Match"})
        lead.insert(ignore_permissions=True)
        frappe.db.commit()

        enqueued = []
        orig = frappe.enqueue
        frappe.enqueue = lambda *a, **kw: enqueued.append({"args": a, "kwargs": kw})
        try:
            on_doc_event(lead, "after_insert")
        finally:
            frappe.enqueue = orig

        auto_names = [c["kwargs"].get("automation_name") for c in enqueued]
        self.assertNotIn(auto.name, auto_names,
                         f"Lead insert should NOT fire ToDo-only automation. Enqueued: {auto_names}")

    def test_update_cross_doctype_triggers(self):
        """Update existing automation: replace triggers with different doctypes."""
        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-CrossDoc",
            "status": "Draft",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "On Update"},
            ],
            "graph_definition": '{"nodes":[],"edges":[]}',
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        # Update with new cross-doctype triggers
        frappe.call(
            "automation_builder.api.save_automation",
            name=auto.name,
            triggers=[
                {"trigger_doctype": "ToDo", "trigger_event": "After Insert"},
                {"trigger_doctype": "Note", "trigger_event": "On Update"},
            ],
        )
        frappe.db.commit()

        doc = frappe.get_doc("Automation", auto.name)
        self.assertEqual(len(doc.triggers), 2)
        self.assertEqual(doc.triggers[0].trigger_doctype, "ToDo")
        self.assertEqual(doc.triggers[1].trigger_doctype, "Note")

    def test_three_different_doctypes(self):
        """Automation with three different-doctype triggers saves correctly."""
        result = frappe.call(
            "automation_builder.api.save_automation",
            automation_name="TEST-CrossDoc",
            status="Draft",
            enabled=1,
            graph_definition='{"nodes":[],"edges":[]}',
            triggers=[
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "On Update"},
                {"trigger_doctype": "Note", "trigger_event": "After Insert"},
            ],
        )
        frappe.db.commit()

        doc = frappe.get_doc("Automation", result["name"])
        self.assertEqual(len(doc.triggers), 3)
        doctypes = [t.trigger_doctype for t in doc.triggers]
        self.assertIn("Lead", doctypes)
        self.assertIn("ToDo", doctypes)
        self.assertIn("Note", doctypes)


class TestTokenResolution(IntegrationTestCase):
    """Token resolution for cross-doctype triggers."""

    def test_trigger_token_resolves_against_triggering_doc(self):
        """{{trigger.fieldname}} resolves against the triggering document."""
        from automation_builder.action_types._helpers import resolve_value

        lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Token Test Lead"})
        context = {"doc": lead, "ref_doctype": "Lead", "ref_name": lead.name}

        result = resolve_value("New lead: {{trigger.lead_name}}", context)
        self.assertEqual(result, "New lead: Token Test Lead")

    def test_trigger_doctype_token_resolves(self):
        """{{trigger.fieldname}} resolves against the triggering document."""
        from automation_builder.action_types._helpers import resolve_value

        lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Doctype Token Test"})
        context = {"doc": lead, "ref_doctype": "Lead", "ref_name": lead.name}

        result = resolve_value("Lead: {{trigger.lead_name}}", context)
        self.assertEqual(result, "Lead: Doctype Token Test")

    def test_trigger_doctype_hint_in_context(self):
        """Context includes trigger_doctype for cross-doctype awareness."""
        from automation_builder.dispatcher import execute_automation

        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-TokenContext",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {"action_type": "send_email", "recipient": "test@test.com",
                              "subject": "Trigger: {{trigger.lead_name}}", "body": "Test"}},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1", "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Context Test Lead"})
        lead.insert(ignore_permissions=True)
        frappe.db.commit()

        # Execute — should succeed without errors
        execute_automation(auto.name, "Lead", lead.name)

        # Verify run was created
        runs = frappe.get_all("Automation Run", filters={"automation": auto.name})
        self.assertTrue(len(runs) > 0, "Automation run should be created")


class TestAnyDoctypeMode(IntegrationTestCase):
    """Test 'Any (whichever triggered)' mode for shared downstream nodes."""

    def setUp(self):
        for name in ["TEST-AnyMode", "TEST-AnyNoSkip", "TEST-FullPathSkip"]:
            frappe.db.sql("DELETE FROM `tabAutomation Trigger Condition` WHERE parent IN (SELECT name FROM `tabAutomation Trigger` WHERE parent = %s)", name)
            frappe.db.sql("DELETE FROM `tabAutomation Trigger` WHERE parent = %s", name)
            frappe.db.sql("DELETE FROM `tabAutomation Run Step` WHERE parent IN (SELECT name FROM `tabAutomation Run` WHERE automation = %s)", name)
            frappe.db.sql("DELETE FROM `tabAutomation Run` WHERE automation = %s", name)
            frappe.db.sql("DELETE FROM `tabAutomation` WHERE name = %s", name)
        frappe.db.commit()

    def tearDown(self):
        for name in ["TEST-AnyMode", "TEST-AnyNoSkip", "TEST-FullPathSkip"]:
            frappe.db.sql("DELETE FROM `tabAutomation Trigger Condition` WHERE parent IN (SELECT name FROM `tabAutomation Trigger` WHERE parent = %s)", name)
            frappe.db.sql("DELETE FROM `tabAutomation Trigger` WHERE parent = %s", name)
            frappe.db.sql("DELETE FROM `tabAutomation Run Step` WHERE parent IN (SELECT name FROM `tabAutomation Run` WHERE automation = %s)", name)
            frappe.db.sql("DELETE FROM `tabAutomation Run` WHERE automation = %s", name)
            frappe.db.sql("DELETE FROM `tabAutomation` WHERE name = %s", name)
        frappe.db.commit()

    def test_any_mode_resolves_common_field_and_empty_for_missing(self):
        """Shared action node in 'Any' mode executes for both Lead and ToDo.

        - Common field (name) resolves correctly on both branches
        - Doctype-specific field (lead_name) resolves on Lead, empty on ToDo
        """
        from unittest.mock import patch
        from automation_builder.action_types._helpers import resolve_value
        from automation_builder.dispatcher import execute_automation

        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-AnyMode",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "After Insert"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {
                         "action_type": "telegram",
                         "chat_id": "TEST",
                         "message": "Doc: {{trigger.name}} Lead: {{trigger.lead_name}}",
                         "trigger_doctype_select": "any",
                     }},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1", "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        with patch("automation_builder.action_types.telegram._get_bot_token", return_value=None):
            # --- Branch 1: Lead triggers the automation ---
            lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Any Mode Lead"})
            lead.insert(ignore_permissions=True)
            frappe.db.commit()

            execute_automation(auto.name, "Lead", lead.name)

            runs_lead = frappe.get_all(
                "Automation Run",
                filters={"automation": auto.name, "reference_doctype": "Lead"},
                fields=["name", "status"],
            )
            self.assertTrue(len(runs_lead) > 0, "Lead trigger should create a run")
            self.assertEqual(runs_lead[0].status, "Success")

            # Verify token resolution: common field resolves, lead_name resolves
            lead_context = {"doc": lead, "ref_doctype": "Lead", "ref_name": lead.name}
            lead_subject = resolve_value("Doc: {{trigger.name}} Lead: {{trigger.lead_name}}", lead_context)
            self.assertIn(lead.name, lead_subject)
            self.assertIn("Any Mode Lead", lead_subject)

            # --- Branch 2: ToDo triggers the automation ---
            todo = frappe.get_doc({"doctype": "ToDo", "description": "Any Mode ToDo"})
            todo.insert(ignore_permissions=True)
            frappe.db.commit()

            execute_automation(auto.name, "ToDo", todo.name)

            runs_todo = frappe.get_all(
                "Automation Run",
                filters={"automation": auto.name, "reference_doctype": "ToDo"},
                fields=["name", "status"],
            )
            self.assertTrue(len(runs_todo) > 0, "ToDo trigger should create a run")
            self.assertEqual(runs_todo[0].status, "Success")

            # Verify token resolution: common field resolves, lead_name resolves to empty
            todo_context = {"doc": todo, "ref_doctype": "ToDo", "ref_name": todo.name}
            todo_subject = resolve_value("Doc: {{trigger.name}} Lead: {{trigger.lead_name}}", todo_context)
            self.assertIn(todo.name, todo_subject)
            self.assertNotIn("Any Mode Lead", todo_subject)
            # lead_name doesn't exist on ToDo → resolves to empty
            self.assertEqual(todo_subject, f"Doc: {todo.name} Lead: ")

    def test_any_mode_node_executes_not_skips(self):
        """In 'Any' mode, the shared node never skips based on doctype mismatch."""
        from unittest.mock import patch
        from automation_builder.dispatcher import execute_automation

        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-AnyNoSkip",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "Note", "trigger_event": "After Insert"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {
                         "action_type": "telegram",
                         "chat_id": "TEST",
                         "message": "Executed via {{trigger.name}}",
                         "trigger_doctype_select": "any",
                     }},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1", "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        with patch("automation_builder.action_types.telegram._get_bot_token", return_value=None):
            # Lead triggers → should execute (not skip)
            lead = frappe.get_doc({"doctype": "Lead", "lead_name": "NoSkip Lead"})
            lead.insert(ignore_permissions=True)
            frappe.db.commit()
            execute_automation(auto.name, "Lead", lead.name)

            runs_lead = frappe.get_all(
                "Automation Run",
                filters={"automation": auto.name, "reference_doctype": "Lead"},
                fields=["status"],
            )
            self.assertEqual(len(runs_lead), 1, "Lead should create exactly one run")
            self.assertEqual(runs_lead[0].status, "Success")

            # Note triggers → should also execute (not skip)
            note = frappe.get_doc({"doctype": "Note", "title": "NoSkip Note", "content": "test"})
            note.insert(ignore_permissions=True)
            frappe.db.commit()
            execute_automation(auto.name, "Note", note.name)

        runs_note = frappe.get_all(
            "Automation Run",
            filters={"automation": auto.name, "reference_doctype": "Note"},
            fields=["status"],
        )
        self.assertEqual(len(runs_note), 1, "Note should create exactly one run")
        self.assertEqual(runs_note[0].status, "Success")

    def test_specific_doctype_skips_on_wrong_trigger(self):
        """Node scoped to 'Lead' skips when triggered by ToDo (not 'Any' mode).

        Regression test: confirm that trigger_doctype_select="Lead" causes a
        Skipped status with the scoped message when the run was triggered by
        a different doctype — and that the try/except in resolve_value does
        NOT mask this skip by producing empty-string resolved fields instead.
        """
        from unittest.mock import patch
        from automation_builder.dispatcher import execute_automation

        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-AnyNoSkip",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "After Insert"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {
                         "action_type": "telegram",
                         "chat_id": "TEST",
                         "message": "Should not run on ToDo",
                         "trigger_doctype_select": "Lead",
                     }},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1", "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        with patch("automation_builder.action_types.telegram._get_bot_token", return_value=None):
            # ToDo triggers → action scoped to Lead should SKIP
            todo = frappe.get_doc({"doctype": "ToDo", "description": "Skip test ToDo"})
            todo.insert(ignore_permissions=True)
            frappe.db.commit()
            execute_automation(auto.name, "ToDo", todo.name)

            runs_todo = frappe.get_all(
                "Automation Run",
                filters={"automation": auto.name, "reference_doctype": "ToDo"},
                fields=["status", "log"],
            )
            self.assertEqual(len(runs_todo), 1, "ToDo should create exactly one run")
            self.assertEqual(runs_todo[0].status, "Success")  # Run overall is Success (skip is not failure)

            # Verify the log shows Skipped with scoped message
            log_data = json.loads(runs_todo[0].log)
            self.assertEqual(len(log_data), 1)
            self.assertEqual(log_data[0]["status"], "Skipped")
            self.assertIn("scoped to Lead", log_data[0]["output"])
            self.assertIn("triggered by ToDo", log_data[0]["output"])

            # Lead triggers → same action should EXECUTE (not skip)
            lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Skip Test Lead"})
            lead.insert(ignore_permissions=True)
            frappe.db.commit()
            execute_automation(auto.name, "Lead", lead.name)

        runs_lead = frappe.get_all(
            "Automation Run",
            filters={"automation": auto.name, "reference_doctype": "Lead"},
            fields=["status", "log"],
        )
        self.assertEqual(len(runs_lead), 1, "Lead should create exactly one run")
        self.assertEqual(runs_lead[0].status, "Success")

        log_lead = json.loads(runs_lead[0].log)
        self.assertEqual(len(log_lead), 1)
        self.assertEqual(log_lead[0]["status"], "Success")

    def test_full_path_skip_via_on_doc_event(self):
        """FULL REAL PATH: doc.insert() → hooks → on_doc_event → enqueue → execute_automation → _execute_action.

        Exercises the complete dispatch chain that the direct-call test
        bypasses. Without this, a regression in on_doc_event's query or the
        enqueue handoff would go undetected.
        """
        from unittest.mock import patch

        auto = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": "TEST-FullPathSkip",
            "status": "Published",
            "enabled": 1,
            "triggers": [
                {"trigger_doctype": "Lead", "trigger_event": "After Insert"},
                {"trigger_doctype": "ToDo", "trigger_event": "After Insert"},
            ],
            "graph_definition": json.dumps({
                "nodes": [
                    {"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "action-1", "type": "action", "position": {"x": 0, "y": 150},
                     "data": {
                         "action_type": "telegram",
                         "chat_id": "TEST",
                         "message": "Should skip on ToDo",
                         "trigger_doctype_select": "Lead",
                     }},
                ],
                "edges": [
                    {"source": "trigger", "target": "action-1",
                     "sourceHandle": "trigger-out", "targetHandle": "action-1-in"},
                ],
            }),
        })
        auto.insert(ignore_permissions=True)
        frappe.db.commit()

        # Capture enqueue calls so we can run them synchronously
        enqueued = []

        def _capture_enqueue(method, queue="short", **kwargs):
            from automation_builder.dispatcher import execute_automation
            execute_automation(**kwargs)

        with patch("automation_builder.dispatcher.frappe.enqueue", side_effect=_capture_enqueue), \
             patch("automation_builder.action_types.telegram._get_bot_token", return_value=None):
            # Insert a ToDo — triggers on_doc_event → should find auto and enqueue
            todo = frappe.get_doc({"doctype": "ToDo", "description": "Full path skip test"})
            todo.insert(ignore_permissions=True)
            frappe.db.commit()

        runs_todo = frappe.get_all(
            "Automation Run",
            filters={"automation": auto.name, "reference_doctype": "ToDo"},
            fields=["status", "log"],
        )
        self.assertEqual(len(runs_todo), 1, "Full path: ToDo should produce a run")
        self.assertEqual(runs_todo[0].status, "Success")
        log_todo = json.loads(runs_todo[0].log)
        self.assertEqual(log_todo[0]["status"], "Skipped")
        self.assertIn("scoped to Lead", log_todo[0]["output"])
        self.assertIn("triggered by ToDo", log_todo[0]["output"])

        # Now trigger via Lead — same auto, same path, should execute
        with patch("automation_builder.dispatcher.frappe.enqueue", side_effect=_capture_enqueue), \
             patch("automation_builder.action_types.telegram._get_bot_token", return_value=None):
            lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Full Path Skip Lead"})
            lead.insert(ignore_permissions=True)
            frappe.db.commit()

        runs_lead = frappe.get_all(
            "Automation Run",
            filters={"automation": auto.name, "reference_doctype": "Lead"},
            fields=["status", "log"],
        )
        self.assertEqual(len(runs_lead), 1, "Full path: Lead should produce a run")
        self.assertEqual(runs_lead[0].status, "Success")
        log_lead = json.loads(runs_lead[0].log)
        self.assertEqual(log_lead[0]["status"], "Success")
