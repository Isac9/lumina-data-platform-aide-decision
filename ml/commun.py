"""
Outils partagés par les scripts du projet 3 : connexion à l'entrepôt,
lecture et écriture de tables (avec droits et sécurité par pays).
"""

import os

import pandas as pd
from sqlalchemy import create_engine, text

DWH_URI = os.environ.get("DWH_URI", "postgresql+psycopg2://lumina:lumina@localhost:5434/dwh")
LECTEURS = ["direction_groupe", "lecteur_ci", "lecteur_sn", "lecteur_bf"]

moteur = create_engine(DWH_URI)


def lire(sql):
    with moteur.connect() as conn:
        return pd.read_sql(text(sql), conn)


def ecrire_table(df, nom, schema="ml", securite_pays=True):
    """Remplace la table, donne la lecture aux lecteurs et pose la règle
    "chaque pays ne voit que ses lignes" (si la table a une colonne code_entite)."""
    with moteur.begin() as conn:
        conn.execute(text(f"create schema if not exists {schema}"))
        conn.execute(text(f"grant usage on schema {schema} to {', '.join(LECTEURS)}"))
    df.to_sql(nom, moteur, schema=schema, if_exists="replace", index=False)
    with moteur.begin() as conn:
        conn.execute(text(f"grant select on {schema}.{nom} to {', '.join(LECTEURS)}"))
        if securite_pays and "code_entite" in df.columns:
            conn.execute(text(f"alter table {schema}.{nom} enable row level security"))
            conn.execute(text(
                f"create policy filtre_par_entite on {schema}.{nom} for select using ("
                "pg_has_role(current_user, 'direction_groupe', 'member') "
                "or code_entite = upper(replace(current_user, 'lecteur_', '')))"
            ))
    print(f"  {schema}.{nom} : {len(df)} lignes écrites", flush=True)
