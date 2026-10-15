"""
PRÉVISION DES ENCAISSEMENTS des 3 prochains mois, par pays, avec 2 méthodes :

  A. "Échéancier" : mensualités prévues des prêts en cours × taux de recouvrement
     moyen des 6 derniers mois. Simple et compréhensible par la finance, mais
     n'inclut pas les futurs nouveaux prêts.
  B. "Statistique" : un modèle de série temporelle (lissage exponentiel avec
     tendance, ETS) qui prolonge la courbe passée, avec un intervalle de confiance.

On TESTE les deux méthodes sur le passé (backtest) : on "cache" les 3 derniers
mois complets, on les prévoit, et on mesure l'erreur moyenne (MAPE).
"""

import warnings
from datetime import date

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

from commun import ecrire_table, lire

warnings.filterwarnings("ignore")
HORIZON = 3


def charger():
    reel = lire("""
        select code_entite, date_trunc('month', date_paiement)::date as mois, sum(montant) as montant
        from marts.fact_remboursements
        where date_paiement < date_trunc('month', current_date)
        group by 1, 2
    """)
    echeances = lire("""
        select e.code_entite, date_trunc('month', e.date_echeance)::date as mois, sum(e.montant_du) as montant_du
        from marts.fact_echeances e
        join marts.fact_prets p on p.id_pret = e.id_pret
        group by 1, 2
    """)
    actifs = lire("""
        select e.code_entite, date_trunc('month', e.date_echeance)::date as mois, sum(e.montant_du) as montant_du
        from marts.fact_echeances e
        join marts.fact_prets p on p.id_pret = e.id_pret
        where p.encours > 0 and e.date_echeance >= date_trunc('month', current_date)
        group by 1, 2
    """)
    for df in (reel, echeances, actifs):
        df["mois"] = pd.to_datetime(df["mois"])
    return reel, echeances, actifs


def methode_echeancier(reel, echeances_futures, echeances_passees, code, mois_a_prevoir, fin_historique):
    """Mensualités prévues × taux de recouvrement moyen des 6 mois avant fin_historique."""
    hist = reel[(reel.code_entite == code) & (reel.mois <= fin_historique)].set_index("mois")["montant"]
    du = echeances_passees[echeances_passees.code_entite == code].set_index("mois")["montant_du"]
    six_mois = hist.index[-6:]
    taux = hist.loc[six_mois].sum() / du.reindex(six_mois).sum()
    futur = echeances_futures[echeances_futures.code_entite == code].set_index("mois")["montant_du"]
    return pd.Series([futur.get(m, 0.0) * taux for m in mois_a_prevoir], index=mois_a_prevoir), taux


def methode_statistique(serie, nb_mois):
    serie = serie.asfreq("MS").fillna(0.0).iloc[-24:]
    modele = ETSModel(serie.astype(float), error="add", trend="add", damped_trend=True).fit(disp=False)
    prev = modele.get_prediction(start=len(serie), end=len(serie) + nb_mois - 1).summary_frame(alpha=0.2)
    return prev["mean"].clip(lower=0), prev["pi_lower"].clip(lower=0), prev["pi_upper"].clip(lower=0)


def mape(reel, prevu):
    return float(np.mean(np.abs((reel - prevu) / reel)))


def main():
    reel, echeances, actifs = charger()
    dernier_mois = reel["mois"].max()
    futurs = pd.date_range(dernier_mois + pd.offsets.MonthBegin(1), periods=HORIZON, freq="MS")
    lignes, backtests = [], []

    for code in sorted(reel["code_entite"].unique()):
        serie = reel[reel.code_entite == code].set_index("mois")["montant"].sort_index()

        # --- Historique réel
        for m, v in serie.iloc[-18:].items():
            lignes.append({"code_entite": code, "mois": m, "serie": "Réel", "montant": v, "borne_basse": None, "borne_haute": None})

        # --- Prévisions
        prev_a, taux = methode_echeancier(reel, actifs, echeances, code, futurs, dernier_mois)
        moy, bas, haut = methode_statistique(serie, HORIZON)
        for m in futurs:
            lignes.append({"code_entite": code, "mois": m, "serie": "Prévision échéancier",
                           "montant": round(prev_a[m]), "borne_basse": None, "borne_haute": None})
        for m, v, b, h in zip(futurs, moy, bas, haut):
            lignes.append({"code_entite": code, "mois": m, "serie": "Prévision statistique",
                           "montant": round(v), "borne_basse": round(b), "borne_haute": round(h)})

        # --- Backtest : on cache les 3 derniers mois et on les prévoit
        caches = serie.index[-HORIZON:]
        coupure = caches[0] - pd.offsets.MonthBegin(1)
        reel_caches = serie.loc[caches].values
        prev_bt_a, _ = methode_echeancier(reel, echeances, echeances, code, caches, coupure)
        prev_bt_b, _, _ = methode_statistique(serie[serie.index <= coupure], HORIZON)
        for methode, prev in (("Échéancier", prev_bt_a.values), ("Statistique (ETS)", prev_bt_b.values)):
            backtests.append({
                "code_entite": code, "methode": methode,
                "periode_testee": f"{caches[0]:%Y-%m} -> {caches[-1]:%Y-%m}",
                "montant_reel": round(float(reel_caches.sum())), "montant_prevu": round(float(prev.sum())),
                "mape": round(mape(reel_caches, prev), 4), "date_calcul": date.today(),
            })
        print(f"  {code} : taux de recouvrement utilisé {taux:.1%}", flush=True)

    previsions = pd.DataFrame(lignes)
    previsions["mois"] = previsions["mois"].dt.date
    backtest = pd.DataFrame(backtests)
    print(backtest[["code_entite", "methode", "mape"]].to_string(index=False), flush=True)
    ecrire_table(previsions, "prevision_encaissements")
    ecrire_table(backtest, "backtest_previsions")
    print("Prévision terminée.", flush=True)


if __name__ == "__main__":
    main()
