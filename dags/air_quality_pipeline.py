"""
air_quality_pipeline — hourly PM2.5 for Thailand from 3 sources.

create_tables
  -> TaskGroup extract (parallel)
       extract_air4thai                       (A: JSON API)
       plan_openmeteo_batches -> extract_openmeteo.expand(batch)   (B: API, dynamic task mapping per region)
       scrape_aqicn                           (C: HTML scraping, robots.txt checked)
  -> transform_dedupe   (trigger_rule=none_failed_min_one_success: runs if >= 1 source succeeded)
  -> quality_check      (BranchPythonOperator)
       -> load_upsert       (INSERT ... ON CONFLICT DO UPDATE)
       -> quarantine_alert  (writes data_quality_log + air_quality_quarantine)
  -> finish

A failing source logs status=failed into pipeline_runs and is marked *skipped* (not failed),
so the rest of the DAG keeps going with the remaining sources.
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import get_current_context
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

from aq_lib import db, sources, transform

STAGING_DIR = os.environ.get("AQ_STAGING_DIR", "/opt/airflow/data/staging")


def _staging_path(run_id, name):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)
    d = os.path.join(STAGING_DIR, safe)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.json")


def _save(run_id, name, payload):
    path = _staging_path(run_id, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run_extract(source, name, fetch, detail=None):
    """Fetch one source; on any error record status=failed and skip (do not fail the DAG)."""
    run_id = get_current_context()["run_id"]
    started = datetime.now(timezone.utc)
    try:
        raw = fetch()
    except Exception as exc:  # noqa: BLE001 - every source error must be captured
        msg = f"{type(exc).__name__}: {exc}"[:1000]
        db.log_run(run_id, source, "failed", 0, msg, detail, started)
        raise AirflowSkipException(f"{source} unavailable -> skipped ({msg})")
    db.log_run(run_id, source, "success", len(raw), None, detail, started)
    return {"source": source, "path": _save(run_id, name, raw), "rows": len(raw)}


@dag(
    dag_id="air_quality_pipeline",
    description="Hourly PM2.5 (Thailand) from Air4Thai + Open-Meteo + aqicn scrape -> PostgreSQL",
    schedule="@hourly",
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "6621601077", "retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["02739452", "pm25", "exam"],
)
def air_quality_pipeline():

    @task
    def create_tables():
        db.ensure_schema()

    @task(retries=0)
    def extract_air4thai():
        return _run_extract("air4thai", "air4thai", sources.fetch_air4thai)

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def plan_openmeteo_batches(a4t):
        """Station coordinates come from source A; fall back to a built-in list if A is down."""
        stations = []
        if a4t and a4t.get("path"):
            stations = sources.air4thai_station_list(_load(a4t["path"]))
        if not stations:
            stations = sources.FALLBACK_STATIONS
        return sources.make_region_batches(stations)

    @task(retries=0, map_index_template="{{ region }}")
    def extract_openmeteo(batch):
        get_current_context()["region"] = batch["region"]
        return _run_extract(
            "openmeteo", f"openmeteo_{batch['region']}",
            lambda: sources.fetch_openmeteo(batch["stations"]),
            detail=f"region={batch['region']} stations={len(batch['stations'])}",
        )

    @task(retries=0)
    def scrape_aqicn():
        return _run_extract("aqicn_scrape", "aqicn", sources.scrape_aqicn)

    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def transform_dedupe(a4t, om_list, aq):
        run_id = get_current_context()["run_id"]
        started = datetime.now(timezone.utc)
        records, sources_ok = [], []
        if a4t:
            records += transform.normalize_air4thai(_load(a4t["path"]))
            sources_ok.append("air4thai")
        om_items = [x for x in (list(om_list) if om_list else []) if x]
        for item in om_items:
            records += transform.normalize_openmeteo(_load(item["path"]))
        if om_items:
            sources_ok.append("openmeteo")
        if aq:
            records += transform.normalize_aqicn(_load(aq["path"]))
            sources_ok.append("aqicn_scrape")

        kept, removed, removed_by = transform.dedupe(records)
        by_source = dict(Counter(r["source"] for r in kept))
        detail = f"before={len(records)} after={len(kept)} removed={removed} removed_by={removed_by} kept_by={by_source}"
        db.log_run(run_id, "transform_dedupe", "success", len(kept), None, detail, started)
        return {
            "path": _save(run_id, "unified", kept),
            "rows_before": len(records),
            "rows": len(kept),
            "duplicates_removed": removed,
            "sources_ok": sources_ok,
        }

    @task.branch
    def quality_check(t):
        run_id = get_current_context()["run_id"]
        rows = _load(t["path"])
        n = len(rows)
        null_pm25 = sum(1 for r in rows if r["pm25"] is None)
        out_of_range = sum(1 for r in rows if r["pm25"] is not None
                           and not (transform.PM25_MIN <= r["pm25"] <= transform.PM25_MAX))
        out_of_th = sum(1 for r in rows if not transform.in_thailand(r))
        min_rows = int(os.environ.get("QUALITY_MIN_ROWS", "100"))
        max_null = float(os.environ.get("QUALITY_MAX_NULL_RATIO", "0.30"))

        reasons = []
        if n < min_rows:
            reasons.append(f"rows {n} < min {min_rows}")
        if n and null_pm25 / n > max_null:
            reasons.append(f"null pm25 ratio {null_pm25 / n:.2f} > {max_null}")
        if out_of_range:
            reasons.append(f"{out_of_range} pm25 outside 0-1000")
        if out_of_th:
            reasons.append(f"{out_of_th} rows outside Thailand bbox")
        passed = not reasons

        with db.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO data_quality_log (run_id, passed, total_rows, duplicates_removed, null_pm25,
                       out_of_range, out_of_thailand, sources_ok, reasons, action)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (run_id, passed, n, t["duplicates_removed"], null_pm25, out_of_range, out_of_th,
                 ",".join(t["sources_ok"]), "; ".join(reasons) or "all checks passed",
                 "load" if passed else "quarantine"),
            )
        return "load_upsert" if passed else "quarantine_alert"

    @task
    def load_upsert(t):
        run_id = get_current_context()["run_id"]
        started = datetime.now(timezone.utc)
        rows = _load(t["path"])
        sent, total = db.upsert_air_quality(rows)
        db.log_run(run_id, "load_upsert", "success", sent, None, f"table_rows_after={total}", started)
        return {"upserted": sent, "table_rows": total}

    @task
    def quarantine_alert(t):
        run_id = get_current_context()["run_id"]
        started = datetime.now(timezone.utc)
        rows = _load(t["path"])
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT reasons FROM data_quality_log WHERE run_id=%s ORDER BY id DESC LIMIT 1", (run_id,))
            reasons = (cur.fetchone() or ["unknown"])[0]
            cur.execute(
                "INSERT INTO air_quality_quarantine (run_id, reasons, row_count, sample) VALUES (%s,%s,%s,%s)",
                (run_id, reasons, len(rows), json.dumps(rows[:50], ensure_ascii=False)),
            )
        db.log_run(run_id, "quality_alert", "quarantined", len(rows), reasons, None, started)
        print(f"ALERT: data quality failed for {run_id}: {reasons} -> batch quarantined, not loaded")

    finish = EmptyOperator(task_id="finish", trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)

    with TaskGroup(group_id="extract") as extract_group:
        a4t = extract_air4thai()
        om = extract_openmeteo.expand(batch=plan_openmeteo_batches(a4t))
        aq = scrape_aqicn()

    t = transform_dedupe(a4t, om, aq)
    create_tables() >> extract_group
    branch = quality_check(t)
    branch >> [load_upsert(t), quarantine_alert(t)] >> finish


air_quality_pipeline()
