# Fieldforce DZ — Sales Order Overrides
# Validates geofence, credit limits, and van stock on order creation

import frappe
from frappe import _
from frappe.utils import flt


def validate_sales_order(doc, method):
    """Called on Sales Order validate (before save)"""

    # 1. Check credit limit
    customer = frappe.get_doc("Customer", doc.customer)
    if flt(customer.credit_limit) > 0:
        from erpnext.accounts.utils import get_balance_on
        outstanding = abs(flt(get_balance_on(
            party_type="Customer",
            party=doc.customer,
            date=doc.transaction_date
        )))

        if (outstanding + flt(doc.grand_total)) > flt(customer.credit_limit):
            # Allow if sales rep has override permission
            user_roles = frappe.get_roles(frappe.session.user)
            if "Fieldforce Superviseur" not in user_roles:
                frappe.throw(
                    _(
                        "Plafond de crédit dépassé pour {0}!\n\n"
                        "Impayé actuel: <b>{1} DA</b>\n"
                        "Montant commande: <b>{2} DA</b>\n"
                        "Plafond: <b>{3} DA</b>\n\n"
                        "Le montant dépasse le plafond de <b>{4} DA</b>."
                    ).format(
                        doc.customer_name,
                        frappe.format(outstanding, {"fieldtype": "Currency", "currency": "DZD"}),
                        frappe.format(flt(doc.grand_total), {"fieldtype": "Currency", "currency": "DZD"}),
                        frappe.format(flt(customer.credit_limit), {"fieldtype": "Currency", "currency": "DZD"}),
                        frappe.format(
                            outstanding + flt(doc.grand_total) - flt(customer.credit_limit),
                            {"fieldtype": "Currency", "currency": "DZD"}
                        )
                    ),
                    title=_("Limite de crédit atteinte")
                )

    # 2. Validate stock availability in van warehouse
    if doc.set_warehouse:
        for item in doc.items:
            available = flt(frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": doc.set_warehouse},
                "actual_qty"
            ) or 0)
            reserved = flt(frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": doc.set_warehouse},
                "reserved_qty"
            ) or 0)
            available -= reserved

            if flt(item.qty) > available:
                frappe.msgprint(
                    _("Stock insuffisant pour {0} dans {1}: demandé {2}, disponible {3}").format(
                        item.item_name, doc.set_warehouse, item.qty, available
                    ),
                    indicator="red",
                    title=_("Rupture de stock")
                )

    # 3. Geofence validation (if GPS coordinates provided)
    if doc.get("gps_coordinates"):
        try:
            lat, lng = doc.gps_coordinates.split(",")
            from fieldforce_dz.api.geofence import verify_geofence
            result = verify_geofence(doc.customer, flt(lat), flt(lng))
            doc.is_geofenced = 1 if result.get("is_within_geofence") else 0

            if not result.get("is_within_geofence"):
                frappe.msgprint(
                    _(
                        "⚠️ GÉOFENCE: Le vendeur est à {0}m du client (rayon: {1}m). "
                        "Commande marquée hors géofence."
                    ).format(
                        int(result.get("distance_meters", 0)),
                        result.get("geofence_radius", 50)
                    ),
                    indicator="yellow"
                )
        except Exception:
            pass


def on_sales_order_submit(doc, method):
    """After Sales Order is submitted"""
    # Reserve stock in the van warehouse
    if doc.set_warehouse:
        for item in doc.items:
            # Update reserved qty in Bin
            bin_name = frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": doc.set_warehouse},
                "name"
            )
            if bin_name:
                current_reserved = flt(frappe.db.get_value("Bin", bin_name, "reserved_qty"))
                frappe.db.set_value("Bin", bin_name, "reserved_qty", current_reserved + flt(item.qty))

    # Log the order creation
    frappe.publish_realtime(
        event="eval_js",
        message='frappe.show_msgprint("Commande {0} soumise — stock réservé dans {1}")'.format(
            doc.name, doc.set_warehouse
        ),
        user=frappe.session.user,
    )


def on_sales_order_cancel(doc, method):
    """After Sales Order is cancelled — release reserved stock"""
    if doc.set_warehouse:
        for item in doc.items:
            bin_name = frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": doc.set_warehouse},
                "name"
            )
            if bin_name:
                current_reserved = flt(frappe.db.get_value("Bin", bin_name, "reserved_qty"))
                frappe.db.set_value(
                    "Bin", bin_name,
                    "reserved_qty", max(0, current_reserved - flt(item.qty))
                )
