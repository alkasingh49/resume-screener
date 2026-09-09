# AI Resume Screening & Assessment Platform

A demo/POC for a Talent Acquisition team: upload a job description, get
structured requirements extracted by an LLM, bulk-upload resumes against it,
get every candidate parsed and scored with an explainable Fit verdict, and
generate a tailored technical assessment for shortlisted candidates.

```
JD upload → LLM extract → recruiter review/confirm
                                    │
                                    ▼
Resumes bulk upload → auto background pipeline (parse → RAG index → score)
                                    │
                                    ▼
     Screening Results dashboard (filter/sort/search/export)
                                    │
                                    ▼
        Assessment generation → interviewer/candidate export
```

**Stack:** Python 3.11+ · FastAPI + Uvicorn · Streamlit (multipage) ·
LangChain · Google Gemini (free tier) · ChromaDB · SQLite + SQLAlchemy 2.x ·
Pydantic v2. Every dependency is free/local - no paid services required.

Built in 10 phases; all complete. See [docs/BUILD_LOG.md](docs/BUILD_LOG.md)
for phase-by-phase build notes, what was tested and how, and every real bug
that testing caught along the way.

## Setup

**1. System dependencies** (for the OCR fallback on scanned PDFs/images):

```bash
sudo apt-get install tesseract-ocr poppler-utils
```

Everything else works without this - a missing binary surfaces as a clear
error, not a crash.

**2. Python environment:**

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
```

**3. Environment variables:**

```bash
cp .env.example .env
# edit .env and set GOOGLE_API_KEY - free at https://aistudio.google.com/apikey
```

The app works without a key (every LLM-dependent action fails cleanly with
a clear message rather than crashing), but you need one to see real
extraction/scoring/generation happen.

## Quick start

The fastest way to see the whole app working, no API key required:

```bash
make run-backend     # terminal 1 - FastAPI on :8000
make run-frontend     # terminal 2 - Streamlit on :8501
make seed             # terminal 3 - populate a confirmed JD, 4 scored
                       #              candidates, and a sample assessment
```

Open http://localhost:8501 and go straight to **Screening Results** (a
ranked table with Fit/Rating/scores for 4 candidates spanning Best/Medium/No
fit) and **Assessments** (a pre-generated 3-question technical assessment,
ready to export). `make seed` writes directly to the DB - no LLM calls, so
it works immediately. `make seed-reset` wipes and reseeds; `make seed` again
just adds a second copy.

## Full walkthrough (with a real API key)

This is the actual end-to-end flow, using the LLM for real:

1. **Job Descriptions** - upload a `.pdf`/`.docx`/`.txt`/`.rtf`/`.png`/`.jpg`
   JD file. It parses immediately (blocking): text extraction, then an LLM
   call to pull out job title, department, skills, experience range,
   responsibilities, qualifications. Review the extracted fields (edited
   ones get a ✏️ marker if you change them), then **Confirm** - this is
   the gate that makes a JD selectable for screening.
2. **Upload Resumes** - pick that confirmed JD, bulk-upload several resume
   files. Processing starts automatically in the background (no button to
   click) - each resume gets its own worker (bounded concurrency,
   configurable via `PIPELINE_MAX_WORKERS`): text extraction → LLM profile
   extraction → total experience computed from work-history dates → chunked
   and embedded into a per-JD Chroma collection (RAG) → LLM scoring grounded
   in retrieved evidence. Click **Refresh status** to watch resumes move to
   `DONE`. A bad file never aborts the batch - it's marked `FAILED` with a
   clear reason and the rest continue; **Retry** re-runs anything
   PENDING/FAILED.
3. **Screening Results** - pick the JD, get every scored candidate ranked
   by rating: Fit, Rating, Name, Email, Phone, Total/Relevant Experience,
   one column per must-have/good-to-have skill score, and the LLM's
   reasoning. Filter by Fit, search by name or skill, click a row for the
   full detail view (profile, scores, reason, resume text), export
   CSV/Excel.
4. **Assessments** - pick a scored candidate, choose how many
   Easy/Medium/Hard questions, generate. Questions are targeted at the
   overlap between the JD's requirements and that candidate's own resume,
   each tagged with the skill it tests and (for the interviewer) expected
   answer points. Export as interviewer Markdown/CSV, or a candidate-facing
   Markdown with the answer points and skill tags stripped.

## Architecture highlights

**Provider-agnostic LLM layer** (`backend/llm/`) - switching providers is a
`.env`-only change:

```bash
# .env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

No code elsewhere changes. `backend/llm/factory.py` is the only place
`LLM_PROVIDER`/`EMBEDDING_PROVIDER` are read; `backend/llm/providers/` is the
only place a provider SDK may be imported -
`make check-provider-isolation` enforces it in CI. `backend/llm/wrapper.py`
carries retry/backoff/caching/call-logging above the provider, so those
behaviours survive a swap; `backend/llm/structured.py` is the one place
every service asks for schema-validated output.

**JD and resume ingestion are deliberately separate** end-to-end - separate
routes, services, DB tables, prompts, Pydantic schemas. The only code shared
between them is `backend/utils/file_text.py` (a dumb file→text helper with
OCR fallback; it knows nothing about JDs or resumes).

