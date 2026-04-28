# Fieldforce DZ — Affectation Dépôt Mobile
from frappe.model.document import Document
import frappe
from frappe import _

class AffectationDepotMobile(Document):
    def validate(self):
        # Vérifier qu'un seul dépôt mobile actif par vendeur
        existing = frappe.db.exists(
            "Affectation Depot Mobile",
            {"vendeur": self.vendeur, "is_active": 1, "name": ["!=", self.name]}
        )
        if existing:
            frappe.throw(
                _("Ce vendeur a déjà une affectation active: {0}").format(existing),
                title=_("Affectation en doublon")
            )

        # Vérifier que le dépôt existe
        if not frappe.db.exists("Warehouse", self.depot_mobile):
            frappe.throw(_("Dépôt mobile introuvable: {0}").format(self.depot_mobile))

    def on_trash(self):
        # Désactiver au lieu de supprimer
        if self.is_active:
            frappe.throw(_("Veuillez désactiver l'affectation avant de la supprimer"))
