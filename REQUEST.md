# Backend requests — Landing & Login redesign

_Generated while implementing the Atlas-direction Landing Page and Login screens._

## TL;DR

**No new endpoints are required to ship these two screens.** Both work end-to-end against the existing
API. The items below are **optional, non-blocking UX enhancements** — the frontend currently renders the
relevant content statically and will continue to do so until/unless these land.

---

## What already covers these screens (no change needed)

**Login** reuses the existing auth surface — nothing new required:
- `POST /auth/register` `{ company }` — called after Supabase `signUp` (register mode).
- `GET /auth/me` — loads the profile after sign-in.
- Password reset is handled entirely by Supabase (`supabase.auth.resetPasswordForEmail`) → existing
  `/reset-password` route. No backend endpoint needed.

**Landing page** is pre-auth marketing — it calls no API at all.

---

## Optional enhancements (nice-to-have, ranked)

### 1. `GET /public/stats` — live hero / social-proof numbers
**Why:** The hero stat tiles and section copy currently use neutral, non-numeric labels because we did not
want to publish unverifiable hard claims (e.g. "208+ enterprises"). A small public stats endpoint would let
us show *real* figures credibly.

**Shape (suggested):**
```jsonc
GET /public/stats
{
  "enterprises_count": 208,        // distinct orgs that completed an assessment
  "dimensions_count": 6,           // capability dimensions in the framework
  "avg_sector_score": 61.8,        // mean overall maturity across the pool
  "updated_at": "2026-06-01T00:00:00Z"
}
```
- Unauthenticated, cacheable (e.g. 1h). No PII.

### 2. `GET /public/benchmarks` — drive the Benchmarks teaser from real data
**Why:** The "you vs sector avg" bars on the landing page are currently illustrative. A public per-dimension
sector-average payload would make the teaser reflect the actual benchmark pool.

**Shape (suggested):**
```jsonc
GET /public/benchmarks
{
  "dimensions": [
    { "label": "Strategy & Vision",     "sector_avg": 64 },
    { "label": "Technology & Tooling",  "sector_avg": 62 },
    { "label": "Data & Infrastructure", "sector_avg": 58 },
    { "label": "Adoption & Culture",    "sector_avg": 57 },
    { "label": "Talent & Skills",       "sector_avg": 55 },
    { "label": "Governance & Risk",     "sector_avg": 51 }
  ],
  "updated_at": "2026-06-01T00:00:00Z"
}
```
- Unauthenticated, cacheable. Aggregate-only (no per-org data).

### 3. `POST /contact` (a.k.a. `/enterprise-inquiry`) — wire the Enterprise CTA
**Why:** The Pricing section's Enterprise plan has a "Contact sales" button. Today it just routes to the
login page. A lead-capture endpoint would let it open a real inquiry form instead.

**Shape (suggested):**
```jsonc
POST /contact
{ "name": "...", "email": "...", "company": "...", "message": "..." }
→ 202 Accepted
```
- Unauthenticated; needs spam protection (rate limit / captcha). Out of scope for the current pass — only
  build if we decide to add a real contact form. (Note: email/payment logic is explicitly out of scope per
  the frontend CLAUDE.md, so this would be lead capture only, not billing.)

---

## Not requested / out of scope
- No Stripe / billing endpoints — pricing CTAs only navigate to signup; tier upgrades are out of scope.
- No newsletter / analytics-event endpoints for the landing page at this time.

---

---

# Backend requests — Dashboard, Quiz, Report, Sessions redesign

_Generated while implementing the Atlas-direction authenticated app screens (Dashboard, Quiz, Report, Sessions)._

## TL;DR

All four screens ship against the **existing API** with no blocking gaps. The items below are **non-blocking enhancements** that would unlock specific features in the new UI that currently render as empty states or with limited data.

---

## What the redesigned screens use (no change needed)

- `GET /assessments` — available assessments list (Dashboard)
- `GET /assessments/:slug` — questions + dimensions (Quiz)
- `GET /sessions` — session list with `assessment_name`, `assessment_slug` (Dashboard, Sessions)
- `POST /sessions/start` — start session (AssessmentIntro)
- `POST /sessions/:id/answer` — answer submission (Quiz)
- `POST /sessions/:id/submit` — session completion (Quiz)
- `GET /sessions/:id/answers` — restore quiz state on resume (Quiz)
- `GET /reports/:sessionId` — scored report + radar data + recommendations + pdf_url (Report, Dashboard)
- `GET /auth/me` — user profile + tier (Dashboard metric card)

