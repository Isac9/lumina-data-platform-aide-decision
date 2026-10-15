-- Catalogue des tables : propriétaire, classification, données personnelles, volume.

select
    v.nom_schema,
    v.nom_table,
    coalesce(c.domaine, 'NON CLASSÉE')              as domaine,
    c.proprietaire_metier,
    c.responsable_technique,
    coalesce(c.classification, 'NON CLASSÉE')       as classification,
    coalesce(c.donnees_personnelles, '?')           as donnees_personnelles,
    c.description,
    v.nb_lignes
from {{ ref('volumetrie') }} v
left join {{ ref('classification_donnees') }} c
    on c.nom_schema = v.nom_schema and c.nom_table = v.nom_table
where v.nom_schema <> 'raw'
