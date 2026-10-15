# Politique de gouvernance des données

> Objectif : des indicateurs **fiables, traçables et documentés**, accessibles aux **bonnes personnes**, et seulement à elles.

## 1. Les rôles

| Rôle | Qui | Responsabilités |
|---|---|---|
| **Propriétaire métier** | Un directeur (finance, risques, commercial…) | Valide la définition des indicateurs de son domaine, décide qui y a accès, arbitre en cas de doute |
| **Responsable technique** | Data engineer / data scientist | Construit, teste et documente les tables et les modèles |
| **Responsable data** | Data engineer senior | Anime la gouvernance, suit la qualité, tient le catalogue et le dictionnaire |
| **Utilisateur** | Directions, pays, analystes | Utilise les tableaux de bord, signale les anomalies |

La table `gouvernance.catalogue_tables` donne le propriétaire de **chaque** table.

## 2. Classification des données

| Niveau | Exemple | Règle |
|---|---|---|
| **Interne** | Catalogue produits, calendrier, ventes agrégées | Lisible par tous les collaborateurs |
| **Confidentiel** | Prêts, paiements, indicateurs de risque, scores | Lisible selon le besoin, avec un filtre par pays |
| **Données personnelles** | Nom et téléphone des clients | Confidentiel + filtre par pays **obligatoire** + aucun export hors outil sans accord |

Un contrôle automatique (`donnees_personnelles_protegees`) vérifie que **toute table contenant des données personnelles et lisible par un lecteur pays est protégée par la sécurité par pays**.

## 3. Qualité des données

1. **Contrôles automatiques** à chaque exécution : environ 60 tests dbt sur l'entrepôt et le reporting (unicité, cohérence, rapprochement, consolidation).
2. **Historique** : chaque résultat est conservé (`gouvernance.resultats_controles`) pour suivre la qualité dans le temps.
3. **Fraîcheur** : une source non rechargée depuis plus de 26 heures est signalée.
4. **Volumétrie** : le nombre de lignes de chaque table est mesuré chaque jour. Une chute brutale signale un problème de chargement.
5. **Gravité** :
   - **bloquant** (erreur) : les données ne sont pas publiées (exemple : doublon de clé) ;
   - **avertissement** : les données sont publiées et l'anomalie est suivie (exemple : écart de rapprochement ERP).
6. **Traitement** : toute anomalie a un responsable (le propriétaire métier de la table) et un délai de correction.

## 4. Gestion des accès

| Principe | Application |
|---|---|
| **Moindre privilège** | Les lecteurs n'ont accès qu'au schéma final (`marts`, `reporting`, `ml`), jamais aux données brutes |
| **Cloisonnement par pays** | Sécurité au niveau des lignes dans PostgreSQL **et** dans Superset |
| **Traçabilité** | La matrice des droits (`gouvernance.matrice_droits`) est générée automatiquement depuis la base : elle est toujours exacte |
| **Revue** | Revue trimestrielle de la matrice par chaque propriétaire métier |
| **Demande d'accès** | Par écrit au propriétaire métier, mise en œuvre par le responsable data |

## 5. Documentation

| Document | Où | Mise à jour |
|---|---|---|
| Catalogue de données (tables, colonnes, tests, lignage) | http://localhost:8081 (généré par dbt) | Automatique, chaque jour |
| Dictionnaire des indicateurs | `gouvernance.dictionnaire_indicateurs` et tableau de bord 5 | À chaque nouvel indicateur, validé par le propriétaire |
| Fiche du modèle de score | `docs/fiche_modele_scoring.md` | À chaque ré-estimation |
| Architecture et feuille de route | Projet 1, dossier `docs` | À chaque évolution majeure |

## 6. Règle d'or

> **Un indicateur n'existe que s'il a : une définition écrite, une formule unique, un propriétaire, des contrôles qualité, et une place dans le catalogue.**
