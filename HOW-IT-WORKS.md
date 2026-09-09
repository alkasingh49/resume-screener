# How this project works

A walkthrough of the AI Resume Screener: what each piece does, how a request
travels through the system, and why it is built this way.

> **README.md** tells you how to *run* it. This document explains how it
> *works*, so you can change it with confidence.

---

## Contents

1. [The idea in one picture](#1-the-idea-in-one-picture)
2. [The two journeys](#2-the-two-journeys)
3. [How a request travels](#3-how-a-request-travels)
4. [Every file and its job](#4-every-file-and-its-job)
5. [The data model](#5-the-data-model)
6. [How the AI part actually works](#6-how-the-ai-part-actually-works)
7. [The three prompts](#7-the-three-prompts)
8. [How the frontend stays in sync](#8-how-the-frontend-stays-in-sync)
9. [How failure is handled](#9-how-failure-is-handled)
10. [Design decisions and why](#10-design-decisions-and-why)
11. [How to change things](#11-how-to-change-things)

---

## 1. The idea in one picture

```
   RECRUITER                     YOUR APP                        GEMINI
   ─────────                     ────────                        ──────

   uploads a JD    ────────►  save file, read text  ────────►  "what does this
                                                                role need?"
                              ◄────────────────────────────────
                              title, skills, years

   drops 40        ────────►  save all 40 fast,
   resumes                    reply immediately
                                    │
                                    │ (in the background, 4 at a time)
                                    ▼
                              for each resume:      ────────►  "who is this and
                              read text                         how well do they
                                                                fit THIS role?"
                              ◄────────────────────────────────
                              name, email, phone,
                              experience, scores,
                              reason
                                    │
                                    ▼
   watches the     ◄────────  a ranked table
   table fill in

   picks someone   ────────►  their resume + the JD  ────────►  "write interview
                                                                 questions for
                                                                 THIS person"
                              ◄────────────────────────────────
   gets questions  ◄────────  6 tailored questions
```

**The whole system is three AI calls**: one per job description, one per
resume, one per assessment. Everything else is plumbing around those calls.

---

## 2. The two journeys

### Journey A — set up a role (about 10 seconds)

| Step | What you do | What happens inside |
| --- | --- | --- |
| 1 | Click **+ Add job description**, pick a file | Browser sends the file to `POST /api/jds` |
| 2 | — | Backend saves the file to `data/uploads/jds/` |
| 3 | — | `files.py` turns the PDF/DOCX into plain text |
| 4 | — | `services.parse_jd()` asks Gemini for the structured fields |
| 5 | — | Row saved with `status=DONE` |
| 6 | You see the parsed role | The response *already* contains the fields — no polling needed |

This one is **synchronous** — you wait for it. That is deliberate: it is one
small file and you need to see immediately whether the parse looks right.

### Journey B — screen candidates (background)

| Step | What you do | What happens inside |
| --- | --- | --- |
| 1 | Drag 40 resumes onto the drop zone | Browser sends them all to `POST /api/resumes?jd_id=1` |
| 2 | — | Backend saves all 40 files and creates 40 `PENDING` rows |
| 3 | You get a response in **under a second** | It has not screened anything yet — it just stored the files |
| 4 | — | A **background task** starts screening, 4 at a time |
| 5 | Table fills in row by row | Frontend polls `GET /api/resumes?jd_id=1` every 2.5s |
| 6 | All rows show a score | Polling stops automatically |

This one is **asynchronous**. If it were not, you would stare at a spinner for
four minutes while 40 resumes went through the AI one at a time.

---

## 3. How a request travels

Take the most interesting one — uploading resumes — and follow it all the way
down.

```
┌──────────────────────────────────────────────────────────────────────┐
│ BROWSER                                                              │
│                                                                      │
│  UploadZone.tsx      you drop 3 files                                │
│        │                                                             │
│        ▼                                                             │
│  App.tsx             addResumes(files)                               │
│        │                                                             │
│        ▼                                                             │
│  api.ts              POST /api/resumes?jd_id=1   (FormData)          │
└────────┼─────────────────────────────────────────────────────────────┘
         │
         │  Vite dev server proxies /api → localhost:8001
         │  (so the browser only ever sees ONE origin, and there is no CORS)
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ BACKEND                                                              │
│                                                                      │
│  main.py             FastAPI matches the route                       │
│        │                                                             │
│        ▼                                                             │
│  routers/resumes.py  upload_resumes()                                │
│        │             • is the JD real and parsed?      → else 400    │
│        │             • save each file to disk                        │
│        │             • reject unsupported types now    → FAILED row  │
│        │             • create a PENDING row per file                 │
│        │             • db.commit()                                   │
│        │             • background.add_task(screen_batch, ids)        │
│        │                                                             │
│        ├──────────────► RESPONSE GOES BACK NOW  (fast)               │
│        │                                                             │
│        ▼   ...then, after the response is sent:                      │
│  services.py         screen_batch([1,2,3])                           │
│        │             ThreadPoolExecutor, 4 workers                   │
│        │                                                             │
│        ▼             for each resume, in its own thread:             │
│  services.py         screen_resume(resume, jd)                       │
│        │                                                             │
│        ├──► files.py       extract_text()   PDF/DOCX → str           │
│        │                                                             │
│        ├──► llm.py         load_prompt("screen_resume", ...)         │
│        │                   fills {{placeholders}} in the markdown    │
│        │                                                             │
│        ├──► llm.py         ask(prompt, LLMScreening)                 │
│        │        │                                                    │
│        │        └──► rate limiter waits its turn (5/min)             │
│        │             └──► Gemini  →  validated LLMScreening object   │
│        │                                                             │
│        ├──► copy the AI's answer onto the resume row                 │
│        ├──► fit_for(score) → BEST / MEDIUM / NO                      │
│        └──► status = DONE, commit                                    │
└──────────────────────────────────────────────────────────────────────┘
```

The key structural point: **the route does the fast work, the background task
does the slow work.** The route never calls the AI.

---

## 4. Every file and its job

### Backend — 13 files, ~1,000 lines

| File | Lines | Its one job |
| --- | --- | --- |
| `main.py` | 56 | Create the FastAPI app, wire up CORS and the routers, create tables on startup |
| `config.py` | 53 | Every setting, read once from `.env`. Nothing else reads env vars |
| `database.py` | 59 | Build the SQLite engine and hand out sessions |
| `models.py` | 105 | The three database tables |
| `schemas.py` | 160 | What the AI must return, and what the API returns |
| `llm.py` | 93 | **The only file that knows which AI provider you use** |
| `files.py` | 76 | Turn a PDF / DOCX / TXT / RTF into plain text |
| `services.py` | 173 | The actual work: parse a JD, screen a resume, write questions |
| `routers/jds.py` | 97 | The 6 job-description endpoints |
| `routers/resumes.py` | 118 | The 5 resume endpoints |
| `routers/assessments.py` | 46 | The 2 assessment endpoints |

**The layering rule:** routers handle HTTP (status codes, 404s, file saving),
services handle logic (and never import FastAPI), `llm.py` handles the AI.
A router never talks to Gemini directly, and a service never returns an
HTTP error.

### Frontend — 11 files, ~1,300 lines

| File | Lines | Its one job |
| --- | --- | --- |
| `types.ts` | 71 | TypeScript mirrors of the backend's response shapes |
| `api.ts` | 55 | **The only file with URLs in it.** One `request()` helper, one method per endpoint |
| `App.tsx` | 265 | All the state and all the actions. The components are dumb |
| `components/Sidebar.tsx` | 89 | The job list and the "add JD" button |
| `components/JobPanel.tsx` | 87 | The parsed role shown at the top |
| `components/UploadZone.tsx` | 88 | The drag-and-drop area |
| `components/ResultsTable.tsx` | 134 | The ranked candidate table |
| `components/CandidateDrawer.tsx` | 306 | The slide-over: full detail + assessment + export |
| `components/ui.tsx` | 161 | Shared bits: buttons, badges, score bars, spinners |

**The pattern:** `App.tsx` owns *all* state and passes data down as props.
Components render what they are given and call the functions they are given.
No component fetches its own data except the drawer, which loads assessments.

---

## 5. The data model

Three tables. That is the whole database.

```
┌─────────────────────────┐
│   job_descriptions      │
├─────────────────────────┤
│ id                      │
│ filename, storage_path  │  the uploaded file
│ raw_text                │  extracted plain text
│ status, error           │  PENDING → DONE / FAILED
│ ─── from the AI ─────── │
│ title                   │
│ location                │
│ min_years, max_years    │
│ must_have_skills   []   │
│ good_to_have_skills[]   │
│ responsibilities   []   │
└───────────┬─────────────┘
            │ 1 JD has many resumes
            ▼
┌─────────────────────────┐
│        resumes          │   ◄── this row IS the candidate
├─────────────────────────┤       AND the screening result
│ id, jd_id               │
│ filename, storage_path  │
│ raw_text                │
│ status, error           │  PENDING → PROCESSING → DONE / FAILED
│ ─── extracted by AI ─── │
│ name, email, phone      │
│ location                │
│ current_title           │
│ current_company         │
│ total_experience_years  │
│ relevant_experience_yrs │
│ skills             []   │
│ ─── scored by AI ────── │
│ skill_scores       {}   │  {"Python": 9, "AWS": 7}
│ score                   │  0-100
│ fit                     │  BEST / MEDIUM / NO
│ reason                  │  the 2-3 sentence justification
└───────────┬─────────────┘
            │ 1 resume can have many assessments
            ▼
┌─────────────────────────┐
│      assessments        │
├─────────────────────────┤
│ id, resume_id           │
│ questions          []   │  [{question, skill, difficulty,
│                         │    expected_answer}, ...]
└─────────────────────────┘
```

### Why a resume row *is* the candidate

The earlier version of this project had **three** tables here:
`Resume` → `Candidate` → `ScreeningResult`, joined one-to-one-to-one.

That meant every read needed two joins, every write touched three tables, and
a whole `/screening` API resource existed purely to stitch them back together.

But there is only ever **one** candidate per resume and **one** current score
per candidate. Splitting them bought nothing and cost a lot. Collapsing them
into one row deleted three endpoints and roughly 400 lines of code.

> **The rule of thumb:** if two tables are always one-to-one and always
> created together, they are one table.

### Status lifecycle

```
JD:      PENDING ──► DONE      (parsed, ready for resumes)
             └─────► FAILED    (unreadable file, or the AI call failed)

Resume:  PENDING ──► PROCESSING ──► DONE      (screened, has a score)
             │            └────────► FAILED   (bad file, or the AI failed)
             └─────────────────────► FAILED   (unsupported type, rejected
                                               at upload without an AI call)
```

---

## 6. How the AI part actually works

This is the bit worth understanding properly, because it is where the
"magic" is — and it turns out not to be magic at all.

### Structured output: no JSON parsing anywhere

You never ask the model for JSON and then parse it. Instead you hand it a
**Pydantic class** and LangChain makes the model fill it in:

```python
# schemas.py — you describe the shape you want
class LLMScreening(BaseModel):
    name: str | None = Field(None, description="Candidate's full name")
    email: str | None = Field(None, description="Email address")
    total_experience_years: float | None = Field(
        None, description="Total professional experience in years"
    )
    score: int = Field(ge=0, le=100, description="Overall match rating, 0-100")
    reason: str = Field(description="2-3 sentences justifying the score")
    ...

# llm.py — the entire AI interface, one function
def ask(prompt: str, schema: type[T]) -> T:
    return get_model().with_structured_output(schema).invoke(prompt)

# services.py — how you call it
result = ask(prompt, LLMScreening)
result.score          # an int, guaranteed 0-100
result.email          # a str or None
```

Three things happen for free here:

1. **The `description=` text becomes part of the instruction** sent to the
   model. Those descriptions are prompt engineering, not documentation.
2. **`ge=0, le=100` is enforced.** If the model returns 150, Pydantic raises
   and the resume is marked `FAILED` rather than storing nonsense.
3. **You get an object, not a string.** No `json.loads`, no `try/except
   JSONDecodeError`, no "the model wrapped it in ```json again".

### Swapping Gemini for GPT

`llm.py` is the *only* file that imports a provider. Everything else calls
`ask()`.

```python
@lru_cache
def get_model() -> BaseChatModel:
    s = get_settings()

    if s.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=s.LLM_MODEL, ...)

    if s.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=s.LLM_MODEL, ...)
```

So switching provider is two lines in `.env`:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

**This is what LangChain is here for.** Both classes implement the same
`BaseChatModel` interface, so `.with_structured_output(schema).invoke(prompt)`
works identically on either. That is the entire benefit, and it is worth the
dependency.

### The rate limiter

The Gemini free tier allows **5 requests per minute**. Without pacing, four
screening threads fire at once, three get a `429`, and everything backs off
for 30+ seconds.

```python
limiter = InMemoryRateLimiter(
    requests_per_second=s.LLM_RPM_CAP / 60,   # 5/min = one call per 12s
    max_bucket_size=1,
)
```

It is attached to the model itself, so it covers every call path and is shared
across all the screening threads. Raise `LLM_RPM_CAP` in `.env` on a paid key.

---

## 7. The three prompts

They live in `backend/prompts/` as **plain markdown**, not Python strings.
You can rewrite the AI's behaviour without touching any code.

| File | Called by | Returns |
| --- | --- | --- |
| `extract_jd.md` | `parse_jd()` | `LLMJobDescription` |
| `screen_resume.md` | `screen_resume()` | `LLMScreening` |
| `generate_questions.md` | `create_assessment()` | `LLMQuestionSet` |

Placeholders use `{{double_braces}}` and are filled by `load_prompt()`:

```python
prompt = load_prompt(
    "screen_resume",
    job_title=jd.title,
    must_have_skills=", ".join(jd.must_have_skills),
    resume_text=resume.raw_text,
)
```

### The one that matters most

`screen_resume.md` does the heavy lifting. Two instructions in it are doing
almost all the work:

**Relevant vs total experience** — the distinction you actually care about:

> **relevant_experience_years** — only the portion of that experience which
> involved this role's must-have skills and responsibilities. This is
> normally LESS than total experience. A backend engineer of 8 years applying
> for a frontend role may have only 2 relevant years. **Be strict.**

In testing, a frontend engineer with a genuine 5 years came back as **5.0
total, 0.0 relevant** for a backend payments role. That single field is the
difference between a list of resumes and an actual shortlist.

**A scoring rubric, not a vibe** — without this, models cluster everything
around 70:

> - 0 — no mention at all
> - 1-3 — listed in a skills section only, no supporting work described
> - 4-6 — used in real work, described briefly
> - 7-8 — clear repeated hands-on delivery with specifics
> - 9-10 — deep expertise: led, architected, or scaled work with this skill

### Fit is computed, not asked for

The model returns a `score` (0-100). It is never asked for the Best/Medium/No
label. That is worked out in Python:

```python
def fit_for(score: int) -> str:
    if score >= settings.FIT_BEST_MIN:    # 75
        return Fit.BEST
    if score >= settings.FIT_MEDIUM_MIN:  # 45
        return Fit.MEDIUM
    return Fit.NO
```

Why: you can retune the cutoffs in `.env` and every future screening obeys
them instantly — no prompt edit, no risk of the model drifting, and the
thresholds are visible in one place instead of buried in English.

---

## 8. How the frontend stays in sync

The backend has no websockets. The frontend simply **polls while there is
something to wait for, and stops when there is not.**

```tsx
// App.tsx (simplified - the real one also guards against the selected
// job changing mid-interval)
const workingCount = candidates.filter(
  (c) => c.status === "PENDING" || c.status === "PROCESSING",
).length;

useEffect(() => {
  if (workingCount === 0) return;          // nothing pending → no polling

  const timer = setInterval(() => {
    refreshCandidates(jobId);              // re-fetch the table
  }, 2500);

  return () => clearInterval(timer);       // cleanup on change/unmount
}, [workingCount, jobId]);
```

The effect depends on `workingCount`. When the last resume flips to `DONE`,
that count hits zero, the effect re-runs, and the early `return` stops the
polling. No manual "am I still polling?" flag to get wrong.

This is why `GET /api/resumes` returns the *whole* table rather than a diff —
it makes polling a one-liner, and 40 rows of JSON is nothing.

---

## 9. How failure is handled

The rule throughout: **a failure is data, not an exception.** One bad file
must never break a batch of forty.

```python
# services.py
def screen_resume(resume, jd) -> None:
    resume.status = Status.PROCESSING
    try:
        ...
        resume.status = Status.DONE
    except UnreadableFile as exc:
        resume.status, resume.error = Status.FAILED, str(exc)
    except Exception as exc:
        resume.status, resume.error = Status.FAILED, f"Could not screen this resume: {exc}"
```

Note it returns `None` and never raises. The failure is written **onto the
row**, so it appears in the table as a `FAILED` badge with the reason and a
**Retry** button — and the other 39 resumes carry on.

Failures are caught at four levels:

| Where | What it catches | What you see |
| --- | --- | --- |
| Upload | Unsupported file type | Row marked `FAILED` immediately, no AI call wasted |
| `files.py` | Corrupt file, scanned PDF with no text | "No text found in cv.pdf…" |
| `services.py` | AI call failed, quota exhausted, bad response | "Could not screen this resume: …" |
| `_screen_by_id()` | A worker thread crashing outright | Logged; the rest of the batch continues |

The one deliberate exception is **assessment generation**, which *does* raise
and become a `502`. You are sitting there waiting for that one, so an error
message on screen is better than a silently empty panel.

---

## 10. Design decisions and why

Each of these was a real choice with a real alternative.

### One AI call per resume, not two

The obvious design is "extract the profile, then score it" — two calls.
This does both in one, because the model needs the resume in context either
way, and the free tier meters you *per call*. Halving the calls halves the
cost and doubles the throughput.

### No vector database

The natural instinct on a "RAG project" is Chroma + embeddings. It was
deliberately removed.

RAG exists to solve one problem: **source text too big for the context
window.** You chunk it, embed it, and retrieve only the relevant pieces.

A resume is 1-3 pages — roughly 1,000-3,000 tokens. Gemini's context window is
1,000,000. The entire JD *plus* the entire resume uses about **0.3%** of it.

So retrieval could only ever feed the model a *subset* of a document that
already fits whole. It cannot improve the answer; it can only drop the
paragraph that mattered — while adding an embedding call per resume, a vector
DB on disk, and a new way for things to break.

> A vector DB *would* earn its place for search **across** the candidate pool
> ("who has done Kafka migrations?") or for 50-page CVs. Neither is this app.

### No retry wrapper

There was one. It made things worse. Both provider SDKs already retry
internally, so a second layer *multiplied* the wait — an exhausted daily quota
took minutes to surface instead of failing fast. Now retries are bounded by
`MAX_RETRIES` in `llm.py`, and a real failure becomes a `FAILED` row with a
Retry button within seconds.

### No JD "confirm" step

An earlier version made you confirm a JD before uploading resumes, with a
five-state lifecycle and versioning that marked old results stale when a
confirmed JD changed. For a demo that is ceremony. Now a JD is either parsed
or it is not.

### SQLite, no migrations

`Base.metadata.create_all()` on startup. Adding a column means changing
`models.py` and deleting `data/app.db`. That is the right trade for a demo and
the wrong one for production — swap in Alembic if this ever ships.

---

## 11. How to change things

| You want to… | Do this |
| --- | --- |
| Change how candidates are scored | Edit `backend/prompts/screen_resume.md` |
| Change what is pulled from a JD | Edit `backend/prompts/extract_jd.md` |
| Change the interview questions | Edit `backend/prompts/generate_questions.md` |
| Retune Best/Medium/No | `FIT_BEST_MIN` / `FIT_MEDIUM_MIN` in `.env` |
| Capture a **new field** per candidate | 3 steps, see below |
| Switch to GPT | `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4o-mini`, add the key |
| Screen faster | Raise `LLM_RPM_CAP` (needs a paid key) |
| Add a new endpoint | Add to the right `routers/*.py`; it auto-registers |
| Change the table columns | `frontend/src/components/ResultsTable.tsx` |
| Change colours or spacing | `frontend/src/components/ui.tsx` |

### Worked example: adding "notice period"

**1. Ask the AI for it** — `backend/schemas.py`:

```python
class LLMScreening(BaseModel):
    ...
    notice_period_days: int | None = Field(
        None, description="Notice period in days, if the resume states one"
    )
```

**2. Store it** — `backend/models.py`:

```python
class Resume(Base):
    ...
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
```

…and copy it across in `services.screen_resume()`:

```python
resume.notice_period_days = result.notice_period_days
```

…and expose it in `schemas.ResumeOut`:

```python
notice_period_days: int | None
```

**3. Show it** — add the field to `Candidate` in `frontend/src/types.ts`, then
render it wherever you want it.

Then `rm data/app.db` and restart, because there are no migrations.

Note that you did **not** touch a prompt. The `description=` on the field is
the instruction — that is the whole point of structured output.

---

## Quick reference

```bash
./run.sh dev      # API + UI          → http://localhost:5173
./run.sh api      # API alone         → http://localhost:8001/docs
./run.sh test     # 13 tests
./run.sh clean    # wipe the DB and uploads
```

| Thing | Where |
| --- | --- |
| Interactive API docs | http://localhost:8001/docs |
| Database | `data/app.db` (SQLite — open it in any viewer) |
| Uploaded files | `data/uploads/jds/` and `data/uploads/resumes/` |
| Settings | `.env` |
| Prompts | `backend/prompts/*.md` |

### If something looks wrong

| Symptom | Likely cause |
| --- | --- |
| Red banner: "No AI API key" | `GOOGLE_API_KEY` empty in `.env`; restart after setting it |
| Every resume `FAILED` with a quota error | Free-tier daily cap hit. Switch `LLM_MODEL` — the quota is per model |
| Rows stuck on `Pending` for a while | Normal: 5 calls/minute on the free tier. 40 resumes ≈ 8 minutes |
| "No text found in …" | Scanned/image-only PDF. There is no OCR — convert it first |
| Scores feel too generous or harsh | Retune the rubric in `screen_resume.md`, or the `.env` thresholds |
| UI loads but every call fails | Backend is not running, or it is not on port 8001 |
