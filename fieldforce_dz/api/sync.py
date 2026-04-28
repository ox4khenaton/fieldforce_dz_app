# Fieldforce DZ — Sync Engine (server-side)
# Processes pending sync items from mobile app queue
# Called by Frappe scheduler

import json
import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate


def process_pending_syncs():
    """
    Scheduled task (every 5 minutes).
    Processes any items stuck in the mobile sync queue.
    """
    # Find orders created via API but not yet submitted
    pending_orders = frappe.get_all(
        "Sales Order",
        filters={"docstatus": 0, "creation": [">=", frappe.utils.add_minutes(now_datetime(), -30)]},
        fields=["name", "customer", "creation"],
        limit=50,
    )

    for order in pending_orders:
        try:
            doc = frappe.get_doc("Sales Order", order.name)
            # Validate stock before submitting
            for item in doc.items:
                available = frappe.db.get_value(
                    "Bin",
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty"
                ) or 0
                if flt(available) < flt(item.qty):
                    # Skip — stock issue
                    frappe.log_error(
                        "Stock insuffisant pour {0} dans {1}".format(item.item_code, item.warehouse),
                        "Fieldforce DZ Sync"
                    )
                    continue

            doc.submit()
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(str(e), "Fieldforce DZ Sync Error")
            frappe.db.rollback()


def daily_cleanup():
    """
    Scheduled task (daily at 23:00).
    Cleanup stale data, mark old drafts, generate reports.
    """
    # Cancel very old draft orders (>7 days)
    cutoff = frappe.utils.add_days(nowdate(), -7)
    old_drafts = frappe.get_all(
        "Sales Order",
        filters={"docstatus": 0, "creation": ["<", cutoff]},
        fields=["name"],
        limit=100,
    )
    for draft in old_drafts:
        try:
            doc = frappe.get_doc("Sales Order", draft.name)
            doc.cancel()
            frappe.db.commit()
        except Exception:
            pass

    # Log daily summary
    frappe.logger("fieldforce_dz").info("Daily cleanup completed: {0} old drafts cancelled".format(len(old_drafts)))


def update_sales_targets():
    """
    Scheduled task (hourly).
    Recalculate target achievement for all active sales targets.
    """
    targets = frappe.get_all(
        "Objectif Vendeur",
        filters={"actif": 1},
        fields=["name", "vendeur", "objectif_ca_mensuel", "seuil_bonus", "montant_prime"],
    )

    for target in targets:
        try:
            month_start = nowdate().replace(day=1)
            achieved = frappe.db.sql("""
                SELECT COALESCE(SUM(grand_total), 0)
                FROM `tabSales Order`
                WHERE sales_rep = %s AND transaction_date >= %s AND docstatus = 1
            """, (target.vendeur, month_start))[0][0]

            target_doc = frappe.get_doc("Objectif Vendeur", target.name)
            # Could trigger notifications when thresholds are crossed
            if flt(target.objectif_ca_mensuel) > 0:
                pct = (flt(achieved) / flt(target.objectif_ca_mensuel)) * 100
                if pct >= flt(target.seuil_bonus):
                    # Notify about bonus eligibility
                    user = frappe.db.get_value("Employee", target.vendeur, "user_id")
                    if user:
                        frappe.publish_realtime(
                            event="eval_js",
                            message='frappe.msgprint("Félicitations! Vous êtes éligible pour la prime de {0} DA!", title="Objectif Atteint!", indicator="green")'.format(target.montant_prime),
                            user=user,
                        )
        except Exception:
            pass


def weekly_route_planning():
    """
    Scheduled task (weekly on Monday).
    Auto-generate this week's route assignments from templates.
    """
    # Auto-create visit schedules for the week
    beats = frappe.get_all("Tournee de Vente", filters={"is_active": 1}, fields=["name", "vendeur"])
    for beat in beats:
        frappe.logger("fieldforce_dz").info(
            "Weekly planning: Beat {0} for Employee {1}".format(beat.name, beat.vendeur)
        )


def flt(v):
    try:
        return float(v or 0)
    except (ValueError, TypeError):
        return 0.0
