# Fieldforce DZ — Journal de Visite
from frappe.model.document import Document
import frappe
from frappe import _
from frappe.utils import now_datetime

class JournaldeVisite(Document):
    def validate(self):
        # Vérifier que les coordonnées GPS sont présentes
        if not self.gps_latitude or not self.gps_longitude:
            frappe.throw(_("Coordonnées GPS requises pour le journal de visite"))

        # Vérifier la géofence si c'est un check-in
        if self.statut == "En cours" and not self.dans_geofence:
            frappe.msgprint(
                _("Attention: Vous êtes à {0}m du client (rayon autorisé: configuré dans l'affectation dépôt)").format(
                    int(self.distance_client or 0)
                ),
                indicator="red",
                title=_("Hors zone géofence")
            )

    def on_submit(self):
        # Mettre à jour le statut de la visite dans la tournée
        self.update_beat_customer_status()

    def on_cancel(self):
        self.update_beat_customer_status(remove=True)

    def update_beat_customer_status(self, remove=False):
        """Mettre à jour le statut du client dans la tournée"""
        if not self.tournee or not self.client:
            return

        tournee = frappe.get_doc("Tournee de Vente", self.tournee)
        for c in tournee.customers:
            if c.client == self.client:
                c.db_set("dernier_statut_visite", "Visité" if not remove else "En attente")
                c.db_set("derniere_date_visite", now_datetime() if not remove else None)
                break
