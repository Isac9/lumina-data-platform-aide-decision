-- Détail des contrôles de la DERNIÈRE exécution de chaque projet.

with resultats as (
    select *, max(date_execution) over (partition by projet) as derniere
    from {{ source('gouvernance', 'resultats_controles') }}
)

select
    date_execution,
    projet,
    controle,
    case statut
        when 'pass'  then '✅ Réussi'
        when 'warn'  then '⚠️ Avertissement'
        else '❌ Échec'
    end                    as resultat,
    nb_lignes_en_echec,
    duree_secondes
from resultats
where date_execution = derniere
