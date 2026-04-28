# Fieldforce DZ — Dépense Terrain
from frappe.model.document import Document
import frappe
from frappe import _
from frappe.utils import nowdate

class DepenseTerrain(Document):
    def validate(self):
        if not self.type_depense:
            frappe.throw(_("Type de dépense requis"))
        if flt(self.montant) <= 0:
            frappe.throw(_("Le montant doit être supérieur à 0"))

    def on_submit(self):
        self.create_expense_claim()

    def create_expense_claim(self):
        try:
            mapping = {"Carburant": "Fuel", "Repas": "Food", "Péages": "Travel", "Parking": "Parking", "Téléphone": "Communication", "Autre": "Miscellaneous"}
            expense_type = mapping.get(self.type_depense, "Miscellaneous")
            if not frappe.db.exists("Expense Claim Type", expense_type):
                types = frappe.get_all("Expense Claim Type", limit=1)
                if types: expense_type = types[0].name
                else: return

            claim = frappe.new_doc("Expense Claim")
            claim.employee = self.vendeur
            claim.posting_date = self.date or nowdate()
            claim.remark = self.notes or _("Dépense terrain: {0}").format(self.type_depense)
            claim.append("expenses", {"expense_date": self.date or nowdate(), "expense_type": expense_type, "amount": flt(self.montant), "description": self.notes or self.type_depense})
            claim.run_method("set_missing_values")
            claim.insert(ignore_permissions=True)
            self.db_set("expense_claim", claim.name)
        except Exception as e:
            frappe.log_error(str(e), "Fieldforce DZ Expense Claim")

def flt(v):
    try: return float(v or 0)
    except: return 0.0
