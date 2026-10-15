"""
Ajoute AUTOMATIQUEMENT dans Superset (par son API) :
  - les jeux de données du projet 3 (schémas ml et gouvernance) et leurs métriques ;
  - le tableau de bord « 4. Aide à la décision » (scoring, prévisions, anomalies) ;
  - le tableau de bord « 5. Qualité et gouvernance » ;
  - les nouvelles tables dans les règles "chaque directeur ne voit que son pays".
"""

import json
import time

import psycopg2
import requests

SUPERSET = "http://superset:8088"
NOM_BASE = "Entrepôt Lumina"

# (schéma, table) -> métriques (nom, formule SQL, libellé, format)
DATASETS = {
    ("ml", "scores_risque"): [
        ("nb_prets", "count(*)", "Nombre de prêts", ",d"),
        ("encours_total", "sum(encours)", "Encours (FCFA)", ",.0f"),
        ("nb_risque_eleve", "count(*) filter (where classe_risque in ('D - Élevé', 'E - Très élevé'))", "Prêts à risque élevé", ",d"),
        ("encours_risque_eleve", "coalesce(sum(encours) filter (where classe_risque in ('D - Élevé', 'E - Très élevé')), 0)", "Encours à risque élevé (FCFA)", ",.0f"),
    ],
    ("ml", "performance_modeles"): [
        ("auc", "max(auc)", "AUC", ".2f"),
        ("gini", "max(gini)", "Gini", ".2f"),
    ],
    ("ml", "calibration_modele"): [
        ("probabilite_predite", "avg(probabilite_predite)", "Probabilité prédite", ".0%"),
        ("taux_observe", "avg(taux_observe)", "Taux observé", ".0%"),
    ],
    ("ml", "importance_variables"): [],
    ("ml", "prevision_encaissements"): [
        ("montant", "sum(montant)", "Montant (FCFA)", ",.0f"),
    ],
    ("ml", "backtest_previsions"): [
        ("mape", "avg(mape)", "Erreur moyenne (MAPE)", ".1%"),
    ],
    ("ml", "anomalies"): [
        ("nb_anomalies", "count(*)", "Nombre d'anomalies", ",d"),
    ],
    ("gouvernance", "kpi_qualite"): [
        ("taux_reussite", "sum(nb_reussis)::numeric / nullif(sum(nb_controles), 0)", "Taux de réussite des contrôles", ".1%"),
    ],
    ("gouvernance", "controles_derniere_execution"): [],
    ("gouvernance", "fraicheur_sources"): [
        ("nb_sources_en_retard", "count(*) filter (where statut <> '✅ À jour')", "Sources en retard", ",d"),
    ],
    ("gouvernance", "volumetrie_historique"): [
        ("nb_lignes", "sum(nb_lignes)", "Nombre de lignes", ",d"),
    ],
    ("gouvernance", "catalogue_tables"): [
        ("nb_tables", "count(*)", "Tables documentées", ",d"),
    ],
    ("gouvernance", "matrice_droits"): [],
    ("gouvernance", "dictionnaire_indicateurs"): [],
}
TABLES_AVEC_PAYS = ["scores_risque", "prevision_encaissements", "backtest_previsions", "anomalies"]


def filtre_sql(expression):
    return {"expressionType": "SQL", "sqlExpression": expression, "clause": "WHERE"}


# ------------------------------------------------------------------ attentes et API
def attendre_tables():
    print("Attente des tables du projet 3 (créées par les pipelines Airflow)...", flush=True)
    for _ in range(180):
        try:
            with psycopg2.connect(host="dwh-db", dbname="dwh", user="lumina", password="lumina") as conn:
                with conn.cursor() as cur:
                    cur.execute("select to_regclass('ml.anomalies') is not null "
                                "and to_regclass('gouvernance.catalogue_tables') is not null")
                    if cur.fetchone()[0]:
                        print("Tables prêtes.", flush=True)
                        return
        except psycopg2.OperationalError:
            pass
        time.sleep(10)
    raise SystemExit("Tables du projet 3 introuvables : vérifiez les pipelines dans Airflow.")


