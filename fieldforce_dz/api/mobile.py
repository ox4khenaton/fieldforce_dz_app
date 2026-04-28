# ============================================================
# FIELD FORCE DZ — Mobile API Endpoints
# Tous les endpoints pour l'application mobile
# /api/method/fieldforce_dz.api.mobile.<method>
# ============================================================

import json
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, flt, cint, getdate, add_days, fmt_money
from frappe.model.document import Document


# ============================================================
# APP INFO (for testing)
# ============================================================

@frappe.whitelist()
def get_app_info():
    """Test endpoint - returns app info"""
    return {
        "app_name": "fieldforce_dz",
        "version": "1.0.0",
        "status": "OK",
        "api_count": 50,
    }


# ============================================================
# UTILITAIRES
# ============================================================

def _get_employee_from_user(user=None):
    """Retrouver l'employé connecté depuis l'utilisateur Frappe"""
    if not user:
        user = frappe.session.user
    employees = frappe.get_all(
        "Employee",
        filters={"user_id": user, "status": "Active"},
        fields=["name", "employee_name", "department", "company"],
        limit=1
    )
    if not employees:
        frappe.throw(_("Aucun employé actif trouvé pour {0}").format(user), title=_("Erreur"))
    return employees[0]


def _get_van_assignment(employee_id):
    """Retrouver l'affectation dépôt mobile du vendeur"""
    assignments = frappe.get_all(
        "Affectation Depot Mobile",
        filters={"vendeur": employee_id, "is_active": 1},
        fields=["name", "depot_mobile", "geofence_radius", "vehicule"],
        limit=1
    )
    if not assignments:
        return None
    return assignments[0]


def _success(data=None, message=None):
    """Réponse succès standardisée"""
    response = {"success": True}
    if message:
        response["message"] = message
    if data is not None:
        response["data"] = data
    return response


def _error(message, code=400):
    """Réponse erreur standardisée"""
    frappe.clear_last_message()
    return {"success": False, "error": message, "code": code}


# ============================================================
# AUTHENTIFICATION
# ============================================================

@frappe.whitelist()
def login(usr, pwd):
    """
    Connexion vendeur — POST /api/method/fieldforce_dz.api.mobile.login
    Body: {"usr": "email@company.dz", "pwd": "password"}
    """
    try:
        frappe.local.login_manager.login(usr, pwd)
        user = frappe.get_doc("User", frappe.session.user)

        employee = _get_employee_from_user(frappe.session.user)
        van = _get_van_assignment(employee.name)

        return _success({
            "user": frappe.session.user,
            "full_name": user.full_name,
            "employee_id": employee.name,
            "employee_name": employee.employee_name,
            "company": employee.company,
            "van_warehouse": van.depot_mobile if van else None,
            "geofence_radius": van.geofence_radius if van else 50,
            "roles": [r.role for r in user.roles],
        })
    except frappe.AuthenticationError:
        return _error("Email ou mot de passe incorrect", 401)
    except Exception as e:
        return _error(str(e))


@frappe.whitelist()
def get_logged_user():
    """Utilisateur actuellement connecté"""
    user = frappe.get_doc("User", frappe.session.user)
    employee = _get_employee_from_user()
    van = _get_van_assignment(employee.name)

    return _success({
        "user": frappe.session.user,
        "full_name": user.full_name,
        "employee_id": employee.name,
        "van_warehouse": van.depot_mobile if van else None,
    })


@frappe.whitelist()
def health_check():
    """Vérifier l'état du serveur + latence"""
    import time
    start = time.time()
    version = frappe.db.get_single_value("System Settings", "app_version") or "v14+"
    latency = int((time.time() - start) * 1000)

    return _success({
        "connected": True,
        "version": version,
        "user": frappe.session.user,
        "company": frappe.defaults.get_user_default("Company"),
        "latency_ms": latency,
    })


# ============================================================
# TOURNÉES & VISITES
# ============================================================

@frappe.whitelist()
def get_today_route(day=None):
    """
    Récupérer la tournée du jour avec tous les clients
    GET /api/method/fieldforce_dz.api.mobile.get_today_route?day=Lundi
    """
    employee = _get_employee_from_user()

    if not day:
        import calendar
        day = calendar.day_name[getdate().weekday()]
        # Traduction jours français
        day_map = {
            "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
            "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"
        }
        day = day_map.get(day, day)

    tours = frappe.get_all(
        "Tournee de Vente",
        filters={"vendeur": employee.name, "jour_semaine": day, "is_active": 1},
        fields=["name", "nom_tournee", "jour_semaine", "territoire"],
    )

    result = []
    for tour in tours:
        # Charger les clients de la tournée
        doc = frappe.get_doc("Tournee de Vente", tour.name)
        customers = []

        for c in doc.customers:
            # Vérifier s'il y a une visite aujourd'hui
            today_visits = frappe.get_all(
                "Journal de Visite",
                filters={
                    "tournee": tour.name,
                    "client": c.client,
                    "date_creation": ["between", [nowdate(), nowdate()]]
                },
                fields=["name", "statut", "heure_arrivee", "heure_depart"],
                limit=1
            )

            # Récupérer les infos client
            customer_doc = frappe.get_doc("Customer", c.client)

            customers.append({
                "customer_id": c.client,
                "customer_name": c.nom_client or customer_doc.customer_name,
                "sequence": c.ordre,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "address": c.adresse,
                "customer_group": customer_doc.customer_group,
                "price_list": c.tarif or customer_doc.default_price_list,
                "credit_limit": flt(customer_doc.credit_limit) or 0,
                "outstanding_amount": _get_customer_outstanding(c.client),
                "visit_status": today_visits[0].statut if today_visits else "En attente",
                "last_visit_date": None,  # TODO: query last visit
            })

        result.append({
            "id": tour.name,
            "name": tour.nom_tournee,
            "day": tour.jour_semaine,
            "territory": tour.territoire,
            "customers": customers,
        })

    return _success(result)


@frappe.whitelist()
def check_in(tournee, client, latitude, longitude):
    """
    Pointer l'arrivée chez un client avec vérification GPS
    POST /api/method/fieldforce_dz.api.mobile.check_in
    """
    from fieldforce_dz.api.geofence import verify_geofence

    employee = _get_employee_from_user()

    # Vérifier la géofence
    geo_result = verify_geofence(client, flt(latitude), flt(longitude))

    # Créer le Journal de Visite
    visit = frappe.new_doc("Journal de Visite")
    visit.tournee = tournee
    visit.client = client
    visit.vendeur = employee.name
    visit.heure_arrivee = now_datetime()
    visit.gps_latitude = flt(latitude)
    visit.gps_longitude = flt(longitude)
    visit.distance_client = geo_result.get("distance_meters", 0)
    visit.dans_geofence = 1 if geo_result.get("is_within_geofence") else 0
    visit.statut = "En cours"
    visit.insert(ignore_permissions=True)

    return _success({
        "visit_id": visit.name,
        "is_geofenced": bool(geo_result.get("is_within_geofence")),
        "distance_meters": geo_result.get("distance_meters", 0),
        "geofence_radius": geo_result.get("geofence_radius", 50),
        "message": "Pointage enregistré" if geo_result.get("is_within_geofence") else "Attention: vous êtes hors de la zone géofence!",
    })


@frappe.whitelist()
def check_out(visit_id, notes=None):
    """Pointer le départ du client"""
    visit = frappe.get_doc("Journal de Visite", visit_id)
    visit.heure_depart = now_datetime()
    visit.statut = "Visité"
    if notes:
        visit.remarques = notes
    visit.save(ignore_permissions=True)

    return _success({"visit_id": visit.name, "message": "Visite terminée"})


@frappe.whitelist()
def get_visit_history(customer=None, limit=20):
    """Historique des visites"""
    filters = {}
    if customer:
        filters["client"] = customer

    visits = frappe.get_all(
        "Journal de Visite",
        filters=filters,
        fields=["name", "tournee", "client", "statut", "heure_arrivee", "heure_depart",
                "gps_latitude", "gps_longitude", "distance_client", "dans_geofence", "remarques", "creation"],
        order_by="creation desc",
        limit_page_length=cint(limit)
    )

    return _success(visits)


# ============================================================
# STOCK & PRODUITS
# ============================================================

@frappe.whitelist()
def get_van_stock():
    """Récupérer le stock du dépôt mobile du vendeur"""
    employee = _get_employee_from_user()
    van = _get_van_assignment(employee.name)

    if not van:
        return _error("Aucun dépôt mobile assigné")

    warehouse = van.depot_mobile

    # Utiliser Stock Balance report de ERPNext
    stock = frappe.get_all(
        "Bin",
        filters={"warehouse": warehouse, "actual_qty": [">", 0]},
        fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "valuation_rate"]
    )

    result = []
    for s in stock:
        item = frappe.get_doc("Item", s.item_code)
        result.append({
            "item_code": s.item_code,
            "item_name": item.item_name,
            "brand": item.brand,
            "item_group": item.item_group,
            "qty": flt(s.actual_qty),
            "reserved_qty": flt(s.reserved_qty),
            "available_qty": flt(s.actual_qty) - flt(s.reserved_qty),
            "valuation_rate": flt(s.valuation_rate),
            "stock_value": flt(s.actual_qty) * flt(s.valuation_rate),
            "unit": item.stock_uom,
        })

    return _success({
        "warehouse": warehouse,
        "items": result,
        "total_value": sum(r["stock_value"] for r in result),
    })


@frappe.whitelist()
def get_item_price(item_code, price_list):
    """
    Récupérer le prix d'un article selon la liste de prix
    Gère la hiérarchie: Client → Groupe Client → Standard
    """
    # 1. Chercher le prix dans la liste spécifique
    prices = frappe.get_all(
        "Item Price",
        filters={"item_code": item_code, "price_list": price_list, "selling": 1},
        fields=["price_list_rate", "currency"],
        order_by="valid_from desc",
        limit=1
    )

    if prices:
        return _success({
            "item_code": item_code,
            "price_list": price_list,
            "rate": flt(prices[0].price_list_rate),
            "currency": prices[0].currency or "DZD",
            "source": "price_list",
        })

    # 2. Fallback: tarif standard
    item = frappe.get_doc("Item", item_code)
    return _success({
        "item_code": item_code,
        "price_list": price_list,
        "rate": flt(item.standard_rate),
        "currency": "DZD",
        "source": "standard_rate",
        "warning": "Prix standard utilisé — vérifier la liste de prix",
    })


@frappe.whitelist()
def get_all_products(warehouse=None, price_list=None):
    """Catalogue complet des articles vendables avec stock et prix"""
    items = frappe.get_all(
        "Item",
        filters={"is_sales_item": 1, "disabled": 0},
        fields=["name", "item_code", "item_name", "item_group", "brand",
                "standard_rate", "stock_uom", "image", "has_batch_no"]
    )

    result = []
    for item in items:
        entry = {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "item_group": item.item_group,
            "brand": item.brand,
            "standard_rate": flt(item.standard_rate),
            "uom": item.stock_uom,
            "has_batch_no": item.has_batch_no,
        }

        # Stock dans le dépôt mobile
        if warehouse:
            bin_data = frappe.db.get_value(
                "Bin", {"item_code": item.item_code, "warehouse": warehouse},
                ["actual_qty", "reserved_qty"], as_dict=True
            )
            if bin_data:
                entry["van_stock"] = flt(bin_data.actual_qty)
                entry["reserved_qty"] = flt(bin_data.reserved_qty)
            else:
                entry["van_stock"] = 0
                entry["reserved_qty"] = 0

            # Stock dans le dépôt principal
            main_wh = frappe.db.get_value(
                "Affectation Depot Mobile",
                {"depot_mobile": warehouse},
                "depot_principal"
            )
            if main_wh:
                main_bin = frappe.db.get_value(
                    "Bin", {"item_code": item.item_code, "warehouse": main_wh},
                    "actual_qty"
                )
                entry["main_stock"] = flt(main_bin) if main_bin else 0

        # Prix selon la liste
        if price_list:
            ip = frappe.db.get_value(
                "Item Price",
                {"item_code": item.item_code, "price_list": price_list, "selling": 1},
                "price_list_rate"
            )
            entry["rate"] = flt(ip) if ip else flt(item.standard_rate)
        else:
            entry["rate"] = flt(item.standard_rate)

        result.append(entry)

    return _success(result)


