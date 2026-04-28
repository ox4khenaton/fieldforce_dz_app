# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
import json
from frappe import _
from frappe.utils import nowdate, today, now_datetime, get_datetime, add_days, flt, cint

def get_context(context):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Vous devez être connecté"), frappe.PermissionError)
    
    context.brand_html = "🚚 FieldForce Admin"
    context.title = "Admin - Suivi des Vendeurs"
    
    today_date = today()
    
    # Get all active sales reps (Employees with Sales role)
    sales_reps = frappe.db.sql("""
        SELECT 
            e.name, e.employee_name, e.designation, e.department, e.status,
            e.image, e.company_email, e.cell_number
        FROM `tabEmployee` e
        WHERE e.status = 'Active' 
            AND (e.designation LIKE '%Vendeur%' OR e.designation LIKE '%Commercial%' OR e.designation LIKE '%Agent%')
        ORDER BY e.employee_name
    """, as_dict=True)
    
    context.sales_reps = sales_reps or []
    
    # Today's metrics per seller
    seller_metrics = []
    for rep in sales_reps:
        # Orders today
        orders = frappe.db.sql("""
            SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as total,
                   COALESCE(SUM(perpaid_amount), 0) as collected
            FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
        """, (rep.name, today_date), as_dict=True)[0]
        
        # Collections today (via Payment Entry)
        payments = frappe.db.sql("""
            SELECT COUNT(*) as count, COALESCE(SUM(paid_amount), 0) as total
            FROM `tabPayment Entry`
            WHERE party_type = 'Customer' 
                AND owner LIKE %s
                AND posting_date = %s 
                AND docstatus = 1
        """, (f"%{rep.name}%", today_date), as_dict=True)[0]
        
        # Visits today
        visits = frappe.db.sql("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN statut = 'Visité' THEN 1 ELSE 0 END) as completed
            FROM `tabJournal de Visite`
            WHERE creation LIKE %s
        """, (f"{today_date}%",), as_dict=True)[0]
        
        # Products sold today (top 5)
        top_products = frappe.db.sql("""
            SELECT soi.item_name, soi.item_code, SUM(soi.qty) as qty, SUM(soi.amount) as amount
            FROM `tabSales Order Item` soi
            INNER JOIN `tabSales Order` so ON so.name = soi.parent
            WHERE so.sales_rep = %s AND so.transaction_date = %s AND so.docstatus = 1
            GROUP BY soi.item_code, soi.item_name
            ORDER BY amount DESC
            LIMIT 5
        """, (rep.name, today_date), as_dict=True)
        
        # Payment methods breakdown
        payment_breakdown = frappe.db.sql("""
            SELECT 
                SUM(CASE WHEN mode_of_payment IN ('Espèces', 'Cash') THEN paid_amount ELSE 0 END) as cash,
                SUM(CASE WHEN mode_of_payment NOT IN ('Espèces', 'Cash') THEN paid_amount ELSE 0 END) as credit,
                SUM(paid_amount) as total
            FROM `tabPayment Entry`
            WHERE posting_date = %s AND docstatus = 1 AND payment_type = 'Receive'
        """, (today_date,), as_dict=True)[0]
        
        # Get status (online/offline based on recent checkin)
        last_checkin = frappe.db.sql("""
            SELECT check_in FROM `tabAttendance`
            WHERE employee = %s AND attendance_date = %s
            ORDER BY creation DESC LIMIT 1
        """, (rep.name, today_date), as_dict=True)
        
        online = False
        if last_checkin and last_checkin[0].check_in:
            checkin_time = get_datetime(last_checkin[0].check_in)
            # If checked in within last 30 minutes, consider online
            online = (now_datetime() - checkin_time).seconds < 1800
        
        seller_metrics.append({
            "id": rep.name,
            "name": rep.employee_name,
            "designation": rep.designation,
            "orders_count": orders.count if orders else 0,
            "orders_total": orders.total if orders else 0,
            "collected": orders.collected if orders else 0,
            "visits_total": visits.total if visits else 0,
            "visits_completed": visits.completed if visits else 0,
            "top_products": top_products or [],
            "cash_payment": payment_breakdown.cash if payment_breakdown else 0,
            "credit_payment": payment_breakdown.credit if payment_breakdown else 0,
            "online": online,
        })
    
    context.seller_metrics = seller_metrics
    
    # Team totals
    team_orders = frappe.db.sql("""
        SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as total
        FROM `tabSales Order`
        WHERE transaction_date = %s AND docstatus = 1
    """, (today_date,), as_dict=True)[0]
    
    team_collections = frappe.db.sql("""
        SELECT COALESCE(SUM(paid_amount), 0) as total
        FROM `tabPayment Entry`
        WHERE posting_date = %s AND docstatus = 1 AND payment_type = 'Receive'
    """, (today_date,), as_dict=True)[0]
    
    team_visits = frappe.db.sql("""
        SELECT COUNT(*) as total
        FROM `tabJournal de Visite`
        WHERE creation LIKE %s
    """, (f"{today_date}%",), as_dict=True)[0]
    
    context.team_totals = {
        "orders": team_orders.count if team_orders else 0,
        "sales": team_orders.total if team_orders else 0,
        "collections": team_collections.total if team_collections else 0,
        "visits": team_visits.total if team_visits else 0,
    }
    
    context.today_date = today_date


@frappe.whitelist()
def get_seller_details(seller_id, date=None):
    """Obtenir les détails complets d'un vendeur"""
    if not date:
        date = today()
    
    # Orders
    orders = frappe.get_all(
        "Sales Order",
        filters={"sales_rep": seller_id, "transaction_date": date, "docstatus": 1},
        fields=["name", "customer_name", "grand_total", "perpaid_amount", "status", "transaction_date"],
        order_by="creation desc"
    )
    
    # Payments
    payments = frappe.get_all(
        "Payment Entry",
        filters={"posting_date": date, "docstatus": 1, "payment_type": "Receive"},
        fields=["name", "party", "paid_amount", "mode_of_payment", "posting_date"]
    )
    
    # Visit logs
    visits = frappe.get_all(
        "Journal de Visite",
        filters={"creation": ["like", f"{date}%"]},
        fields=["name", "client", "statut", "check_in_time", "check_out_time", "notes"],
        order_by="creation desc"
    )
    
    # Products sold
    products = frappe.db.sql("""
        SELECT soi.item_name, soi.item_code, SUM(soi.qty) as qty, SUM(soi.amount) as amount
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.sales_rep = %s AND so.transaction_date = %s AND so.docstatus = 1
        GROUP BY soi.item_code, soi.item_name
        ORDER BY amount DESC
    """, (seller_id, date), as_dict=True)
    
    return {
        "orders": orders,
        "payments": payments,
        "visits": visits,
        "products": products,
    }


@frappe.whitelist()
def get_realtime_activity(hours=2):
    """Activité en temps réel des dernières heures"""
    from_time = add_days(now_datetime(), -hours/24)
    
    # Recent orders
    recent_orders = frappe.db.sql(f"""
        SELECT so.name, so.customer_name, so.grand_total, so.perpaid_amount,
               e.employee_name as seller, so.transaction_date as time
        FROM `tabSales Order` so
        LEFT JOIN `tabEmployee` e ON e.name = so.sales_rep
        WHERE so.docstatus = 1 AND so.creation >= %s
        ORDER BY so.creation DESC
        LIMIT 20
    """, (from_time,), as_dict=True)
    
    # Recent payments
    recent_payments = frappe.db.sql(f"""
        SELECT pe.name, pe.party, pe.paid_amount, pe.mode_of_payment,
               pe.creation as time
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1 AND pe.creation >= %s
        ORDER BY pe.creation DESC
        LIMIT 20
    """, (from_time,), as_dict=True)
    
    return {
        "orders": recent_orders or [],
        "payments": recent_payments or [],
    }


@frappe.whitelist()
def get_payment_analysis(date=None):
    """Analyse des paiement (espèces vs crédit)"""
    if not date:
        date = today()
    
    by_method = frappe.db.sql("""
        SELECT 
            mode_of_payment,
            COUNT(*) as count,
            SUM(paid_amount) as total
        FROM `tabPayment Entry`
        WHERE posting_date = %s AND docstatus = 1 AND payment_type = 'Receive'
        GROUP BY mode_of_payment
        ORDER BY total DESC
    """, (date,), as_dict=True)
    
    return {
        "by_method": by_method or [],
    }