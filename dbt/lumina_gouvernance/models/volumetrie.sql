-- Nombre EXACT de lignes de chaque table de l'entrepôt (hors tables temporaires et partitions).
-- Astuce PostgreSQL : query_to_xml exécute un "select count(*)" pour chaque table.

select
    t.schemaname                                as nom_schema,
    t.tablename                                 as nom_table,
    (xpath('/row/n/text()',
        query_to_xml(format('select count(*) as n from %I.%I', t.schemaname, t.tablename), false, true, '')
    ))[1]::text::bigint                         as nb_lignes,
    current_date                                as date_mesure
from pg_tables t
join pg_class c on c.relname = t.tablename
join pg_namespace n on n.oid = c.relnamespace and n.nspname = t.schemaname
where t.schemaname in ('raw', 'marts', 'reporting', 'ml')
  and not c.relispartition
  and t.tablename not like '%dbt_tmp%'
  and t.tablename not like '%dbt_backup%'
