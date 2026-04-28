# ============================================================
# FieldForce DZ — Geofence Validation Engine
# Validation GPS: Haversine distance + geofence check
# ============================================================

import math
import frappe
from frappe import _


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculer la distance entre deux points GPS (formule de Haversine)
    Retourne la distance en mètres
    """
    R = 6371000  # Rayon de la Terre en mètres

    phi1 = math.radians(flt(lat1))
    phi2 = math.radians(flt(lat2))
    delta_phi = math.radians(flt(lat2) - flt(lat1))
    delta_lambda = math.radians(flt(lon2) - flt(lon1))

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def verify_geofence(customer, phone_lat, phone_lng):
    """
    Vérifier si le vendeur est dans la zone géofence du client.
    
    Args:
        customer: ID du client (Customer doctype)
        phone_lat: Latitude du téléphone du vendeur
        phone_lng: Longitude du téléphone du vendeur
    
    Returns:
        dict with distance_meters, is_within_geofence, geofence_radius
    """
    # Récupérer les coordonnées du client
    customer_doc = frappe.get_doc("Customer", customer)

    # Les coordonnées GPS sont stockées dans les champs personnalisés
    customer_lat = flt(customer_doc.get("latitude") or 
                       frappe.db.get_value("Customer", customer, "latitude") or 0)
    customer_lng = flt(customer_doc.get("longitude") or 
                       frappe.db.get_value("Customer", customer, "longitude") or 0)

    if not customer_lat or not customer_lng:
        # Essayer de récupérer depuis l'adresse principale
        address = frappe.get_all(
            "Address",
            filters={"dynamic_type": "Customer", "dynamic_name": customer,
                     "is_primary_address": 1},
            fields=["latitude", "longitude"],
            limit=1
        )
        if address:
            customer_lat = flt(address[0].latitude)
            customer_lng = flt(address[0].longitude)

    if not customer_lat or not customer_lng:
        frappe.throw(
            _("Coordonnées GPS non configurées pour le client {0}. "
              "Veuillez configurer la latitude et longitude dans la fiche client.").format(customer),
            title=_("GPS manquant")
        )

    # Récupérer le rayon géofence
    geofence_radius = _get_geofence_radius()

    # Calculer la distance
    distance = haversine_distance(phone_lat, phone_lng, customer_lat, customer_lng)
    is_within = distance <= geofence_radius

    return {
        "customer_lat": customer_lat,
        "customer_lng": customer_lng,
        "phone_lat": flt(phone_lat),
        "phone_lng": flt(phone_lng),
        "distance_meters": round(distance, 1),
        "geofence_radius": geofence_radius,
        "is_within_geofence": is_within,
        "accuracy_level": _get_accuracy_level(distance, geofence_radius),
    }


def _get_geofence_radius():
    """
    Récupérer le rayon géofence configuré.
    Par défaut 50 mètres.
    """
    # 1. Vérifier l'affectation dépôt mobile du vendeur
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")

    if employee:
        radius = frappe.db.get_value(
            "Affectation Depot Mobile",
            {"vendeur": employee, "is_active": 1},
            "geofence_radius"
        )
        if radius:
            return cint(radius)

    # 2. Vérifier les paramètres globaux
    radius = frappe.db.get_single_value("Fieldforce DZ Settings", "default_geofence_radius")
    if radius:
        return cint(radius)

    # 3. Défaut
    return 50


def _get_accuracy_level(distance, radius):
    """Niveau de précision du GPS pour l'affichage"""
    if distance <= 10:
        return {"level": "excellent", "color": "green", "label": "Excellent (< 10m)"}
    elif distance <= radius * 0.5:
        return {"level": "good", "color": "green", "label": "Bon"}
    elif distance <= radius:
        return {"level": "acceptable", "color": "yellow", "label": "Acceptable"}
    elif distance <= radius * 1.5:
        return {"level": "marginal", "color": "orange", "label": "Marginal"}
    else:
        return {"level": "outside", "color": "red", "label": "Hors zone"}


def validate_geofence_for_order(customer, phone_lat, phone_lng):
    """
    Validation stricte pour la création de commande.
    Lève une exception si le vendeur est hors zone.
    """
    result = verify_geofence(customer, phone_lat, phone_lng)

    if not result["is_within_geofence"]:
        frappe.throw(
            _(
                "🚫 GÉOFENCE VIOLÉ — Impossible de créer la commande.\n\n"
                "Distance du client: <b>{distance}m</b> (rayon autorisé: {radius}m)\n"
                "Coordonnées téléphone: {phone_lat:.6f}, {phone_lng:.6f}\n"
                "Coordonnées client: {cust_lat:.6f}, {cust_lng:.6f}\n\n"
                "Veuillez vous rapprocher du client et réessayer."
            ).format(
                distance=int(result["distance_meters"]),
                radius=result["geofence_radius"],
                phone_lat=result["phone_lat"],
                phone_lng=result["phone_lng"],
                cust_lat=result["customer_lat"],
                cust_lng=result["customer_lng"],
            ),
            title=_("Vérification GPS échouée")
        )

    return result


def flt(val):
    """Frappe-compatible float conversion"""
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0


def cint(val):
    """Frappe-compatible int conversion"""
    try:
        return int(float(val or 0))
    except (ValueError, TypeError):
        return 0
