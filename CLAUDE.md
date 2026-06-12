# Red Elk — Backend Agent Reference

## What this is
FastAPI backend for an AI maturity assessment platform. Organisations take scored assessments and receive radar chart reports with tiered recommendations. Frontend is a separate React/Vite repo; this is REST API only.

---

## Stack
| Layer | Choice |
|---|---|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 async (`Mapped[T]` / `mapped_column`) |
| DB | PostgreSQL on Supabase (direct connection) |
| Migrations | Alembic |
| Schemas | Pydantic v2 |
| Auth | Supabase JWT verification only — we never issue tokens |
| PDF | WeasyPrint → Cloudinary |
| Deploy | Railway + `nixpacks.toml` (needs libpango for WeasyPrint) — DB hosted on Supabase, not Railway |

---

## Folder structure
```
app/
├── main.py            # app init, CORS, router registration
├── db.py              # re-exports get_db, engine from core/database.py
├── dependencies.py    # get_current_user (Supabase JWT), get_current_admin
├── core/
│   ├── config.py      # Settings (pydantic-settings), all env vars
│   └── database.py    # async engine + session factory + get_db()
├── models/models.py   # all 5 SQLAlchemy models (single file)
├── schemas/schemas.py # all Pydantic request/response schemas (single file)
├── routers/
│   ├── auth.py        # POST /auth/register, GET /auth/me
│   ├── assessments.py # GET /assessments, GET /assessments/{slug}
│   ├── sessions.py    # POST /sessions/start, /{id}/answer, /{id}/submit, GET /sessions
│   ├── reports.py     # GET /reports/{session_id}, GET /reports/{session_id}/pdf
│   └── admin.py       # GET /admin/sessions, GET /admin/analytics
├── services/
│   ├── scoring.py     # PURE FUNCTIONS ONLY — no DB, no imports from models
│   ├── report_builder.py  # DB-aware: fetches responses, calls scoring, writes Report row
│   └── pdf.py         # WeasyPrint render → Cloudinary upload → return URL
├── templates/
│   └── report.html    # Jinja2 template for PDF
assessments/
└── ai-maturity-v1.json  # assessment config — seeded to DB on startup
```

---

## Environment variables (`.env`)
```
DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD]@db.tjjbiekkcfxsrzwonppd.supabase.co:5432/postgres   # async SQLAlchemy
DIRECT_URL=postgresql://postgres:[PASSWORD]@db.tjjbiekkcfxsrzwonppd.supabase.co:5432/postgres              # Alembic migrations only
SUPABASE_URL=https://tjjbiekkcfxsrzwonppd.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...      # backend only, never exposed to frontend
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```
# Note: DATABASE_URL uses +asyncpg for async SQLAlchemy
# Use DIRECT_URL for Alembic migrations (set in alembic/env.py)

---

## Database — 5 tables

```
users              id (UUID, mirrors Supabase auth.users.id), email, tier, company, role, created_at
assessments        id, slug (unique), name, description, config (JSONB), is_published, version
assessment_sessions id, user_id→users, assessment_id→assessments, status, tier_at_time, started_at, completed_at
responses          id, session_id→assessment_sessions, question_id (str), dimension_id (str), answer_value, answered_at
reports            id, session_id→assessment_sessions (unique), scores (JSONB), overall_score, tier_result, pdf_url, generated_at
```

**Key design decisions:**
- All assessment config (dimensions, questions, scoring thresholds, recommendations) is in `assessments.config` JSONB — no separate dimensions/questions tables.
- `responses` has one row per answer (not a JSON blob), enabling per-question analytics.
- `tier_at_time` is snapshotted on session start — a tier upgrade mid-session does not affect scoring.
- Enums: `TierEnum(free, basic, premium)`, `SessionStatus(in_progress, completed, abandoned)`.

---

## Auth pattern

Supabase handles all login/signup. Backend only verifies JWTs.

```python
# app/dependencies.py
async def get_current_user(credentials, db) -> User:
    sb_user = _get_supabase().auth.get_user(token)   # raises on invalid
    user = await db.get(User, UUID(sb_user.id))
    if not user:
        user = User(id=..., email=..., tier=free)    # auto-create on first login
        db.add(user); await db.commit()
    return user
```

Supabase client is lazy-initialised (`@lru_cache`) — server starts even if `SUPABASE_URL` is not set; fails only at first authenticated request.

`get_current_admin` wraps `get_current_user` and checks `user.role == "admin"`. Role is set directly in DB (no endpoint — manual or via Supabase dashboard).

---

## Tier gating

| Tier | Questions per dimension |
|---|---|
| free | 2 (first 2 with `tier == "free"`) |
| basic | 4 (first 4 with `tier in [free, basic]`) |
| premium | all |

Applied at **serve time** in `GET /assessments/{slug}` and at **scoring time** in `scoring.py`. Both use `_TIER_ORDER = {free:0, basic:1, premium:2}` and `_TIER_LIMITS = {free:2, basic:4, premium:None}`.

---

## Scoring service (`app/services/scoring.py`)

**Constraint: no DB access, no SQLAlchemy imports.** Pure Python only — unit testable in isolation.

```python
def score_responses(responses: list[dict], config: dict, tier: str) -> ScoringResult
```

