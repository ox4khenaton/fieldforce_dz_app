# Fieldforce DZ — Objectif Vendeur
from frappe.model.document import Document
import frappe
from frappe import _

class ObjectifVendeur(Document):
    def validate(self):
        if flt(self.objectif_ca_journalier) <= 0 and flt(self.objectif_ca_mensuel) <= 0:
            frappe.throw(_("Au moins un objectif CA est requis"))

    def get_achievement(self):
        """Calculer le taux de réalisation"""
        from frappe.utils import nowdate, getdate
        today = nowdate()
        month_start = today.replace(day=1)

        achieved = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0)
            FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date >= %s AND docstatus = 1
        """, (self.vendeur, month_start))[0][0]

        target = flt(self.objectif_ca_mensuel)
        pct = (flt(achieved) / target * 100) if target > 0 else 0

        return {
            "achieved": flt(achieved),
            "target": target,
            "percentage": round(min(pct, 100), 1),
            "is_bonus_eligible": pct >= flt(self.seuil_bonus),
        }

def flt(v):
    try: return float(v or 0)
    except: return 0.0
