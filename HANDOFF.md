# HANDOFF — Influencer Real Time Report

คู่มือย้ายไปทำต่อบนเครื่องใหม่ / ส่งต่อโปรเจกต์ (อัปเดต 2026-07)

> **เว็บที่รันจริง:** `https://exhibitiondashboard-production.up.railway.app` (ตั้งชื่อ subdomain ที่ Railway → Settings → Networking)
> ตั้งค่าที่ Railway เท่านั้น — ไม่มีในโค้ด · path ในระบบ: หน้าแรก `/` · รายงาน `/c/<รหัส>` · ลิงก์ลูกค้า `/v/<รหัส>`
>
> **การเข้าถึง:** ทุกหน้าทำงานต้อง login ที่ `/login` ด้วยบัญชีพนักงาน Wazzup
> (identity backend ตั้งได้ผ่าน env `WAZZUP_BASE_URL`, default `https://api.fareastfamelineddb.com`)
> · ลิงก์ลูกค้า `/v/<รหัส>` เปิดดูได้โดยไม่ต้อง login · API ฝั่งเขียน/สั่งงานตรวจ bearer token ที่เซิร์ฟเวอร์

---

## 1. โปรเจกต์นี้อยู่ที่ไหน

| ส่วน | ที่อยู่ | หมายเหตุ |
|---|---|---|
| โค้ด + config (รายชื่อ KOL ทุกแคมเปญ) | GitHub: `github.com/superoyo/exhibitiondashboard` | source of truth |
| เว็บที่รันจริง | Railway: `https://exhibitiondashboard-production.up.railway.app` (subdomain ตั้งได้ที่ Railway) | auto-deploy จาก GitHub `main` |
| ฐานข้อมูล | Railway Postgres plugin | inject `DATABASE_URL` ให้อัตโนมัติ |
| Secrets | Railway → Variables | `APIFY_TOKEN`, `ADMIN_KEY` |

> **โปรเจกต์ไม่ผูกกับเครื่อง/Claude account** — Claude Code เป็นแค่เครื่องมือ ใครโคลน repo ก็ทำต่อได้
> แต่ **GitHub (superoyo) + Railway ต้องเป็นบัญชีเดิม** ถึงจะคุมโค้ด+เว็บตัวเดิมได้

---

## 2. ต้อง backup ก่อนคืนเครื่องเก่า (ของพวกนี้ไม่ได้อยู่บน GitHub)

1. **ไฟล์ Excel ต้นฉบับ** (อยู่บน Desktop ของเครื่องเก่า ไม่ได้อยู่ใน repo):
   - `Process _PAO Super Perfume 2026.xlsx`
   - `Working Process.xlsx`
2. **ค่าใน `.env`** โดยเฉพาะ `APIFY_TOKEN`, `ADMIN_KEY`
   - กู้คืนได้จาก **Railway → Variables** ถ้าลืม backup
3. (ไม่จำเป็น) โฟลเดอร์ `_report_test/` = ไฟล์ทดลองตอนแรก ถูกแทนที่ด้วยระบบจริงแล้ว

---

## 3. ตั้งค่าบนเครื่องใหม่

```bash
# ต้องมี: git, Python 3.11, Node 20+ (pnpm ผ่าน corepack), Claude Code

git clone https://github.com/superoyo/exhibitiondashboard.git
cd exhibitiondashboard

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

corepack enable pnpm && pnpm install

# สร้าง .env (ดูค่าจาก Railway → Variables)
cat > .env <<'EOF'
APIFY_TOKEN=<เอาจาก Railway>
ADMIN_KEY=<เอาจาก Railway>
TZ=Asia/Bangkok
EOF

# รัน local (embedded Postgres — ไม่ต้องลง Postgres เอง)
python scripts/dev_db.py        # สตาร์ท DB + เขียน DATABASE_URL ลง .env
alembic upgrade head            # สร้างตาราง + seed รายชื่อ KOL
uvicorn app.main:app --reload   # API ที่ http://localhost:8000

# frontend (คนละ terminal) — ใช้ตัวนี้ตอนพัฒนา
pnpm dev                        # http://localhost:5173
```

> **frontend เป็น React SPA ที่ต้อง build** — FastAPI เสิร์ฟจาก `apps/web/dist`
> ถ้าเปิด `:8000` แล้วขึ้น 503 คือยังไม่ได้ build → `pnpm --filter @kol/web build`
> บน Railway มี `buildCommand` ใน `railway.json` รันให้อัตโนมัติแล้ว