- `responses`: `[{"question_id", "dimension_id", "answer_value"}, ...]`
- `config`: assessment config dict (from `assessments.config` JSONB)
- `tier`: value of `session.tier_at_time`

**Algorithm:**
1. Filter questions accessible at tier
2. Per question: `score = answer_value / max_score * 100` (scale type)
3. Per dimension: `dim_score = mean(question_scores)`
4. Overall: `weighted_avg(dim_scores, weights)` using `dimension.weight`
5. Classify: compare overall to `config.scoring.thresholds`
6. Recommendations: `config.scoring.recommendations[dim_id][tier_result]`

**Output `ScoringResult` fields:** `dimension_scores`, `dimension_names`, `overall_score`, `tier_result`, `recommendations`

**Tier results:** `nascent` (0–30) → `developing` (30–55) → `maturing` (55–75) → `leading` (75–100)

---

## Assessment JSON config format

File: `assessments/{slug}.json` — seeded to DB on startup, upserted by slug.

```json
{
  "slug": "ai-maturity-v1",
  "name": "...",
  "description": "...",
  "version": 1,
  "is_published": true,
  "dimensions": [
    {
      "id": "strategy",
      "name": "Strategy & Vision",
      "weight": 0.25,
      "questions": [
        { "id": "s1", "text": "...", "tier": "free", "type": "scale", "max_score": 5 },
        { "id": "s2", "text": "...", "tier": "free",    "type": "scale", "max_score": 5 },
        { "id": "s3", "text": "...", "tier": "basic",   "type": "scale", "max_score": 5 },
        { "id": "s4", "text": "...", "tier": "basic",   "type": "scale", "max_score": 5 },
        { "id": "s5", "text": "...", "tier": "premium", "type": "scale", "max_score": 5 }
      ]
    }
  ],
  "scoring": {
    "thresholds": { "nascent": [0,30], "developing": [30,55], "maturing": [55,75], "leading": [75,100] },
    "recommendations": {
      "strategy": { "nascent": "...", "developing": "...", "maturing": "...", "leading": "..." }
    }
  }
}
```

**To add a new assessment:** use `POST /admin/assessments/from-xlsx` to upload an XLSX file. No code changes or restarts needed.

---

## Session lifecycle

```
POST /sessions/start         → creates AssessmentSession (status=in_progress, snapshots tier)
POST /sessions/{id}/answer   → upserts Response row (idempotent: re-submitting overwrites)
POST /sessions/{id}/submit   → sets status=completed, calls report_builder.build_report()
                               kicks off _generate_pdf_background() as asyncio.create_task()
GET  /reports/{session_id}   → returns ReportOut (scores, tier_result, recommendations, radar_data)
GET  /reports/{session_id}/pdf → redirects 302 to Cloudinary PDF URL; generates on demand if missing
```

PDF generation failure is swallowed silently — it must not break the submit flow.

---

## API routes summary

```
POST /auth/register      # sync local user record (company field) — JWT required
GET  /auth/me            # current user profile + maturity_summary (latest completed report: overall_score, tier_result, radar_data; null if none)

GET  /assessments        # list published assessments
GET  /assessments/{slug} # assessment with questions filtered by user tier

POST /sessions/start              body: {assessment_slug}
POST /sessions/{id}/answer        body: {question_id, dimension_id, answer_value}
POST /sessions/{id}/submit
GET  /sessions                    # each session includes: score + tier_result + dimension_scores (completed, from report; else null), progress_pct (in_progress only)

GET  /reports/{session_id}        # includes previous_radar_data (prior completed session of same assessment, or null)
GET  /reports/{session_id}/pdf    # 302 to Cloudinary; generates on demand; 502 if generation fails

GET  /admin/sessions              ?limit=50&offset=0
GET  /admin/analytics
GET  /admin/users
PATCH /admin/users/{user_id}/role     body: {role: "admin"|"user"}
POST /admin/assessments/from-xlsx     multipart: file=<xlsx>, slug?, name?, description?, publish?
```

All endpoints except `/health` and `/` require a valid Supabase Bearer token.

---

## Running locally

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Set up DB (Railway URL or local postgres)
# Add DATABASE_URL + SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to .env

# 3. Run migrations
alembic upgrade head

# 4. Start server (seeds assessments on startup)
uvicorn app.main:app --reload
```

Server starts even without `SUPABASE_URL` — Supabase client is lazy. First auth request will fail if not configured.

---

## Migrations

New Alembic migration chain:
1. `0ede583bc5bd` — original schema
2. `5658704f7c4c` — NOT NULL constraints
3. `a1b2c3d4e5f6` — **drops all old tables**, creates 5 new tables (current schema)

When changing the schema: add a new migration file, never edit existing ones.

---

## Out of scope (do not add)
- Stripe / payments (tier upgrades are manual DB edits)
- Email delivery
- LLM-generated recommendations
- Company-level dashboards
- Mobile

## Claude Instructions
- Always follow the layered architecture: routers → services → DB
- scoring.py must stay pure — no DB imports, ever
- Never add Stripe, email, or LLM recommendations (out of scope)
- Run `alembic upgrade head` and confirm no migration errors after schema changes
- After any endpoint change, check it against the API routes summary below