# ============================================================
# COMMANDES
# ============================================================

@frappe.whitelist()
def create_order(customer, items, price_list=None, warehouse=None, gps_lat=None, gps_lng=None):
    """
    Créer une commande vente depuis le mobile
    POST /api/method/fieldforce_dz.api.mobile.create_order
    Body: {
        "customer": "CLT-001",
        "items": [{"item_code": "ART-001", "qty": 10}, ...],
        "price_list": "Tarif Détaillant",
        "warehouse": "Dépôt Mobile - KB",
        "gps_lat": 36.7538,
        "gps_lng": 3.0588
    }
    """
    employee = _get_employee_from_user()
    van = _get_van_assignment(employee.name)

    if not warehouse:
        warehouse = van.depot_mobile if van else None

    if not warehouse:
        return _error("Aucun dépôt mobile assigné")

    # Vérifier le plafond de crédit
    outstanding = _get_customer_outstanding(customer)
    credit_limit = flt(frappe.db.get_value("Customer", customer, "credit_limit") or 0)

    # Parser les items
    if isinstance(items, str):
        items = json.loads(items)

    # Calculer le total pour vérification crédit
    total_amount = 0
    order_items = []

    for it in items:
        item_code = it.get("item_code")
        qty = flt(it.get("qty", 0))

        # Récupérer le prix
        price_data = json.loads(get_item_price(item_code, price_list or "Standard Selling"))
        rate = flt(price_data.get("data", {}).get("rate", 0))

        # Vérifier le stock disponible
        available = flt(frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": warehouse},
            "actual_qty"
        ) or 0)
        reserved = flt(frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": warehouse},
            "reserved_qty"
        ) or 0)
        if qty > (available - reserved):
            frappe.throw(
                _("Stock insuffisant pour {0}: demandé {1}, disponible {2}").format(
                    item_code, qty, available - reserved
                ),
                title=_("Rupture de stock")
            )

        amount = qty * rate
        total_amount += amount
        order_items.append({
            "item_code": item_code,
            "qty": qty,
            "rate": rate,
            "amount": amount,
            "warehouse": warehouse,
        })

    # Vérification plafond crédit
    if credit_limit > 0 and (outstanding + total_amount) > credit_limit:
        return _error(
            "Plafond de crédit dépassé: Impayé {0} + Commande {1} > Plafond {2}".format(
                fmt_money(outstanding), fmt_money(total_amount), fmt_money(credit_limit)
            )
        )

    # Vérification géofence (optionnel)
    is_geofenced = 0
    if gps_lat and gps_lng:
        from fieldforce_dz.api.geofence import verify_geofence
        geo = verify_geofence(customer, flt(gps_lat), flt(gps_lng))
        is_geofenced = 1 if geo.get("is_within_geofence") else 0

    # Créer la commande dans ERPNext
    so = frappe.new_doc("Sales Order")
    so.customer = customer
    so.order_type = "Sales"
    so.transaction_date = nowdate()
    so.delivery_date = nowdate()
    so.selling_price_list = price_list or "Standard Selling"
    so.set_warehouse = warehouse
    so.is_geofenced = is_geofenced
    so.gps_coordinates = "{0},{1}".format(gps_lat, gps_lng) if gps_lat else ""

    for oi in order_items:
        so.append("items", {
            "item_code": oi["item_code"],
            "qty": oi["qty"],
            "rate": oi["rate"],
            "warehouse": oi["warehouse"],
            "delivery_date": nowdate(),
        })

    so.run_method("set_missing_values")
    so.run_method("calculate_taxes_and_totals")
    so.insert(ignore_permissions=True)

    # Ajouter à la file de sync
    return _success({
        "order_id": so.name,
        "grand_total": flt(so.grand_total),
        "total_qty": flt(so.total_qty),
        "status": so.status,
        "is_geofenced": bool(is_geofenced),
        "message": "Commande créée avec succès",
    })


@frappe.whitelist()
def submit_order(order_id):
    """Soumettre une commande (passer de Draft à Submitted)"""
    so = frappe.get_doc("Sales Order", order_id)
    if so.status != "Draft":
        return _error("Commande déjà soumise")

    so.submit()

    return _success({
        "order_id": so.name,
        "status": so.status,
        "message": "Commande soumise avec succès",
    })


@frappe.whitelist()
def get_orders(status=None, limit=50):
    """Liste des commandes du vendeur"""
    filters = {}
    if status:
        filters["status"] = status

    orders = frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "customer_name", "transaction_date",
                "grand_total", "total_qty", "status", "creation"],
        order_by="creation desc",
        limit_page_length=cint(limit)
    )

    return _success(orders)


@frappe.whitelist()
def cancel_order(order_id, reason=None):
    """Annuler une commande"""
    so = frappe.get_doc("Sales Order", order_id)
    so.cancel()

    return _success({"order_id": so.name, "status": "Cancelled"})


# ============================================================
# PAIEMENTS
# ============================================================

@frappe.whitelist()
def create_payment(customer, amount, mode_of_payment, reference_no=None, reference_date=None, order_id=None):
    """
    Créer une écriture de paiement
    POST /api/method/fieldforce_dz.api.mobile.create_payment
    """
    employee = _get_employee_from_user()
    company = frappe.defaults.get_user_default("Company")

    # Déterminer le compte selon le mode de paiement
    mode = frappe.get_doc("Mode of Payment", mode_of_payment)
    account = None
    for m in mode.accounts:
        if m.company == company:
            account = m.default_account
            break

    if not account:
        return _error("Aucun compte configuré pour le mode de paiement: {0}".format(mode_of_payment))

    # Créer le Payment Entry
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.paid_amount = flt(amount)
    pe.received_amount = flt(amount)
    pe.mode_of_payment = mode_of_payment
    pe.paid_to = account
    pe.reference_no = reference_no or frappe.generate_hash(length=8)
    pe.reference_date = reference_date or nowdate()
    pe.company = company

    # Lier à une commande si fournie
    if order_id:
        pe.append("references", {
            "reference_doctype": "Sales Order",
            "reference_name": order_id,
            "allocated_amount": flt(amount),
        })

    pe.run_method("set_missing_values")
    pe.insert(ignore_permissions=True)
    pe.submit()

    return _success({
        "payment_id": pe.name,
        "amount": flt(pe.paid_amount),
        "status": pe.status,
        "message": "Paiement enregistré avec succès",
    })


@frappe.whitelist()
def get_outstanding(customer):
    """Montant impayé d'un client"""
    outstanding = _get_customer_outstanding(customer)
    credit_limit = flt(frappe.db.get_value("Customer", customer, "credit_limit") or 0)

    return _success({
        "customer": customer,
        "outstanding": outstanding,
        "credit_limit": credit_limit,
        "available_credit": max(0, credit_limit - outstanding),
        "credit_usage_pct": round((outstanding / credit_limit) * 100, 1) if credit_limit > 0 else 0,
    })


