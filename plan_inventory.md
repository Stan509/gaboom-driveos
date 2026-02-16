# Inventaire comparatif des plans — Starter, Business, Enterprise

Version des plans inventoriés : configuration applicative active (PLAN_CONFIGS)
Date de l’inventaire : 2026-02-11
Source principale : [services.py:L9-L69](file:///d:/GaboomDriveOs/agencies/services.py#L9-L69)

## Plan 1 — Starter
Nom exact : Starter

### Fonctionnalités fournies
- public_site : Site public activé
- online_booking : Réservations en ligne activées
- Capacité agences : 1 agence
- Capacité utilisateurs : 3 utilisateurs
- Capacité véhicules : 20 véhicules

### Fonctionnalités non incluses
- gps_tracking : Suivi GPS non disponible
- marketing_tools : Outils marketing non disponibles
- loyalty : Programme de fidélité non disponible
- client_portal : Portail client non disponible
- priority_support : Support prioritaire non disponible
- workflows : Workflows non disponibles
- integrations : Intégrations non disponibles

## Plan 2 — Business
Nom exact : Business

### Fonctionnalités fournies
- public_site : Site public activé
- online_booking : Réservations en ligne activées
- gps_tracking : Suivi GPS disponible
- marketing_tools : Outils marketing disponibles
- loyalty : Programme de fidélité disponible
- client_portal : Portail client disponible
- priority_support : Support prioritaire disponible
- Capacité agences : 3 agences
- Capacité utilisateurs : illimité (valeur 0)
- Capacité véhicules : illimité (valeur 0)

### Fonctionnalités non incluses
- workflows : Workflows non disponibles
- integrations : Intégrations non disponibles

## Plan 3 — Enterprise
Nom exact : Enterprise

### Fonctionnalités fournies
- public_site : Site public activé
- online_booking : Réservations en ligne activées
- gps_tracking : Suivi GPS disponible
- marketing_tools : Outils marketing disponibles
- loyalty : Programme de fidélité disponible
- client_portal : Portail client disponible
- priority_support : Support prioritaire disponible
- workflows : Workflows disponibles
- integrations : Intégrations disponibles
- Capacité agences : illimité (valeur 0)
- Capacité utilisateurs : illimité (valeur 0)
- Capacité véhicules : illimité (valeur 0)

### Fonctionnalités non incluses
- Aucune

## Tableau comparatif croisé

| Fonctionnalité / Capacité | Starter | Business | Enterprise |
| --- | --- | --- | --- |
| public_site | Oui | Oui | Oui |
| online_booking | Oui | Oui | Oui |
| gps_tracking | Non | Oui | Oui |
| marketing_tools | Non | Oui | Oui |
| loyalty | Non | Oui | Oui |
| client_portal | Non | Oui | Oui |
| priority_support | Non | Oui | Oui |
| workflows | Non | Non | Oui |
| integrations | Non | Non | Oui |
| Capacité agences | 1 | 3 | Illimité (0) |
| Capacité utilisateurs | 3 | Illimité (0) | Illimité (0) |
| Capacité véhicules | 20 | Illimité (0) | Illimité (0) |

## Note méthodologique
- Source des informations : configuration interne des plans dans PLAN_CONFIGS ([services.py:L9-L69](file:///d:/GaboomDriveOs/agencies/services.py#L9-L69)).
- Méthode : lecture des clés de fonctionnalités et des limites (max_agencies, max_users, max_vehicles) définies pour chaque plan.
- Hypothèse d’interprétation : une valeur 0 sur les limites correspond à un accès illimité, conformément au comportement appliqué par la logique d’accès (max_users/max_vehicles/max_agencies).
- Date d’inventaire : 2026-02-11.
