# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
import json
from frappe import _
from frappe.utils import nowdate, today, now_datetime, get_datetime, add_days
from frappe.boot import get_bootinfo

def get_context(context):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("You must be logged in"), frappe.PermissionError)
    
    context.brand_html = "🚚 FieldForce DZ"
    context.top_bar_items = [
        {"label": _("Dashboard"), "url": "/app/fieldforce-dashboard"},
        {"label": _("Tournées"), "url": "/app/tournee-de-vente"},
        {"label": _("Rapports"), "url": "/app/query-report"},
        {"label": _("Nouvelles Commandes"), "url": "/app/sales-order"},
        {"label": _("Encaissements"), "url": "/app/payment-entry"},
    ]
    
    # Get today's data
    today_date = today()
    
    # Sales stats
    sales_stats = frappe.db.sql("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(grand_total) as total_sales,
            SUM(paid_amount) as total_collected
        FROM `tabSales Order`
        WHERE transaction_date = %s AND docstatus = 1
    """, (today_date,), as_dict=True)[0]
    
    # Visit stats
    visit_stats = frappe.db.sql("""
        SELECT 
            COUNT(*) as total_visits,
            SUM(CASE WHEN statut = 'Visité' THEN 1 ELSE 0 END) as completed_visits
        FROM `tabJournal de Visite`
        WHERE creation LIKE %s
    """, (f"{today_date}%",), as_dict=True)[0]
    
    # Active vendors
    active_vendors = frappe.db.sql("""
        SELECT 
            e.name, e.employee_name, e.department,
            COUNT(so.name) as orders_today,
            COALESCE(SUM(so.grand_total), 0) as sales_today
        FROM `tabEmployee` e
        LEFT JOIN `tabSales Order` so ON so.sales_rep = e.name 
            AND so.transaction_date = %s AND so.docstatus = 1
        WHERE e.status = 'Active' AND e.designation LIKE '%Vendeur%'
        GROUP BY e.name
        ORDER BY sales_today DESC
        LIMIT 10
    """, (today_date,), as_dict=True)
    
    # Today's routes
    today_routes = frappe.db.sql("""
        SELECT 
            tv.name, tv.nom_tournee, tv.jour_semaine, tv.territoire,
            e.employee_name as vendeur,
            (SELECT COUNT(*) FROM `tabClient Tournée` WHERE parent = tv.name) as clients_count
        FROM `tabTournee de Vente` tv
        LEFT JOIN `tabEmployee` e ON e.name = tv.vendeur
        WHERE tv.is_active = 1
        ORDER BY tv.jour_semaine
    """, as_dict=True)
    
    # Recent orders
    recent_orders = frappe.db.sql("""
        SELECT 
            so.name, so.customer_name, so.grand_total, so.status,
            so.transaction_date, e.employee_name
        FROM `tabSales Order` so
        LEFT JOIN `tabEmployee` e ON e.name = so.sales_rep
        ORDER BY so.creation DESC
        LIMIT 20
    """, as_dict=True)
    
    # Pending sync
    pending_sync = frappe.db.count("Offline Queue", {"status": "Pending"})
    
    # Recent payments (linked to orders)
    recent_payments = frappe.db.sql("""
        SELECT 
            pe.name, pe.party, pe.paid_amount, pe.mode_of_payment, pe.posting_date,
            pe.reference_no, pe.docstatus,
            (SELECT reference_name FROM `tabPayment Entry Reference` 
             WHERE parent = pe.name AND reference_doctype = 'Sales Order' 
             LIMIT 1) as linked_order
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
        ORDER BY pe.creation DESC
        LIMIT 10
    """, as_dict=True)
    
    # Alerts - customers with exceeded credit
    credit_alerts = frappe.db.sql("""
        SELECT 
            c.name as customer, c.customer_name,
            c.credit_limit, c.outstanding_amount,
            (c.credit_limit - c.outstanding_amount) as available_credit
        FROM `tabCustomer` c
        WHERE c.outstanding_amount > c.credit_limit * 0.8
        ORDER BY (c.outstanding_amount / c.credit_limit) DESC
        LIMIT 5
    """, as_dict=True)
    
    # Low stock alerts
    stock_alerts = frappe.db.sql("""
        SELECT 
            item_code, item_name, actual_qty, reorder_level
        FROM `tabBin`
        WHERE actual_qty < reorder_level AND actual_qty > 0
        ORDER BY actual_qty ASC
        LIMIT 5
    """, as_dict=True)
    
    # Out of stock
    out_of_stock = frappe.db.sql("""
        SELECT item_code, item_name
        FROM `tabBin`
        WHERE actual_qty <= 0
        ORDER BY item_name
        LIMIT 5
    """, as_dict=True)
    
    # Pending orders awaiting payment
    pending_payments_orders = frappe.db.sql("""
        SELECT 
            so.name, so.customer_name, so.grand_total, so.perpaid_amount,
            (so.grand_total - so.perpaid_amount) as balance_due
        FROM `tabSales Order` so
        WHERE so.docstatus = 1 AND so.perpaid_amount < so.grand_total
        ORDER BY so.transaction_date DESC
        LIMIT 10
    """, as_dict=True)
    
    # Assign to context
    context.sales_stats = sales_stats or {"total_orders": 0, "total_sales": 0, "total_collected": 0}
    context.visit_stats = visit_stats or {"total_visits": 0, "completed_visits": 0}
    context.active_vendors = active_vendors or []
    context.today_routes = today_routes or []
    context.recent_orders = recent_orders or []
    context.recent_payments = recent_payments or []
    context.pending_sync = pending_sync or 0
    context.credit_alerts = credit_alerts or []
    context.stock_alerts = stock_alerts or []
    context.out_of_stock = out_of_stock or []
    context.pending_payments_orders = pending_payments_orders or []
    
    # Calculate day of week in French
    import calendar
    day_name = calendar.day_name[get_datetime().weekday()]
    day_map = {
        "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
        "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
    }
    context.today_day = day_map.get(day_name, day_name)
    context.current_date = today_date

@frappe.whitelist()
def get_vendor_performance(vendor_id=None, from_date=None, to_date=None):
    """Get performance metrics for a vendor"""
    if not from_date:
        from_date = today()
    if not to_date:
        to_date = today()
    
    filters = {"transaction_date": ["between", [from_date, to_date]], "docstatus": 1}
    if vendor_id:
        filters["sales_rep"] = vendor_id
    
    orders = frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "customer_name", "grand_total", "transaction_date", "total_qty"]
    )
    
    total_sales = sum(o.grand_total for o in orders)
    total_orders = len(orders)
    
    return {
        "orders": orders,
        "total_sales": total_sales,
        "total_orders": total_orders,
        "avg_order_value": total_sales / total_orders if total_orders > 0 else 0
    }

@frappe.whitelist()
def get_route_details(route_id):
    """Get detailed route information with clients"""
    route = frappe.get_doc("Tournee de Vente", route_id)
    
    clients = []
    for client in route.customers:
        # Get last visit
        last_visit = frappe.db.sql("""
            SELECT creation, statut FROM `tabJournal de Visite`
            WHERE client = %s AND tournee = %s
            ORDER BY creation DESC LIMIT 1
        """, (client.client, route_id), as_dict=True)
        
        # Get customer outstanding
        outstanding = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) - COALESCE(SUM(paid_amount), 0)
            FROM `tabSales Invoice`
            WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
        """, (client.client,))[0][0]
        
        clients.append({
            "client": client.client,
            "client_name": client.nom_client,
            "sequence": client.ordre,
            "address": client.adresse,
            "latitude": client.latitude,
            "longitude": client.longitude,
            "last_visit": last_visit[0].creation if last_visit else None,
            "last_status": last_visit[0].statut if last_visit else None,
            "outstanding": outstanding
        })
    
    return {
        "route": {
            "name": route.name,
            "nom_tournee": route.nom_tournee,
            "jour_semaine": route.jour_semaine,
            "territoire": route.territoire,
        },
        "clients": clients
    }