def _get_customer_outstanding(customer):
    """Calculer le montant impayé réel d'un client"""
    from erpnext.accounts.utils import get_balance_on
    try:
        return flt(get_balance_on(
            party_type="Customer",
            party=customer,
            date=nowdate()
        ))
    except Exception:
        # Fallback: calculer manuellement
        total = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) - COALESCE(SUM(paid_amount), 0)
            FROM `tabSales Invoice`
            WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
        """, (customer,))
        return flt(total[0][0]) if total else 0


# ============================================================
# SYNC BATCH
# ============================================================

@frappe.whitelist()
def sync_batch(data):
    """
    Synchronisation par lot — plusieurs documents en une requête
    POST /api/method/fieldforce_dz.api.mobile.sync_batch
    Body: {
        "data": {
            "orders": [...],
            "payments": [...],
            "visits": [...],
            "expenses": [...]
        }
    }
    """
    if isinstance(data, str):
        data = json.loads(data)

    results = {"orders": [], "payments": [], "visits": [], "expenses": []}

    # Traiter les commandes
    for order_data in data.get("orders", []):
        try:
            result = json.loads(create_order(
                customer=order_data.get("customer"),
                items=order_data.get("items"),
                price_list=order_data.get("price_list"),
                warehouse=order_data.get("warehouse"),
                gps_lat=order_data.get("gps_lat"),
                gps_lng=order_data.get("gps_lng"),
            ))
            results["orders"].append({"local_id": order_data.get("local_id"), **result})
        except Exception as e:
            results["orders"].append({
                "local_id": order_data.get("local_id"),
                "success": False,
                "error": str(e)
            })

    # Traiter les paiements
    for pay_data in data.get("payments", []):
        try:
            result = json.loads(create_payment(
                customer=pay_data.get("customer"),
                amount=pay_data.get("amount"),
                mode_of_payment=pay_data.get("mode_of_payment"),
                reference_no=pay_data.get("reference_no"),
                reference_date=pay_data.get("reference_date"),
                order_id=pay_data.get("order_id"),
            ))
            results["payments"].append({"local_id": pay_data.get("local_id"), **result})
        except Exception as e:
            results["payments"].append({
                "local_id": pay_data.get("local_id"),
                "success": False,
                "error": str(e)
            })

    # Traiter les visites
    for visit_data in data.get("visits", []):
        try:
            result = json.loads(check_in(
                tournee=visit_data.get("tournee"),
                client=visit_data.get("client"),
                latitude=visit_data.get("latitude"),
                longitude=visit_data.get("longitude"),
            ))
            results["visits"].append({"local_id": visit_data.get("local_id"), **result})
        except Exception as e:
            results["visits"].append({
                "local_id": visit_data.get("local_id"),
                "success": False,
                "error": str(e)
            })

    return _success(results, "Sync terminé")


@frappe.whitelist()
def get_updates(last_sync=None):
    """Récupérer les mises à jour serveur depuis la dernière sync"""
    employee = _get_employee_from_user()

    # Récupérer les modifications depuis last_sync
    result = {
        "customers": [],
        "items": [],
        "prices": [],
        "beats": [],
    }

    if last_sync:
        # Clients modifiés
        result["customers"] = frappe.get_all(
            "Customer",
            filters={"modified": [">=", last_sync], "disabled": 0},
            fields=["name", "customer_name", "customer_group", "territory",
                    "default_price_list", "credit_limit", "modified"]
        )

        # Articles modifiés
        result["items"] = frappe.get_all(
            "Item",
            filters={"modified": [">=", last_sync], "disabled": 0, "is_sales_item": 1},
            fields=["name", "item_code", "item_name", "item_group", "brand",
                    "standard_rate", "stock_uom", "modified"]
        )

        # Prix modifiés
        result["prices"] = frappe.get_all(
            "Item Price",
            filters={"modified": [">=", last_sync], "selling": 1},
            fields=["item_code", "price_list", "price_list_rate", "currency", "modified"]
        )

    return _success(result)


# ============================================================
# DÉPENSES
# ============================================================

@frappe.whitelist()
def create_expense(type_depense, montant, notes=None, date=None):
    """Enregistrer une dépense terrain"""
    employee = _get_employee_from_user()

    expense = frappe.new_doc("Depense Terrain")
    expense.vendeur = employee.name
    expense.type_depense = type_depense
    expense.montant = flt(montant)
    expense.date = date or nowdate()
    expense.notes = notes
    expense.insert(ignore_permissions=True)

    return _success({
        "expense_id": expense.name,
        "amount": flt(expense.montant),
        "message": "Dépense enregistrée",
    })


# ============================================================
# OBJECTIFS & BILAN
# ============================================================

@frappe.whitelist()
def get_targets():
    """Récupérer les objectifs du vendeur"""
    employee = _get_employee_from_user()

    targets = frappe.get_all(
        "Objectif Vendeur",
        filters={"vendeur": employee.name, "actif": 1},
        fields=["*"],
        limit=1
    )

    if not targets:
        return _success(None, "Aucun objectif défini")

    target = targets[0]

    # Calculer les réalisations
    today = nowdate()
    month_start = today.replace(day=1)

    # CA du jour
    daily_revenue = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0)
        FROM `tabSales Order`
        WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
    """, (employee.name, today))[0][0])

    # CA du mois
    monthly_revenue = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0)
        FROM `tabSales Order`
        WHERE sales_rep = %s AND transaction_date >= %s AND docstatus = 1
    """, (employee.name, month_start))[0][0])

    # Nombre de commandes du mois
    monthly_orders = cint(frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabSales Order`
        WHERE sales_rep = %s AND transaction_date >= %s AND docstatus = 1
    """, (employee.name, month_start))[0][0])

    # Visites du mois
    monthly_visits = cint(frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabJournal de Visite`
        WHERE vendeur = %s AND creation >= %s AND docstatus = 1
    """, (employee.name, month_start))[0][0])

    return _success({
        "target_amount": flt(target.objectif_ca_mensuel),
        "daily_target": flt(target.objectif_ca_journalier),
        "achieved_daily": daily_revenue,
        "achieved_monthly": monthly_revenue,
        "achieved_pct": round((monthly_revenue / flt(target.objectif_ca_mensuel)) * 100, 1) if flt(target.objectif_ca_mensuel) > 0 else 0,
        "monthly_orders": monthly_orders,
        "monthly_visits": monthly_visits,
        "incentive_amount": flt(target.montant_prime),
        "bonus_threshold": flt(target.seuil_bonus),
    })


@frappe.whitelist()
def day_end_report(notes=None):
    """Générer le bilan de fin de journée"""
    employee = _get_employee_from_user()
    today = nowdate()

    # Statistiques du jour
    orders = frappe.get_all(
        "Sales Order",
        filters={"sales_rep": employee.name, "transaction_date": today, "docstatus": 1},
        fields=["name", "grand_total", "customer", "total_qty"]
    )

    payments = frappe.get_all(
        "Payment Entry",
        filters={"party": ["in", [o.customer for o in orders]], "posting_date": today, "docstatus": 1},
        fields=["name", "paid_amount", "mode_of_payment"]
    )

    visits = frappe.get_all(
        "Journal de Visite",
        filters={"vendeur": employee.name, "creation": ["between", [today, today]]},
        fields=["name", "statut"]
    )

    total_revenue = sum(flt(o.grand_total) for o in orders)
    total_collections = sum(flt(p.paid_amount) for p in payments)
    visited = len([v for v in visits if v.statut == "Visité"])

    # Top produit du jour
    top_product = frappe.db.sql("""
        SELECT item_code, SUM(qty) as total_qty
        FROM `tabSales Order Item`
        WHERE parent IN (
            SELECT name FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
        )
        GROUP BY item_code ORDER BY total_qty DESC LIMIT 1
    """, (employee.name, today))

    return _success({
        "date": today,
        "sales_rep": employee.employee_name,
        "total_orders": len(orders),
        "total_revenue": total_revenue,
        "total_collections": total_collections,
        "customers_visited": visited,
        "top_product": top_product[0][0] if top_product else None,
        "top_product_qty": flt(top_product[0][1]) if top_product else 0,
        "orders": [{"id": o.name, "amount": flt(o.grand_total)} for o in orders],
    })


@frappe.whitelist()
def auto_day_end_reminder():
    """Tâche planifiée: rappel bilan fin de journée (appelé par scheduler)"""
    # Envoyer notification aux vendeurs qui n'ont pas clôturé
    employees = frappe.get_all(
        "Affectation Depot Mobile",
        filters={"is_active": 1},
        fields=["vendeur"]
    )

    for emp in employees:
        # Vérifier s'il y a des visites aujourd'hui sans check-out
        pending = frappe.db.count("Journal de Visite", {
            "vendeur": emp.vendeur,
            "statut": "En cours",
        })

        if pending > 0:
            user = frappe.db.get_value("Employee", emp.vendeur, "user_id")
            if user:
                frappe.publish_realtime(
                    event="eval_js",
                    message=f'frappe.msgprint("Rappel: {pending} visite(s) non clôturée(s). Pensez à faire votre bilan.", title="Bilan Fin de Journée", indicator="orange")',
                    user=user,
                )


# ============================================================
# VÉRIFICATION CRÉDIT (endpoint dédié)
# ============================================================

@frappe.whitelist()
def check_credit_limit(customer, order_amount=0):
    """Vérifier le plafond de crédit avant de passer commande"""
    outstanding = _get_customer_outstanding(customer)
    credit_limit = flt(frappe.db.get_value("Customer", customer, "credit_limit") or 0)
    amount = flt(order_amount)

    can_order = True
    if credit_limit > 0:
        can_order = (outstanding + amount) <= credit_limit

    return _success({
        "customer": customer,
        "outstanding": outstanding,
        "credit_limit": credit_limit,
        "order_amount": amount,
        "projected_outstanding": outstanding + amount,
        "can_order": can_order,
        "credit_usage_pct": round((outstanding / credit_limit) * 100, 1) if credit_limit > 0 else 0,
        "warning_level": "danger" if not can_order else "warning" if (outstanding + amount) > credit_limit * 0.8 else "ok",
    })


# ============================================================
# NEXTAPP-INSPIRED FEATURES
# ============================================================

@frappe.whitelist()
def get_all_doctypes():
    """
    Liste tous les doctypes accessibles pour le mobile
    Inspired by NextApp - All Modules & Documents
    """
    modules_doctypes = {
        "Selling": ["Sales Order", "Sales Invoice", "Delivery Note", "Customer", "Address", "Contact", "Lead", "Opportunity"],
        "Buying": ["Purchase Order", "Purchase Invoice", "Purchase Receipt", "Supplier"],
        "Stock": ["Item", "Stock Entry", "Material Request", "Delivery Note", "Purchase Receipt"],
        "Accounting": ["Payment Entry", "Journal Entry", "Sales Invoice", "Purchase Invoice"],
        "HR": ["Employee", "Leave Application", "Attendance", "Expense Claim", "Employee Checkin"],
        "CRM": ["Lead", "Opportunity", "Customer", "Contact"],
    }

    result = []
    for module, doctypes in modules_doctypes.items():
        result.append({
            "module": module,
            "doctypes": doctypes,
        })

    return _success(result)


@frappe.whitelist()
def get_doctype_fields(doctype):
    """
    Récupérer les champs d'un doctype pour affichage mobile
    Inspired by NextApp - Document Fields
    """
    meta = frappe.get_meta(doctype)
    fields = []

    for df in meta.fields:
        if df.fieldtype in ["Section Break", "Column Break", "Tab Break"]:
            continue
        fields.append({
            "fieldname": df.fieldname,
            "label": df.label,
            "fieldtype": df.fieldtype,
            "options": df.options,
            "reqd": df.reqd,
            "hidden": df.hidden,
            "read_only": df.read_only,
        })

    return _success({
        "doctype": doctype,
        "fields": fields,
        "title_field": meta.title_field,
    })


@frappe.whitelist()
def list_documents(doctype, filters=None, fields=None, limit=50, order_by="modified desc"):
    """
    Liste les documents d'un doctype avec filtres
    Inspired by NextApp - Document Listing
    """
    if isinstance(filters, str):
        filters = json.loads(filters)

    if isinstance(fields, str):
        fields = json.loads(fields)

    if not fields:
        meta = frappe.get_meta(doctype)
        fields = [f.fieldname for f in meta.fields if f.fieldname][:20]

    docs = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=fields,
        order_by=order_by,
        limit_page_length=cint(limit)
    )

    return _success({
        "doctype": doctype,
        "count": len(docs),
        "documents": docs,
    })


@frappe.whitelist()
def get_document(doctype, name):
    """
    Récupérer un document complet avec ses détails
    Inspired by NextApp - Document Details
    """
    doc = frappe.get_doc(doctype, name)
    meta = frappe.get_meta(doctype)

    result = {"name": doc.name, "doctype": doctype}

    for df in meta.fields:
        if df.fieldtype in ["Section Break", "Column Break", "Tab Break", "Table"]:
            continue
        value = doc.get(df.fieldname)
        result[df.fieldname] = str(value) if value else None

    result["_comments"] = doc.get("__comments") or []
    result["_workflow_state"] = doc.get("workflow_state")
    result["_status"] = doc.get("status")

    return _success(result)


@frappe.whitelist()
def create_document(doctype, data):
    """
    Créer un document depuis le mobile
    Inspired by NextApp - Create Documents
    """
    if isinstance(data, str):
        data = json.loads(data)

    doc = frappe.new_doc(doctype)

    for field, value in data.items():
        if field not in ["doctype", "name"]:
            doc.set(field, value)

    doc.insert(ignore_permissions=True)

    return _success({
        "doctype": doctype,
        "name": doc.name,
        "message": "Document créé avec succès",
    })


@frappe.whitelist()
def update_document(doctype, name, data):
    """
    Mettre à jour un document
    Inspired by NextApp - Edit & Update
    """
    if isinstance(data, str):
        data = json.loads(data)

    doc = frappe.get_doc(doctype, name)

    for field, value in data.items():
        if field not in ["doctype", "name"]:
            doc.set(field, value)

    doc.save(ignore_permissions=True)

    return _success({
        "doctype": doctype,
        "name": doc.name,
        "message": "Document mis à jour",
    })


@frappe.whitelist()
def submit_document(doctype, name):
    """
    Soumettre un document (Draft -> Submitted)
    Inspired by NextApp - Submit Documents
    """
    doc = frappe.get_doc(doctype, name)
    doc.submit()

    return _success({
        "doctype": doctype,
        "name": doc.name,
        "status": doc.status,
        "message": "Document soumis",
    })


@frappe.whitelist()
def cancel_document(doctype, name, reason=None):
    """
    Annuler un document
    Inspired by NextApp - Cancel Documents
    """
    doc = frappe.get_doc(doctype, name)
    doc.cancel()

    return _success({
        "doctype": doctype,
        "name": doc.name,
        "status": "Cancelled",
        "message": "Document annulé",
    })


@frappe.whitelist()
def amend_document(doctype, name):
    """
    Créer une nouvelle version/amendement du document
    Inspired by NextApp - Amend Documents
    """
    doc = frappe.get_doc(doctype, name)

    if hasattr(doc, "amend"):
        doc.amend()
    else:
        frappe.throw(_("Amendement non supporté pour {0}").format(doctype))

    return _success({
        "doctype": doctype,
        "name": doc.name,
        "message": "Document amendé",
    })


@frappe.whitelist()
def add_comment(doctype, name, content):
    """
    Ajouter un commentaire à un document
    Inspired by NextApp - Commenting on Documents
    """
    comment = frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": doctype,
        "reference_name": name,
        "content": content,
    })
    comment.insert(ignore_permissions=True)

    return _success({
        "comment_id": comment.name,
        "message": "Commentaire ajouté",
    })


@frappe.whitelist()
def get_comments(doctype, name):
    """
    Récupérer les commentaires d'un document
    Inspired by NextApp - Comments Section
    """
    comments = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": doctype,
            "reference_name": name,
            "comment_type": ["in", ["Comment", "Info"]],
        },
        fields=["name", "content", "owner", "creation"],
        order_by="creation desc"
    )

    return _success(comments)


@frappe.whitelist()
def get_document_history(doctype, name):
    """
    Historique des modifications d'un document
    Inspired by NextApp - Document History
    """
    logs = frappe.get_all(
        "Version",
        filters={
            "docname": name,
        },
        fields=["name", "data", "creation", "owner"],
        order_by="creation desc",
        limit=20
    )

    history = []
    for log in logs:
        data = json.loads(log.data) if isinstance(log.data, str) else log.data
        history.append({
            "version": log.name,
            "changed": data.get("changed"),
            "owner": log.owner,
            "creation": log.creation,
        })

    return _success(history)


@frappe.whitelist()
def get_document_connections(doctype, name):
    """
    Récupérer les documents liés/connectés
    Inspired by NextApp - Document Connections
    """
    meta = frappe.get_meta(doctype)
    connections = []

    for df in meta.fields:
        if df.fieldtype in ["Link", "Dynamic Link", "Table"]:
            link_doctype = df.options
            if link_doctype:
                links = frappe.get_all(
                    link_doctype,
                    filters={df.fieldname: name},
                    fields=["name"],
                    limit=10
                )
                if links:
                    connections.append({
                        "doctype": link_doctype,
                        "fieldname": df.fieldname,
                        "count": len(links),
                        "documents": [{"name": l.name} for l in links],
                    })

    return _success(connections)


@frappe.whitelist()
def get_workflow_actions(doctype, name):
    """
    Récupérer les actions de workflow disponibles
    Inspired by NextApp - Workflow Actions
    """
    doc = frappe.get_doc(doctype, name)

    if not hasattr(doc, "get_workflow_actions"):
        return _success([])

    actions = doc.get_workflow_actions()

    return _success([{
        "action": a.action,
        "action_label": a.action_label,
    } for a in actions])


@frappe.whitelist()
def apply_workflow_action(doctype, name, action):
    """
    Appliquer une action de workflow
    Inspired by NextApp - Workflow Actions
    """
    from frappe.workflow.doctype.workflow_action import workflow_action as wf_action
    wf_action.apply_action(action, docname=name, doctype=doctype)

    return _success({
        "message": "Action de workflow appliquée",
    })


@frappe.whitelist()
def search_documents(doctype, query, limit=20):
    """
    Rechercher des documents par mot-clé
    Inspired by NextApp - Document Searching
    """
    meta = frappe.get_meta(doctype)
    search_fields = [f.fieldname for f in meta.fields if f.fieldtype in ["Data", "Small Text", "Text", "Link"]]
    search_fields = search_fields[:10]

    filters = {}
    for field in search_fields:
        filters[field] = ["like", f"%{query}%"]

    docs = frappe.get_all(
        doctype,
        filters=filters,
        fields=["name"] + search_fields,
        limit=cint(limit)
    )

    return _success({
        "doctype": doctype,
        "query": query,
        "count": len(docs),
        "documents": docs,
    })


@frappe.whitelist()
def filter_documents(doctype, filters_json):
    """
    Appliquer des filtres complexes sur les documents
    Inspired by NextApp - Document Filtering
    """
    if isinstance(filters_json, str):
        filters = json.loads(filters_json)
    else:
        filters = filters_json

    meta = frappe.get_meta(doctype)
    fields = [f.fieldname for f in meta.fields if f.fieldname][:20]

    docs = frappe.get_all(
        doctype,
        filters=filters,
        fields=fields,
        limit=50
    )

    return _success({
        "doctype": doctype,
        "filters": filters,
        "count": len(docs),
        "documents": docs,
    })


@frappe.whitelist()
def download_document_pdf(doctype, name):
    """
    Générer un PDF du document
    Inspired by NextApp - Download PDF
    """
    pdf_content = frappe.attach_print(doctype, name, print_format="Standard")

    return _success({
        "doctype": doctype,
        "name": name,
        "file": pdf_content,
        "message": "PDF généré",
    })


@frappe.whitelist()
def add_attachment(doctype, name, file_url, file_name=None):
    """
    Ajouter une pièce jointe à un document
    Inspired by NextApp - Adding Attachments
    """
    doc = frappe.get_doc(doctype, name)

    if hasattr(doc, "add_attachments"):
        doc.add_attachments(file_url, file_name)

    return _success({
        "message": "Pièce jointe ajoutée",
    })


@frappe.whitelist()
def get_notifications():
    """
    Récupérer toutes les notifications
    Inspired by NextApp - Push Notifications
    """
    notifications = frappe.get_all(
        "Notification Log",
        filters={"owner": frappe.session.user},
        fields=["name", "type", "title", "message", "creation", "read"],
        order_by="creation desc",
        limit=50
    )

    unread_count = frappe.db.count("Notification Log", {
        "owner": frappe.session.user,
        "read": 0,
    })

    return _success({
        "notifications": notifications,
        "unread_count": unread_count,
    })


@frappe.whitelist()
def mark_notification_read(notification_name):
    """
    Marquer une notification comme lue
    Inspired by NextApp - Mark as Read
    """
    frappe.db.set_value("Notification Log", notification_name, "read", 1)

    return _success({"message": "Notification marquée comme lue"})


# ============================================================
# HR & ATTENDANCE (NextApp-inspired)
# ============================================================

@frappe.whitelist()
def employee_checkin(employee_id=None, latitude=None, longitude=None, log_type="IN"):
    """
    Employee GPS Check-in
    Inspired by NextApp - HR Employee Checkin
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    checkin = frappe.new_doc("Employee Checkin")
    checkin.employee = employee_id
    checkin.log_type = log_type
    checkin.time = now_datetime()
    checkin.device_id = "mobile"

    if latitude and longitude:
        checkin.location = f"{latitude},{longitude}"

    checkin.insert(ignore_permissions=True)

    return _success({
        "checkin_id": checkin.name,
        "log_type": log_type,
        "time": checkin.time,
        "message": f"Pointage {log_type} enregistré",
    })


@frappe.whitelist()
def create_leave_application(employee, leave_type, from_date, to_date, reason=None):
    """
    Créer une demande de congés
    Inspired by NextApp - Leave Applications
    """
    leave = frappe.new_doc("Leave Application")
    leave.employee = employee
    leave.leave_type = leave_type
    leave.from_date = from_date
    leave.to_date = to_date
    leave.reason = reason
    leave.insert(ignore_permissions=True)

    return _success({
        "leave_id": leave.name,
        "message": "Demande de congés soumise",
    })


@frappe.whitelist()
def create_expense_claim(employee, expense_type, amount, description=None, date=None):
    """
    Créer une demande de remboursement de frais
    Inspired by NextApp - Expense Claims
    """
    claim = frappe.new_doc("Expense Claim")
    claim.employee = employee
    claim.expense_type = expense_type
    claim.amount = flt(amount)
    claim.description = description
    claim.date = date or nowdate()
    claim.insert(ignore_permissions=True)

    return _success({
        "claim_id": claim.name,
        "amount": flt(amount),
        "message": "Demande de frais soumise",
    })


@frappe.whitelist()
def get_employee_attendance(employee_id=None, from_date=None, to_date=None):
    """
    Récupérer la présence d'un employé
    Inspired by NextApp - Attendance Tracking
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    filters = {"employee": employee_id}
    if from_date:
        filters["attendance_date"] = ["between", [from_date, to_date or nowdate()]]

    attendance = frappe.get_all(
        "Attendance",
        filters=filters,
        fields=["name", "attendance_date", "status", "in_time", "out_time"],
        order_by="attendance_date desc",
        limit=30
    )

    return _success(attendance)


# ============================================================
# CRM FEATURES (NextApp-inspired)
# ============================================================

@frappe.whitelist()
def create_lead(lead_name, company_name=None, source=None, email=None, phone=None, mobile=None):
    """
    Créer un lead
    Inspired by NextApp - Lead Management
    """
    lead = frappe.new_doc("Lead")
    lead.lead_name = lead_name
    lead.company_name = company_name
    lead.source = source
    lead.email = email
    lead.phone = phone
    lead.mobile = mobile
    lead.insert(ignore_permissions=True)

    return _success({
        "lead_id": lead.name,
        "message": "Lead créé",
    })


@frappe.whitelist()
def create_opportunity(doctype, name, opportunity_type=None):
    """
    Créer une opportunité depuis un lead
    Inspired by NextApp - Opportunities
    """
    opp = frappe.new_doc("Opportunity")
    opp.opportunity_from = doctype
    opp_party = name
    if doctype == "Lead":
        opp_party = frappe.db.get_value("Lead", name, "lead_name")

    opp.party_name = opp_party
    opp.opportunity_type = opportunity_type or "Sales"
    opp.insert(ignore_permissions=True)

    return _success({
        "opportunity_id": opp.name,
        "message": "Opportunité créée",
    })


@frappe.whitelist()
def create_address(address_type, address_line1, city, state=None, country="Algeria",
                  pincode=None, phone=None, latitude=None, longitude=None):
    """
    Créer une adresse avec GPS
    Inspired by NextApp - Address with GPS
    """
    address = frappe.new_doc("Address")
    address.address_type = address_type
    address.address_line1 = address_line1
    address.city = city
    address.state = state
    address.country = country
    address.pincode = pincode
    address.phone = phone

    if latitude and longitude:
        address.latitude = flt(latitude)
        address.longitude = flt(longitude)

    address.insert(ignore_permissions=True)

    return _success({
        "address_id": address.name,
        "message": "Adresse créée",
    })


@frappe.whitelist()
def create_contact(first_name, last_name=None, email=None, phone=None, mobile=None, company=None):
    """
    Créer un contact
    Inspired by NextApp - Contact Management
    """
    contact = frappe.new_doc("Contact")
    contact.first_name = first_name
    contact.last_name = last_name
    contact.email_id = email
    contact.phone = phone
    contact.mobile_no = mobile
    contact.company_name = company
    contact.insert(ignore_permissions=True)

    return _success({
        "contact_id": contact.name,
        "message": "Contact créé",
    })


# ============================================================
# STOCK FEATURES (NextApp-inspired)
# ============================================================

@frappe.whitelist()
def create_material_request(items, from_warehouse, to_warehouse, reason=None):
    """
    Créer une demande de transfert de stock
    Inspired by NextApp - Material Requests
    """
    if isinstance(items, str):
        items = json.loads(items)

    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Material Transfer"
    mr.from_warehouse = from_warehouse
    mr.set_warehouse = to_warehouse
    mr.reason = reason

    for item in items:
        mr.append("items", {
            "item_code": item.get("item_code"),
            "qty": flt(item.get("qty")),
            "from_warehouse": from_warehouse,
            "warehouse": to_warehouse,
        })

    mr.insert(ignore_permissions=True)

    return _success({
        "request_id": mr.name,
        "message": "Demande de transfert créée",
    })


@frappe.whitelist()
def create_stock_entry(stock_entry_type, items, from_warehouse=None, to_warehouse=None):
    """
    Créer une opération de stock
    Inspired by NextApp - Stock Entries
    """
    if isinstance(items, str):
        items = json.loads(items)

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = stock_entry_type

    if stock_entry_type == "Material Transfer":
        se.from_warehouse = from_warehouse
        se.to_warehouse = to_warehouse
    elif stock_entry_type == "Material Receipt":
        se.to_warehouse = to_warehouse
    elif stock_entry_type == "Material Issue":
        se.from_warehouse = from_warehouse

    for item in items:
        se.append("items", {
            "item_code": item.get("item_code"),
            "qty": flt(item.get("qty")),
            "s_warehouse": from_warehouse,
            "t_warehouse": to_warehouse,
            "qty": flt(item.get("qty")),
        })

    se.insert(ignore_permissions=True)

    return _success({
        "entry_id": se.name,
        "message": "Opération de stock créée",
    })


@frappe.whitelist()
def create_delivery_note(sales_order=None, customer=None, items=None, delivery_date=None):
    """
    Créer un bon de livraison
    Inspired by NextApp - Delivery Notes
    """
    dn = frappe.new_doc("Delivery Note")
    dn.customer = customer
    dn.delivery_date = delivery_date or nowdate()

    if sales_order:
        so = frappe.get_doc("Sales Order", sales_order)
        dn.sales_order = sales_order
        for item in so.items:
            dn.append("items", {
                "item_code": item.item_code,
                "qty": item.qty,
                "rate": item.rate,
                "amount": item.amount,
            })
    elif items:
        if isinstance(items, str):
            items = json.loads(items)
        for item in items:
            dn.append("items", {
                "item_code": item.get("item_code"),
                "qty": flt(item.get("qty")),
                "rate": flt(item.get("rate")),
            })

    dn.insert(ignore_permissions=True)

    return _success({
        "delivery_note_id": dn.name,
        "message": "Bon de livraison créé",
    })


# ============================================================
# ACCOUNTING FEATURES (NextApp-inspired)
# ============================================================

@frappe.whitelist()
def create_sales_invoice(customer, items=None, due_date=None):
    """
    Créer une facture vente
    Inspired by NextApp - Sales Invoices
    """
    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = customer
    invoice.due_date = due_date or add_days(nowdate(), 30)

    if isinstance(items, str):
        items = json.loads(items)

    if items:
        for item in items:
            invoice.append("items", {
                "item_code": item.get("item_code"),
                "qty": flt(item.get("qty")),
                "rate": flt(item.get("rate")),
                "amount": flt(item.get("qty")) * flt(item.get("rate")),
            })

    invoice.insert(ignore_permissions=True)

    return _success({
        "invoice_id": invoice.name,
        "total": flt(invoice.grand_total),
        "message": "Facture créée",
    })


@frappe.whitelist()
def create_purchase_invoice(supplier, items=None, due_date=None):
    """
    Créer une facture achat
    Inspired by NextApp - Purchase Invoices
    """
    invoice = frappe.new_doc("Purchase Invoice")
    invoice.supplier = supplier
    invoice.bill_date = nowdate()
    invoice.due_date = due_date or add_days(nowdate(), 30)

    if isinstance(items, str):
        items = json.loads(items)

    if items:
        for item in items:
            invoice.append("items", {
                "item_code": item.get("item_code"),
                "qty": flt(item.get("qty")),
                "rate": flt(item.get("rate")),
                "amount": flt(item.get("qty")) * flt(item.get("rate")),
            })

    invoice.insert(ignore_permissions=True)

    return _success({
        "invoice_id": invoice.name,
        "total": flt(invoice.grand_total),
        "message": "Facture d'achat créée",
    })


@frappe.whitelist()
def create_journal_entry(accounts, user_remark=None):
    """
    Créer une écriture journal
    Inspired by NextApp - Journal Entries
    """
    if isinstance(accounts, str):
        accounts = json.loads(accounts)

    je = frappe.new_doc("Journal Entry")
    je.user_remark = user_remark
    je.posting_date = nowdate()

    total_debit = 0
    total_credit = 0

    for acc in accounts:
        je.append("accounts", {
            "account": acc.get("account"),
            "debit_in_account_currency": flt(acc.get("debit", 0)),
            "credit_in_account_currency": flt(acc.get("credit", 0)),
            "cost_center": acc.get("cost_center"),
        })
        total_debit += flt(acc.get("debit", 0))
        total_credit += flt(acc.get("credit", 0))

    if total_debit != total_credit:
        frappe.throw(_("Total débit {0} doit être égal au total crédit {1}").format(total_debit, total_credit))

    je.insert(ignore_permissions=True)

    return _success({
        "journal_entry_id": je.name,
        "total_debit": total_debit,
        "message": "Écriture journal créée",
    })


# ============================================================
# DASHBOARD & ANALYTICS (NextApp-inspired)
# ============================================================

@frappe.whitelist()
def get_dashboard():
    """
    Dashboard principal avec KPIs
    Inspired by NextApp - Dashboard
    """
    employee = _get_employee_from_user()
    today = nowdate()

    sales_today = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0)
        FROM `tabSales Order`
        WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
    """, (employee.name, today))[0][0])

    orders_today = cint(frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabSales Order`
        WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
    """, (employee.name, today))[0][0])

    visits_today = cint(frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabJournal de Visite`
        WHERE vendeur = %s AND creation LIKE %s
    """, (employee.name, f"{today}%"))[0][0])

    collection_today = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(paid_amount), 0)
        FROM `tabPayment Entry`
        WHERE owner = %s AND posting_date = %s AND docstatus = 1
    """, (employee.name, today))[0][0])

    pending_payments = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE customer IN (
            SELECT client FROM `tabJournal de Visite` WHERE vendeur = %s
        ) AND docstatus = 1 AND outstanding_amount > 0
    """, (employee.name,))[0][0])

    return _success({
        "date": today,
        "sales_today": sales_today,
        "orders_today": orders_today,
        "visits_today": visits_today,
        "collection_today": collection_today,
        "pending_payments": pending_payments,
    })


