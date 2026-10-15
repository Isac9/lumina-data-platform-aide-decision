"""
DAG Airflow : modèles d'aide à la décision (projet 3).

Il démarre quand le reporting du projet 2 est prêt ("lumina://dwh/reporting").

    scorer_risque ──> prevoir_encaissements ──> detecter_anomalies
"""

from datetime import datetime, timedelta

from airflow.datasets import Dataset
from airflow.decorators import dag
from airflow.operators.bash import BashOperator

PYTHON = "cd /opt/ml && /home/airflow/ml_venv/bin/python"

REPORTING_PRET = Dataset("lumina://dwh/reporting")
MODELES_PRETS = Dataset("lumina://dwh/ml")


@dag(
    dag_id="pipeline_aide_decision_lumina",
    description="Scoring de risque, prévision des encaissements, détection d'anomalies",
    schedule=[REPORTING_PRET],
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["lumina", "ml", "aide-decision"],
)
def pipeline_aide_decision_lumina():
    scorer = BashOperator(task_id="scorer_risque", bash_command=f"{PYTHON} scoring.py")
    prevoir = BashOperator(task_id="prevoir_encaissements", bash_command=f"{PYTHON} prevision.py")
    anomalies = BashOperator(task_id="detecter_anomalies", bash_command=f"{PYTHON} anomalies.py",
                             outlets=[MODELES_PRETS])

    scorer >> prevoir >> anomalies


pipeline_aide_decision_lumina()
