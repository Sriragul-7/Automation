"""Generate PDF action type — renders a Print Format to PDF via Frappe.

Uses Frappe's real print-format rendering (frappe.attach_print — the same
call the desk's Print button uses) rather than hand-rolling PDF generation.
The generated PDF can be attached to the target document and/or emailed as
an attachment in a single step.

Target document resolution follows the same "Same Document / Linked Document"
pattern as update_field.py.
"""

import frappe
from frappe.utils.print_utils import attach_print

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
        "description": "Which document to render and attach the PDF to.",
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
        "name": "print_format",
        "type": "print_format_picker",
        "label": "Print Format",
        "description": "Print Format to render (populated from the target doctype's available Print Formats).",
    },
    {
        "name": "attach_to_document",
        "type": "select",
        "label": "Attach PDF",
        "options": ["Yes", "No"],
        "default": "Yes",
        "description": "Save the generated PDF as an attachment on the target document.",
    },
    {
        "name": "email_to",
        "type": "data",
        "label": "Email PDF To",
        "description": "Optional. Also email the PDF as an attachment. Supports {{trigger.fieldname}} and {{env.varname}} tokens.",
    },
    {
        "name": "email_subject",
        "type": "data",
        "label": "Email Subject",
        "description": "Subject for the PDF email. Supports tokens.",
    },
]


def execute(context, config):
    """Generate a PDF via Frappe's print-format rendering; attach and/or email it.

    config format::

        {
            "target": "Same Document",
            "link_fieldname": "",
            "print_format": "Standard",
            "attach_to_document": "Yes",
            "email_to": "{{trigger.email}}"
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

    print_format = (config.get("print_format") or "").strip()
    if not print_format:
        raise ValueError("No print_format specified in generate_pdf action config")

    attach = (config.get("attach_to_document") or "Yes") == "Yes"
    email_to = (resolve_value(config.get("email_to", ""), context) or "").strip()
    email_subject = resolve_value(config.get("email_subject", ""), context)

    if not attach and not email_to:
        raise ValueError(
            "Nothing to do: set 'Attach PDF' to Yes and/or provide an email recipient"
        )

    file_name = None
    pdf_content = None
    if attach or email_to:
        # Real Frappe print rendering — attach_print returns {"fname", "fcontent"}
        # (the PDF bytes); it does not persist a File record itself.
        rendered = attach_print(
            target_doctype,
            target_name,
            file_name=print_format,
            print_format=print_format,
            doc=frappe.get_doc(target_doctype, target_name),
            print_letterhead=True,
        )
        file_name = (rendered or {}).get("fname") or f"{print_format}.pdf"
        pdf_content = (rendered or {}).get("fcontent")

    file_doc = None
    if attach:
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": target_doctype,
            "attached_to_name": target_name,
            "folder": "Home/Attachments",
            "is_private": 0,
        })
        file_doc.content = pdf_content
        file_doc.insert(ignore_permissions=True)

    if email_to:
        if file_doc:
            attachments = [{"fid": file_doc.name}]
        else:
            attachments = [{
                "fname": file_name,
                "fcontent": pdf_content,
            }]

        subject = email_subject or f"{target_doctype} {target_name} — PDF"
        frappe.sendmail(
            recipients=[email_to],
            subject=subject,
            message=f"Please find the attached PDF for {target_doctype} {target_name}.",
            attachments=attachments,
        )

    # Build a human-readable result log
    parts = []
    if file_doc:
        parts.append(f"attached as {file_doc.file_name} (File {file_doc.name})")
    if email_to:
        parts.append(f"emailed to {email_to}")

    return {
        "step_type": "generate_pdf",
        "status": "Success",
        "output": (
            f"Generated PDF of {target_doctype} {target_name} "
            f"({print_format}): " + "; ".join(parts)
        ),
    }


register_action_type(
    key="generate_pdf",
    label="Generate PDF",
    config_schema=CONFIG_SCHEMA,
    execute_fn=execute,
)
