# 🇩🇿 FieldForce DZ — ERPNext Custom App
# Installation Guide Complète

## Qu'est-ce que c'est ?

**fieldforce_dz** est une application ERPNext personnalisée qui connecte l'application mobile FieldForce Pro DZ à votre serveur ERPNext. Elle ajoute les DocTypes, API, validations et rapports nécessaires pour gérer une équipe de vente terrain en Algérie.

---

## 📦 Installation

### Prérequis
- ERPNext v14 ou v15 installé et fonctionnel
- Accès SSH au serveur (bench command)
- Python 3.10+
- L'application mobile FieldForce Pro DZ (ou le web app)

### Étape 1 : Copier l'application

```bash
# Aller dans le dossier apps de votre bench
cd /home/frappe/frappe-bench/apps/

# Cloner ou copier l'application
# Option A: Si vous avez un dépôt git
git clone https://github.com/votre-compte/fieldforce_dz.git

# Option B: Copier le dossier fieldforce_dz_app/fieldforce_dz/ directement
cp -r /chemin/vers/fieldforce_dz_app/fieldforce_dz/ ./
```

### Étape 2 : Installer l'application sur votre site

```bash
cd /home/frappe/frappe-bench/

# Installer l'app dans le bench
bench get-app fieldforce_dz  # si cloné via git
# OU si copié manuellement:
bench build --app fieldforce_dz

# Installer sur votre site
bench --site votre-site.com install-app fieldforce_dz

# Migrer la base de données
bench --site votre-site.com migrate

# Redémarrer
bench restart
```

### Étape 3 : Configurer CORS

Éditez `site_config.json` de votre site (`sites/votre-site.com/site_config.json`) :

```json
{
  "allow_cors": "*",
  "allow_cors_origins": ["https://votre-domaine.com"],
  "ignore_csrf": ["/api/method/fieldforce_dz.api.mobile.*"]
}
```

### Étape 4 : Configurer Nginx (si behind proxy)

Ajoutez dans votre config Nginx pour le site :

