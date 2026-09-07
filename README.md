# Detail Ops — Voice AI Agent for Car Detailing

A phone agent that answers caller questions from your own documents and books, reschedules,
and cancels appointments — plus an admin dashboard to manage the knowledge base and the calendar.

```
Caller (phone)                     Admin (browser)
   Vapi voice call                    React + Tailwind
        │                                   │
        ▼                                   ▼
┌───────────────────── FastAPI backend ─────────────────────┐
│   RAG engine          Booking engine          Admin API   │
│   caller Q&A          book / move / cancel    CRUD ops    │
└───────────┬───────────────────┬───────────────────┬───────┘
            ▼                   ▼                   ▼
     pgvector (Neon)      ──── Postgres (Neon) ────
     doc embeddings       bookings, customers, docs
```

## Two rules the whole system is built around

1. **The agent answers only from retrieved context.** Empty retrieval means it says it does not
   know and offers a callback — it never guesses a price.
2. **The backend owns validation.** The LLM supplies arguments; it never supplies trust. Voice
   tools and the admin dashboard write through the *same* functions in
   [booking.py](backend/app/services/booking.py) — there is no second write path.

## Stack

| Layer | Choice | Cost |
|---|---|---|
| Backend | FastAPI + SQLAlchemy 2 | Render free tier |
| Database + vectors | Postgres + pgvector | Neon free tier |
| Embeddings | OpenAI `text-embedding-3-small` | ~cents for dozens of docs |
| Frontend | Vite + React + TS + Tailwind v4 | Cloudflare Pages free |
| Voice | Vapi tools → this API | per-minute |

Everything runs locally on SQLite with a deterministic hash embedder and no API keys, so you can
develop and test the full path offline.

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt   # macOS/Linux

cp .env.example .env        # defaults work as-is for local dev
python scripts_demo_data.py # seeds admin, services, a pricing doc, 6 bookings
python -m uvicorn app.main:app --reload
```

API at http://127.0.0.1:8000, interactive docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at http://localhost:5173 — Vite proxies `/api` to the backend, so no CORS setup in dev.
Sign in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env`
(defaults `admin@example.com` / `changeme`).

### Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

27 tests covering auth, chunking, booking validation (past times, business hours, double-booking,
per-market isolation), the voice tools, and the RAG contract — including that deleting a document
removes its embeddings, and that an empty knowledge base produces a refusal rather than a guess.

## The admin dashboard

- **Overview** — today / upcoming / weekly counts, bookings per market, next appointments.
- **Bookings** — grouped by day, filterable by date range, market, status, and detailer.
  Reschedule picks from real open slots; status changes go through the shared write path.
- **Knowledge** — drag-and-drop PDF/text upload. Each file is chunked with overlap, embedded, and
  stored in pgvector. Deleting a document removes its vector rows in the same transaction, so the
  agent cannot keep quoting withdrawn pricing.
- **Agent test** — ask a question against the exact endpoint the phone agent calls, and see the
  retrieved chunks and their scores. Use it to confirm what callers will actually hear.

Light and dark themes, persisted per browser, applied before first paint.

## Vapi tools

Point each Vapi tool at `POST {API}/api/vapi/<tool>` with header `X-Vapi-Secret: <VAPI_SECRET>`.

| Tool | Purpose |
|---|---|
| `ask` | Grounded answer to a caller question |
| `list_slots` | Open times for a market and day |
| `book_appointment` | Create a booking |
| `lookup_appointments` | Find a caller's active bookings by phone |
| `reschedule_appointment` | Move a booking |
| `cancel_appointment` | Cancel a booking |

Parameter schemas are in [vapi-tools.json](vapi-tools.json); they mirror
[schemas.py](backend/app/schemas.py) exactly. Invalid arguments come back as a 4xx with a
caller-safe message the agent can read aloud (`"That slot is already taken. Offer the caller
another time."`), rather than a stack trace.

## Deploying (free tier)

1. **Neon** — create a project, then run `CREATE EXTENSION IF NOT EXISTS vector;` (the app also
   does this on startup). Copy the connection string, changing the scheme to
   `postgresql+psycopg://`.
2. **Render** — the repo ships [render.yaml](backend/render.yaml). Set `DATABASE_URL`,
   `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `OPENAI_API_KEY`, and `CORS_ORIGINS` (your Pages URL).
   Note the free tier sleeps after inactivity — the first call after idle takes ~30s, which is too
   slow for a live phone call. Keep it warm with an uptime pinger, or move to the paid tier before
   taking real calls.
3. **Cloudflare Pages** — build command `npm run build`, output `dist`, root `frontend`. Set
   `VITE_API_BASE` to your Render URL. `public/_redirects` already handles SPA routing.
4. **Vapi** — create the six tools above pointing at your Render URL with the `X-Vapi-Secret`
   header, and give the assistant a system prompt telling it to call `ask` for any question about
   pricing, services, or policy rather than answering from its own knowledge.

## Layout

```
backend/
  app/
    main.py          app wiring, CORS, startup
    config.py        settings (env-driven)
    models.py        SQLAlchemy models; pgvector column, JSON fallback on SQLite
    schemas.py       one source of truth for request/response shapes
    security.py      bcrypt + JWT
    routers/         auth, documents, bookings, vapi
    services/
      booking.py     the only booking write path
      rag.py         retrieval + grounded answering
      embeddings.py  OpenAI or offline hash embedder
      chunking.py    overlapping chunks, PDF/text extraction
  tests/
frontend/
  src/
    pages/           Login, Dashboard, Bookings, Documents, Playground
    components/      Shell, modals, ui/ primitives
    context/         auth, theme
    lib/             api client, types, helpers
```

## Notes / what to change next

- Embeddings and completions are behind small interfaces (`get_embedder`, `_complete`), so
  swapping the model — Kimi K2, Claude, another provider — is a one-function change.
- The relevance floor lives on the embedder, not as a global constant, because the offline hash
  embedder and a real embedding model score in different ranges.
- Auth is a single admin with a JWT, sized for a small business. Add roles when there is a second
  kind of user, not before.
- Booking hours (8:00–18:00), slot step (30 min), and horizon (60 days) are constants at the top
  of `services/booking.py`. They are currently UTC — set them per market before launch if your
  markets span time zones.
