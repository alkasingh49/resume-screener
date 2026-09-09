# Build log

Phase-by-phase notes on what was verified at the end of each phase - how it
was tested, and every real bug that testing caught along the way (with what
was wrong and how it was fixed). Kept as a historical record; the top-level
[README.md](../README.md) has the current setup/run/demo instructions.

## Phase 0 - Skeleton

FastAPI `/health`, config, logging, Streamlit shell with a backend-health
check button. Verified: booted both processes for real, hit `/health`
directly and through the Streamlit button, ran `pytest`.

## Phase 1 - LLM abstraction layer

`backend/llm/`: `factory.py` (`get_chat_model()`/`get_embeddings()`),
`registry.py` (provider name → adapter), `providers/gemini.py` +
`providers/openai.py` (stub, proves the abstraction), `structured.py`
(native `with_structured_output()` first, `PydanticOutputParser` fallback),
`wrapper.py` (retry/backoff, cache, call logging).

Design note: rather than subclassing `BaseChatModel` to wrap it, retry/cache/
logging live in a function (`run_with_resilience`) that `structured.py`
calls around the model invocation, while rate limiting is attached at
construction time via LangChain's native `rate_limiter` support. A full
subclass wrapper would have broken `bind_tools()`/native structured-output
delegation to the underlying provider.

Verified: 15 tests (provider switching, unknown-provider errors, retry-then-
succeed, cache hit/miss, native vs. fallback structured-output paths - all
without a real network call). `make check-provider-isolation` (provider SDK
imports may only live in `backend/llm/providers/`) - verified it both passes
cleanly and correctly fails on an injected violation. Ran
`scripts/llm_smoke_test.py` against the real `ChatGoogleGenerativeAI`
construction path - reached Google's client and failed on missing
credentials as expected (no key set), confirming the wiring is live.

## Phase 2 - DB models + `file_text.py`

7 SQLAlchemy tables (`job_descriptions`, `resumes`, `candidates`,
`screening_results`, `assessments`, `llm_call_logs`, `llm_cache`) via
`backend/db/session.py:init_db()` (`create_all`, no migrations tool for this
POC). `backend/utils/file_text.py`: the one function shared between the JD
and resume flows - PDF (native + **per-page** OCR fallback when a page's
native text is too sparse), DOCX, TXT, RTF, PNG/JPG (always OCR). `.doc`
(legacy binary Word) is deliberately unsupported - no reliable pure-Python
parser without a heavier system dependency.

Verified: 9 tests against real generated fixtures in `tests/fixtures/` (a
real native-text PDF, DOCX with a table, TXT, RTF, a real "scanned" PDF/PNG
with no text layer). The scanned-PDF/image paths use **real** poppler
rendering (`pdf2image`) with only the OCR text recognition mocked, since
`tesseract-ocr` isn't installed in this sandbox (no passwordless sudo) - a
dedicated test confirms a missing binary is wrapped in a clear
`FileTextExtractionError`, not a raw traceback. `test_db_models.py` persists
a full JD→Resume→Candidate→ScreeningResult/Assessment chain into a real
temp SQLite DB and reads it back, and confirms a bad FK raises
`IntegrityError`. Booted the real backend - all 7 tables created correctly
at startup.

## Phase 3 - JD section end to end

Upload (blocking - parses immediately), review/edit (✏️ marks
recruiter-edited fields), confirm (requires job title + ≥1 must-have skill),
re-parse, soft-delete. Editing an already-**CONFIRMED** JD bumps its
`version` and marks existing `CURRENT` screening results `STALE`
immediately - not deferred to a second "confirm" click.

Verified: `test_jd_routes.py` covers the whole lifecycle against a real temp
DB and real text extraction (LLM mocked). Also drove the real backend +
a real (credential-less) LLM call end to end via curl, and rendered the
actual Streamlit page headlessly with `AppTest`.

**Bug caught:** `st.success(...)` called immediately before `st.rerun()`
never reached the user - the rerun discards the message before it's shown.
Fixed with a session-state "flash message" pattern
(`frontend/components/flash.py`, shared across pages) that survives the
rerun.

## Phase 4 - Resume section: bulk upload, per-file status

