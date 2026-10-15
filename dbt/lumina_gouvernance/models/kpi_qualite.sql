-- Taux de réussite des contrôles qualité, à chaque exécution et pour chaque projet.

with resultats as (
    select * from {{ source('gouvernance', 'resultats_controles') }}
),

par_execution as (
    select
        date_execution,
        projet,
        count(*)                                                  as nb_controles,
        count(*) filter (where statut = 'pass')                   as nb_reussis,
        count(*) filter (where statut = 'warn')                   as nb_avertissements,
        count(*) filter (where statut in ('fail', 'error'))       as nb_echecs
    from resultats
    group by date_execution, projet
)

select
    *,
    round(nb_reussis::numeric / nullif(nb_controles, 0), 4)                as taux_reussite,
    date_execution = max(date_execution) over (partition by projet)        as est_derniere_execution
from par_execution
