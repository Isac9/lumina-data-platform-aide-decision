"""
SCORING DE RISQUE : quelle est la probabilité qu'un prêt aujourd'hui "sain"
(30 jours de retard ou moins) passe en PAR 30 dans les 3 prochains mois ?

Méthode :
  1. On reprend les "photos" mensuelles du portefeuille (projet 2).
  2. Pour chaque photo passée, on regarde ce qui s'est passé ENSUITE (la cible).
  3. On entraîne 2 modèles sur le passé et on les teste sur les mois les plus récents :
       - régression logistique (CHAMPION : simple et explicable) ;
       - gradient boosting (CHALLENGER : plus complexe, pour comparer).
  4. On note tous les prêts d'aujourd'hui avec le champion et on explique
     chaque note par ses 3 principales raisons.
"""

from datetime import date

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from commun import ecrire_table, lire

HORIZON_MOIS = 3
MOIS_DE_TEST = 6

VARIABLES_NUMERIQUES = [
    "retard_actuel", "retard_max_passe", "nb_mois_en_retard", "arrieres_en_mensualites",
    "part_remboursee", "age_pret_mois", "log_montant_finance", "duree_mois", "taux_apport",
    "anciennete_client_mois",
]
VARIABLES_CATEGORIELLES = ["code_produit", "segment", "code_entite"]

LIBELLES = {
    "retard_actuel": "Retard actuel",
    "retard_max_passe": "Plus gros retard passé",
    "nb_mois_en_retard": "Nombre de mois en retard",
    "arrieres_en_mensualites": "Arriérés",
    "part_remboursee": "Part déjà remboursée",
    "age_pret_mois": "Ancienneté du prêt",
    "log_montant_finance": "Montant financé",
    "duree_mois": "Durée du prêt",
    "taux_apport": "Apport initial",
    "anciennete_client_mois": "Ancienneté du client",
    "code_produit": "Produit",
    "segment": "Segment",
    "code_entite": "Pays",
}


def charger_photos():
    df = lire("""
        select s.date_arrete, s.est_dernier_arrete, s.id_pret, s.id_client, s.id_agent,
               s.code_entite, s.code_produit, s.montant_finance, s.total_paye, s.encours,
               s.arrieres, s.jours_retard, p.duree_mois, p.mensualite, p.apport_initial,
               p.prix_vente, p.date_decaissement, c.segment, c.date_inscription,
               c.nom_complet as nom_client, c.telephone, a.nom_complet as nom_agent
        from reporting.fct_situation_prets s
        join marts.fact_prets p on p.id_pret = s.id_pret
        join marts.dim_client c on c.id_client = s.id_client
        left join marts.dim_agent a on a.id_agent = s.id_agent
    """)
    for col in ("date_arrete", "date_decaissement", "date_inscription"):
        df[col] = pd.to_datetime(df[col])
    df = df.sort_values(["id_pret", "date_arrete"]).reset_index(drop=True)

    # --- Variables explicatives (toutes connues À LA DATE de la photo)
    g = df.groupby("id_pret")["jours_retard"]
    df["retard_actuel"] = df["jours_retard"]
    df["retard_max_passe"] = g.cummax()
    df["nb_mois_en_retard"] = (df["jours_retard"] > 0).astype(int).groupby(df["id_pret"]).cumsum()
    df["arrieres_en_mensualites"] = df["arrieres"] / df["mensualite"]
    df["part_remboursee"] = df["total_paye"] / df["montant_finance"]
    df["age_pret_mois"] = (df["date_arrete"] - df["date_decaissement"]).dt.days / 30.4
    df["log_montant_finance"] = np.log(df["montant_finance"])
    df["taux_apport"] = df["apport_initial"] / df["prix_vente"]
    df["anciennete_client_mois"] = (df["date_arrete"] - df["date_inscription"]).dt.days / 30.4
    return df


def construire_cible(df):
    """Cible = 1 si le prêt dépasse 30 jours de retard dans les 3 photos mensuelles suivantes."""
    mensuel = df[~df["est_dernier_arrete"]].copy()
    g = mensuel.groupby("id_pret")["jours_retard"]
    futur = pd.concat([g.shift(-k) for k in range(1, HORIZON_MOIS + 1)], axis=1).max(axis=1)
    mensuel["cible"] = (futur > 30).astype(int)
    # On ne garde que les photos dont on connaît l'avenir complet, et les prêts encore "sains"
    derniere = mensuel["date_arrete"].max()
    limite = derniere - pd.DateOffset(months=HORIZON_MOIS)
    return mensuel[(mensuel["date_arrete"] <= limite) & (mensuel["jours_retard"] <= 30)]


def pipeline(modele):
    prepa = ColumnTransformer([
        ("num", StandardScaler(), VARIABLES_NUMERIQUES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), VARIABLES_CATEGORIELLES),
    ])
    return Pipeline([("prepa", prepa), ("modele", modele)])


def mesurer(y, p):
    auc = roc_auc_score(y, p)
    fpr, tpr, _ = roc_curve(y, p)
    return {"auc": round(auc, 4), "gini": round(2 * auc - 1, 4), "ks": round(float(np.max(tpr - fpr)), 4)}


def classe(p):
    if p < 0.05:
        return "A - Très faible"
    if p < 0.10:
        return "B - Faible"
    if p < 0.20:
        return "C - Moyen"
    if p < 0.40:
        return "D - Élevé"
    return "E - Très élevé"