@frappe.whitelist()
def get_sales_report(from_date=None, to_date=None, group_by="day"):
    """
    Rapport de ventes détaillé
    Inspired by NextApp - Sales Reports
    """
    employee = _get_employee_from_user()
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    if group_by == "day":
        report = frappe.db.sql("""
            SELECT transaction_date as date,
                   COUNT(*) as orders,
                   SUM(grand_total) as total
            FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date BETWEEN %s AND %s AND docstatus = 1
            GROUP BY transaction_date
            ORDER BY transaction_date
        """, (employee.name, from_date, to_date), as_dict=True)
    elif group_by == "customer":
        report = frappe.db.sql("""
            SELECT customer, customer_name,
                   COUNT(*) as orders,
                   SUM(grand_total) as total
            FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date BETWEEN %s AND %s AND docstatus = 1
            GROUP BY customer
            ORDER BY total DESC
            LIMIT 20
        """, (employee.name, from_date, to_date), as_dict=True)
    elif group_by == "item":
        report = frappe.db.sql("""
            SELECT item_code,
                   SUM(qty) as qty,
                   SUM(amount) as total
            FROM `tabSales Order Item`
            WHERE parent IN (
                SELECT name FROM `tabSales Order`
                WHERE sales_rep = %s AND transaction_date BETWEEN %s AND %s AND docstatus = 1
            )
            GROUP BY item_code
            ORDER BY total DESC
            LIMIT 20
        """, (employee.name, from_date, to_date), as_dict=True)

    return _success({
        "from_date": from_date,
        "to_date": to_date,
        "group_by": group_by,
        "report": report,
    })