class Superset:
    def __init__(self):
        self.s = requests.Session()
        jeton = self.s.post(f"{SUPERSET}/api/v1/security/login", json={
            "username": "admin", "password": "admin", "provider": "db", "refresh": True,
        }).json()["access_token"]
        self.s.headers["Authorization"] = f"Bearer {jeton}"
        csrf = self.s.get(f"{SUPERSET}/api/v1/security/csrf_token/").json()["result"]
        self.s.headers.update({"X-CSRFToken": csrf, "Referer": SUPERSET})

    def appel(self, methode, chemin, **kwargs):
        reponse = self.s.request(methode, f"{SUPERSET}/api/v1/{chemin}", **kwargs)
        if reponse.status_code >= 400:
            raise RuntimeError(f"{methode} {chemin} -> {reponse.status_code} : {reponse.text[:500]}")
        return reponse.json()

    def chercher(self, ressource, colonne, valeur):
        q = f"(filters:!((col:{colonne},opr:eq,value:'{valeur}')))"
        resultats = self.appel("GET", f"{ressource}/", params={"q": q})["result"]
        return resultats[0] if resultats else None


def creer_datasets(api):
    id_base = api.chercher("database", "database_name", NOM_BASE)["id"]
    ids = {}
    for (schema, table), metriques in DATASETS.items():
        existant = api.chercher("dataset", "table_name", table)
        if existant:
            ids[table] = existant["id"]
            continue
        id_ds = api.appel("POST", "dataset/", json={"database": id_base, "schema": schema, "table_name": table})["id"]
        if metriques:
            api.appel("PUT", f"dataset/{id_ds}", json={"metrics": [
                {"metric_name": n, "expression": e, "verbose_name": l, "d3format": f} for n, e, l, f in metriques
            ]})
        ids[table] = id_ds
        print(f"  dataset {schema}.{table} : id {id_ds}", flush=True)
    return ids


# ------------------------------------------------------------------ graphiques
def grand_nombre(titre, metrique, fmt, filtres=()):
    return {"viz_type": "big_number_total", "metric": metrique, "y_axis_format": fmt,
            "adhoc_filters": list(filtres), "header_font_size": 0.4, "subheader_font_size": 0.15, "_titre": titre}


def courbe(titre, x, metriques, fmt, groupby=(), grain="P1M", filtres=()):
    return {"viz_type": "echarts_timeseries_line", "x_axis": x, "time_grain_sqla": grain,
            "metrics": metriques, "groupby": list(groupby), "adhoc_filters": list(filtres),
            "y_axis_format": fmt, "row_limit": 10000, "show_legend": True, "rich_tooltip": True,
            "markerEnabled": True, "_titre": titre}


def barres_categories(titre, x, metrique):
    return {"viz_type": "echarts_timeseries_bar", "x_axis": x, "metrics": [metrique], "groupby": [],
            "adhoc_filters": [], "row_limit": 100, "x_axis_sort": x, "x_axis_sort_asc": True,
            "show_legend": False, "rich_tooltip": True, "show_value": True, "_titre": titre}


def tableau(titre, colonnes, tri=None, decroissant=True, formats=None, filtres=(), lignes=1000):
    return {"viz_type": "table", "query_mode": "raw", "all_columns": colonnes,
            "order_by_cols": [json.dumps([tri, not decroissant])] if tri else [],
            "adhoc_filters": list(filtres), "row_limit": lignes, "server_page_length": 20,
            "table_timestamp_format": "%d/%m/%Y",
            "column_config": {c: {"d3NumberFormat": f} for c, f in (formats or {}).items()},
            "_titre": titre}


