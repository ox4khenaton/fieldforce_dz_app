# Fieldforce DZ — Customer Overrides
# Adds GPS coordinates to Customer doctype

import frappe
from frappe import _
from frappe.utils import flt


def validate_customer(doc, method):
    """Validate GPS coordinates on Customer save"""
    # If coordinates are set, validate they're reasonable (Algeria bounds)
    if flt(doc.get("latitude")) and flt(doc.get("longitude")):
        lat = flt(doc.latitude)
        lng = flt(doc.longitude)

        # Algeria bounds: Lat 18-37, Lng -9 to 12
        if not (18 <= lat <= 37):
            frappe.throw(
                _("Latitude doit être entre 18° et 37° (Algérie). Valeur: {0}").format(lat),
                title=_("Coordonnées GPS invalides")
            )
        if not (-9 <= lng <= 12):
            frappe.throw(
                _("Longitude doit être entre -9° et 12° (Algérie). Valeur: {0}").format(lng),
                title=_("Coordonnées GPS invalides")
            )