@frappe.whitelist()
def get_day_summary(date=None):
    """Get complete day summary for day end report"""
    if not date:
        date = today()
    
    # Orders summary
    orders = frappe.db.sql("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(grand_total) as total_sales,
            SUM(perpaid_amount) as total_collected,
            SUM(grand_total - COALESCE(perpaid_amount, 0)) as total_pending
        FROM `tabSales Order`
        WHERE transaction_date = %s AND docstatus = 1
    """, (date,), as_dict=True)[0]
    
    # Visits summary
    visits = frappe.db.sql("""
        SELECT 
            COUNT(*) as total_visits,
            SUM(CASE WHEN statut = 'Visité' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN statut = 'Ignoré' THEN 1 ELSE 0 END) as skipped
        FROM `tabJournal de Visite`
        WHERE creation LIKE %s
    """, (f"{date}%",), as_dict=True)[0]
    
    # Top products
    top_products = frappe.db.sql("""
        SELECT 
            item_code, item_name, SUM(qty) as qty, SUM(amount) as amount
        FROM `tabSales Order Item`
        WHERE parent IN (SELECT name FROM `tabSales Order` WHERE transaction_date = %s)
        GROUP BY item_code, item_name
        ORDER BY amount DESC
        LIMIT 10
    """, (date,), as_dict=True)
    
    # Top customers
    top_customers = frappe.db.sql("""
        SELECT 
            customer_name, COUNT(*) as orders, SUM(grand_total) as total
        FROM `tabSales Order`
        WHERE transaction_date = %s AND docstatus = 1
        GROUP BY customer_name
        ORDER BY total DESC
        LIMIT 10
    """, (date,), as_dict=True)
    
    return {
        "date": date,
        "orders": orders,
        "visits": visits,
        "top_products": top_products,
        "top_customers": top_customers
    }

@frappe.whitelist()
def get_team_performance(from_date=None, to_date=None):
    """Get team/vendors performance comparison"""
    if not from_date:
        from_date = add_days(today(), -30)
    if not to_date:
        to_date = today()
    
    vendors = frappe.db.sql("""
        SELECT 
            e.name, e.employee_name,
            COUNT(DISTINCT so.name) as orders,
            COALESCE(SUM(so.grand_total), 0) as sales,
            COALESCE(SUM(so.perpaid_amount), 0) as collected
        FROM `tabEmployee` e
        LEFT JOIN `tabSales Order` so ON so.sales_rep = e.name 
            AND so.transaction_date BETWEEN %s AND %s AND so.docstatus = 1
        WHERE e.status = 'Active' AND e.designation LIKE '%Vendeur%'
        GROUP BY e.name, e.employee_name
        ORDER BY sales DESC
        LIMIT 20
    """, (from_date, to_date), as_dict=True)
    
    return {
        "from_date": from_date,
        "to_date": to_date,
        "vendors": vendors,
        "total_orders": sum(v.get("orders", 0) for v in vendors),
        "total_sales": sum(v.get("sales", 0) for v in vendors),
        "total_collected": sum(v.get("collected", 0) for v in vendors)
    }

@frappe.whitelist()
def get_alerts():
    """Get all current alerts for dashboard"""
    alerts = []
    
    # Credit alerts
    credit_alerts = frappe.db.sql("""
        SELECT customer_name as customer, outstanding_amount as outstanding, credit_limit as limit
        FROM `tabCustomer`
        WHERE outstanding_amount > credit_limit * 0.8
        ORDER BY (outstanding_amount / credit_limit) DESC
        LIMIT 10
    """, as_dict=True)
    
    for c in credit_alerts:
        alerts.append({
            "type": "credit",
            "severity": "danger" if c.outstanding > c.limit else "warning",
            "title": f"Crédit {c.customer}",
            "message": f"Encours: {c.outstanding} DA / Plafond: {c.limit} DA"
        })
    
    # Stock alerts
    stock = frappe.db.sql("""
        SELECT item_code, item_name, actual_qty as qty, reorder_level as level
        FROM `tabBin`
        WHERE actual_qty < reorder_level
        ORDER BY actual_qty ASC
        LIMIT 10
    """, as_dict=True)
    
    for s in stock:
        alerts.append({
            "type": "stock",
            "severity": "danger" if s.qty <= 0 else "warning",
            "title": s.item_name,
            "message": f"Stock: {s.qty} / Seuil: {s.level}"
        })
    
    return alerts
