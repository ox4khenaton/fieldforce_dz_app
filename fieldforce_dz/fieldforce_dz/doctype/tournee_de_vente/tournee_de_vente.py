# Fieldforce DZ — Tournee de Vente
from frappe.model.document import Document
import frappe
from frappe import _

class Tourneedevente(Document):
    def validate(self):
        # Vérifier l'unicité: une seule tournée par vendeur par jour
        existing = frappe.db.exists(
            "Tournee de Vente",
            {"vendeur": self.vendeur, "jour_semaine": self.jour_semaine,
             "name": ["!=", self.name], "is_active": 1}
        )
        if existing:
            frappe.throw(
                _("Une tournée active existe déjà pour ce vendeur le {0}: {1}").format(
                    self.jour_semaine, existing
                ),
                title=_("Tournée en doublon")
            )

        # Vérifier que tous les clients ont des coordonnées GPS
        for c in self.customers:
            if not flt(c.latitude) or not flt(c.longitude):
                frappe.msgprint(
                    _("Attention: {0} n'a pas de coordonnées GPS configurées").format(c.client),
                    indicator="yellow"
                )

    def on_submit(self):
        # Marquer les visites comme planifiées
        pass

def flt(v):
    try: return float(v or 0)
    except: return 0.0