JD selection required (no CONFIRMED JD → no upload). Bulk upload; one bad
file is stored and marked `FAILED` with a clear reason, never aborting the
batch. At this point resumes just sit at `PENDING`/`FAILED` - no automatic
progression yet (that's Phase 7).

Verified: `test_resume_routes.py` covers JD-must-be-confirmed,
JD-must-exist, and a real mixed-batch upload (2 good files + 1 `.doc`).
Drove the real backend via curl, rendered both pages headlessly with
`AppTest`.

**Bugs caught:**
- `use_container_width=True` is deprecated in the installed Streamlit
  (1.63) - switched to `width="stretch"` across both pages.
- The Phase 3-4 test suite had been silently writing real files into this
  repo's `data/uploads/` on every run (only `DATABASE_URL` was
  test-isolated). Fixed `tests/conftest.py`'s `isolated_db` fixture to also
  redirect `UPLOAD_DIR_JDS`/`UPLOAD_DIR_RESUMES`/`CHROMA_DIR` at a temp dir.

## Phase 5 - Candidate profile extraction, computed total experience

LLM extraction of name/email/phone/location/title/company/skills/education/
work_history/certifications. **Total experience is computed from
work_history dates** (`backend/utils/dates.py`) - merging
overlapping/concurrent roles so they aren't double-counted - falling back to
the LLM's own estimate only when no date is parseable
(`total_experience_source` records which happened). A manual "Process
pending now" button stood in for the not-yet-built background pipeline.

Verified: `tests/test_dates.py` - 12 unmocked cases (multiple formats,
overlapping/concurrent roles, ongoing roles, unparseable/malformed entries).
`tests/test_resume_processing.py` against a real temp DB and real text
extraction, LLM mocked. Live-verified real docx extraction, the LLM call
reached and failing cleanly on missing credentials (not a 500),
retry-after-failure working.

## Phase 6 - RAG: chunking, embeddings, per-JD Chroma collections

`backend/services/vectorstore.py`: `RecursiveCharacterTextSplitter`
(800 chars / 100 overlap), one Chroma collection per JD, chunks tagged with
`resume_id`. Wired into `process_resume()` - a resume only reaches
`SCORING` once its chunks are indexed; an indexing failure fails the resume
like an extraction failure does.

Verified: `tests/test_vectorstore.py` (9 tests) against a **real** local
Chroma collection and real chunking - only the embedding model is faked,
with a small deterministic *keyword-count* embedding (not random) so
similarity search stays meaningful: querying "Python" against a resume with
both a Python-heavy and a hobbies section genuinely ranks the Python chunk
first. Covers per-resume/per-JD scoping and that reprocessing replaces old
chunks rather than duplicating them.

**Bug caught:** the Candidate row was originally written *before* the RAG
indexing call, so an indexing failure would still leave a fully-populated
(misleading) candidate record behind even though the resume ended up
`FAILED`. A dedicated test asserting the candidate shouldn't exist in that
case caught it; fixed by moving indexing before the candidate write.

## Phase 7 - Scoring pipeline with rate limiting, retries, caching

`backend/services/scoring.py`: per-skill scores, overall rating, and
"relevant" (JD-matching, not total) experience from the LLM, grounded in RAG
evidence retrieved per must-have skill. **Fit is never asked of the LLM** -
computed from `overall_rating` against `FIT_THRESHOLD_BEST`/`MEDIUM` in
config. Re-scoring marks the prior `CURRENT` result `STALE` and inserts a
new one - history kept, not overwritten. Cache key includes `jd_version`.

`backend/services/pipeline.py`: the real background pipeline - bounded
concurrency (`PIPELINE_MAX_WORKERS`, default 3, each worker its own DB
session), triggered automatically via FastAPI `BackgroundTasks` on upload.
**Uploading a resume now requires zero manual clicks.**

Verified: 17 new tests (`test_scoring.py`, `test_pipeline.py`) covering Fit
computation across all threshold boundaries, STALE-marking/history, the
`jd_version` cache-key guarantee, automatic upload→DONE via a real
`TestClient` background-task run, manual retry endpoints, and
JD-no-longer-confirmed defensive handling.