---

## Blockers (required to unlock features that currently show empty states)

### 1. `Session.score` field — surface overall score on Sessions cards

**Why:** The redesigned Sessions page shows a compact card per completed session. Ideally it shows the final overall score. Today `GET /sessions` returns no score — the frontend would need to fire `GET /reports/:id` per session (N+1) to retrieve it.

**Requested change:** Add `score: number | null` and `tier_result: string | null` to the `Session` object in `GET /sessions`.

**Suggested shape (diff from current):**
```jsonc
// GET /sessions → Session[]
{
  "id": "...",
  "assessment_id": "...",
  "assessment_name": "Enterprise AI Maturity",
  "assessment_slug": "enterprise-ai-maturity",
  "status": "completed",
  "tier_at_time": "basic",
  "started_at": "...",
  "completed_at": "...",
  "score": 71,          // ← new: overall_score from the linked report, null if no report yet
  "tier_result": "maturing" // ← new: tier_result from the linked report, null if no report yet
}
```
- Populated via a JOIN on the `reports` table; null if the session is still in_progress or the report hasn't been generated.
- No breaking change — both fields default to `null`.

---

## Optional enhancements (nice-to-have, ranked)

### 2. `GET /reports/:sessionId` — include `previous_radar_data`

**Why:** The Report page design shows a dashed overlay on the radar chart for the *previous* assessment of the same type. This requires knowing the prior session's dimension scores. Today the report only has `radar_data` for the current session.

**Suggested addition:**
```jsonc
// GET /reports/:sessionId
{
  "radar_data": [...],
  "previous_radar_data": [          // ← new: radar_data from the previous completed session of the same assessment, or null
    { "dimension": "strategy", "label": "Strategy & Vision", "score": 63 },
    ...
  ] | null
}
```
- Lookup: the most recent completed session *before* the current one for the same `assessment_id` and `user_id`.
- If no prior session exists → `null`.

### 3. `GET /sessions` — include `dimension_scores` per completed session

**Why:** The Sessions design shows a mini radar per session card. Currently per-session dimension scores are only available by calling `GET /reports/:id` for each session individually (N+1). An inline `dimension_scores` array on the session list would allow the mini radars without extra requests.

**Suggested addition:**
```jsonc
// GET /sessions → Session (completed only)
{
  "dimension_scores": [             // ← new: null for in_progress sessions
    { "dimension": "strategy", "label": "Strategy & Vision", "score": 78 },
    ...
  ] | null
}
```
- Can be omitted for in_progress sessions (set to `null`).

### 4. `GET /auth/me` — include `maturity_summary`

**Why:** The Dashboard hero always fetches the most recent completed session's report to display the overall maturity score + dimension bars. This requires two requests on every dashboard load (`GET /sessions` → find latest → `GET /reports/:id`). A summary on the user profile would reduce this to one.

**Suggested addition:**
```jsonc
// GET /auth/me
{
  "id": "...",
  "email": "...",
  "role": "...",
  "tier": "...",
  "maturity_summary": {             // ← new: null if user has no completed sessions
    "overall_score": 71,
    "tier_result": "maturing",
    "radar_data": [...],
    "as_of_session_id": "...",
    "as_of_date": "2025-03-12T..."
  } | null
}
```
- Derived from the most recent completed session's report for this user.
- Cached (can be invalidated when a new report is generated for this user).

### 5. `GET /sessions` — include `progress_pct` for in_progress sessions

**Why:** The Dashboard "Continue" card and Sessions in-progress banner would show a real progress bar instead of a hardcoded `35%` placeholder.

**Suggested addition:**
```jsonc
// GET /sessions → Session (in_progress only)
{
  "progress_pct": 42    // ← new: (answers submitted / total questions) * 100, rounded; null for completed
}
```

---

## Not requested / out of scope
- No Stripe / billing endpoints — tier upgrades remain out of scope.
- No sector benchmark endpoint (benchmarks feature is not yet in the app screens).