@frappe.whitelist()
def get_inventory_report(warehouse=None):
    """
    Rapport d'inventaire
    Inspired by NextApp - Stock Reports
    """
    employee = _get_employee_from_user()
    van = _get_van_assignment(employee.name)

    if not warehouse:
        warehouse = van.depot_mobile if van else None

    if not warehouse:
        return _error("Aucun dépôt configuré")

    stock = frappe.get_all(
        "Bin",
        filters={"warehouse": warehouse},
        fields=["item_code", "actual_qty", "reserved_qty", "valuation_rate", "stock_value"],
        order_by="actual_qty desc",
        limit=100
    )

    low_stock = []
    for s in stock:
        item = frappe.get_doc("Item", s.item_code)
        if s.actual_qty < item.re_order_level:
            low_stock.append({
                "item_code": s.item_code,
                "item_name": item.item_name,
                "current_qty": s.actual_qty,
                "re_order_level": item.re_order_level,
            })

    return _success({
        "warehouse": warehouse,
        "total_items": len(stock),
        "low_stock_items": low_stock,
        "stock": stock,
    })


@frappe.whitelist()
def get_pending_tasks():
    """
    Récupérer les tâches en attente (documents à soumettre, etc)
    Inspired by NextApp - Task Management
    """
    employee = _get_employee_from_user()

    pending_orders = frappe.get_all(
        "Sales Order",
        filters={"sales_rep": employee.name, "status": "Draft"},
        fields=["name", "customer", "grand_total", "transaction_date"],
        limit=10
    )

    pending_delivery = frappe.get_all(
        "Delivery Note",
        filters={"sales_rep": employee.name, "docstatus": 0},
        fields=["name", "customer", "grand_total"],
        limit=10
    )

    return _success({
        "pending_orders": pending_orders,
        "pending_delivery": pending_delivery,
    })


# ============================================================
# OFFLINE QUEUE MANAGEMENT
# ============================================================

@frappe.whitelist()
def queue_offline_operation(operation_type, data, local_id):
    """
    Ajouter une opération à la file d'attente hors-ligne
    Pour traitement quand connexion rétablie
    """
    if isinstance(data, str):
        data = json.loads(data)

    queue_item = frappe.new_doc("Offline Queue")
    queue_item.operation_type = operation_type
    queue_item.data = json.dumps(data)
    queue_item.local_id = local_id
    queue_item.status = "Pending"
    queue_item.insert(ignore_permissions=True)

    return _success({
        "queue_id": queue_item.name,
        "local_id": local_id,
        "message": "Opération mise en file d'attente",
    })


@frappe.whitelist()
def get_offline_queue():
    """
    Récupérer la file d'attente des opérations hors-ligne
    """
    queue = frappe.get_all(
        "Offline Queue",
        filters={"status": "Pending"},
        fields=["name", "operation_type", "local_id", "data", "creation"],
        order_by="creation asc"
    )

    return _success(queue)


@frappe.whitelist()
def process_offline_item(queue_item_name):
    """
    Traiter un élément de la file d'attente
    """
    queue_item = frappe.get_doc("Offline Queue", queue_item_name)
    data = json.loads(queue_item.data)

    try:
        if queue_item.operation_type == "order":
            result = create_order(**data)
            queue_item.status = "Processed"
        elif queue_item.operation_type == "payment":
            result = create_payment(**data)
            queue_item.status = "Processed"
        elif queue_item.operation_type == "visit":
            result = check_in(**data)
            queue_item.status = "Processed"
        else:
            queue_item.status = "Failed"
            queue_item.error_message = "Unknown operation type"

        queue_item.server_response = json.dumps(result)
        queue_item.save(ignore_permissions=True)
        return _success({"message": "Item processed"})
    except Exception as e:
        queue_item.status = "Failed"
        queue_item.error_message = str(e)
        queue_item.save(ignore_permissions=True)
        return _error(str(e))


# ============================================================
# GPS TRACKING & ROUTE OPTIMIZATION
# ============================================================

