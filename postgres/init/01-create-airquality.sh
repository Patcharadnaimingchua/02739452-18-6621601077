#!/bin/bash
# Runs once on an empty data volume: create the data database next to the Airflow metadata DB.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE ${AQ_DB_NAME:-airquality};
EOSQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${AQ_DB_NAME:-airquality}" -f /docker-entrypoint-initdb.d/schema.sql.txt