- **GitHub push:** เครื่องใหม่ต้องล็อกอิน GitHub ด้วย **Personal Access Token** (Settings → Developer settings → Tokens, scope `repo`) ใส่เป็น password ตอน `git push`
- **Deploy:** `git push origin main` → Railway auto-deploy ~1–2 นาที · เช็คเวอร์ชันที่ `…/api/version`

---

## 4. หน้าเว็บ / โครงระบบ

| URL | คือ |
|---|---|
| `/` | รายงานแคมเปญ **Sahagroup** (Mega Kol + Micro-Nano Kol) |
| `/report` | รายงานแคมเปญ **PAO Super Perfume** |
| `/kols` | แก้ไขรายชื่อ KOL + ลิงก์โพสต์ (เลือกแคมเปญ Sahagroup/PAO/Tracker) |
| `/token` | ดู/เปลี่ยน Apify token (เปลี่ยน key ได้เลยไม่ต้อง deploy) |
| `/tracker` | dashboard live เดิม (KOL Tracker 7-day rolling) |

- **แคมเปญ** = field `campaign` (`pao`, `sahagroup`) บน `report_kols`/`report_posts`
- รายชื่อเริ่มต้น seed จาก `config/*.json` (seed ครั้งเดียวตอน DB ว่าง — แก้ผ่าน /kols แล้วไม่โดนทับ)
- **2 ปุ่มบนหน้ารายงาน:**
  - 🔄 **Refresh Data** — scrape ลิงก์โพสต์ของ KOL ที่ active (TikTok = postURLs, Facebook = FB actor) → อัปเดต stat
  - 🖼️ **ดึงรูปโปรไฟล์** — scrape โปรไฟล์ช่อง เอา avatar + followers (ไม่ต้องมีลิงก์โพสต์)
- ทุก refresh คิดเงิน Apify จริง → โชว์ **ยอดสะสมแยกแคมเปญ** ใต้ปุ่ม

---

## 5. สิ่งที่ควรรู้ / ข้อควรระวัง

- **ไม่มี auto-update** (ตั้งใจ) — อัปเดต stat เฉพาะตอนกดปุ่มเอง เพื่อคุมค่า Apify
- **Refresh คิดเงินเฉพาะแคมเปญที่กด** และเฉพาะ KOL ที่ติ๊ก active
- **Apify token หมด?** → ไปหน้า `/token` กดทดสอบ/เปลี่ยน key ใหม่ได้เลย
- เพิ่มแคมเปญใหม่: ทำ `config/<name>_kols.json` + seed function ใน `app/seed.py` + เพิ่ม nav (รูปแบบเดียวกับ sahagroup)
- DB migration: แก้ model แล้วเพิ่มไฟล์ใน `migrations/versions/` (รันอัตโนมัติตอน deploy ผ่าน `alembic upgrade head` ใน Procfile)

---

## 5.1 Deploy — ตอนนี้มีกี่ service

Railway มี service เดียว (`exhibitiondashboard`) รัน **Python** ซึ่งเสิร์ฟทั้ง API และหน้าเว็บ
`railway.json` + `nixpacks.toml` ที่ root เป็นของ service นี้

**Express (`@kol/api`) ยังไม่ได้ deploy** โค้ดพร้อมแล้วแต่ยังไม่มีใครเรียกใช้จริง

### ทำไม Express ยังเอามาแทน Python ตรง ๆ ไม่ได้

`apps/api/src/app.ts` mount ไว้แค่ `/api` เท่านั้น — **ไม่มี** static asset, ไม่มี SPA
fallback, ไม่มี `/v/<token>`, ไม่มี inject OG/`window.__CAMPAIGN__`
(`env.webDistPath` คำนวณไว้แต่ยังไม่มีใครใช้) ถ้าชี้โดเมนมาที่ Express ตอนนี้
`/` `/login` `/report` `/v/...` `/assets/*` จะ 404 ทั้งหมด เหลือแค่ `/api`

และถึงย้ายได้ ตอนนี้ก็ยังไม่ได้อะไร เพราะ Express พอร์ต native แค่ campaigns + roster
ที่เหลือ proxy กลับไป Python อยู่ดี — ได้ hop เพิ่มมาหนึ่งชั้นโดยที่ Python ก็ยังต้องอยู่

### ถ้าจะ deploy Express เป็น service ที่สอง

