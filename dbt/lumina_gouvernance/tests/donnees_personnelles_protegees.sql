-- CONTRÔLE DE GOUVERNANCE : toute table contenant des données personnelles
-- doit être "Confidentiel" ou "Interne" ET protégée par la sécurité par pays
-- dès qu'elle est lisible par un lecteur pays.

select c.nom_schema, c.nom_table, m.role_lecteur
from {{ ref('catalogue_tables') }} c
join {{ ref('matrice_droits') }} m
  on m.nom_schema = c.nom_schema and m.nom_table = c.nom_table
where c.donnees_personnelles = 'oui'
  and m.role_lecteur like 'lecteur_%'
  and not m.securite_lignes_active
