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
# DocEvents (optionnel - pour le moment désactivé)
# -----------------------------------------------------------
# doc_events = {}

# -----------------------------------------------------------
# Scheduled Tasks (désactivé pour l'instant)
# -----------------------------------------------------------
# scheduler_events = {}

# -----------------------------------------------------------
# Hooks before_install / after_install
# -----------------------------------------------------------
# after_install = "fieldforce_dz.install.after_install"

# -----------------------------------------------------------
# Fixtures (données de référence à exporter)
# -----------------------------------------------------------
fixtures = [
    # Parameteres de l'application
    {"doctype": "Fieldforce DZ Settings"},
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
