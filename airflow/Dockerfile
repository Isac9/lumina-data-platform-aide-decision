FROM apache/airflow:2.10.5-python3.11

# 1) dbt, comme au projet 1
RUN python -m venv /home/airflow/dbt_venv && PIP_USER=false /home/airflow/dbt_venv/bin/pip install --no-cache-dir dbt-core==1.9.4 dbt-postgres==1.9.0

# 2) NOUVEAU : les outils de Machine Learning et de prévision, dans leur propre environnement
RUN python -m venv /home/airflow/ml_venv && PIP_USER=false /home/airflow/ml_venv/bin/pip install --no-cache-dir pandas==2.2.3 scikit-learn==1.5.2 statsmodels==0.14.4 SQLAlchemy==2.0.36 psycopg2-binary==2.9.10