def raisons(modele, X):
    """Les 3 variables qui poussent le plus la probabilité vers le haut, pour chaque prêt."""
    prepa = modele.named_steps["prepa"]
    coefs = modele.named_steps["modele"].coef_[0]
    Xt = prepa.transform(X)
    Xt = Xt.toarray() if hasattr(Xt, "toarray") else Xt
    noms = prepa.get_feature_names_out()
    contributions = Xt * coefs
    textes = []
    for i in range(len(X)):
        par_variable = {}
        for nom, valeur, contrib in zip(noms, Xt[i], contributions[i]):
            type_, variable = nom.split("__", 1)
            if type_ == "num":
                sens = "élevé" if valeur > 0 else "faible"
                cle = f"{LIBELLES[variable]} ({sens})"
            else:
                if valeur == 0:
                    continue
                base, modalite = variable.rsplit("_", 1)
                cle = f"{LIBELLES[base]} = {modalite}"
            par_variable[cle] = par_variable.get(cle, 0) + contrib
        top = [k for k, v in sorted(par_variable.items(), key=lambda kv: -kv[1]) if v > 0][:3]
        textes.append(" ; ".join(top) if top else "Aucun facteur de risque marqué")
    return textes


def main():
    print("Chargement des photos du portefeuille...", flush=True)
    photos = charger_photos()
    donnees = construire_cible(photos)
    X, y = donnees[VARIABLES_NUMERIQUES + VARIABLES_CATEGORIELLES], donnees["cible"]

    # --- Découpage dans le TEMPS : on apprend sur le passé, on teste sur les mois récents
    dates = sorted(donnees["date_arrete"].unique())
    debut_test = dates[-MOIS_DE_TEST]
    entrainement = donnees["date_arrete"] < debut_test
    print(f"{len(donnees)} exemples, {y.mean():.1%} de cibles. Test à partir du {pd.Timestamp(debut_test).date()}.", flush=True)

    modeles = {
        "Régression logistique": ("Champion", pipeline(LogisticRegression(max_iter=2000))),
        "Gradient boosting": ("Challenger", pipeline(HistGradientBoostingClassifier(max_depth=4, random_state=42))),
    }
    performances, calibration = [], None
    for nom, (role, modele) in modeles.items():
        modele.fit(X[entrainement], y[entrainement])
        p_test = modele.predict_proba(X[~entrainement])[:, 1]
        mesures = mesurer(y[~entrainement], p_test)
        performances.append({
            "date_entrainement": date.today(), "modele": nom, "role": role, **mesures,
            "nb_exemples_entrainement": int(entrainement.sum()), "nb_exemples_test": int((~entrainement).sum()),
            "taux_cible_test": round(float(y[~entrainement].mean()), 4),
            "periode_test": f"{pd.Timestamp(debut_test).date()} -> {pd.Timestamp(dates[-1]).date()}",
        })
        print(f"  {nom} ({role}) : AUC {mesures['auc']} | Gini {mesures['gini']} | KS {mesures['ks']}", flush=True)
        if role == "Champion":
            cal = pd.DataFrame({"p": p_test, "y": y[~entrainement].values})
            cal["decile"] = pd.qcut(cal["p"], 10, labels=False, duplicates="drop") + 1
            calibration = cal.groupby("decile").agg(
                probabilite_predite=("p", "mean"), taux_observe=("y", "mean"), nb_prets=("y", "size")
            ).reset_index()

    # --- Le champion est ré-entraîné sur TOUT l'historique, puis note les prêts d'aujourd'hui
    champion = modeles["Régression logistique"][1]
    champion.fit(X, y)
    aujourdhui = photos[photos["est_dernier_arrete"]].copy()
    sains = aujourdhui["jours_retard"] <= 30
    Xa = aujourdhui.loc[sains, VARIABLES_NUMERIQUES + VARIABLES_CATEGORIELLES]
    aujourdhui.loc[sains, "probabilite_defaut"] = champion.predict_proba(Xa)[:, 1]
    aujourdhui.loc[sains, "raisons"] = raisons(champion, Xa)
    aujourdhui["score"] = ((1 - aujourdhui["probabilite_defaut"]) * 1000).round()
    aujourdhui["classe_risque"] = [
        classe(p) if pd.notna(p) else "F - Déjà en PAR 30" for p in aujourdhui["probabilite_defaut"]
    ]
    aujourdhui.loc[~sains, "raisons"] = "Déjà plus de 30 jours de retard : à traiter par le recouvrement"

    scores = aujourdhui[[
        "id_pret", "id_client", "nom_client", "telephone", "id_agent", "nom_agent", "code_entite",
        "code_produit", "encours", "jours_retard", "probabilite_defaut", "score", "classe_risque", "raisons",
    ]].assign(date_score=date.today())

    coefs = champion.named_steps["modele"].coef_[0]
    noms = champion.named_steps["prepa"].get_feature_names_out()
    importance = pd.DataFrame({"variable": [n.split("__", 1)[1] for n in noms], "poids": coefs})
    importance["variable_metier"] = [LIBELLES.get(v, LIBELLES.get(v.rsplit("_", 1)[0], v)) for v in importance["variable"]]
    importance["effet"] = np.where(importance["poids"] > 0, "Augmente le risque", "Diminue le risque")
    importance = importance.reindex(importance["poids"].abs().sort_values(ascending=False).index)

    ecrire_table(scores, "scores_risque")
    ecrire_table(pd.DataFrame(performances), "performance_modeles")
    ecrire_table(calibration, "calibration_modele")
    ecrire_table(importance, "importance_variables")
    print("Scoring terminé.", flush=True)


if __name__ == "__main__":
    main()
