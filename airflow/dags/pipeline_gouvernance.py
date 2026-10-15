"""
DAG Airflow : gouvernance des données (projet 3).

Il démarre quand le reporting du projet 2 est prêt.

  controles_entrepot ─> controles_reporting ─> enregistrer_controles ─> dbt_gouvernance ─> catalogue

- les contrôles qualité des projets 1 et 2 sont rejoués et leur résultat est GARDÉ ;
- dbt calcule la fraîcheur des sources, la volumétrie, la matrice des droits... ;
- le catalogue de données (documentation dbt) est régénéré.
"""

from datetime import datetime, timedelta

from airflow.datasets import Dataset
from airflow.decorators import dag
from airflow.operators.bash import BashOperator

DBT = "/home/airflow/dbt_venv/bin/dbt"
PYTHON = "cd /opt/ml && /home/airflow/ml_venv/bin/python"
P1 = "cd /opt/dbt/lumina_dwh"
P2 = "cd /opt/dbt_reporting/lumina_reporting"
P3 = "cd /opt/dbt_gouvernance/lumina_gouvernance"

REPORTING_PRET = Dataset("lumina://dwh/reporting")


@dag(
    dag_id="pipeline_gouvernance_lumina",
    description="Historique des contrôles qualité, fraîcheur, volumétrie, droits, catalogue",
    schedule=[REPORTING_PRET],
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["lumina", "gouvernance", "qualite"],
)
def pipeline_gouvernance_lumina():
    # "; exit 0" : un contrôle en échec ne doit pas arrêter la gouvernance, on veut l'ENREGISTRER
    controles_entrepot = BashOperator(
        task_id="controles_entrepot",
        bash_command=f"{P1} && {DBT} test --target-path /tmp/gouv_entrepot; exit 0",
    )
    controles_reporting = BashOperator(
        task_id="controles_reporting",
        bash_command=f"{P2} && {DBT} test --profiles-dir . --target-path /tmp/gouv_reporting; exit 0",
    )
    enregistrer = BashOperator(task_id="enregistrer_controles", bash_command=f"{PYTHON} collecter_controles.py")
    dbt_gouvernance = BashOperator(
        task_id="dbt_gouvernance",
        bash_command=f"{P3} && {DBT} build --profiles-dir . --target-path /tmp/dbt_target_gouvernance",
    )
    catalogue = BashOperator(
        task_id="catalogue",
        bash_command=(
            f"{P1} && {DBT} docs generate --target-path /opt/catalogue/entrepot && "
            f"{P2} && {DBT} docs generate --profiles-dir . --target-path /opt/catalogue/reporting && "
            f"{P3} && {DBT} docs generate --profiles-dir . --target-path /opt/catalogue/gouvernance"
        ),
    )

    controles_entrepot >> controles_reporting >> enregistrer >> dbt_gouvernance >> catalogue


pipeline_gouvernance_lumina()