```nginx
location /api/ {
    add_header Access-Control-Allow-Origin *;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, Accept, X-Frappe-CSRF-Token";
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS";
    add_header Access-Control-Max-Age 3600;

    if ($request_method = OPTIONS) {
        return 204;
    }

    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Puis : `sudo nginx -t && sudo systemctl reload nginx`

### Étape 5 : Générer les clés API

1. Connectez-vous à ERPNext avec le compte du vendeur
2. Allez dans **User** → votre profil → **API Access** → **Generate Keys**
3. Copiez **API Key** et **API Secret**
4. Utilisez-les dans l'application mobile

---

## 📋 DocTypes Créés

| DocType | Description | Module |
|---------|-------------|--------|
| **Tournée de Vente** | Planification des routes journalières | Fieldforce DZ |
| **Client Tournée** | Table enfant: clients sur une route | Fieldforce DZ |
| **Journal de Visite** | Suivi GPS des visites clients | Fieldforce DZ |
| **Affectation Dépôt Mobile** | Association vendeur ↔ dépôt mobile | Fieldforce DZ |
| **Dépense Terrain** | Notes de frais (carburant, repas, etc.) | Fieldforce DZ |
| **Objectif Vendeur** | Objectifs de vente quotidiens/mensuels | Fieldforce DZ |

---

## 🔌 API Endpoints Mobile

Tous les endpoints sont sous `/api/method/fieldforce_dz.api.mobile.*`

### Authentification
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `fieldforce_dz.api.mobile.login` | Connexion vendeur |
| GET | `fieldforce_dz.api.mobile.get_logged_user` | Utilisateur connecté |

### Tournées & Visites
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `fieldforce_dz.api.mobile.get_today_route` | Tournée du jour |
| POST | `fieldforce_dz.api.mobile.check_in` | Pointage GPS arrivée |
| POST | `fieldforce_dz.api.mobile.check_out` | Départ client |
| GET | `fieldforce_dz.api.mobile.get_visit_history` | Historique visites |

### Commandes
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `fieldforce_dz.api.mobile.create_order` | Créer commande |
| GET | `fieldforce_dz.api.mobile.get_orders` | Liste commandes |
| POST | `fieldforce_dz.api.mobile.submit_order` | Soumettre commande |
| POST | `fieldforce_dz.api.mobile.cancel_order` | Annuler commande |

### Stock
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `fieldforce_dz.api.mobile.get_van_stock` | Stock dépôt mobile |
| GET | `fieldforce_dz.api.mobile.get_item_price` | Prix d'un article |
| GET | `fieldforce_dz.api.mobile.check_credit_limit` | Vérifier plafond crédit |

### Paiements
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `fieldforce_dz.api.mobile.create_payment` | Enregistrer paiement |
| GET | `fieldforce_dz.api.mobile.get_outstanding` | Montant impayé client |

### Synchronisation
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `fieldforce_dz.api.mobile.sync_batch` | Sync par lot (batch) |
| GET | `fieldforce_dz.api.mobile.get_updates` | Mises à jour serveur |
| GET | `fieldforce_dz.api.mobile.health_check` | État du serveur |

### Dépenses & Bilan
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `fieldforce_dz.api.mobile.create_expense` | Enregistrer dépense |
| POST | `fieldforce_dz.api.mobile.day_end_report` | Bilan fin de journée |
| GET | `fieldforce_dz.api.mobile.get_targets` | Objectifs vendeur |

---

## 🗄️ Structure de l'Application

```
fieldforce_dz/
├── setup.py                          # Métadonnées paquet Python
├── requirements.txt                  # Dépendances
├── MANIFEST.in                       # Inclusion fichiers non-Python
├── README.md                         # Ce fichier
├── fieldforce_dz/
│   ├── __init__.py
│   ├── hooks.py                      # Hooks Frappe (CRITICAL)
│   ├── modules.txt                   # Liste des modules
│   ├── patches.txt                   # Scripts migration
│   ├── fieldforce_dz/                # Module principal
│   │   ├── __init__.py
│   │   └── doctype/                 # DocTypes personnalisés
│   │       ├── __init__.py
│   │       ├── tournee_de_vente/    # Tournée de Vente
│   │       ├── client_tournee/      # Client Tournée (enfant)
│   │       ├── journal_de_visite/   # Journal de Visite
│   │       ├── affectation_depot_mobile/  # Affectation Dépôt
│   │       ├── depense_terrain/     # Dépense Terrain
│   │       └── objectif_vendeur/    # Objectif Vendeur
│   ├── api/                          # API endpoints
│   │   ├── __init__.py
│   │   ├── mobile.py                # API mobile principale
│   │   └── geofence.py              # Validation GPS
│   ├── overrides/                    # Surcharges DocTypes standard
│   │   ├── __init__.py
│   │   └── sales_order.py           # Override Sales Order
│   ├── report/                       # Rapports
│   │   ├── vente_journaliere/       # Vente Journalière
│   │   └── performance_vendeur/     # Performance Vendeur
│   └── print_format/                # Formats impression
│       └── recu_thermique/          # Reçu thermique 58/80mm
```

---

## ⚙️ Configuration Post-Installation

### 1. Créer les Rôles
Aller dans **Role** et créer :
- **Fieldforce Vendeur** — Accès mobile complet
- **Fieldforce Superviseur** — Rapports + validation

### 2. Assigner les Permissions
Pour chaque DocType ci-dessus, aller dans **Role Permission Manager** :
- Vendeur: Create, Read, Write
- Superviseur: Tous les droits + Submit + Cancel

### 3. Créer un Dépôt Mobile
1. **Stock → Warehouse** → Créer "Dépôt Mobile - KB"
2. **Créer Affectation Dépôt Mobile**:
   - Vendeur: Karim Benali
   - Dépôt: Dépôt Mobile - KB
   - Rayon Géofence: 50m

### 4. Créer une Tournée
1. **Tournée de Vente** → Nouveau
2 - Remplir: Nom, Jour, Vendeur
3. Ajouter les clients avec leurs coordonnées GPS
4. Sauvegarder

### 5. Créer les Objectifs
1. **Objectif Vendeur** → Nouveau
2. Définir CA quotidien et mensuel
3. Associer au vendeur

---

## 🔒 Sécurité

- **Token Auth** : L'API utilise les tokens ERPNext (Authorization: token key:secret)
- **Géofence** : Validation serveur des coordonnées GPS
- **Credit Limit** : Vérification côté serveur AVANT création commande
- **Rate Limiting** : Protection contre les requêtes excessives
- **HTTPS requis** : En production, TOUJOURS utiliser HTTPS

---

## 📱 Connexion depuis l'Application Mobile

Dans les paramètres de FieldForce Pro DZ :
1. **URL Serveur** : `https://votre-erp.algerie.dz`
2. **Clé API** : (copiée depuis ERPNext)
3. **Secret API** : (copié depuis ERPNext)
4. Cliquer **Tester la Connexion**

Si tous les voyants sont verts → c'est prêt !

---

## 🐛 Dépannage

| Problème | Solution |
|----------|----------|
| CORS bloqué | Ajouter `"allow_cors": "*"` dans site_config.json |
| 401 Unauthorized | Régénérer les clés API dans User → API Access |
| 403 Forbidden | Vérifier que l'utilisateur a le rôle Fieldforce Vendeur |
| DocType introuvable | Lancer `bench migrate` |
| GPS toujours refusé | Vérifier les coordonnées dans le master Customer |
| Sync échoue | Vérifier la connectivité, consulter Error Log dans ERPNext |

---

## 📄 Licence

MIT License — Libre d'utilisation pour le marché algérien.
