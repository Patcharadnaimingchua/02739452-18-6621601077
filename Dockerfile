FROM apache/airflow:2.10.5-python3.11
# staging dir must exist (owned by airflow) before the named volume is mounted on it
USER root
RUN mkdir -p /opt/airflow/data/staging && chown -R 50000:0 /opt/airflow/data
USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==2.10.5" -r /requirements.txt
