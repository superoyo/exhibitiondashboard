# HANDOFF — KOL Campaign Report (Sahagroup KOL Hub)

คู่มือย้ายไปทำต่อบนเครื่องใหม่ / ส่งต่อโปรเจกต์ (อัปเดต 2026-06)

---

## 1. โปรเจกต์นี้อยู่ที่ไหน

| ส่วน | ที่อยู่ | หมายเหตุ |
|---|---|---|
| โค้ด + config (รายชื่อ KOL ทุกแคมเปญ) | GitHub: `github.com/superoyo/exhibitiondashboard` | source of truth |
| เว็บที่รันจริง | Railway: `https://exhibitiondashboard-production.up.railway.app` | auto-deploy จาก GitHub `main` |
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
# ต้องมี: git, Python 3.11, Claude Code (ล็อกอิน Claude account ไหนก็ได้)

git clone https://github.com/superoyo/exhibitiondashboard.git
cd exhibitiondashboard

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# สร้าง .env (ดูค่าจาก Railway → Variables)
cat > .env <<'EOF'
APIFY_TOKEN=<เอาจาก Railway>
ADMIN_KEY=<เอาจาก Railway>
TZ=Asia/Bangkok
EOF

# รัน local (embedded Postgres — ไม่ต้องลง Postgres เอง)
python scripts/dev_db.py        # สตาร์ท DB + เขียน DATABASE_URL ลง .env
alembic upgrade head            # สร้างตาราง + seed รายชื่อ KOL
uvicorn app.main:app --reload   # เปิด http://localhost:8000
```

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

## 6. โครงไฟล์ย่อ

```
app/
  main.py            routes หน้าเว็บ + startup seed
  api/routes.py      REST API (roster, report data, refresh, profiles, token)
  models.py          ตาราง DB (SQLAlchemy)
  report_refresh.py  scrape logic (posts / facebook / profiles) + cost
  apify_client.py    เรียก Apify actor
  seed.py            seed รายชื่อจาก config/
  settings.py        token (DB→env) + ยอด cost สะสม
config/              รายชื่อ KOL ตั้งต้นแต่ละแคมเปญ (.json)
frontend/            report.html (รายงาน) · kols.html (แก้ไข) · token.html · index.html (tracker)
migrations/          alembic
```
