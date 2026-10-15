-- Matrice des droits d'accès : QUI peut lire QUOI, et sur quelles LIGNES.
-- Lue directement dans le catalogue de PostgreSQL : elle est toujours à jour.

with droits as (
    select
        grantee                                                   as role_lecteur,
        table_schema                                              as nom_schema,
        table_name                                                as nom_table,
        string_agg(privilege_type, ', ' order by privilege_type)  as privileges
    from information_schema.role_table_grants
    where grantee in ('direction_groupe', 'lecteur_ci', 'lecteur_sn', 'lecteur_bf')
    group by 1, 2, 3
),

regles as (
    select schemaname, tablename
    from pg_policies
    group by 1, 2
)

select
    d.role_lecteur,
    d.nom_schema,
    d.nom_table,
    d.privileges,
    r.tablename is not null as securite_lignes_active,
    case
        when r.tablename is null                 then 'Toutes les lignes'
        when d.role_lecteur = 'direction_groupe' then 'Toutes les entités'
        else 'Uniquement ' || upper(replace(d.role_lecteur, 'lecteur_', ''))
    end                     as perimetre_visible
from droits d
left join regles r on r.schemaname = d.nom_schema and r.tablename = d.nom_table
