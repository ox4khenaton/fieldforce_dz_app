# ============================================================
# FieldForce DZ — Frappe Hooks
# Application de Vente Terrain pour ERPNext (Algérie)
# ============================================================

app_name = "fieldforce_dz"
app_title = "FieldForce DZ"
app_publisher = "FieldForce DZ"
app_description = "Application de vente terrain connectee a ERPNext"
app_email = "dev@fieldforce.dz"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

# DocTypes are created via API, no fixtures needed
fixtures = []

# ============================================================
# CORS Headers for Mobile App
# ============================================================
def cors_add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Frappe-CSRF-Token, X-App-Device-Id'
    return response

after_request = ["fieldforce_dz.hooks.cors_add_headers"]