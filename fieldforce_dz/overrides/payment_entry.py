# Fieldforce DZ — Payment Entry Overrides
# Links payments to mobile app sales orders

import frappe
from frappe import _


def validate_payment_entry(doc, method):
    """Validate payment against mobile orders"""
    # Ensure the party is a Customer for field sales payments
    if doc.payment_type == "Receive" and doc.party_type == "Customer":
        # Verify the customer exists
        if not frappe.db.exists("Customer", doc.party):
            frappe.throw(
                _("Client {0} introuvable").format(doc.party),
                title=_("Client invalide")
            )


def on_payment_submit(doc, method):
    """After payment is submitted — update outstanding"""
    # Log the payment for mobile sync tracking
    frappe.logger("fieldforce_dz").info(
        "Payment Entry submitted: {0} — Customer: {1} — Amount: {2}".format(
            doc.name, doc.party, doc.paid_amount
        )
    )
