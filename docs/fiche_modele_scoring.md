# Fiche modèle : score de risque « passage en PAR 30 à 3 mois »

> Une fiche modèle (*model card*) décrit **ce que fait un modèle, comment il a été construit, ses performances et ses limites**. Elle est obligatoire avant toute utilisation d'un modèle de risque.

## 1. Objectif métier

Repérer, **parmi les prêts encore sains** (30 jours de retard ou moins), ceux qui risquent de **dépasser 30 jours de retard dans les 3 prochains mois**, pour que le recouvrement les appelle **avant** qu'ils n'entrent dans le PAR 30.

**Utilisateurs :** Direction des risques et équipes de recouvrement (liste d'appels priorisée).
**Ce que le modèle ne fait PAS :** il ne décide pas d'accorder ou de refuser un crédit (score d'octroi). C'est un **score comportemental**.

## 2. Données

| Élément | Choix |
|---|---|
| Population | Prêts actifs avec 30 jours de retard ou moins, à chaque fin de mois |
| Source | `reporting.fct_situation_prets` (projet 2), plus les informations prêt et client de l'entrepôt |
| Cible | 1 si le prêt dépasse 30 jours de retard à l'une des 3 fins de mois suivantes ; 0 sinon (y compris s'il est soldé) |
| Période | Toutes les fins de mois dont les 3 mois suivants sont connus |
| Découpage | **Temporel** : apprentissage sur le passé, test sur les 6 dernières fins de mois disponibles (jamais de mélange passé / futur) |

## 3. Variables

| Variable | Signification | Pourquoi |
|---|---|---|
| Retard actuel | Jours de retard à la date de la photo | Comportement présent |
| Plus gros retard passé | Maximum des retards observés depuis le début du prêt | Historique de difficulté |
| Nombre de mois en retard | Nombre de fins de mois avec un retard > 0 | Régularité du paiement |
| Arriérés (en mensualités) | Montant impayé ÷ mensualité | Gravité du retard |
| Part déjà remboursée | Total payé ÷ montant financé | Engagement du client |
| Ancienneté du prêt | Mois depuis le décaissement | Les débuts de prêt sont plus risqués |
| Montant financé (log), durée, apport | Caractéristiques du crédit | Effort demandé au client |
| Ancienneté du client | Mois depuis l'inscription | Connaissance du client |
| Produit, segment, pays | Catégories | Différences de risque structurelles |

**Variables volontairement exclues :** sexe, âge, ethnie, religion, et toute donnée sensible ou discriminante. Le nom et le téléphone ne servent qu'à l'affichage, jamais au calcul.

## 4. Méthode

| | Champion | Challenger |
|---|---|---|
| Modèle | Régression logistique | Gradient boosting (arbres) |
| Pourquoi | **Explicable** : chaque note se décompose en contributions de variables, ce qui donne les « 3 raisons » affichées pour chaque prêt | Plus flexible : sert à vérifier qu'on ne perd pas trop de performance en restant simple |

Le champion est ensuite **ré-entraîné sur tout l'historique** pour noter les prêts du jour.

**Score** = (1 − probabilité) × 1000. **Classes de risque :**

| Classe | Probabilité de passer en PAR 30 dans les 3 mois |
|---|---|
| A - Très faible | moins de 5 % |
| B - Faible | 5 à 10 % |
| C - Moyen | 10 à 20 % |
| D - Élevé | 20 à 40 % |
| E - Très élevé | 40 % et plus |
| F - Déjà en PAR 30 | non noté : déjà en recouvrement |

## 5. Performance

Les valeurs à jour sont dans `ml.performance_modeles` et dans le tableau de bord **4. Aide à la décision**. Lors de la construction du projet :

| Modèle | AUC | Gini | KS |
|---|---|---|---|
| Régression logistique (champion) | 0,84 | 0,68 | 0,55 |
| Gradient boosting (challenger) | 0,82 | 0,64 | 0,54 |

- **AUC** : probabilité qu'un prêt qui va mal tourner ait une note plus risquée qu'un prêt qui va bien. 0,5 = hasard, 1 = parfait.
- **Gini** = 2 × AUC − 1 : la mesure habituelle des banques. Au-dessus de 0,5, un score comportemental est considéré comme bon.
- **KS** : écart maximal entre les « bons » et les « mauvais » prêts.
- **Calibration** : par décile, la probabilité prédite est proche du taux réellement observé (graphique dans le tableau de bord 4).

👉 Le modèle **simple** bat le modèle complexe : on garde la régression logistique.

## 6. Limites et risques

- **Données simulées** : les performances réelles seront différentes. Il faut ré-estimer le modèle sur des données réelles.
- **Peu d'historique** (environ 2 ans) : le modèle n'a pas connu de crise (mauvaise saison agricole, inflation…).
- **Dérive** : si le comportement des clients change, le score se dégrade. Il faut le surveiller.
- **Effet du recouvrement** : si les clients bien notés « risqués » sont appelés et paient, le modèle semblera se tromper. C'est le but recherché, mais il faut en tenir compte lors du suivi.

## 7. Suivi et gouvernance

| Contrôle | Fréquence | Seuil d'alerte |
|---|---|---|
| AUC sur les nouveaux mois | Mensuelle | AUC < 0,75 |
| Calibration (prédit / observé) | Mensuelle | Écart > 5 points sur un décile |
| Stabilité de la population (PSI) | Mensuelle | PSI > 0,25 |
| Revue complète et validation indépendante | Annuelle | |

**Propriétaire du modèle :** Direction des risques. **Responsable technique :** Data scientist. **Code :** `ml/scoring.py`. **Exécution :** pipeline Airflow `pipeline_aide_decision_lumina`, chaque jour.