**RAG** (`backend/services/vectorstore.py`) - each processed resume is
chunked and embedded into a Chroma collection scoped to its JD. Scoring
retrieves only the chunks relevant to each must-have skill, instead of
feeding the whole resume into the prompt.

**Background pipeline** (`backend/services/pipeline.py`) - resume upload
queues a bounded-concurrency worker pool (FastAPI `BackgroundTasks`, no
Celery/Redis - each worker owns its own DB session) that runs every
PENDING resume through parse → RAG index → score automatically.

**Fit is computed, never asked of the LLM** - `overall_rating` (0-100) comes
from the model; Fit (Best/Medium/No) is derived from it against
`FIT_THRESHOLD_BEST`/`FIT_THRESHOLD_MEDIUM` in config, so tuning the
cutoffs never touches a prompt.

**Caching** - every LLM call is cached (`llm_cache` table) keyed by content
hash + JD id + JD **version** + model name, so re-running the same
extraction/scoring/assessment is free, and editing a confirmed JD (which
bumps its version and marks existing screening results `STALE`) can never
silently reuse a cache entry computed against the old JD text.

## Configuration reference

All settings are read once, centrally, in `backend/core/config.py` - see
`.env.example` for the full list with defaults. The ones worth knowing:

| Key | What it controls |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | chat model for extraction/scoring/assessment generation |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | embedding model for RAG |
| `LLM_RPM_CAP` | requests/minute cap (rate limiter attached at model construction) |
| `FIT_THRESHOLD_BEST` / `FIT_THRESHOLD_MEDIUM` | overall_rating cutoffs for the Fit verdict |
| `PIPELINE_MAX_WORKERS` | bounded concurrency for the background parse+score pipeline |

## Testing

```bash
make test                       # full suite (118 tests)
make check-provider-isolation   # guards the LLM abstraction boundary
```

Tests run against a real temp SQLite DB and, wherever feasible, real
libraries doing real work (real PDF/DOCX/RTF parsing, real poppler
rendering, a real local Chroma collection with real chunking) - only the
actual network call to an LLM/embeddings provider is mocked, always at the
same narrow boundary each service exposes for exactly that purpose. See
[docs/BUILD_LOG.md](docs/BUILD_LOG.md) for what each phase's tests cover and
every real bug this approach caught (several only showed up once two
phases' code ran together in the same session - see the log's closing
note).

`tests/test_full_flow_integration.py` walks the entire product flow in one
test - JD confirm → resume upload (auto-pipeline) → screening results →
assessment generation - through the real HTTP routes, proving the phases
click together as a system.

## Project layout

```
backend/
  core/        config, logging, shared enums
  llm/         provider-agnostic LLM layer (factory/registry/providers/wrapper)
  api/v1/      FastAPI routes - jd, resumes, screening, assessments
  db/          SQLAlchemy models + session
  schemas/     Pydantic schemas (per flow: jd, resume, candidate, screening, assessment)
  services/    business logic (jd/, resume/, vectorstore, scoring, assessment, pipeline)
  prompts/     LLM prompts as .md files, loaded at runtime
  utils/       file_text (shared), dates, hashing, prompt_loader
frontend/
  pages/       the 4 Streamlit pages
  components/  shared UI pieces (flash messages, assessment export)
  services/    api_client.py - the only file that calls the backend over HTTP
data/          uploads, Chroma persistence, app.db (all gitignored)
scripts/       seed_demo.py, llm_smoke_test.py
tests/         one file per concern, mirrors backend/ structure
docs/          BUILD_LOG.md
```

## Known limitations

- **OCR quality** depends entirely on `tesseract-ocr`'s output on the
  scanned page - no confidence gating in this POC.
- **`.doc`** (legacy binary Word) is unsupported - no reliable pure-Python
  parser without a heavier system dependency; convert to `.docx`/PDF.
- **No auth / single-tenant** - this is a demo for one recruiter's local
  session, not a multi-user deployment.
- **SQLite, no migrations tool** - fine for a POC (`init_db()` just
  `create_all`s); a real deployment would want Alembic + a server DB.
- **Relevant Experience** is an LLM judgment call (which roles match the
  JD), not computed like Total Experience - it's inherently more subjective.

## Project phases

- [x] Phase 0 - Skeleton, config, logging, `/health`, Streamlit shell
- [x] Phase 1 - LLM abstraction layer (factory, registry, Gemini adapter, OpenAI stub)
- [x] Phase 2 - DB models + `file_text.py` OCR utility
- [x] Phase 3 - JD section end to end
- [x] Phase 4 - Resume section: bulk upload, per-file status
- [x] Phase 5 - Candidate profile extraction, computed total experience
- [x] Phase 6 - RAG: chunking, embeddings, per-JD Chroma collections
- [x] Phase 7 - Scoring pipeline with rate limiting, retries, caching
- [x] Phase 8 - Results dashboard: table, filters, detail, exports
- [x] Phase 9 - Assessment generation and export
- [x] Phase 10 - Polish: error handling, seed script, tests, demo walkthrough

Full notes on each phase: [docs/BUILD_LOG.md](docs/BUILD_LOG.md).
