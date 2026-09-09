# AI Resume Screener

A recruiter uploads a job description and a pile of resumes. The AI reads
every resume, pulls out the candidate's details, scores them against the
role, and writes a tailored set of interview questions.

![stack](https://img.shields.io/badge/FastAPI-backend-009688) ![stack](https://img.shields.io/badge/React_19-frontend-61dafb) ![stack](https://img.shields.io/badge/LangChain-Gemini_or_GPT-1c3c3c)

---

## Quick start

```bash
cp .env.example .env      # then add your GOOGLE_API_KEY
./run.sh install
./run.sh dev
```

Open **http://localhost:5173**.

Get a free Gemini key at <https://aistudio.google.com/apikey>. Without one
the app still runs, but every upload fails with a message telling you the
key is missing.

### Commands

| Command            | What it does                                   |
| ------------------ | ---------------------------------------------- |
| `./run.sh dev`     | API + UI together → http://localhost:5173      |
| `./run.sh api`     | Just the API → http://localhost:8001/docs      |
| `./run.sh ui`      | Just the React app                             |
| `./run.sh test`    | Run the tests                                  |
| `./run.sh build`   | Production build of the frontend               |
| `./run.sh clean`   | Wipe the database and uploaded files           |

The API runs on **8001**, not 8000, because 8000 is often already taken.
Change it with `PORT=8080 ./run.sh dev`.

---

## What it does

1. **Add a job description.** Upload a PDF/DOCX/TXT/RTF. The AI extracts the
   title, must-have and good-to-have skills, experience range and
   responsibilities. You can correct any of it.
2. **Bulk-upload resumes.** Drop in as many as you like at once. They screen
   in the background, four at a time, and the table fills in as they finish.
3. **Read the results.** One row per candidate, best score first:

   | Field | Where it comes from |
   | --- | --- |
   | Name, Email, Contact no | Read out of the resume |
   | Total experience | Summed from the dated roles in the work history |
   | Relevant experience | Only the years matching *this* role — usually lower |
   | Fit — Best / Medium / No | Computed from the rating, see below |
   | Rating | 0–100 overall match |
   | Scores | 0–10 per must-have skill |
   | Reason | 2–3 sentences citing evidence from the resume |

4. **Generate the tech round.** Open a candidate and generate interview
   questions grounded in their own claimed work. Export two versions: one
   for the candidate, and one for the interviewer with expected answers.

One bad file never breaks a batch — it lands in the table as `FAILED` with a
reason and a Retry button, and the rest carry on.

---

## Layout

```
backend/
  main.py         FastAPI app, CORS, startup
  config.py       Every setting, read from .env
  database.py     SQLite engine and sessions
  models.py       3 tables: job_descriptions, resumes, assessments
  schemas.py      What the LLM returns, and what the API returns
  llm.py          The ONLY file that picks an LLM provider
  files.py        PDF / DOCX / TXT / RTF -> text
  services.py     Parse a JD, screen a resume, write questions
  routers/        jds.py · resumes.py · assessments.py
  prompts/        The three prompts, as editable markdown
frontend/
  src/api.ts      Typed client - the only place URLs live
  src/App.tsx     Layout and state
  src/components/ Sidebar · JobPanel · UploadZone · ResultsTable · CandidateDrawer
tests/            Unit tests plus a full end-to-end journey
```

**A candidate is a resume row.** Everything extracted and everything scored
lives on that one row. There is no separate candidate or screening-result
table, because there is never more than one of each per resume.

---

## The API

| Method | Endpoint | |
| --- | --- | --- |
| `GET` | `/api/health` | Also reports whether an API key is configured |
| `POST` | `/api/jds` | Upload a JD. The response already contains the parsed fields |
| `GET` | `/api/jds` | List them |
| `GET` | `/api/jds/{id}` | One, in full |
| `PUT` | `/api/jds/{id}` | Correct what the AI extracted |
| `POST` | `/api/jds/{id}/reparse` | Analyse it again |
| `DELETE` | `/api/jds/{id}` | Delete it and its resumes |
| `POST` | `/api/resumes?jd_id=` | Bulk upload. Screening starts automatically |
| `GET` | `/api/resumes?jd_id=` | The results table. Poll while screening |
| `GET` | `/api/resumes/{id}` | One candidate |
| `POST` | `/api/resumes/{id}/rescreen` | Retry a failed one |
| `DELETE` | `/api/resumes/{id}` | Remove a candidate |
| `POST` | `/api/assessments?resume_id=&num_questions=` | Write the tech round |
| `GET` | `/api/assessments?resume_id=` | Past assessments, newest first |

Interactive docs at http://localhost:8001/docs.

---

## Swapping the LLM

`backend/llm.py` is the only file that knows which provider is in use.
Everything else calls `ask(prompt, Schema)` and gets a validated Pydantic
object back, because LangChain gives every provider the same interface.

```dotenv
# Gemini
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
GOOGLE_API_KEY=...

# OpenAI - no code changes
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=...
```

To add another provider, add one branch to `get_model()`.

### Tuning

Editing `backend/prompts/*.md` changes the AI's behaviour without touching
Python. The Fit cutoffs live in `.env`, deliberately outside the prompt:

```dotenv
FIT_BEST_MIN=75      # >= 75  -> Best
FIT_MEDIUM_MIN=45    # >= 45  -> Medium, below -> No
```

### Free-tier quotas (read this before a demo)

The Gemini free tier limits you **per model, per minute and per day**, and
the daily caps are small — `gemini-3.8-flash` allows only **20 requests a
day**. Each resume costs one call, and each assessment one more.

The default is therefore **`gemini-3.1-flash-lite`**, which has a far larger
daily allowance and scored the same candidates in the same order as the
bigger model in testing. Swap to `gemini-3.8-flash` for the best possible
extraction quality if you are on a paid key, or for a small, high-stakes
batch.

`LLM_RPM_CAP` (default 5, matching the free tier) paces calls so a bulk
upload spreads out instead of bursting into a 429 and waiting out a backoff.
Raise it on a paid plan to screen faster:

```dotenv
LLM_RPM_CAP=5            # requests per minute
MAX_PARALLEL_RESUMES=4   # screening threads
```

The daily quota is **per model**, so if you exhaust one, switching
`LLM_MODEL` gives you a fresh allowance.

Retries are left to the provider SDK and capped at `MAX_RETRIES` in
`backend/llm.py`. There is deliberately no second retry layer on top: when
one was there, an exhausted daily quota took *minutes* to surface instead of
failing fast. A call that does fail marks that resume `FAILED` with the
reason, and the table gives you a Retry button.

---

## Notes and limits

- **One LLM call per resume** does the extraction and the scoring together,
  which matters when the free tier meters you by the call.
- **No vector database.** A resume is 1–3 pages and fits in well under 1% of
  the model's context window, so the whole thing goes into the prompt.
  Retrieval could only ever give the model *less* of the resume. If you later
  need search *across* candidates, that is when a vector store earns its place.
- **Scanned/image-only PDFs are rejected** with a clear message. OCR needs
  system packages (`tesseract-ocr`, `poppler-utils`) and was left out.
- **No auth, no migrations.** SQLite plus `create_all`. This is a demo.
- **Uploads are trusted.** Do not expose this to the open internet as-is.
