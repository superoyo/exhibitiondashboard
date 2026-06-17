# KOL TikTok Tracker — Sahagroup Fair 2026

เว็บ dashboard ที่ **ดึงข้อมูล TikTok ของ KOL อัตโนมัติทุกเช้า 05:00 น. (เวลาไทย)** ผ่าน Apify
เก็บลง Postgres แล้วแสดง KPI / กราฟ / ตาราง พร้อมแนวโน้มย้อนหลัง (trend) และ delta เทียบเมื่อวาน

- **Stack:** Python 3.11 · FastAPI · SQLAlchemy + Alembic · PostgreSQL · httpx · ECharts + Tailwind (single-file SPA)
- **Data source:** Apify actor [`clockworks/tiktok-scraper`](https://apify.com/clockworks/tiktok-scraper)
- **Deploy:** Railway (web service + cron service + Postgres plugin)

---

## โครงสร้าง

```
app/            FastAPI app, scraper job, models, aggregation, API
config/kols.json  ลิสต์ KOL (แก้ที่นี่ ไม่ต้องแตะโค้ด)
migrations/     Alembic
frontend/index.html  dashboard (เสิร์ฟจาก FastAPI ที่ /)
scripts/        seed + dev helpers
```

---

## ค่าใช้จ่าย (Apify)

41 โปรไฟล์ × 20 โพสต์ + date filter ≈ **~255 โพสต์ ≈ $1 ต่อการรัน 1 ครั้ง**
รันทุกวัน ≈ **~$30 / เดือน** (แปรผันตามจำนวนโพสต์จริง). คุม cost ได้ที่
`RESULTS_PER_PAGE` และ `LOOKBACK_DAYS` ใน `app/config.py`.

---

## รันในเครื่อง (Local)

ต้องมี PostgreSQL. ถ้าไม่มี ใช้ embedded Postgres (`pgserver`, ไม่ต้องลง system):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt          # รวม pgserver สำหรับ dev

cp .env.example .env                          # ใส่ APIFY_TOKEN, ADMIN_KEY, DATABASE_URL
alembic upgrade head                          # สร้างตาราง
python scripts/seed_kols.py                   # seed KOL 41 ราย

python -m app.scrape                          # ดึงข้อมูลจริง 1 ครั้ง (~$1)
uvicorn app.main:app --reload                 # เปิด http://localhost:8000
```

> ถ้าใช้ `pgserver` ดูสคริปต์ `scripts/dev_db.py` (สร้าง/รัน embedded Postgres + พิมพ์ DATABASE_URL).

---

## Deploy บน Railway

1. push repo ขึ้น **GitHub**
2. Railway → **New Project → Deploy from GitHub repo**
3. เพิ่ม **PostgreSQL** plugin (Railway inject `DATABASE_URL` ให้อัตโนมัติ)
4. **Service `web`**:
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Pre-deploy Command** (Settings → Deploy): `alembic upgrade head`
     (รัน migration อัตโนมัติทุกครั้งที่ deploy — วิธีที่ Railway แนะนำ)
5. รัน seed ครั้งแรก (Railway shell หรือ one-off command): `python scripts/seed_kols.py`
6. **Service `cron-scrape`** (จาก repo เดียวกัน) →
   - Start Command: `python -m app.scrape`
   - **Cron Schedule: `0 22 * * *`**
     > ⚠️ Railway cron เป็น **UTC**. `0 22 * * * UTC = 05:00 Asia/Bangkok` (UTC+7). อย่าแก้เป็น `0 5 * * *`.
7. **Variables** (ทั้งสอง service):
   ```
   APIFY_TOKEN   = <Apify token ของคุณ>
   ADMIN_KEY     = <secret ยาว ๆ สำหรับ trigger /api/scrape/run>
   TZ            = Asia/Bangkok
   # ALERT_WEBHOOK_URL = <optional: Slack webhook แจ้งเตือน scrape fail>
   ```
   `DATABASE_URL` มาจาก Postgres plugin อัตโนมัติ — ไม่ต้องตั้งเอง
8. (แนะนำ) เก็บข้อมูลวันแรกเลย:
   ```bash
   curl -X POST https://<your-app>.up.railway.app/api/scrape/run -H "X-ADMIN-KEY: <ADMIN_KEY>"
   ```
   แล้วเปิดหน้าเว็บตรวจสอบ

> 🔒 `APIFY_TOKEN` และ secret ทั้งหมดอยู่ใน Railway Variables เท่านั้น — **ห้าม commit `.env`**

---

## แก้รายชื่อ KOL

แก้ `config/kols.json` (เพิ่ม/ลบ/เปลี่ยนกลุ่ม) — `username` ต้องตรงกับ handle หลัง `@` บน TikTok —
แล้วรัน `python scripts/seed_kols.py` อีกครั้ง.
KOL ที่ถูกลบออกจากไฟล์จะถูกตั้ง `active=false` (เก็บประวัติไว้ ไม่ลบทิ้ง).

กลุ่มคอนเทนต์: `Fashion` · `Food` · `Beauty` · `Household Items`.

---

## API

| Endpoint | คืน |
|---|---|
| `GET /api/health` | สถานะ + วันที่ scrape ล่าสุด + ผลรันล่าสุด |
| `GET /api/summary?date=latest&group=all` | KPI + delta เทียบเมื่อวาน + สรุปต่อ KOL |
| `GET /api/kols/{username}` | รายละเอียด KOL + trend + โพสต์ |
| `GET /api/posts?date=latest&group=&sort=views` | รายโพสต์ filter/sort |
| `GET /api/trend?metric=views&group=all&days=30` | time-series (`metric`: views/engagement/likes/followers/posts) |
| `POST /api/scrape/run` | trigger เอง (header `X-ADMIN-KEY: <ADMIN_KEY>`) |

---

## หมายเหตุข้อมูล

- ตัวเลข (view/like/…) เป็น **snapshot ณ เวลาที่ดึง** — เปลี่ยนได้ตลอด เว็บระบุ "ข้อมูล ณ <วันที่>"
- โพสต์/สรุปนับเฉพาะ **7 วันล่าสุด** ของแต่ละรอบ
- KOL ที่ไม่มีโพสต์ใน 7 วัน → แสดงเป็น 0 (ยังเก็บ followers ถ้าดึงได้)
- เก็บข้อมูลแบบ **idempotent**: รันซ้ำวันเดียวกันไม่เกิด record ซ้ำ (upsert ตาม unique keys)
