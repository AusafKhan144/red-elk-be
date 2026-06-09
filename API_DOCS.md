# Red Elk API — Frontend Reference

> **Base URL:** `https://<your-railway-domain>` (or `http://localhost:8000` locally)

---

## Important concepts before you start

### Subscription tier vs. Maturity level — do not confuse these

There are two completely different things that use similar words in this app:

| Concept | Values | What it means |
|---|---|---|
| **Subscription tier** | `free`, `basic`, `premium` | The plan the user is paying for. Controls how many questions they see per dimension. Stored on the user account. |
| **Maturity level** | `nascent`, `developing`, `maturing`, `leading` | The result of scoring the completed assessment. A rating of how mature the organisation's AI capability is. Has nothing to do with the subscription. |

In the API responses, the field `tier_at_time` always refers to the **subscription tier**. The field `tier_result` inside a report is the **maturity level** — treat it as "maturity_level" or "ai_maturity" in your UI labels.

---

## Authentication

Every endpoint (except `GET /` and `GET /health`) requires a Supabase JWT in the `Authorization` header.

```
Authorization: Bearer <supabase_access_token>
```

The token comes from Supabase Auth on the frontend side. The backend only verifies it — it does not issue tokens.

**On first login:** Calling any authenticated endpoint auto-creates the user row in the database. You do not need to call `/auth/register` to create the account — only to attach a company name.

### Error responses

All errors follow this shape:
```json
{ "detail": "Human-readable error message" }
```