def definir_tableaux_de_bord():
    pct = ".1%"
    return [
        {
            "titre": "4. Aide à la décision", "slug": "aide-decision", "dataset_filtre": "scores_risque",
            "lignes": [
                [("scores_risque", grand_nombre("Prêts à risque élevé (classes D et E)", "nb_risque_eleve", ",d"), 3, 40),
                 ("scores_risque", grand_nombre("Encours à risque élevé (FCFA)", "encours_risque_eleve", ",.0f"), 3, 40),
                 ("performance_modeles", grand_nombre("Qualité du modèle de score (AUC)", "auc", ".2f",
                                                      [filtre_sql("role = 'Champion'")]), 3, 40),
                 ("backtest_previsions", grand_nombre("Erreur de la prévision (MAPE)", "mape", pct,
                                                      [filtre_sql("methode = 'Échéancier'")]), 3, 40)],
                [("scores_risque", barres_categories("Prêts par classe de risque", "classe_risque", "nb_prets"), 4, 55),
                 ("calibration_modele", courbe("Calibration : probabilité prédite et taux observé (par décile)",
                                               "decile", ["probabilite_predite", "taux_observe"], ".0%", grain=None), 4, 55),
                 ("importance_variables", tableau("Ce qui fait monter ou baisser le risque",
                                                  ["variable_metier", "variable", "poids", "effet"], "poids",
                                                  formats={"poids": ".2f"}), 4, 55)],
                [("scores_risque", tableau(
                    "Prêts à surveiller en priorité (pas encore en PAR 30)",
                    ["code_entite", "nom_client", "telephone", "nom_agent", "code_produit", "encours",
                     "jours_retard", "probabilite_defaut", "classe_risque", "raisons"],
                    "probabilite_defaut", formats={"probabilite_defaut": ".0%", "encours": ",.0f"},
                    filtres=[filtre_sql("probabilite_defaut is not null")], lignes=100), 12, 70)],
                [("prevision_encaissements", courbe("Encaissements : réel et prévisions (FCFA)", "mois", ["montant"],
                                                    ",.0f", groupby=["serie"]), 8, 60),
                 ("backtest_previsions", tableau("Fiabilité des prévisions (test sur les 3 derniers mois)",
                                                 ["code_entite", "methode", "montant_reel", "montant_prevu", "mape"],
                                                 formats={"mape": pct, "montant_reel": ",.0f", "montant_prevu": ",.0f"}), 4, 60)],
                [("anomalies", tableau("Anomalies à investiguer",
                                       ["gravite", "type_anomalie", "code_entite", "objet", "date_concernee", "description", "statut"],
                                       "score"), 12, 70)],
            ],
        },
        {
            "titre": "5. Qualité et gouvernance", "slug": "qualite-gouvernance", "dataset_filtre": None,
            "lignes": [
                [("kpi_qualite", grand_nombre("Contrôles qualité réussis (dernière exécution)", "taux_reussite", pct,
                                              [filtre_sql("est_derniere_execution")]), 4, 40),
                 ("fraicheur_sources", grand_nombre("Sources en retard de chargement", "nb_sources_en_retard", ",d"), 4, 40),
                 ("catalogue_tables", grand_nombre("Tables documentées dans le catalogue", "nb_tables", ",d"), 4, 40)],
                [("kpi_qualite", courbe("Taux de réussite des contrôles dans le temps", "date_execution", ["taux_reussite"],
                                        pct, groupby=["projet"], grain="P1D"), 6, 55),
                 ("controles_derniere_execution", tableau("Contrôles à regarder (dernière exécution)",
                                                          ["projet", "controle", "resultat", "nb_lignes_en_echec"],
                                                          filtres=[filtre_sql("resultat <> '✅ Réussi'")]), 6, 55)],
                [("fraicheur_sources", tableau("Fraîcheur des sources",
                                               ["systeme_source", "table_brute", "dernier_chargement", "age_heures", "nb_lignes", "statut"]), 6, 55),
                 ("volumetrie_historique", courbe("Volumétrie des tables finales (nombre de lignes)", "date_mesure",
                                                  ["nb_lignes"], ",d", groupby=["nom_table"], grain="P1D",
                                                  filtres=[filtre_sql("nom_schema = 'marts'")]), 6, 55)],
                [("catalogue_tables", tableau("Catalogue des tables : propriétaire, classification, données personnelles",
                                              ["nom_schema", "nom_table", "domaine", "proprietaire_metier", "classification",
                                               "donnees_personnelles", "nb_lignes", "description"]), 12, 60)],
                [("dictionnaire_indicateurs", tableau("Dictionnaire des indicateurs",
                                                      ["indicateur", "definition", "formule", "proprietaire", "frequence", "seuil_alerte"]), 12, 60)],
                [("matrice_droits", tableau("Matrice des droits d'accès",
                                            ["role_lecteur", "nom_schema", "nom_table", "privileges", "perimetre_visible"]), 12, 60)],
            ],
        },
    ]