@frappe.whitelist()
def update_gps_location(latitude, longitude, accuracy=None, battery_level=None):
    """
    Mettre à jour la position GPS actuelle du vendeur
    Usage en temps réel pour tracking
    """
    employee = _get_employee_from_user()

    location_log = frappe.new_doc("GPS Location Log")
    location_log.vendeur = employee.name
    location_log.latitude = flt(latitude)
    location_log.longitude = flt(longitude)
    location_log.accuracy = flt(accuracy) if accuracy else None
    location_log.battery_level = flt(battery_level) if battery_level else None
    location_log.insert(ignore_permissions=True)

    return _success({
        "location_id": location_log.name,
        "message": "Position GPS enregistrée",
    })


@frappe.whitelist()
def get_gps_history(from_date=None, to_date=None):
    """
    Historique des positions GPS du vendeur
    """
    employee = _get_employee_from_user()

    filters = {"vendeur": employee.name}
    if from_date:
        filters["creation"] = ["between", [from_date, to_date or nowdate()]]

    locations = frappe.get_all(
        "GPS Location Log",
        filters=filters,
        fields=["name", "latitude", "longitude", "accuracy", "creation"],
        order_by="creation desc",
        limit=500
    )

    return _success(locations)


@frappe.whitelist()
def get_route_distanceMatrix(customers):
    """
    Calculer la matrice des distances entre clients pour optimisation
    """
    if isinstance(customers, str):
        customers = json.loads(customers)

    from fieldforce_dz.api.geofence import haversine_distance

    customer_coords = {}
    for cust in customers:
        customer_doc = frappe.get_doc("Customer", cust)
        lat = customer_doc.get("latitude") or frappe.db.get_value("Customer", cust, "latitude")
        lng = customer_doc.get("longitude") or frappe.db.get_value("Customer", cust, "longitude")
        if lat and lng:
            customer_coords[cust] = {"lat": flt(lat), "lng": flt(lng)}

    matrix = {}
    for c1 in customer_coords:
        matrix[c1] = {}
        for c2 in customer_coords:
            if c1 != c2:
                dist = haversine_distance(
                    customer_coords[c1]["lat"], customer_coords[c1]["lng"],
                    customer_coords[c2]["lat"], customer_coords[c2]["lng"]
                )
                matrix[c1][c2] = {"distance_m": round(dist, 1)}

    return _success({
        "matrix": matrix,
        "customers": list(customer_coords.keys()),
    })


# ============================================================
# BARCODE & SKU SCANNING
# ============================================================

@frappe.whitelist()
def scan_barcode(barcode):
    """
    Rechercher un article par code-barres
    """
    item_code = frappe.db.get_value("Item", {"barcode": barcode}, "name")

    if not item_code:
        item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")

    if not item_code:
        return _error("Article non trouvé pour code-barres: {0}".format(barcode))

    item = frappe.get_doc("Item", item_code)

    return _success({
        "item_code": item.item_code,
        "item_name": item.item_name,
        "stock_uom": item.stock_uom,
        "standard_rate": flt(item.standard_rate),
        "has_batch_no": item.has_batch_no,
    })


@frappe.whitelist()
def get_item_batch_numbers(item_code):
    """
    Récupérer les numéros de lot pour un article
    """
    batches = frappe.get_all(
        "Batch",
        filters={"item": item_code, "expiry_date": [">", nowdate()]},
        fields=["name", "batch_id", "expiry_date", "qty"],
        order_by="expiry_date asc"
    )

    return _success(batches)


# ============================================================
# CUSTOMER FEEDBACK & RATINGS
# ============================================================

@frappe.whitelist()
def submit_customer_feedback(customer, rating, comments=None, order_id=None):
    """
    Soumettre unfeedback client après visite
    """
    employee = _get_employee_from_user()

    feedback = frappe.new_doc("Customer Feedback")
    feedback.customer = customer
    feedback.vendeur = employee.name
    feedback.rating = cint(rating)
    feedback.comments = comments
    feedback.related_order = order_id
    feedback.insert(ignore_permissions=True)

    return _success({
        "feedback_id": feedback.name,
        "rating": rating,
        "message": "Feedback enregistré",
    })


@frappe.whitelist()
def get_customer_feedback(customer):
    """
    Récupérer le feedback d'un client
    """
    feedback = frappe.get_all(
        "Customer Feedback",
        filters={"customer": customer},
        fields=["name", "rating", "comments", "vendeur", "creation"],
        order_by="creation desc",
        limit=10
    )

    avg_rating = frappe.db.sql("""
        SELECT AVG(rating) FROM `tabCustomer Feedback` WHERE customer = %s
    """, (customer,))[0][0]

    return _success({
        "feedback": feedback,
        "average_rating": flt(avg_rating) if avg_rating else 0,
    })


# ============================================================
# PROMOTIONS & OFFERS
# ============================================================

@frappe.whitelist()
def get_active_promotions():
    """
    Récupérer les promotions actives
    """
    promotions = frappe.get_all(
        "Promotion",
        filters={"promo_type": "Selling", "active": 1},
        fields=["name", "promo_code", "title", "discount_percent", "discount_amount", "start_date", "end_date"],
        limit=20
    )

    return _success(promotions)


@frappe.whitelist()
def apply_promo_code(customer, promo_code):
    """
    Appliquer un code promo à une commande
    """
    promo = frappe.get_doc("Promotion", promo_code)

    if not promo.active:
        return _error("Promotion inactive")

    if promo.start_date and promo.start_date > nowdate():
        return _error("Promotion pas encore starts")

    if promo.end_date and promo.end_date < nowdate():
        return _error("Promotion expire")

    return _success({
        "promo_code": promo.promo_code,
        "discount_percent": flt(promo.discount_percent),
        "discount_amount": flt(promo.discount_amount),
        "message": "Code promo appliqué",
    })


# ============================================================
# MULTI-WAREHOUSE TRANSFERS
# ============================================================

@frappe.whitelist()
def request_stock_transfer(items, from_warehouse, to_warehouse, reason=None):
    """
    Demander un transfert de stock entre dépôts
    """
    if isinstance(items, str):
        items = json.loads(items)

    transfer = frappe.new_doc("Stock Transfer")
    transfer.from_warehouse = from_warehouse
    transfer.to_warehouse = to_warehouse
    transfer.reason = reason

    for item in items:
        transfer.append("items", {
            "item_code": item.get("item_code"),
            "qty": flt(item.get("qty")),
            "from_warehouse": from_warehouse,
            "to_warehouse": to_warehouse,
        })

    transfer.insert(ignore_permissions=True)

    return _success({
        "transfer_id": transfer.name,
        "message": "Demande de transfert créée",
    })


@frappe.whitelist()
def get_warehouse_list():
    """
    Liste de tous les dépôts
    """
    warehouses = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0},
        fields=["name", "warehouse_name", "company"],
        order_by="warehouse_name"
    )

    return _success(warehouses)


# ============================================================
# PRICE CHECK & COMPARISON
# ============================================================

@frappe.whitelist()
def compare_item_prices(item_code, price_lists):
    """
    Comparer les prix d'un articleacross différentes listes
    """
    if isinstance(price_lists, str):
        price_lists = json.loads(price_lists)

    prices = []
    for pl in price_lists:
        rate = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": pl, "selling": 1},
            "price_list_rate"
        ) or frappe.db.get_value("Item", item_code, "standard_rate") or 0

        prices.append({
            "price_list": pl,
            "rate": flt(rate),
        })

    return _success({
        "item_code": item_code,
        "prices": prices,
    })


# ============================================================
# RETURN MANAGEMENT
# ============================================================

@frappe.whitelist()
def create_sales_return(sales_invoice, items, reason=None):
    """
    Créer un retour client (Sales Return)
    """
    if isinstance(items, str):
        items = json.loads(items)

    return_doc = frappe.new_doc("Sales Return")
    return_doc.return_against = sales_invoice
    return_doc.customer = frappe.db.get_value("Sales Invoice", sales_invoice, "customer")
    return_doc.reason = reason
    return_doc.insert(ignore_permissions=True)

    for item in items:
        return_doc.append("items", {
            "item_code": item.get("item_code"),
            "qty": flt(item.get("qty")),
            "rate": flt(item.get("rate")),
        })

    return_doc.insert(ignore_permissions=True)

    return _success({
        "return_id": return_doc.name,
        "message": "Retour créé",
    })


@frappe.whitelist()
def get_return_history(customer):
    """
    Historique des retours client
    """
    returns = frappe.get_all(
        "Sales Return",
        filters={"customer": customer},
        fields=["name", "return_against", "grand_total", "creation"],
        order_by="creation desc",
        limit=20
    )

    return _success(returns)


# ============================================================
# QUICK ACTIONS
# ============================================================

@frappe.whitelist()
def quick_order(customer, item_code, qty, price_list=None):
    """
    Commande rapide - un seul article
    """
    return create_order(
        customer=customer,
        items=json.dumps([{"item_code": item_code, "qty": qty}]),
        price_list=price_list,
    )


@frappe.whitelist()
def quick_payment(customer, amount, mode_of_payment="Espèces"):
    """
    Paiement rapide sans référence
    """
    return create_payment(
        customer=customer,
        amount=amount,
        mode_of_payment=mode_of_payment,
    )


@frappe.whitelist()
def quick_visit(customer):
    """
    Visite rapide sans commande
    """
    employee = _get_employee_from_user()

    visit = frappe.new_doc("Journal de Visite")
    visit.client = customer
    visit.vendeur = employee.name
    visit.heure_arrivee = now_datetime()
    visit.statut = "Visité"
    visit.insert(ignore_permissions=True)

    return _success({
        "visit_id": visit.name,
        "message": "Visite enregistrée",
    })


# ============================================================
# SUPERVISOR FEATURES
# ============================================================

