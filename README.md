# ค่า PM2.5 รายชั่วโมง — สถานีตรวจวัดคุณภาพอากาศทั่วประเทศไทย

ข้อสอบปฏิบัติ วิชา **02739452 แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์**
นายพชรดนัย มิ่งเชื้อ · รหัส 6621601077 · หมู่ 700

Data pipeline บน **Apache Airflow 2.10** ดึงค่า PM2.5 รายชั่วโมงจาก 3 แหล่ง → รวมเป็น schema เดียว → ตัดซ้ำข้ามแหล่ง → ตรวจคุณภาพ → UPSERT ลง **PostgreSQL** → แสดงผลบน **Streamlit** dashboard ที่อ่านจาก PostgreSQL โดยตรง

## แหล่งข้อมูล

| # | แหล่ง | วิธี | ข้อมูลที่ได้ | เหตุผลที่เลือก |
|---|---|---|---|---|
| A | **Air4Thai** (กรมควบคุมมลพิษ) `https://air4thai.pcd.go.th/services/getNewAQI_JSON.php` | REST API (JSON) | ~173 สถานีทั่วประเทศ ค่า PM2.5 ชั่วโมงล่าสุด, พิกัด, จังหวัด | แหล่งทางการของไทย ข้อมูลวัดจริง → priority สูงสุด |
| B | **Open-Meteo Air Quality API** `https://air-quality-api.open-meteo.com/v1/air-quality` | REST API (JSON) ไม่ต้องใช้ key | PM2.5 รายชั่วโมงย้อนหลัง 24 ชม. ที่พิกัดของทุกสถานี Air4Thai (ข้อมูลแบบจำลอง CAMS) | OpenAQ v3 ต้องใช้ API key จึงใช้ Open-Meteo แทน; เติมข้อมูลย้อนหลังให้กราฟแนวโน้ม |
| C | **aqicn.org** หน้า `/city/@<id>/` ของสถานีไทย | **Web scraping** ด้วย `requests` + `BeautifulSoup(lxml)` (ไม่มี JS/Selenium) | ~40 สถานี: US AQI ของ PM2.5 (`#cur_pm25`), เวลาอัปเดต, พิกัด → แปลง AQI เป็น µg/m³ ตาม breakpoint ของ US EPA | หน้า HTML static อ่านได้ด้วย requests; `robots.txt` = `User-agent: *` / `Disallow:` (อนุญาตทั้งหมด) |

**จริยธรรม / กฎหมาย**
- ตรวจ `robots.txt` อัตโนมัติด้วย `urllib.robotparser` ทุกครั้งก่อน scrape (ถ้าไม่อนุญาต task จะหยุดและบันทึก failed)
- ใส่ `User-Agent` ระบุตัวตน (`KU-02739452-AirQualityExam/1.0 (student 6621601077; ...)`) และ `sleep` ระหว่าง request (`SCRAPE_DELAY_SEC`, ค่าเริ่มต้น 1 วินาที) จำกัดจำนวนหน้า (`SCRAPE_MAX_PAGES`)
- **PDPA**: เก็บเฉพาะข้อมูลสถานีตรวจวัด (ชื่อสถานี/จังหวัด/พิกัด/ค่าฝุ่น) ไม่มีข้อมูลส่วนบุคคล
- ไม่มีรหัสผ่าน/API key ใน repo — ใช้ `.env` (ถูก ignore) และ `.env.example`

## สถาปัตยกรรม

```
                 ┌────────────── TaskGroup: extract (parallel) ───────────────┐
create_tables ──►│ extract_air4thai ───────► plan_openmeteo_batches            │
                 │                              └► extract_openmeteo.expand()  │  (Dynamic Task Mapping ต่อภูมิภาค)
                 │ scrape_aqicn                                                 │
                 └──────────────────────────────┬──────────────────────────────┘
                                                ▼  trigger_rule = none_failed_min_one_success
                                         transform_dedupe
                                                ▼
                                    quality_check (BranchPythonOperator)
                                     ├──► load_upsert       (INSERT ... ON CONFLICT DO UPDATE)
                                     └──► quarantine_alert  (data_quality_log + air_quality_quarantine)
                                                ▼  none_failed_min_one_success
                                              finish
```

| Service | Port | หน้าที่ |
|---|---|---|
| `postgres` (16) | 5433 (host, ตั้งด้วย `POSTGRES_HOST_PORT`) | DB `airflow` (metadata) + DB `airquality` (ข้อมูล) สร้างด้วย `postgres/init/` |
| `airflow-init` | – | `airflow db migrate` + สร้าง admin user |
| `airflow-webserver` | **8080** | Airflow UI |
| `airflow-scheduler` | – | LocalExecutor (รัน task) |
| `web` (Streamlit) | **8501** | Dashboard + หน้า Pipeline Status |