def disposition(titre, lignes):
    pos = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": titre}},
    }
    for i, ligne in enumerate(lignes):
        id_ligne = f"ROW-{i}"
        pos["GRID_ID"]["children"].append(id_ligne)
        pos[id_ligne] = {"type": "ROW", "id": id_ligne, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                         "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        for id_graphique, nom, largeur, hauteur in ligne:
            cle = f"CHART-{id_graphique}"
            pos[id_ligne]["children"].append(cle)
            pos[cle] = {"type": "CHART", "id": cle, "children": [], "parents": ["ROOT_ID", "GRID_ID", id_ligne],
                        "meta": {"chartId": id_graphique, "width": largeur, "height": hauteur, "sliceName": nom}}
    return pos


def creer_tableaux_de_bord(api, datasets):
    for tdb in definir_tableaux_de_bord():
        if api.chercher("dashboard", "slug", tdb["slug"]):
            print(f"Tableau de bord « {tdb['titre']} » déjà présent.", flush=True)
            continue
        id_tdb = api.appel("POST", "dashboard/", json={"dashboard_title": tdb["titre"], "slug": tdb["slug"], "published": True})["id"]
        lignes, ids_graphiques = [], []
        for ligne in tdb["lignes"]:
            ligne_creee = []
            for table, params, largeur, hauteur in ligne:
                titre = params.pop("_titre")
                params["datasource"] = f"{datasets[table]}__table"
                id_g = api.appel("POST", "chart/", json={
                    "slice_name": titre, "viz_type": params["viz_type"], "datasource_id": datasets[table],
                    "datasource_type": "table", "params": json.dumps(params), "dashboards": [id_tdb],
                })["id"]
                ids_graphiques.append(id_g)
                ligne_creee.append((id_g, titre, largeur, hauteur))
            lignes.append(ligne_creee)
        filtres = []
        if tdb["dataset_filtre"]:
            filtres.append({
                "id": "NATIVE_FILTER-pays", "name": "Pays", "filterType": "filter_select", "type": "NATIVE_FILTER",
                "targets": [{"datasetId": datasets[tdb["dataset_filtre"]], "column": {"name": "code_entite"}}],
                "controlValues": {"enableEmptyFilter": False, "defaultToFirstItem": False, "multiSelect": True,
                                  "searchAllOptions": False, "inverseSelection": False},
                "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
                "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": ids_graphiques, "tabsInScope": [], "description": "Choisir un ou plusieurs pays",
            })
        api.appel("PUT", f"dashboard/{id_tdb}", json={
            "position_json": json.dumps(disposition(tdb["titre"], lignes)),
            "json_metadata": json.dumps({
                "native_filter_configuration": filtres, "color_scheme": "supersetColors",
                "cross_filters_enabled": True, "refresh_frequency": 0, "expanded_slices": {},
                "label_colors": {}, "timed_refresh_immune_slices": [], "chart_configuration": {},
            }),
        })
        print(f"Tableau de bord « {tdb['titre']} » créé ({len(ids_graphiques)} graphiques).", flush=True)


def etendre_securite_pays(api, datasets):
    """Ajoute les nouvelles tables (avec code_entite) aux règles RLS des directeurs pays."""
    regles = api.appel("GET", "rowlevelsecurity/", params={"q": "(page_size:100)"})["result"]
    for regle in regles:
        if not regle["name"].startswith("Filtre "):
            continue
        tables = {t["id"] for t in regle["tables"]} | {datasets[t] for t in TABLES_AVEC_PAYS}
        api.appel("PUT", f"rowlevelsecurity/{regle['id']}", json={
            "name": regle["name"], "filter_type": regle["filter_type"], "tables": sorted(tables),
            "roles": [r["id"] for r in regle["roles"]], "clause": regle["clause"],
            "group_key": regle.get("group_key") or "", "description": regle.get("description") or "",
        })
        print(f"Règle « {regle['name']} » étendue aux tables du projet 3.", flush=True)


if __name__ == "__main__":
    attendre_tables()
    api = Superset()
    datasets = creer_datasets(api)
    creer_tableaux_de_bord(api, datasets)
    etendre_securite_pays(api, datasets)
    print("✅ Tableaux de bord 4 et 5 prêts : http://localhost:8088", flush=True)
