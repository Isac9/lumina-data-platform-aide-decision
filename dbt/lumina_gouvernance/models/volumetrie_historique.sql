-- Historique de la volumétrie : on AJOUTE la mesure du jour (modèle "incrémental").
-- Une chute brutale du nombre de lignes = un problème de chargement à investiguer.
{{ config(
    materialized='incremental',
    unique_key=['date_mesure', 'nom_schema', 'nom_table'],
    incremental_strategy='delete+insert'
) }}

select date_mesure, nom_schema, nom_table, nb_lignes
from {{ ref('volumetrie') }}