@frappe.whitelist()
def get_team_performance(team_leader=None):
    """
    Performance de léquipe (pour superviseurs)
    """
    if not team_leader:
        return _error("team_leader requis")

    today = nowdate()

    team_members = frappe.get_all(
        "Employee",
        filters={"reports_to": team_leader, "status": "Active"},
        fields=["name", "employee_name"]
    )

    performance = []
    for member in team_members:
        orders_today = cint(frappe.db.sql("""
            SELECT COUNT(*) FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
        """, (member.name, today))[0][0])

        sales_today = flt(frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) FROM `tabSales Order`
            WHERE sales_rep = %s AND transaction_date = %s AND docstatus = 1
        """, (member.name, today))[0][0])

        visits_today = cint(frappe.db.sql("""
            SELECT COUNT(*) FROM `tabJournal de Visite`
            WHERE vendeur = %s AND creation LIKE %s
        """, (member.name, f"{today}%"))[0][0])

        performance.append({
            "employee": member.name,
            "employee_name": member.employee_name,
            "orders_today": orders_today,
            "sales_today": sales_today,
            "visits_today": visits_today,
        })

    return _success(performance)


@frappe.whitelist()
def get_team_location(team_leader=None):
    """
    Positions GPS temps réel de léquipe
    """
    if not team_leader:
        return _error("team_leader requis")

    team_members = frappe.get_all(
        "Employee",
        filters={"reports_to": team_leader, "status": "Active"},
        fields=["name"]
    )

    locations = []
    for member in team_members:
        last_location = frappe.get_all(
            "GPS Location Log",
            filters={"vendeur": member.name},
            fields=["vendeur", "latitude", "longitude", "creation"],
            order_by="creation desc",
            limit=1
        )
        if last_location:
            locations.append(last_location[0])

    return _success(locations)


@frappe.whitelist()
def assign_route_to_vendor(vendor, route_name, date=None):
    """
    Assigner une tournée à un vendeur
    """
    if not date:
        date = nowdate()

    assignment = frappe.new_doc("Route Assignment")
    assignment.vendeur = vendor
    assignment.route = route_name
    assignment.assignment_date = date
    assignment.status = "Assigned"
    assignment.insert(ignore_permissions=True)

    return _success({
        "assignment_id": assignment.name,
        "message": "Tournée assignée",
    })


# ============================================================
# ANALYTICS DEEP DIVE
# ============================================================

@frappe.whitelist()
def get_customer_analytics(customer):
    """
    Analytique détaillée dun client
    """
    total_orders = cint(frappe.db.sql("""
        SELECT COUNT(*) FROM `tabSales Order` WHERE customer = %s AND docstatus = 1
    """, (customer,))[0][0])

    total_sales = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0) FROM `tabSales Order` WHERE customer = %s AND docstatus = 1
    """, (customer,))[0][0])

    avg_order = total_sales / total_orders if total_orders > 0 else 0

    last_order_date = frappe.db.sql("""
        SELECT MAX(transaction_date) FROM `tabSales Order` WHERE customer = %s AND docstatus = 1
    """, (customer,))[0][0]

    last_payment = frappe.db.sql("""
        SELECT MAX(posting_date) FROM `tabPayment Entry` WHERE party = %s AND docstatus = 1
    """, (customer,))[0][0]

    outstanding = _get_customer_outstanding(customer)

    top_items = frappe.db.sql("""
        SELECT item_code, SUM(qty) as qty, SUM(amount) as amount
        FROM `tabSales Order Item`
        WHERE parent IN (SELECT name FROM `tabSales Order` WHERE customer = %s AND docstatus = 1)
        GROUP BY item_code ORDER BY amount DESC LIMIT 5
    """, (customer,), as_dict=True)

    return _success({
        "customer": customer,
        "total_orders": total_orders,
        "total_sales": total_sales,
        "average_order": flt(avg_order),
        "last_order_date": last_order_date,
        "last_payment_date": last_payment,
        "outstanding": outstanding,
        "top_items": top_items,
    })


@frappe.whitelist()
def get_product_analytics(item_code):
    """
    Analytique détaillée d un article
    """
    total_sold = cint(frappe.db.sql("""
        SELECT COALESCE(SUM(qty), 0) FROM `tabSales Order Item` WHERE item_code = %s
    """, (item_code,))[0][0])

    total_revenue = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(amount), 0) FROM `tabSales Order Item` WHERE item_code = %s
    """, (item_code,))[0][0])

    current_stock = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(actual_qty), 0) FROM `tabBin` WHERE item_code = %s
    """, (item_code,))[0][0])

    low_stock_warehouses = frappe.db.sql("""
        SELECT warehouse, actual_qty FROM `tabBin`
        WHERE item_code = %s AND actual_qty < 10
    """, (item_code,), as_dict=True)

    customer_count = cint(frappe.db.sql("""
        SELECT COUNT(DISTINCT customer) FROM `tabSales Order Item`
        WHERE parent IN (SELECT name FROM `tabSales Order` WHERE docstatus = 1)
        AND item_code = %s
    """, (item_code,))[0][0])

    return _success({
        "item_code": item_code,
        "total_sold": total_sold,
        "total_revenue": total_revenue,
        "current_stock": current_stock,
        "customer_count": customer_count,
        "low_stock_warehouses": low_stock_warehouses,
    })


# ============================================================
# DAILY METRICS
# ============================================================

@frappe.whitelist()
def get_daily_metrics(date=None):
    """Obtenir les métriques du jour pour le dashboard"""
    if not date:
        date = nowdate()
    
    # Commandes du jour
    orders_today = frappe.db.sql("""
        SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as total
        FROM `tabSales Order`
        WHERE transaction_date = %s AND docstatus = 1
    """, (date,), as_dict=True)[0]
    
    # Encaissements du jour
    collections_today = frappe.db.sql("""
        SELECT COUNT(*) as count, COALESCE(SUM(paid_amount), 0) as total
        FROM `tabPayment Entry`
        WHERE posting_date = %s AND docstatus = 1 AND payment_type = 'Receive'
    """, (date,), as_dict=True)[0]
    
    # Visites du jour
    visits_today = frappe.db.sql("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN statut = 'Visité' THEN 1 ELSE 0 END) as completed
        FROM `tabJournal de Visite`
        WHERE creation LIKE %s
    """, (f"{date}%",), as_dict=True)[0]
    
    # Objectif du jour (par défaut 35000 DA)
    target_amount = 35000
    achievement = (orders_today.total / target_amount * 100) if orders_today.total else 0
    
    return _success({
        "date": date,
        "orders_today": orders_today.count or 0,
        "sales_today": orders_today.total or 0,
        "collections_today": collections_today.total or 0,
        "visits_today": visits_today.total or 0,
        "visits_completed": visits_today.completed or 0,
        "target_amount": target_amount,
        "achievement": round(achievement, 1),
    })


# ============================================================
# HR FEATURES - NextApp Inspired
# ============================================================

@frappe.whitelist()
def get_employee_profile(employee_id=None):
    """
    Profil complet de l'employé - NextApp HR
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    emp = frappe.get_doc("Employee", employee_id)
    
    # Get company info
    company = frappe.get_doc("Company", emp.company) if emp.company else None
    
    # Get reporting manager
    reports_to = None
    if emp.reports_to:
        manager = frappe.get_doc("Employee", emp.reports_to)
        reports_to = {
            "name": manager.name,
            "employee_name": manager.employee_name,
            "designation": manager.designation,
        }
    
    # Get depot mobile assignment
    van = _get_van_assignment(employee_id)
    
    return _success({
        "employee": {
            "name": emp.name,
            "employee_name": emp.employee_name,
            "designation": emp.designation,
            "department": emp.department,
            "branch": emp.branch,
            "company": emp.company,
            "company_name": company.name if company else None,
            "date_of_joining": emp.date_of_joining,
            "date_of_birth": emp.date_of_birth,
            "gender": emp.gender,
            "marital_status": emp.marital_status,
            "blood_group": emp.blood_group,
            "phone": emp.phone,
            "cell_number": emp.cell_number,
            "personal_email": emp.personal_email,
            "company_email": emp.employee_name,
            "permanent_address": emp.permanent_address,
            "current_address": emp.current_address,
            "reports_to": reports_to,
            "image": emp.image,
            "status": emp.status,
        },
        "van_assignment": van,
    })


@frappe.whitelist()
def get_leave_balance(employee_id=None):
    """
    Solde de congés - NextApp HR Leave Balance
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    leave_types = frappe.get_all(
        "Leave Type",
        fields=["name", "leave_type_name", "max_days_allowed", "is_carry_forward", "carry_forward_days"],
        order_by="leave_type_name"
    )

    balances = []
    for lt in leave_types:
        allocated = frappe.db.get_value(
            "Leave Allocation",
            {
                "employee": employee_id,
                "leave_type": lt.name,
                "from_date": ["<=", nowdate()],
                "to_date": [">=", nowdate()],
                "status": "Approved"
            },
            "total_leaves_allocated"
        ) or 0

        spent = frappe.db.get_value(
            "Leave Application",
            {
                "employee": employee_id,
                "leave_type": lt.name,
                "from_date": ["<=", nowdate()],
                "to_date": [">=", nowdate()],
                "status": "Approved"
            },
            "sum(from_date)"
        )

        pending = frappe.db.get_value(
            "Leave Application",
            {
                "employee": employee_id,
                "leave_type": lt.name,
                "status": ["in", ["Pending", "Half Day"]]
            },
            "count(*)"
        ) or 0

        # Calculate pending days
        pending_days = 0
        pending_apps = frappe.get_all(
            "Leave Application",
            filters={
                "employee": employee_id,
                "leave_type": lt.name,
                "status": "Pending"
            },
            fields=["from_date", "to_date"]
        )
        for app in pending_apps:
            from_dt = getdate(app.from_date)
            to_dt = getdate(app.to_date)
            pending_days += (to_dt - from_dt).days + 1

        balances.append({
            "leave_type": lt.name,
            "leave_type_name": lt.leave_type_name,
            "allocated": flt(allocated),
            "spent": flt(allocated) - flt(pending_days) - flt(spent or 0),
            "pending": pending_days,
            "balance": flt(allocated) - flt(spent or 0) - pending_days,
            "max_allowed": lt.max_days_allowed,
            "is_carry_forward": lt.is_carry_forward,
        })

    return _success({"leave_balances": balances})


@frappe.whitelist()
def get_leave_applications(employee_id=None, status=None, limit=20):
    """
    Demandes de congés - NextApp HR Leave History
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    filters = {"employee": employee_id}
    if status:
        filters["status"] = status

    applications = frappe.get_all(
        "Leave Application",
        filters=filters,
        fields=["name", "leave_type", "from_date", "to_date", "total_leave_days", 
                "status", "reason", "created_by", "creation", "modified"],
        order_by="creation desc",
        limit=limit
    )

    for app in applications:
        app.leave_type_name = frappe.db.get_value("Leave Type", app.leave_type, "leave_type_name")
        app.approved_by = frappe.db.get_value("Leave Application", app.name, "approved_by")

    return _success({"leave_applications": applications})


@frappe.whitelist()
def get_holidays(from_date=None, to_date=None, employee_id=None):
    """
    Jours fériés - NextApp HR Holidays
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    # Get employee's holiday list
    emp = frappe.get_doc("Employee", employee_id)
    holiday_list_name = emp.holiday_list or frappe.db.get_value("Company", emp.company, "default_holiday_list")

    filters = {}
    if holiday_list_name:
        filters["parent"] = holiday_list_name
    if from_date:
        filters["holiday_date"] = [">=", from_date]
    if to_date:
        filters["holiday_date"] = ["<=", to_date]

    holidays = frappe.get_all(
        "Holiday",
        filters=filters,
        fields=["name", "holiday_date", "description"],
        order_by="holiday_date"
    )

    return _success({
        "holidays": holidays,
        "holiday_list": holiday_list_name,
        "total": len(holidays),
    })


@frappe.whitelist()
def get_salary_slips(employee_id=None, limit=6):
    """
    Bulletins de salaire - NextApp HR Salary
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee_id,
            "docstatus": ["!=", 0]
        },
        fields=["name", "start_date", "end_date", "gross_pay", "total_deduction", 
                "net_pay", "status", "posting_date", "fiscal_year"],
        order_by="start_date desc",
        limit=limit
    )

    for slip in slips:
        # Get earning details
        earnings = frappe.get_all(
            "Salary Detail",
            filters={"parent": slip.name, "parentfield": "earnings"},
            fields=["salary_component", "amount", "abbr"]
        )
        slip.earnings = [e for e in earnings if e.amount > 0]

        # Get deduction details
        deductions = frappe.get_all(
            "Salary Detail",
            filters={"parent": slip.name, "parentfield": "deductions"},
            fields=["salary_component", "amount", "abbr"]
        )
        slip.deductions = [d for d in deductions if d.amount > 0]

    return _success({"salary_slips": slips})


