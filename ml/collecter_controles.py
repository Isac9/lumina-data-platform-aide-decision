"""
Enregistre dans l'entrepôt le résultat de CHAQUE contrôle qualité dbt
(projets 1 et 2), à chaque exécution. On garde tout l'historique :
c'est ce qui permet de suivre la qualité des données dans le temps.
"""

import json
import os

import pandas as pd

from commun import ecrire_table, lire, moteur

RESULTATS = {
    "Entrepôt (projet 1)": "/tmp/gouv_entrepot/run_results.json",
    "Reporting (projet 2)": "/tmp/gouv_reporting/run_results.json",
}


def main():
    lignes = []
    for projet, chemin in RESULTATS.items():
        if not os.path.exists(chemin):
            print(f"  (pas de résultats pour {projet})", flush=True)
            continue
        with open(chemin, encoding="utf-8") as f:
            resultats = json.load(f)
        execution = pd.Timestamp(resultats["metadata"]["generated_at"]).tz_convert("UTC").tz_localize(None).floor("s")
        for r in resultats["results"]:
            if not r["unique_id"].startswith("test."):
                continue
            lignes.append({
                "date_execution": execution,
                "projet": projet,
                "controle": r["unique_id"].split(".")[2],
                "statut": r["status"],
                "nb_lignes_en_echec": int(r.get("failures") or 0),
                "message": (r.get("message") or "")[:500],
                "duree_secondes": round(float(r.get("execution_time") or 0), 2),
            })
    nouveaux = pd.DataFrame(lignes)
    # On AJOUTE à l'historique existant (sans doublon si on relance)
    try:
        historique = lire("select * from gouvernance.resultats_controles")
        historique["date_execution"] = pd.to_datetime(historique["date_execution"])
        tout = pd.concat([historique, nouveaux]).drop_duplicates(["date_execution", "projet", "controle"])
    except Exception:
        tout = nouveaux
    ecrire_table(tout, "resultats_controles", schema="gouvernance", securite_pays=False)
    print(f"{len(nouveaux)} résultats de contrôles enregistrés.", flush=True)


if __name__ == "__main__":
    main()