**Bugs caught, both in `services/resume/profile.py`:**
- `Candidate(resume_id=resume.id)` + `db.add()` sets the FK but does **not**
  update the in-session `resume.candidate` relationship cache - `scoring.py`
  reading it immediately after (same pipeline run) saw a stale `None` and
  raised. Fixed by assigning the relationship directly
  (`resume.candidate = candidate`).
- Even after that fix, the new Candidate row had no `id` yet (never
  flushed) when scoring tried to write `candidate_id`, hitting a NOT NULL
  constraint. Fixed by flushing at the end of `process_resume()`.

Both were only caught because `test_pipeline.py` exercises parse-then-score
in one continuous run - something the Phase 5/6 tests, each mocking the
other half in isolation, never did. Also discovered `TestClient` runs
`BackgroundTasks` **synchronously** before `client.post()` returns, meaning
every earlier resume-upload test silently auto-triggered real background
processing unless mocked out.

## Phase 8 - Results dashboard: table, filters, detail, exports

New backend piece: `GET /screening/results/table` joins each `CURRENT`
`ScreeningResult` with its candidate's profile fields server-side, so the
dashboard renders from one request. Frontend: Fit filter, name/skill search,
click a row (`st.dataframe(..., on_select="rerun")`) for the full detail
view, CSV/Excel export of whatever's filtered.

Verified: 5 new route tests (join, sort order, `STALE` exclusion). Seeded a
JD with three realistic scored candidates directly via the DB and
live-verified the real page: `AppTest` renders the table, exercises
filters, **simulates a row-selection click** (by setting the dataframe
widget's session-state directly, since `AppTest` has no native gesture for
grid selection), and the CSV/Excel export bytes were independently verified
to round-trip correctly through `openpyxl`.

**Bug caught:** the JD dropdown was built from `list_jds()`, which returns
the lightweight `JDListItem` with no `must_have_skills`/`good_to_have_skills`
- so the per-skill score columns silently never appeared. Caught because
`AppTest` showed 8 columns where 12 were expected; fixed by fetching the
full JD via `get_jd()` instead of reusing the list-page item.

## Phase 9 - Assessment generation and export

`backend/services/assessment.py` computes the overlap between the JD's
must-have/good-to-have skills and the candidate's own resume skills
(case-insensitive, falling back to the JD's must-have list when there's no
overlap at all), and targets the prompt at exactly that. Every generation is
a new row (history kept). Export is built client-side
(`frontend/components/assessment_export.py`, pure functions) - interviewer
Markdown/CSV, and a candidate-facing Markdown with both the expected answer
points *and* the skill tags stripped (the tag would hint at the answer).

Verified: 12 new tests (overlap computation, all three routes, cache-key
guarantee) plus 5 real non-Streamlit unit tests on the export formatting
itself, confirming the candidate version genuinely has no answer points or
skill names in it.

**Bug caught:** `list_assessments` sorted only by `created_at`, which has
only second-level resolution in SQLite - two assessments generated within
the same second got an unstable sort order. Caught by a test generating two
back-to-back and asserting newest-first; fixed by adding `id DESC` as a
secondary sort key.

## Testing philosophy, in one paragraph

Every phase's tests ran against a **real** temp SQLite DB and, wherever
feasible, real libraries doing real work - real PDF/DOCX/RTF parsing, real
poppler rendering, a real local Chroma collection with real chunking. Only
the actual network call to an LLM/embeddings provider is mocked, always at
the same narrow boundary each service exposes for exactly that purpose
(`extract_jd_fields`, `extract_candidate_fields`, `_score_via_llm`,
`_generate_via_llm`, `vectorstore.get_embeddings`). Every phase was also
live-verified against the real running backend (and, from Phase 3 on, the
real Streamlit frontend via `AppTest`) with no `GOOGLE_API_KEY` set - every
LLM-dependent flow reaches the real provider client construction and fails
cleanly on missing credentials rather than crashing, which is what proves
the wiring is actually live end-to-end rather than just passing under
mocks. This combination is what caught every real bug listed above - none
of them would have been caught by mocking the LLM boundary alone.