Common HTTP status codes:
- `401` — missing or invalid JWT
- `403` — valid JWT but not allowed (e.g. accessing another user's session, or non-admin hitting an admin route)
- `404` — resource not found
- `409` — conflict (e.g. trying to answer questions on a session that is already completed)
- `422` — request body validation failed

---

## Auth endpoints

### `POST /auth/register`

Call this once after the user signs up (via Supabase) to save their company name to our database. You do **not** need this call just to log in — you only need it if you want to store the company field.

**Request body:**
```json
{
  "company": "Acme Corp"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company` | string or null | No | The user's company name. Can be omitted to leave it unset. |

**Response: `UserProfile`**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "tier": "free",
  "company": "Acme Corp",
  "role": "user",
  "created_at": "2024-01-15T10:30:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | The user's unique ID (same as their Supabase Auth user ID) |
| `email` | string | The user's email address |
| `tier` | `"free"` \| `"basic"` \| `"premium"` | **Subscription tier** — controls how many assessment questions they can see |
| `company` | string or null | Company name, if set |
| `role` | `"user"` \| `"admin"` | Admin role is set manually in the DB — do not expose this to regular users |
| `created_at` | ISO 8601 datetime string | When the account was created |

---

### `GET /auth/me`

Returns the currently logged-in user's profile. Use this on app load to know the user's subscription tier and role.

**No request body.**

**Response: `UserProfile`** — same shape as above.

---

### `PATCH /auth/me`

Update the current user's profile. Use this to let users change their company name from a profile/settings page.

**Request body:**
```json
{
  "company": "New Company Name"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company` | string or null | No | The new company name. Pass `null` to clear it. If omitted, nothing changes. |

**Response: `UserProfile`** — the updated profile.

---

## Assessment endpoints

Assessments are the questionnaires users take. Each assessment has multiple dimensions (topic areas), and each dimension has questions. The number of questions shown per dimension depends on the user's **subscription tier**.

### `GET /assessments`

Returns a list of all published assessments. Use this to show a "pick an assessment" screen.

**No request body.**

**Response: array of `AssessmentListItem`**
```json
[
  {
    "id": "a1b2c3d4-...",
    "slug": "ai-maturity-v1",
    "name": "AI Maturity Assessment",
    "description": "Evaluate your organisation's AI capability across key dimensions.",
    "version": 1
  }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Unique ID of the assessment |
| `slug` | string | URL-friendly identifier, e.g. `"ai-maturity-v1"`. Use this to load the full assessment. |
| `name` | string | Display name of the assessment |
| `description` | string or null | Short description to show users before they start |
| `version` | integer | Version number — increments when an admin updates the assessment |

---

### `GET /assessments/{slug}`

Loads the full assessment including all questions the user is allowed to see (filtered by their subscription tier). Call this before starting a session so you can render the questions.

**URL parameter:** `slug` — the slug from the list endpoint (e.g. `ai-maturity-v1`)

**No request body.**

**Response: `AssessmentOut`**
```json
{
  "id": "a1b2c3d4-...",
  "slug": "ai-maturity-v1",
  "name": "AI Maturity Assessment",
  "description": "Evaluate your organisation's AI capability across key dimensions.",
  "version": 1,
  "dimensions": [
    {
      "id": "strategy",
      "name": "Strategy & Vision",
      "weight": 0.25,
      "questions": [
        {
          "id": "s1",
          "text": "Does your organisation have a documented AI strategy?",
          "tier": "free",
          "type": "scale",
          "options": null,
          "max_score": 5
        }
      ]
    }
  ]
}
```

**Top-level fields:**

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Assessment ID |
| `slug` | string | URL-friendly identifier |
| `name` | string | Display name |
| `description` | string or null | Short description |
| `version` | integer | Version number |
| `dimensions` | array | List of topic areas — each contains questions |

**`DimensionOut` fields (each item in `dimensions`):**

| Field | Type | Description |
|---|---|---|
| `id` | string | Dimension identifier, e.g. `"strategy"`, `"data"`, `"culture"` |
| `name` | string | Human-readable dimension name to display, e.g. `"Strategy & Vision"` |
| `weight` | float | How much this dimension contributes to the overall score (used by the backend, you don't need to use this directly) |
| `questions` | array | The questions the user must answer — already filtered to only the ones their subscription allows |

**`QuestionOut` fields (each item in `questions`):**

| Field | Type | Description |
|---|---|---|
| `id` | string | Question identifier, e.g. `"s1"`. You must send this back when submitting answers. |
| `text` | string | The question text to display to the user |
| `tier` | `"free"` \| `"basic"` \| `"premium"` | Which **subscription tier** this question belongs to. This is metadata — the backend already filtered the list for you, so you don't need to filter again. Just render all questions returned. |
| `type` | `"scale"` \| `"boolean"` \| `"multiple_choice"` \| `"text"` | Question type — determines what kind of input to render (see below) |
| `options` | object or null | Extra data for `multiple_choice` questions. For `scale` and `boolean` questions this is null. |
| `max_score` | float | For `scale` questions: the highest number the user can enter (e.g. `5` means the scale is 1–5). Not relevant for other types. |

**Question types — what to render:**

| `type` value | What to show | What value to send |
|---|---|---|
| `"scale"` | A slider or 1-to-N radio buttons, where N is `max_score` | A number, e.g. `3` for "3 out of 5" |
| `"boolean"` | A Yes/No toggle | `1` for Yes, `0` for No |
| `"multiple_choice"` | A set of radio/select options from `options.choices` | The index of the chosen option (0-based integer, sent as a float) |
| `"text"` | A text area | `1` if the user typed something, `0` if they left it blank |

---

## Session endpoints

A session represents one attempt at an assessment by one user. You must start a session, then submit answers, then submit the session to trigger scoring.

### `POST /sessions/start`

Creates a new session. Call this when the user clicks "Start Assessment". Returns a session ID that you'll use for all subsequent answer submissions.

**Important:** The user's current subscription tier is **locked in** at session start. If their subscription changes mid-session, scoring still uses the tier they had when they started.

**Request body:**
```json
{
  "assessment_slug": "ai-maturity-v1"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `assessment_slug` | string | Yes | The slug of the assessment to start (from `GET /assessments`) |

**Response: `SessionOut`** (HTTP 201)
```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "assessment_id": "a1b2c3d4-...",
  "status": "in_progress",
  "tier_at_time": "basic",
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": null,
  "assessment_name": null,
  "assessment_slug": null
}
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | **Save this.** You need the session ID to submit answers and to submit the session. |
| `assessment_id` | UUID string | The assessment being taken |
| `status` | `"in_progress"` \| `"completed"` \| `"abandoned"` | Current state. Will be `"in_progress"` immediately after starting. |
| `tier_at_time` | `"free"` \| `"basic"` \| `"premium"` | The user's **subscription tier** locked in at the moment they started the session |
| `started_at` | ISO 8601 datetime string | When the session was started |
| `completed_at` | ISO 8601 datetime string or null | Null until the session is submitted |
| `assessment_name` | string or null | Human-readable assessment name. Populated in `GET /sessions` list; null when returned from `POST /sessions/start`. |
| `assessment_slug` | string or null | Assessment slug. Populated in `GET /sessions` list; null when returned from `POST /sessions/start`. |

---

### `POST /sessions/{session_id}/answer`

Submit one question's answer. Safe to call multiple times for the same question — the latest answer overwrites the previous one. Call this for each question as the user fills them in (or batch them before submit — either works).

**URL parameter:** `session_id` — the UUID from `POST /sessions/start`

**Request body:**
```json
{
  "question_id": "s1",
  "dimension_id": "strategy",
  "answer_value": 3
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `question_id` | string | Yes | The `id` of the question being answered (from the questions list in `GET /assessments/{slug}`) |
| `dimension_id` | string | Yes | The `id` of the dimension this question belongs to (from the `DimensionOut` that contains this question) |
| `answer_value` | float | Yes | The user's answer. See question types above for what values to send. |

**Response:**
```json
{ "ok": true }
```

**Errors:**
- `409` if the session is already completed or abandoned — you cannot add answers after submitting.

---

### `GET /sessions/{session_id}/answers`

Fetch all saved answers for a session. Use this to restore in-progress quiz state when the user returns to an unfinished session (e.g. after closing and reopening the browser tab).

**URL parameter:** `session_id` — the UUID from `POST /sessions/start`

**No request body.**

**Response: array of `AnswerOut`**
```json
[
  {
    "question_id": "s1",
    "dimension_id": "strategy",
    "answer_value": 3.0
  },
  {
    "question_id": "s2",
    "dimension_id": "strategy",
    "answer_value": 5.0
  }
]
```

Returns `[]` if no answers have been saved yet.

| Field | Type | Description |
|---|---|---|
| `question_id` | string | The question that was answered |
| `dimension_id` | string | The dimension the question belongs to |
| `answer_value` | float | The saved answer value |

**Errors:**
- `403` if the session belongs to a different user
- `404` if the session does not exist

---

### `POST /sessions/{session_id}/submit`

Mark the session as complete and trigger scoring. Call this when the user clicks "Submit". After this, the report is generated and you can fetch it with `GET /reports/{session_id}`.

**URL parameter:** `session_id` — the UUID from `POST /sessions/start`

**No request body.**

**Response:**
```json
{
  "ok": true,
  "report_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
}
```

| Field | Type | Description |
|---|---|---|
| `ok` | boolean | Always `true` on success |
| `report_id` | UUID string | The ID of the generated report. You can also use the session ID to fetch the report via `GET /reports/{session_id}`. |

**Errors:**
- `409` if the session is already completed or abandoned.

**Note on PDF:** After submission, PDF generation runs in the background. The `GET /reports/{session_id}` endpoint returns immediately with scores — you do not need to wait for the PDF.

---

### `PATCH /sessions/{session_id}/abandon`

Mark an in-progress session as abandoned. Use this when the user explicitly wants to discard their current attempt (e.g. a "Start Over" button). Once abandoned, the session cannot receive new answers or be submitted.

**URL parameter:** `session_id` — the UUID from `POST /sessions/start`

**No request body.**

**Response:**
```json
{ "ok": true }
```

**Errors:**
- `403` if the session belongs to a different user
- `404` if the session does not exist
- `409` if the session is already completed or abandoned

---

### `GET /sessions`

Returns all sessions for the currently logged-in user, newest first. Use this to show a "your past attempts" screen. The `assessment_name` and `assessment_slug` fields are populated in this response so you can display human-readable names without extra API calls.

**No request body.**

**Response: array of `SessionOut`**

Same shape as the single `SessionOut` above, but with `assessment_name` and `assessment_slug` filled in. An empty array `[]` means the user has not started any sessions yet.

---

## Report endpoints

Reports contain the scored results of a completed session.

### `GET /reports/{session_id}`

Fetch the full scored report for a completed session. Use this to render the results page with the radar chart and recommendations.

**URL parameter:** `session_id` — the UUID of the session (not the report ID)

**No request body.**

**Response: `ReportOut`**
```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "scores": {
    "strategy": 72.5,
    "data": 45.0,
    "culture": 60.0,
    "technology": 55.0,
    "governance": 38.0
  },
  "overall_score": 54.1,
  "tier_result": "developing",
  "recommendations": {
    "strategy": "Focus on formalising your AI roadmap with measurable milestones...",
    "data": "Invest in centralised data infrastructure before scaling AI initiatives...",
    "culture": "Run cross-functional AI literacy workshops to build shared understanding...",
    "technology": "Evaluate existing ML tooling and identify gaps before new procurement...",
    "governance": "Establish an AI ethics framework and assign clear ownership..."
  },
  "radar_data": [
    { "dimension": "strategy", "score": 72.5, "label": "Strategy & Vision" },
    { "dimension": "data", "score": 45.0, "label": "Data Readiness" },
    { "dimension": "culture", "score": 60.0, "label": "Culture & People" },
    { "dimension": "technology", "score": 55.0, "label": "Technology" },
    { "dimension": "governance", "score": 38.0, "label": "Governance & Ethics" }
  ],
  "pdf_url": "https://res.cloudinary.com/...",
  "generated_at": "2024-01-15T10:35:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Report ID |
| `session_id` | UUID string | The session this report belongs to |
| `scores` | object | Per-dimension scores. Keys are dimension IDs (e.g. `"strategy"`), values are floats from 0 to 100. |
| `overall_score` | float | Overall weighted score from 0 to 100. This is what determines the maturity level. |
| `tier_result` | `"nascent"` \| `"developing"` \| `"maturing"` \| `"leading"` | **AI maturity level** of the organisation. This is NOT a subscription tier — it is the output of scoring the assessment. Display this prominently as the headline result. See maturity level table below. |
| `recommendations` | object | Per-dimension recommendation text. Keys are dimension IDs, values are the recommendation string to display. |
| `radar_data` | array | Pre-formatted data for rendering a radar/spider chart. Each item is one dimension. |
| `pdf_url` | string or null | URL to the generated PDF report on Cloudinary. May be `null` if background PDF generation hasn't finished yet — poll once or show a "download not ready" state and try again. |
| `generated_at` | ISO 8601 datetime string | When the report was generated |

**`RadarPoint` fields (each item in `radar_data`):**

| Field | Type | Description |
|---|---|---|
| `dimension` | string | Dimension ID (e.g. `"strategy"`) — matches a key in `scores` and `recommendations` |
| `score` | float | Score for this dimension, 0–100 |
| `label` | string | Human-readable dimension name for chart labels (e.g. `"Strategy & Vision"`) |

**AI maturity levels (`tier_result`) — display guide:**

| Value | Score range | What to show the user |
|---|---|---|
| `"nascent"` | 0–30 | "Nascent" — early stage, foundational work needed |
| `"developing"` | 30–55 | "Developing" — building capabilities, some gaps remain |
| `"maturing"` | 55–75 | "Maturing" — solid foundations, optimising and scaling |
| `"leading"` | 75–100 | "Leading" — advanced, competitive AI capability |

**Errors:**
- `404` if the session does not exist, or if the report hasn't been generated yet (the user hasn't submitted the session yet).

---

### `GET /reports/{session_id}/pdf`

Redirects (HTTP 302) to the Cloudinary PDF URL. Use this as the href on a "Download PDF" button — the browser will follow the redirect to the file.

**URL parameter:** `session_id` — the UUID of the session

**No request body.**

**Response:** HTTP 302 redirect to the PDF URL. If the PDF is not yet generated, this endpoint generates it on-demand before redirecting (may take a few seconds).

**Errors:**
- `404` if the session doesn't exist or the report hasn't been generated yet.

---

## Admin endpoints

These endpoints require the user to have `role: "admin"`. Regular users will receive a `403` error. Do not show these screens to regular users.

---

### `GET /admin/sessions`

Lists all sessions across all users, newest first. Supports pagination.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `50` | How many sessions to return (max 200) |
| `offset` | integer | `0` | How many sessions to skip (for pagination) |

**Response: array of `AdminSessionOut`**
```json
[
  {
    "id": "f47ac10b-...",
    "user_id": "550e8400-...",
    "assessment_id": "a1b2c3d4-...",
    "status": "completed",
    "tier_at_time": "basic",
    "started_at": "2024-01-15T10:30:00Z",
    "completed_at": "2024-01-15T10:45:00Z"
  }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Session ID |
| `user_id` | UUID string | The user who took this session |
| `assessment_id` | UUID string | Which assessment was taken |
| `status` | `"in_progress"` \| `"completed"` \| `"abandoned"` | Session state |
| `tier_at_time` | `"free"` \| `"basic"` \| `"premium"` | **Subscription tier** the user had when they started this session |
| `started_at` | ISO 8601 datetime string | Session start time |
| `completed_at` | ISO 8601 datetime string or null | Session completion time, null if not yet completed |

---

### `GET /admin/sessions/export`

Downloads all sessions as a CSV file. Use this for external analysis in spreadsheet tools or BI platforms. Returns all sessions with no pagination.

**No request body.**

**Response:** `Content-Type: text/csv` with `Content-Disposition: attachment; filename="sessions.csv"`

Columns: `session_id`, `user_id`, `assessment_id`, `status`, `tier_at_time`, `started_at`, `completed_at`

---

### `GET /admin/analytics`

Platform-wide aggregate statistics. Use this for an admin dashboard. Supports optional date range filtering — if omitted, returns all-time data.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `from` | ISO 8601 datetime string | No | Filter sessions started on or after this datetime. If omitted, no lower bound. |
| `to` | ISO 8601 datetime string | No | Filter sessions started on or before this datetime. If omitted, no upper bound. |

**Example:** `GET /admin/analytics?from=2024-01-01T00:00:00Z&to=2024-01-31T23:59:59Z`

**Response: `AnalyticsOut`**
```json
{
  "total_sessions": 152,
  "completed_sessions": 94,
  "sessions_by_tier": {
    "free": 80,
    "basic": 50,
    "premium": 22
  },
  "avg_overall_score": 57.3,
  "dimensions": [
    {
      "dimension_id": "strategy",
      "dimension_name": "Strategy & Vision",
      "avg_score": 61.4
    },
    {
      "dimension_id": "data",
      "dimension_name": "Data Readiness",
      "avg_score": 48.9
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `total_sessions` | integer | Total number of sessions started in the filtered range |
| `completed_sessions` | integer | Number of completed sessions in the filtered range |
| `sessions_by_tier` | object | Breakdown of **total** sessions grouped by subscription tier. Keys: `"free"`, `"basic"`, `"premium"`. Values: integer counts. |
| `avg_overall_score` | float or null | Average overall score across completed sessions in the range. `null` if no completed sessions. |
| `dimensions` | array | Per-dimension average answer values across completed sessions in the range |

**`DimensionAnalytics` fields (each item in `dimensions`):**

| Field | Type | Description |
|---|---|---|
| `dimension_id` | string | Dimension identifier |
| `dimension_name` | string | Human-readable dimension name |
| `avg_score` | float | Average raw answer value for this dimension across completed sessions in the range |

---

### `GET /admin/users`

Lists all registered users, newest first.

**No request body.**

**Response: array of `UserProfile`**

Same shape as the `UserProfile` response from `GET /auth/me`. Includes all users on the platform.

---

### `GET /admin/users/export`

Downloads all users as a CSV file.

**No request body.**

**Response:** `Content-Type: text/csv` with `Content-Disposition: attachment; filename="users.csv"`

Columns: `user_id`, `email`, `company`, `tier`, `role`, `created_at`

---

### `GET /admin/users/{user_id}/sessions`

Returns the full session history for a specific user. Use this on a user detail page when an admin drills in from the users table.

**URL parameter:** `user_id` — UUID of the user

**No request body.**

**Response: array of `AdminSessionOut`** — same shape as `GET /admin/sessions`. Returns `[]` if the user has no sessions.

**Errors:**
- `404` if the user does not exist

---

### `PATCH /admin/users/{user_id}/role`

Change a user's role to `admin` or back to `user`. Admins cannot change their own role.

**URL parameter:** `user_id` — UUID of the user to update

**Request body:**
```json
{
  "role": "admin"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `role` | `"admin"` \| `"user"` | Yes | The new role to assign |

**Response: `UserProfile`** — the updated user's profile.

**Errors:**
- `400` if `role` is not `"admin"` or `"user"`
- `400` if you try to change your own role
- `404` if the user doesn't exist

---

### `PATCH /admin/users/{user_id}/tier`

Change a user's subscription tier. Admins cannot change their own tier.

**URL parameter:** `user_id` — UUID of the user to update

**Request body:**
```json
{
  "tier": "premium"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `tier` | `"free"` \| `"basic"` \| `"premium"` | Yes | The new subscription tier to assign |

**Response: `UserProfile`** — the updated user's profile.

**Errors:**
- `400` if you try to change your own tier
- `404` if the user doesn't exist

---

### `POST /admin/assessments/from-xlsx`

Upload an Excel file to create or update an assessment. Use this to add new assessments without touching code.

If an assessment with the same slug already exists, it is **updated** (version number incremented). Otherwise a new one is created.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file (.xlsx or .xlsm) | Yes | The Excel file containing the assessment questions |
| `slug` | string | No | URL-friendly identifier for this assessment (e.g. `"ai-maturity-v2"`). If omitted, derived from the filename. |
| `name` | string | No | Display name. If omitted, derived from the filename. |
| `description` | string | No | Short description shown before users start. Defaults to empty string. |
| `publish` | boolean | No | If `true`, the assessment is immediately visible to users. Defaults to `false` (draft). |

**Response: `AssessmentImportOut`**
```json
{
  "id": "a1b2c3d4-...",
  "slug": "ai-maturity-v2",
  "name": "AI Maturity Assessment v2",
  "version": 1,
  "is_published": false
}
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Assessment ID |
| `slug` | string | The slug assigned to this assessment |
| `name` | string | Display name |
| `version` | integer | Version number (starts at 1, increments on each update) |
| `is_published` | boolean | Whether this assessment is visible to regular users |

**Errors:**
- `400` if the uploaded file is not an Excel file
- `422` if the Excel file cannot be parsed into a valid assessment format

---

## Typical frontend user flow

```
1. User logs in via Supabase Auth (frontend handles this)
2. Call GET /auth/me  →  get user profile (tier, role)
3. Call GET /assessments  →  show list of available assessments
4. User picks one → Call GET /assessments/{slug}  →  get questions (filtered by their tier)
5. Call POST /sessions/start  →  get session_id, save it
   5a. (On page load for an existing in-progress session) Call GET /sessions/{id}/answers
       →  pre-populate answers state, jump to first unanswered question
6. User answers each question → Call POST /sessions/{id}/answer for each answer
7. User clicks Submit → Call POST /sessions/{id}/submit
   OR User clicks Abandon → Call PATCH /sessions/{id}/abandon
8. Navigate to results page → Call GET /reports/{session_id}
9. Display overall_score, tier_result (maturity level), radar_data chart, recommendations
10. If user wants PDF → link to GET /reports/{session_id}/pdf
11. Profile page → Call PATCH /auth/me to update company name
```
