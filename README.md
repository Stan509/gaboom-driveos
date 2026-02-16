# Gaboom DriveOS (MVP)

Gaboom DriveOS est une architecture Django prête pour une **plateforme SaaS multi-agence** de gestion de locations automobiles. Elle sépare clairement les équipes internes (Owner/Admin/Staff) des clients finaux, encapsule les sites publics par slug et prépare l’intégration Stripe côté agence.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Copie les variables d’environnement suivantes :

| Nom | Description |
| --- | --- |
| `DJANGO_SECRET_KEY` | Clé secrète Django. |
| `DJANGO_DEBUG` | `1` (dev) ou `0` (prod). |
| `DJANGO_ALLOWED_HOSTS` | Liste séparée par des virgules. |
| `POSTGRES_*` | Définitions Postgres (si `POSTGRES_HOST` renseigné). |

## Commandes courantes

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser   # Seule façon de créer un superadmin
python manage.py runserver
```

## Qualité (proposé)

```bash
python manage.py check
python -m ruff check .
python -m mypy .
python manage.py test core marketing superadmin
```

> **⚠ Aucun compte par défaut n'est créé.**
> Le superuser doit être créé manuellement via `createsuperuser`.
> La commande `seed_test` est réservée aux démos et nécessite `ENABLE_DEMO_SEED=1`.
> Elle génère un mot de passe aléatoire — rien n'est hardcodé.

## Structure

```
GaboomDriveOs/
├── config/           # settings, urls, ASGI/WSGI
├── core/             # Custom User, middleware
├── agencies/         # Agency + Vehicle models
├── dashboard/        # Interface back-office
├── public_site/      # Site public par slug + catalog/book
├── clients/          # ClientUser (non-auth) pour les clients finaux
├── billing/          # Futurs composants Stripe/facturation
├── marketing/        # Landing, signup, demo
├── templates/        # Bases partagées (+ Tailwind CDN)
├── media/            # Uploads images véhicules
└── static/           # Manifest, logos, etc.
```

## Rôles & sécurité

| Rôle | `role` | `is_staff` | `is_superuser` | `/admin` | Dashboard |
|------|--------|------------|----------------|----------|-----------|
| SuperAdmin | — | `True` | `True` | ✅ | ✅ |
| Agency Owner | `owner` | `False` | `False` | ❌ | Tout |
| Agency Admin | `admin` | `False` | `False` | ❌ | CRUD véhicules/clients |
| Agency Staff | `staff` | `False` | `False` | ❌ | Lecture seule |

- **1 user = 1 agency** — contrainte DB + validation `clean()`.
- Seul un superuser peut exister sans agence.
- `/admin/` est protégé par `SuperAdminOnlyMiddleware` + gate URL.
- Toutes les requêtes dashboard utilisent `Vehicle.objects.for_agency(agency)` — aucun `.all()`.
- Décorateurs : `@require_agency_user`, `@require_agency_admin`, `@require_agency_owner`.

## Logique multi-agence

- Chaque `core.User` non-superuser doit appartenir à une agence (`on_delete=models.CASCADE`).
- `Agency` expose `public_enabled`, `maintenance_mode`, `stripe_*` et un `slug` indexé.
- Le middleware `core.middleware.AgencyMiddleware` attache `request.agency` pour toute route commençant par `/a/<slug>/` et bloque l'accès si l'agence est désactivée.
- La plateforme publique (`/a/<slug>/...`) propose catalogue, détails véhicule et page de réservation, avec gestion des modes maintenance et visibilité.
- `clients.ClientUser` stocke les clients finaux par agence sans utiliser Django auth.
- `AgencyQuerySet.for_agency(agency)` est le seul moyen d'accéder aux données scoped.

## Préparation Stripe / futures évolutions

- Champs `stripe_account_id`, `stripe_customer_id`, `stripe_subscription_id`, `stripe_enabled` et `subscription_status` prêts pour intégrer Stripe Connect.
- PWA : `<meta name="theme-color">` + `manifest.json` référencé dans `templates/base.html`.
- Les templates publics utilisent les couleurs d'agence, les images véhicules uploadées via `ImageField` et affichent un catalogue premium.

## Configuration Email (Brevo)

1. Copier le fichier modèle :
   ```bash
   cp .env.example .env
   ```
2. Remplir les variables dans `.env` — en particulier `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL` et `SERVER_EMAIL`.
3. **Ne jamais commiter `.env`** — il est exclu par `.gitignore`.
4. En production (`DJANGO_DEBUG=0`), si `BREVO_API_KEY` est vide le serveur refusera de démarrer (`ImproperlyConfigured`).
5. En production, définir les variables via le panel de votre hébergeur (Render, Railway, etc.) ou via les secrets de votre CI/CD.

## Assets & médias

- `MEDIA_URL = /media/`, `MEDIA_ROOT = BASE_DIR / media`.
- `Pillow` est nécessaire pour gérer les `ImageField`.

## Routes utiles

- Landing : `/`
- Signup agence : `/signup/`
- Dashboard : `/dashboard/`
- Site public : `/a/<slug>/`, `/a/<slug>/catalog/`, `/a/<slug>/vehicle/<id>/`, `/a/<slug>/book/`
- Connexion : `/login/`
```