ใช้ `railway.api.json` (มีในรีโปแล้ว) — ตั้งใน Railway → service ใหม่ → Settings:

| ตั้งค่า | ค่า |
|---|---|
| Config-as-code path | `railway.api.json` |
| Root Directory | ปล่อยว่าง (build จาก repo root — pnpm workspace ต้องเห็น lockfile) |

Variables ที่ต้องใส่:

| ตัวแปร | ค่า |
|---|---|
| `DATABASE_URL` | ตัวเดียวกับ service Python |
| `PYTHON_SERVICE_URL` | URL ของ service Python (endpoint ที่ยังไม่พอร์ตจะ proxy ไปที่นี่) |
| `NODE_ENV` | `production` |
| `TZ` | `Asia/Bangkok` — load-bearing ดู `apps/api/src/utils/dates.ts` |
| `ADMIN_KEY` / `APIFY_TOKEN` | ตามค่าเดิม |

⚠️ **กับดัก:** `Procfile` ที่ root เขียนว่า `alembic upgrade head && uvicorn app.main:app …`
Nixpacks อ่านไฟล์นี้เป็น start command ถ้า `railway.api.json` ไม่ override
`startCommand` service ใหม่จะไป**รัน migration แล้วสตาร์ต Python** แทน Express
`railway.api.json` override ไว้ให้แล้ว — และ **service นี้ต้องไม่รัน alembic**
เจ้าของ schema คือฝั่ง Python ที่เดียว

---

## 6. โครงไฟล์ย่อ

```
app/
  main.py            เสิร์ฟ SPA (apps/web/dist) + inject OG/__CAMPAIGN__ + startup seed
  api/routes.py      REST API (roster, report data, refresh, profiles, token)
  models.py          ตาราง DB (SQLAlchemy) — เป็นเจ้าของ schema
  report_refresh.py  scrape logic (posts / facebook / profiles) + cost
  apify_client.py    เรียก Apify actor
  pptx_report.py     สร้าง PowerPoint (python-pptx) — คงไว้เป็น Python
  tiein.py           AI tie-in shot (ffmpeg + Claude) — คงไว้เป็น Python
apps/web/src/
  features/          auth · campaigns · report · roster · tracker · settings
  components/ui/     shadcn/ui primitives
  lib/               axios (แนบ token) · format · colors · echarts · platforms
  app/router.tsx     route ทั้งหมด — /v/... ต้องอยู่นอก RequireAuth
apps/api/src/
  routes/ controllers/ services/ repositories/ middleware/ config/ models/
  middleware/openPaths.ts   allowlist ว่า endpoint ไหนไม่ต้อง login (ห้ามแก้เผิน ๆ)
  middleware/pythonProxy.ts endpoint ที่ยังไม่ย้าย → ส่งต่อไป Python
packages/shared/     types + zod schemas ใช้ร่วมกันสองฝั่ง
config/              รายชื่อ KOL ตั้งต้นแต่ละแคมเปญ (.json)
frontend/            หน้าเดิม (fallback เท่านั้น — ลบได้เมื่อ deploy ใหม่ผ่านแล้ว)
migrations/          alembic
```

**⚠️ จุดที่ห้ามแก้เผิน ๆ** (มีเหตุผลอยู่ ดู `MIGRATION_PLAN.md` §6)

- `_serve_shell()` ใน `app/main.py` ฝัง `<title>`/OG **ที่ server** เพราะ crawler ของ
  LINE/Messenger ไม่รัน JS — ถ้าเอาออก ลิงก์ที่แชร์จะไม่มี preview
- `/v/<token>` ต้องได้ `window.__CAMPAIGN__` จาก server และเปิดได้**โดยไม่ต้อง login**
- สูตร ER: มี views → eng/views · ไม่มี views แต่มี followers → eng/followers ใส่ `*` ·
  ไม่มีทั้งสอง → `—` (ห้ามโชว์ 0.00%)
- `apps/api/middleware/openPaths.ts` = allowlist auth — ผิดทางไหนก็แย่ทั้งคู่
  (เข้มเกิน = ลิงก์ลูกค้าพัง · หลวมเกิน = API หลุด). เช็คด้วย `pnpm --filter @kol/api verify:auth`
- **Alembic เป็นเจ้าของ schema** — Drizzle ใช้ query เท่านั้น ห้ามรัน `drizzle-kit push`
  เช็คว่าตรงกันด้วย `pnpm --filter @kol/api verify:schema`