@frappe.whitelist()
def get_expense_claims(employee_id=None, status=None, limit=20):
    """
    Notes de frais - NextApp HR Expense Claims
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    filters = {"employee": employee_id}
    if status:
        filters["status"] = status

    claims = frappe.get_all(
        "Expense Claim",
        filters=filters,
        fields=["name", "expense_type", "description", "amount", "claimed_amount",
                "approved_amount", "status", "posting_date", "creation"],
        order_by="creation desc",
        limit=limit
    )

    return _success({"expense_claims": claims})


@frappe.whitelist()
def get_attendance_summary(employee_id=None, month=None, year=None):
    """
    Résumé présence mensuelle - NextApp HR Attendance Summary
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    import calendar
    import datetime
    
    if not month:
        month = nowdate().month
    if not year:
        year = nowdate().year
    
    first_day = f"{year}-{month:02d}-01"
    last_day = f"{year}-{month:02d}-{calendar.monthrange(int(year), int(month))[1]:02d}"

    attendance_list = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee_id,
            "attendance_date": ["between", [first_day, last_day]],
            "docstatus": 1
        },
        fields=["name", "attendance_date", "status", "in_time", "out_time", "working_hours"]
    )

    summary = {
        "total_days": calendar.monthrange(int(year), int(month))[1],
        "present": 0,
        "absent": 0,
        "on_leave": 0,
        "half_day": 0,
        "work_from_home": 0,
    }

    for att in attendance_list:
        if att.status == "Present":
            summary["present"] += 1
        elif att.status == "Absent":
            summary["absent"] += 1
        elif att.status == "On Leave":
            summary["on_leave"] += 1
        elif att.status == "Half Day":
            summary["half_day"] += 1
        elif att.status == "Work From Home":
            summary["work_from_home"] += 1

    return _success({
        "summary": summary,
        "month": month,
        "year": year,
        "first_day": first_day,
        "last_day": last_day,
        "attendance": attendance_list,
    })


@frappe.whitelist()
def get_team_calendar(employee_id=None, from_date=None, to_date=None):
    """
    Calendrier équipe - NextApp HR Team Calendar
    Pour managers qui voient les congés de leur équipe
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    # Get team members (employees who report to this user)
    team_members = frappe.get_all(
        "Employee",
        filters={"reports_to": employee_id, "status": "Active"},
        fields=["name", "employee_name", "designation", "department"]
    )

    if not team_members:
        return _success({"team_leaves": [], "team_members": []})

    team_ids = [m.name for m in team_members]
    
    # Get leaves for team
    leave_filters = {"employee": ["in", team_ids], "status": ["in", ["Pending", "Approved"]]}
    if from_date:
        leave_filters["from_date"] = [">=", from_date]
    if to_date:
        leave_filters["to_date"] = ["<=", to_date]

    team_leaves = frappe.get_all(
        "Leave Application",
        filters=leave_filters,
        fields=["name", "employee", "leave_type", "from_date", "to_date", 
                "total_leave_days", "status", "reason", "created_by"]
    )

    for leave in team_leaves:
        emp_name = next((m.employee_name for m in team_members if m.name == leave.employee), leave.employee)
        leave.employee_name = emp_name

    return _success({
        "team_members": team_members,
        "team_leaves": team_leaves,
    })


@frappe.whitelist()
def get_payroll_summary(employee_id=None):
    """
    Résumé paie - NextApp HR Payroll Summary
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    # Get last 3 salary slips
    recent_slips = frappe.get_all(
        "Salary Slip",
        filters={"employee": employee_id, "docstatus": 1},
        fields=["name", "start_date", "end_date", "gross_pay", "net_pay"],
        order_by="start_date desc",
        limit=3
    )

    total_gross = sum(flt(s.gross_pay) for s in recent_slips)
    total_net = sum(flt(s.net_pay) for s in recent_slips)

    # Get deductions summary
    deductions = frappe.get_all(
        "Salary Detail",
        filters={"parent": ["in", [s.name for s in recent_slips]], "parentfield": "deductions"},
        fields=["salary_component", "amount"]
    )

    deduction_summary = {}
    for d in deductions:
        if d.salary_component not in deduction_summary:
            deduction_summary[d.salary_component] = 0
        deduction_summary[d.salary_component] += flt(d.amount)

    return _success({
        "recent_slips": recent_slips,
        "total_gross_avg": flt(total_gross) / 3 if recent_slips else 0,
        "total_net_avg": flt(total_net) / 3 if recent_slips else 0,
        "deduction_summary": deduction_summary,
    })


@frappe.whitelist()
def get_notifications(employee_id=None, notif_type=None, limit=50):
    """
    Notifications RH - NextApp HR Notifications
    """
    if not employee_id:
        employee = _get_employee_from_user()
        employee_id = employee.name

    notifications = []

    # Leave status notifications
    pending_leaves = frappe.get_all(
        "Leave Application",
        filters={"employee": employee_id, "status": "Pending"},
        fields=["name", "leave_type", "from_date", "to_date", "creation"]
    )
    for leave in pending_leaves:
        notifications.append({
            "type": "leave_pending",
            "title": "Congé en attente",
            "message": f"Votre demande de congé ({leave.leave_type}) du {leave.from_date} au {leave.to_date} est en attente d'approbation",
            "reference": leave.name,
            "date": leave.creation,
            "read": False,
        })

    # Expense claim status
    pending_expenses = frappe.get_all(
        "Expense Claim",
        filters={"employee": employee_id, "status": "Pending"},
        fields=["name", "expense_type", "amount", "creation"]
    )
    for expense in pending_expenses:
        notifications.append({
            "type": "expense_pending",
            "title": "Note de frais en attente",
            "message": f"Votre note de frais ({expense.expense_type}) de {expense.amount} DA est en attente",
            "reference": expense.name,
            "date": expense.creation,
            "read": False,
        })

    # Team leave approvals (for managers)
    team_members = frappe.get_all(
        "Employee",
        filters={"reports_to": employee_id, "status": "Active"},
        fields=["name"]
    )
    if team_members:
        team_ids = [m.name for m in team_members]
        pending_team_leaves = frappe.get_all(
            "Leave Application",
            filters={"employee": ["in", team_ids], "status": "Pending"},
            fields=["name", "employee", "leave_type", "from_date", "to_date", "creation"]
        )
        for leave in pending_team_leaves:
            emp_name = frappe.db.get_value("Employee", leave.employee, "employee_name")
            notifications.append({
                "type": "leave_approval",
                "title": "Approbation requise",
                "message": f"{emp_name} a demandé un congé ({leave.leave_type}) du {leave.from_date} au {leave.to_date}",
                "reference": leave.name,
                "date": leave.creation,
                "read": False,
                "action_required": True,
            })

    # Sort by date
    notifications.sort(key=lambda x: x["date"], reverse=True)

    # Filter by type
    if notif_type:
        notifications = [n for n in notifications if n["type"] == notif_type]

    return _success({
        "notifications": notifications[:limit],
        "total": len(notifications),
        "unread": len([n for n in notifications if not n.get("read", False)]),
    })


@frappe.whitelist()
def create_sales_order(customer, items, currency="DZD", po_no=None, notes=None):
    """
    Créer une Sales Order depuis l'app mobile - NextApp Order Flow
    """
    try:
        # Validate customer
        if not customer:
            return _error("Client requis", 400)
        
        # Validate items
        if not items or len(items) == 0:
            return _error("Au moins un article requis", 400)
        
        # Get employee for sales team assignment
        employee = _get_employee_from_user()
        van = _get_van_assignment(employee.name)
        
        # Get customer info for price list
        customer_doc = frappe.get_doc("Customer", customer)
        price_list = customer_doc.default_price_list or "Standard Selling"
        
        # Create Sales Order
        so = frappe.new_doc("Sales Order")
        so.customer = customer
        so.currency = currency
        so.price_list = price_list
        so.selling_price_list = price_list
        
        # Add items
        total_qty = 0
        total_amount = 0
        for item in items:
            item_code = item.get('item_code')
            qty = flt(item.get('qty', 1))
            rate = flt(item.get('rate', 0))
            
            # Get stock availability in van warehouse
            if van:
                stock_qty = frappe.db.get_value(
                    "Bin",
                    {"item_code": item_code, "warehouse": van.depot_mobile},
                    "actual_qty"
                ) or 0
            else:
                stock_qty = 0
            
            so.append("items", {
                "item_code": item_code,
                "qty": qty,
                "rate": rate,
                "warehouse": van.depot_mobile if van else None,
                "transfer_qty": qty,
                "uom": frappe.db.get_value("Item", item_code, "stock_uom") or "Nos",
            })
            
            total_qty += qty
            total_amount += qty * rate
        
        # Set company
        so.company = employee.company
        
        # Assign sales team
        so.sales_person = employee.name
        
        # PO reference if provided
        if po_no:
            so.po_no = po_no
        
        # Notes
        if notes:
            so.notes = notes
        
        # Auto-submit for mobile (vendors can create submitted orders)
        so.insert()
        so.submit()
        
        # Create payment entry if payment is received (cash on delivery)
        payment_received = flt(notes.get('payment_amount')) if notes and isinstance(notes, dict) else 0
        if payment_received > 0:
            pe = frappe.new_doc("Payment Entry")
            pe.payment_type = "Receive"
            pe.party_type = "Customer"
            pe.party = customer
            pe.amount = payment_received
            pe.received_amount = payment_received
            pe.reference_doctype = "Sales Order"
            pe.reference_name = so.name
            pe.insert()
            pe.submit()
        
        return _success({
            "order_id": so.name,
            "status": so.status,
            "total_qty": total_qty,
            "grand_total": so.grand_total,
            "message": f"Commande {so.name} créée avec succès",
        })
        
    except frappe.ValidationError as e:
        return _error(str(e), 400)
    except Exception as e:
        frappe.log_error(f"Mobile Order Creation Error: {str(e)}")
        return _error(f"Erreur création commande: {str(e)}", 500)


@frappe.whitelist()
def create_payment_entry(customer, amount, mode_of_payment="Cash", reference_no=None, sales_order=None):
    """
    Créer une Payment Entry depuis l'app mobile - NextApp Payment Collection
    """
    try:
        if not customer:
            return _error("Client requis", 400)
        
        if not amount or amount <= 0:
            return _error("Montant invalide", 400)
        
        employee = _get_employee_from_user()
        
        # Get company from employee
        company = frappe.db.get_value("Employee", employee.name, "company")
        
        # Get cash account for the company
        cash_account = frappe.db.get_value("Company", company, "default_cash_account")
        if not cash_account:
            cash_account = frappe.db.get_value("Account", 
                {"company": company, "account_type": "Cash", "is_group": 0}, "name")
        
        # Get receivable account
        receivable_account = frappe.db.get_value("Company", company, "default_receivable_account")
        
        # Create Payment Entry
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = customer
        pe.amount = flt(amount)
        pe.received_amount = flt(amount)
        pe.mode_of_payment = mode_of_payment
        pe.reference_no = reference_no or ""
        pe.reference_date = nowdate()
        pe.company = company
        pe.paid_to = cash_account
        pe.paid_from = receivable_account
        pe.remarks = f"Payment created from FieldForce DZ mobile app by {employee.employee_name}"
        
        # Link to Sales Order if provided
        if sales_order:
            pe.append("references", {
                "reference_doctype": "Sales Order",
                "reference_name": sales_order,
                "allocated_amount": flt(amount),
            })
        
        pe.insert()
        pe.submit()
        
        return _success({
            "payment_id": pe.name,
            "amount": pe.amount,
            "mode_of_payment": pe.mode_of_payment,
            "status": pe.status,
            "message": f"Paiement {pe.name} enregistré",
        })
        
    except frappe.ValidationError as e:
        return _error(str(e), 400)
    except Exception as e:
        frappe.log_error(f"Mobile Payment Creation Error: {str(e)}")
        return _error(f"Erreur création paiement: {str(e)}", 500)