### ระดับที่ทำ
- **ระดับ 1** — 1 แหล่ง → DAG `air_quality_pipeline` (extract → transform → load) → PostgreSQL → เว็บตาราง + กราฟ
- **ระดับ 2** — 3 แหล่งใน `TaskGroup("extract")` รันขนาน; normalize เป็น schema เดียว (ชื่อสถานี/จังหวัด, เวลาเป็น Asia/Bangkok ปัดเป็นชั่วโมง, ค่าไม่ถูกต้อง เช่น `-1` หรือ นอกช่วง 0–1000 → `NULL`); **UPSERT**; เว็บมี KPI (จำนวนแถว, PM2.5 เฉลี่ย, สูงสุดพร้อมชื่อสถานี, จำนวนสถานี, เวลาข้อมูลล่าสุด) + ตัวกรอง (จังหวัด, แหล่ง, ช่วงวันที่, ช่วงค่า PM2.5) + กราฟแนวโน้ม, top 10, แผนที่
- **ระดับ 3** — แต่ละ extract จับ exception → เขียน `pipeline_runs(status='failed', error_message)` แล้ว raise `AirflowSkipException` (task = skipped ไม่ใช่ failed) → `transform_dedupe` ใช้ `trigger_rule=none_failed_min_one_success` จึงรวมจากแหล่งที่เหลือได้; ถ้า Air4Thai ล่ม Open-Meteo จะใช้รายการพิกัดสำรอง; **ตัดซ้ำข้ามแหล่ง** key = (lat,lon ปัด 3 ตำแหน่ง, observed_at) และ (station_id, observed_at) เลือกตาม priority **Air4Thai > Open-Meteo > aqicn** และบันทึกจำนวนที่ตัด; **quality check** (แถว ≥ `QUALITY_MIN_ROWS`, สัดส่วน null ≤ `QUALITY_MAX_NULL_RATIO`, pm25 ใน 0–1000, พิกัดอยู่ในกรอบประเทศไทย) → `BranchPythonOperator`
- **โบนัส** — Dynamic Task Mapping `extract_openmeteo.expand(batch=...)` แยกต่อภูมิภาค (north/northeast/central-n/east/south) + หน้าเว็บ **Pipeline Status** (อ่าน `pipeline_runs` และ `data_quality_log`)

### ตาราง (DB `airquality`)
- `air_quality(station_id, station_name, province, lat, lon, pm25, observed_at, source, ingested_at, PRIMARY KEY (station_id, observed_at))`
- `pipeline_runs(id, run_id, source, status, rows_fetched, error_message, detail, started_at, finished_at)`
- `data_quality_log(run_id, checked_at, passed, total_rows, duplicates_removed, null_pm25, out_of_range, out_of_thailand, sources_ok, reasons, action)`
- `air_quality_quarantine(run_id, reasons, row_count, sample JSONB)`

UPSERT จะไม่ให้แหล่ง priority ต่ำกว่าเขียนทับแถวของแหล่ง priority สูงกว่า (`ON CONFLICT ... DO UPDATE ... WHERE priority(EXCLUDED.source) <= priority(t.source)`)

## วิธีรัน

ต้องมี Docker Desktop (Compose v2) และอินเทอร์เน็ต

```bash
git clone https://github.com/Patcharadnaimingchua/02739452-18-6621601077.git && cd 02739452-18-6621601077
cp .env.example .env          # แก้รหัสผ่านใน .env ได้ (ถ้าไม่มี .env จะใช้ค่า default ใน compose)
docker compose up -d --build  # ครั้งแรก build image ~2-4 นาที
```

- Airflow UI: http://localhost:8080 (user/pass ตาม `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` ใน `.env`; ถ้าไม่ได้สร้าง `.env` คือ `admin` / `admin`)
- Dashboard: http://localhost:8501 (หน้า **Pipeline Status** อยู่ที่ sidebar)

DAG ถูก unpause อัตโนมัติและตั้ง `@hourly` — เมื่อ scheduler ขึ้นจะรันรอบแรกเองภายใน ~1 นาที (ใช้เวลารันประมาณ 1–1.5 นาที เพราะ scrape แบบ sleep 1 วินาที/หน้า) หรือ trigger เอง:

```bash
docker compose exec airflow-scheduler airflow dags trigger air_quality_pipeline
```

