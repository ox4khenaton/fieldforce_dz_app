# Fieldforce DZ — Post-install / Post-migrate hooks
# Creates roles, settings, and custom fields on Customer

import frappe


def after_install():
    """Run after app is installed"""
    _create_roles()
    _create_custom_fields()
    _create_settings()
    frappe.db.commit()


def after_migrate():
    """Run after bench migrate"""
    _create_custom_fields()
    frappe.db.commit()


def before_uninstall():
    """Run before app is uninstalled"""
    pass


def _create_roles():
    """Create Fieldforce roles"""
    for role_name in ["Fieldforce Vendeur", "Fieldforce Superviseur"]:
        if not frappe.db.exists("Role", role_name):
            role = frappe.get_doc({"doctype": "Role", "role_name": role_name})
            role.insert(ignore_permissions=True)


def _create_custom_fields():
    """Add GPS fields to Customer and Sales Order doctypes"""
    custom_fields = {
        "Customer": [
            {
                "fieldname": "latitude",
                "label": "Latitude",
                "fieldtype": "Float",
                "insert_after": "territory",
                "description": "GPS Latitude du client (requis pour géofence)",
            },
            {
                "fieldname": "longitude",
                "label": "Longitude",
                "fieldtype": "Float",
                "insert_after": "latitude",
                "description": "GPS Longitude du client (requis pour géofence)",
            },
        ],
        "Sales Order": [
            {
                "fieldname": "is_geofenced",
                "label": "Géofencé",
                "fieldtype": "Check",
                "insert_after": "order_type",
                "description": "Commande créée dans la zone géofence",
            },
            {
                "fieldname": "gps_coordinates",
                "label": "Coordonnées GPS",
                "fieldtype": "Data",
                "insert_after": "is_geofenced",
                "description": "Latitude,Longitude du téléphone au moment de la commande",
            },
        ],
    }

    for doctype, fields in custom_fields.items():
        for field in fields:
            if not frappe.db.exists(
                "Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}
            ):
                frappe.get_doc({
                    "doctype": "Custom Field",
                    "dt": doctype,
                    **field,
                }).insert(ignore_permissions=True)


def _create_settings():
    """Create Fieldforce DZ Settings singleton"""
    pass  # Optional: create a Settings DocType later
