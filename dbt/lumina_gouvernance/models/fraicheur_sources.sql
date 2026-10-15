-- Fraîcheur des sources : à quand remonte le dernier chargement de chaque table brute ?
-- Au-delà de 26 heures, la source est "en retard" (le pipeline tourne chaque jour).

{% set tables_brutes = [
    ('CRM', 'crm_agents'), ('CRM', 'crm_clients'),
    ('Portefeuille', 'pf_produits'), ('Portefeuille', 'pf_prets'),
    ('Portefeuille', 'pf_echeances'), ('Portefeuille', 'pf_remboursements'),
    ('ERP', 'erp_factures'), ('ERP', 'erp_encaissements')
] %}

with chargements as (
    {% for systeme, table in tables_brutes %}
    select '{{ systeme }}' as systeme_source, '{{ table }}' as table_brute,
           max(_charge_le) as dernier_chargement, count(*) as nb_lignes
    from raw.{{ table }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    systeme_source,
    table_brute,
    dernier_chargement,
    nb_lignes,
    round(extract(epoch from (now() - dernier_chargement)) / 3600, 1) as age_heures,
    case
        when dernier_chargement is null                         then '❌ Jamais chargée'
        when now() - dernier_chargement > interval '26 hours'   then '⚠️ En retard'
        else '✅ À jour'
    end as statut
from chargements