ตรวจผล:

```bash
docker compose exec postgres psql -U airflow -d airquality -c "SELECT source, COUNT(*) FROM air_quality GROUP BY 1"
docker compose exec postgres psql -U airflow -d airquality -c "SELECT run_id, source, status, rows_fetched, error_message FROM pipeline_runs ORDER BY id DESC LIMIT 15"
```

## วิธีทดสอบ

### 1) UPSERT — รันซ้ำแล้วจำนวนแถวไม่เพิ่ม
```bash
docker compose exec postgres psql -U airflow -d airquality -Atc "SELECT COUNT(*) FROM air_quality"
docker compose exec airflow-scheduler airflow dags trigger air_quality_pipeline -r upsert_1   # รอให้เสร็จ
docker compose exec postgres psql -U airflow -d airquality -Atc "SELECT COUNT(*) FROM air_quality"
docker compose exec airflow-scheduler airflow dags trigger air_quality_pipeline -r upsert_2   # รอให้เสร็จ
docker compose exec postgres psql -U airflow -d airquality -Atc "SELECT COUNT(*) FROM air_quality"
```
จำนวนแถวคงที่ (จะเพิ่มได้เฉพาะเมื่อแหล่งข้อมูลปล่อยชั่วโมงใหม่ออกมาระหว่างรอบ) — ผลจริงอยู่ที่ [evidence/upsert_test.txt](evidence/upsert_test.txt)

### 2) แหล่งข้อมูลล่ม
```bash
AIR4THAI_URL=https://air4thai.pcd.go.th/services/WRONG_URL_TEST.php docker compose up -d airflow-scheduler
docker compose exec airflow-scheduler airflow dags trigger air_quality_pipeline -r source_down_test
# ผล: extract_air4thai = skipped, pipeline_runs มี air4thai/failed + error, DAG = success, ข้อมูลจาก Open-Meteo + aqicn ถูกโหลด
docker compose up -d airflow-scheduler   # คืนค่าเดิม
```
ผลจริง: [evidence/source_down_test.txt](evidence/source_down_test.txt) (เปลี่ยน `OPENMETEO_URL` หรือ `AQICN_BASE_URL` ได้แบบเดียวกัน)

### 3) Quality check ไม่ผ่าน → quarantine
```bash
QUALITY_MIN_ROWS=100000 docker compose up -d airflow-scheduler
docker compose exec airflow-scheduler airflow dags trigger air_quality_pipeline -r quality_fail_test
# ผล: quality_check เลือก quarantine_alert, load_upsert = skipped, DAG = success, data_quality_log.passed = false
docker compose up -d airflow-scheduler
```
ผลจริง: [evidence/quality_fail_test.txt](evidence/quality_fail_test.txt)

### เริ่มใหม่จากศูนย์
```bash
docker compose down -v && docker compose up -d --build
```

## โครงสร้าง repo
```
dags/air_quality_pipeline.py   DAG หลัก
dags/aq_lib/sources.py         ตัวดึงข้อมูล 3 แหล่ง (API + scraping + robots.txt)
dags/aq_lib/transform.py       normalize, AQI→µg/m³, dedupe
dags/aq_lib/db.py              schema, UPSERT, pipeline_runs logging
dags/aq_lib/certs/             intermediate CA ของ Let's Encrypt (YR1/Root YR) — ดูหมายเหตุ
web/app.py                     Streamlit dashboard
web/pages/1_Pipeline_Status.py หน้า Pipeline Status
postgres/init/                 สร้าง DB airquality + ตาราง
docker-compose.yml, Dockerfile, requirements.txt, .env.example
evidence/                      ผลการทดสอบจริง
```

## หมายเหตุ
- `air4thai.pcd.go.th` ส่ง certificate chain ไม่ครบ (leaf ออกโดย Let's Encrypt YR1 แต่แนบ chain ของ Sectigo) ทำให้ Python verify ไม่ผ่าน จึงแนบ intermediate สาธารณะ YR1 + Root YR (cross-signed โดย ISRG Root X1 ที่อยู่ใน certifi) ไว้ใน `dags/aq_lib/certs/` — **ยังเปิดการตรวจสอบ TLS ตามปกติ** ไม่ได้ใช้ `verify=False`
- ข้อมูล Open-Meteo เป็นค่าจากแบบจำลอง (CAMS) ไม่ใช่ค่าวัดจริง จึงมี priority ต่ำกว่า Air4Thai; ค่าจาก aqicn แปลงกลับจาก US AQI จึงเป็นค่าประมาณ
