# ============================================================
# FieldForce DZ — Frappe Hooks
# Application de Vente Terrain pour ERPNext (Algérie)
# ============================================================

app_name = "fieldforce_dz"
app_title = "FieldForce DZ"
app_publisher = "FieldForce DZ"
app_description = "Application de vente terrain connectée à ERPNext — Optimisée pour le marché algérien"
app_email = "dev@fieldforce.dz"
app_license = "MIT"

# Requis pour Frappe v14+
required_apps = ["frappe", "erpnext"]

# -----------------------------------------------------------
# Modules
# -----------------------------------------------------------
modules = {
    "Fieldforce DZ": {
        "color": "#10b981",
        "icon": "octicon octicon-device-mobile",
        "type": "module"
    }
}

# -----------------------------------------------------------
# DocTypes à installer (automatiquement via bench migrate)
# Chemin: fieldforce_dz/fieldforce_dz/doctype/<name>/<name>.json
# -----------------------------------------------------------

# Surcharge des DocTypes standard ERPNext
# (ex: ajouter champs GPS au Customer, Sales Order)
override_doctypes = {
    "Customer": "fieldforce_dz.overrides.customer",
}

# -----------------------------------------------------------
# Website Route Rules (optionnel)
# -----------------------------------------------------------
# website_route_rules = [...]

# -----------------------------------------------------------
# JavaScript / CSS injectés dans l'interface
# -----------------------------------------------------------
# app_include_js = "fieldforce_dz.bundle.js"
# app_include_css = "fieldforce_dz.bundle.css"

# -----------------------------------------------------------
# Événements DocType
# -----------------------------------------------------------
doc_events = {
    "Sales Order": {
        "validate": "fieldforce_dz.overrides.sales_order.validate_sales_order",
        "on_submit": "fieldforce_dz.overrides.sales_order.on_sales_order_submit",
        "on_cancel": "fieldforce_dz.overrides.sales_order.on_sales_order_cancel",
    },
    "Payment Entry": {
        "validate": "fieldforce_dz.overrides.payment_entry.validate_payment_entry",
        "on_submit": "fieldforce_dz.overrides.payment_entry.on_payment_submit",
    },
    "Customer": {
        "validate": "fieldforce_dz.overrides.customer.validate_customer",
    },
}

# -----------------------------------------------------------
# Scheduled Tasks (tâches planifiées)
# -----------------------------------------------------------
scheduler_events = {
    # Toutes les 5 minutes: vérifier les sync en attente
    "all": [
        "fieldforce_dz.api.sync.process_pending_syncs",
    ],
    # Chaque jour à 23h00: bilan automatique
    "daily": [
        "fieldforce_dz.api.sync.daily_cleanup",
        "fieldforce_dz.api.mobile.auto_day_end_reminder",
    ],
    # Chaque heure: mettre à jour les objectifs
    "hourly": [
        "fieldforce_dz.api.sync.update_sales_targets",
    ],
    # Chaque lundi: planifier les tournées de la semaine
    "weekly": [
        "fieldforce_dz.api.sync.weekly_route_planning",
    ],
}

# -----------------------------------------------------------
# Hooks before_install / after_install
# -----------------------------------------------------------
after_install = "fieldforce_dz.install.after_install"
before_uninstall = "fieldforce_dz.install.before_uninstall"
after_migrate = "fieldforce_dz.install.after_migrate"

# -----------------------------------------------------------
# Fixtures (données de référence à exporter)
# -----------------------------------------------------------
fixtures = [
    # Rôles personnalisés
    {"doctype": "Role", "filters": [["name", "in", [
        "Fieldforce Vendeur",
        "Fieldforce Superviseur",
    ]]]},
    # Formats d'impression
    {"doctype": "Print Format", "filters": [["name", "in", [
        "Reçu Thermique 58mm",
        "Reçu Thermique 80mm",
    ]]]},
    # Paramètres de l'application
    {"doctype": "Fieldforce DZ Settings"},
    # File d'attente Offline
    {"doctype": "Offline Queue"},
    # Log GPS
    {"doctype": "GPS Location Log"},
    # Feedback client
    {"doctype": "Customer Feedback"},
    # Assignation de tournée
    {"doctype": "Route Assignment"},
]

# -----------------------------------------------------------
# Notification (optionnel)
# -----------------------------------------------------------
# notification_config = "fieldforce_dz.notifications.get_notification_config"

# -----------------------------------------------------------
# Print Formats
# -----------------------------------------------------------
# Enregistrés via fixtures ou créés dans after_install

# -----------------------------------------------------------
# Reports
# -----------------------------------------------------------
# Les rapports sont découverts automatiquement via
# fieldforce_dz/report/<report_name>/<report_name>.json

# -----------------------------------------------------------
# Page (pages personnalisées)
# -----------------------------------------------------------
# fieldforce_dz/page/<page_name>/<page_name>.json
