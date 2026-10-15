"""
DÉTECTION D'ANOMALIES : signaler ce qui sort de l'ordinaire, pour enquête.

  1. Agents commerciaux au comportement inhabituel (Isolation Forest) :
     ventes, montants, apports, et part de clients qui n'ont JAMAIS payé
     ("défaut de premier paiement" : un signal classique de fraude).
  2. Journées d'encaissement anormales par pays (écart à la moyenne, "z-score").
  3. Écarts entre le portefeuille et la comptabilité (rapprochement du projet 1).

Une anomalie n'est PAS une faute : c'est une alerte "à investiguer".
"""

from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from commun import ecrire_table, lire

LIBELLES = {
    "nb_ventes": "nombre de ventes",
    "montant_moyen": "montant moyen financé",
    "taux_apport_moyen": "apport moyen",
    "part_gros_equipements": "part de gros équipements",
    "part_jamais_paye": "part de clients n'ayant jamais payé",
}


def anomalies_agents():
    df = lire("""
        with prets as (
            select p.id_pret, p.id_agent, p.code_entite, date_trunc('month', p.date_decaissement)::date as mois,
                   p.montant_finance, p.apport_initial / p.prix_vente as taux_apport,
                   p.code_produit in ('KIT-L', 'POMPE') as gros_equipement,
                   p.nb_paiements = 0 and p.date_decaissement < current_date - 75 as jamais_paye,
                   p.date_decaissement < current_date - 75 as observable
            from marts.fact_prets p
        )
        select pr.id_agent, a.nom_complet as nom_agent, pr.code_entite, pr.mois,
               count(*)                                   as nb_ventes,
               avg(montant_finance)                       as montant_moyen,
               avg(taux_apport)                           as taux_apport_moyen,
               avg(gros_equipement::int)                  as part_gros_equipements,
               coalesce(avg(jamais_paye::int) filter (where observable), 0) as part_jamais_paye
        from prets pr
        join marts.dim_agent a on a.id_agent = pr.id_agent
        group by 1, 2, 3, 4
        having count(*) >= 3
    """)
    variables = list(LIBELLES)
    X = df[variables].astype(float)
    foret = IsolationForest(n_estimators=300, contamination=0.03, random_state=42).fit(X)
    df["anomalie"] = foret.predict(X) == -1
    df["score"] = -foret.score_samples(X)
    z = (X - X.mean()) / X.std()
    lignes = []
    for i, ligne in df[df["anomalie"]].iterrows():
        variable = z.loc[i].abs().idxmax()
        sens = "très élevé(e)" if z.loc[i, variable] > 0 else "très faible"
        valeur = ligne[variable]
        valeur_txt = f"{valeur:.0%}" if variable.startswith(("part", "taux")) else f"{valeur:,.0f}".replace(",", " ")
        lignes.append({
            "type_anomalie": "Agent commercial inhabituel", "code_entite": ligne["code_entite"],
            "objet": ligne["nom_agent"], "date_concernee": ligne["mois"], "score": round(float(ligne["score"]), 3),
            "description": f"{LIBELLES[variable].capitalize()} {sens} ce mois-là ({valeur_txt}) "
                           f"pour {int(ligne['nb_ventes'])} ventes",
        })
    return lignes


def anomalies_encaissements():
    df = lire("""
        select code_entite, date_paiement as jour, sum(montant) as montant
        from marts.fact_remboursements
        group by 1, 2
    """)
    df["jour"] = pd.to_datetime(df["jour"])
    lignes = []
    for code, groupe in df.groupby("code_entite"):
        serie = groupe.set_index("jour")["montant"].asfreq("D").fillna(0.0)
        moyenne = serie.rolling(60, min_periods=30).mean().shift(1)
        ecart = serie.rolling(60, min_periods=30).std().shift(1)
        z = (serie - moyenne) / ecart
        for jour, valeur in z[(z.abs() > 4) & (serie.index >= serie.index.max() - pd.Timedelta(days=180))].items():
            lignes.append({
                "type_anomalie": "Journée d'encaissement inhabituelle", "code_entite": code,
                "objet": f"Encaissements du {jour:%d/%m/%Y}", "date_concernee": jour.date(),
                "score": round(float(abs(valeur)), 3),
                "description": f"{serie[jour]:,.0f} FCFA encaissés, contre {moyenne[jour]:,.0f} en moyenne".replace(",", " "),
            })
    return lignes


def anomalies_rapprochement():
    df = lire("""
        select code_entite, id_remboursement, num_piece_erp, date_paiement, montant, montant_erp, statut_rapprochement
        from marts.fact_remboursements
        where statut_rapprochement <> 'RAPPROCHE'
    """)
    lignes = []
    for _, l in df.iterrows():
        if l["statut_rapprochement"] == "ABSENT_ERP":
            texte = f"Paiement n°{l['id_remboursement']} de {l['montant']:,.0f} FCFA absent de la comptabilité"
        else:
            texte = (f"Paiement n°{l['id_remboursement']} : {l['montant']:,.0f} FCFA dans le portefeuille "
                     f"mais {l['montant_erp']:,.0f} FCFA en comptabilité")
        lignes.append({
            "type_anomalie": "Écart portefeuille / comptabilité", "code_entite": l["code_entite"],
            "objet": f"Paiement n°{l['id_remboursement']}", "date_concernee": l["date_paiement"],
            "score": 1.0, "description": texte.replace(",", " "),
        })
    return lignes


def main():
    lignes = anomalies_agents() + anomalies_encaissements() + anomalies_rapprochement()
    df = pd.DataFrame(lignes)
    df["gravite"] = np.where(df["type_anomalie"] == "Écart portefeuille / comptabilité", "Moyenne", "Haute")
    df["statut"] = "À investiguer"
    df["date_detection"] = date.today()
    print(df.groupby("type_anomalie").size().to_string(), flush=True)
    ecrire_table(df, "anomalies")
    print("Détection d'anomalies terminée.", flush=True)


if __name__ == "__main__":
    main()
