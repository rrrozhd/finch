# Quarterly Tax Copilot

An agent that works out a NYC freelancer's quarterly estimated taxes (federal 1040-ES and NYS/NYC IT-2105) from a zip of bank exports and receipts.

You drop in your files, answer seven profile questions, and get the next payment for each authority, with every dollar traced back to the source rows. The app never pays or files anything. It links to IRS Direct Pay and NYS Online Services and stops there.

Built at the Daytona HackSprint with Arize AI (NYC, October 2026).

## The idea in one paragraph

The LLM only **labels**; deterministic code **computes**. Rules categorize the obvious transactions. An LLM labels the remaining merchants and flags the ones only the taxpayer could know (was that dinner with a client?). Those flagged ones get a best guess and land in a review list instead of blocking the flow. Every label is a typed fact in SurrealDB that is **superseded, never overwritten**, so corrections keep their history. The tax math runs inside a **Daytona sandbox**: PolicyEngine-US for annual liability, plus the 1040-ES / IT-2105 safe-harbor rules for the installment.

## Pipeline

```
upload.zip
  │
  ▼
Daytona sandbox ─ unzip (untrusted), parse CSV/XLSX, OCR receipts (RapidOCR)      app/sandbox_worker.py
  │                 no API keys inside; low-confidence receipts → vision fallback on the server
  ▼
Categorize ─ regex rules first → LLM for leftover merchants (one batched call)    app/pipeline.py, app/llm.py
  │          unsure merchants get a best guess tagged "llm-guess" for review
  ▼
Facts ─ SurrealDB, typed and time-aware; writing a key supersedes the old fact     app/facts.py
  │
  ▼
Interview ─ fixed 7-question profile checklist (state, NYC, filing status,         app/pipeline.py
  │          line of work, prior-year tax/AGI); LLM only words the questions and parses answers
  ▼
Compute (in Daytona) ─ PolicyEngine-US annual liability + safe-harbor installments  app/engine.py via app/sandbox.py
  │
  ▼
Results ─ next payment per authority, "how we got here" breakdown, click any line
          to see source rows; review list of guessed labels with per-row or
          per-merchant fixes; chat agent for questions and what-ifs              web/src/Results.tsx, app/agent.py
```

## Where each sponsor tool does real work

| Tool | Job in this app | Code |
|---|---|---|
| **Daytona** | One long-lived sandbox per server. It unzips and parses untrusted uploads, OCRs receipts, and runs the tax engine. PolicyEngine is imported once in a persistent code-interpreter context, so a what-if takes about 1–2 s instead of a 25 s cold import. The image pins `policyengine-us==2.49.1` and runs the engine's golden self-check at build time. | `app/sandbox.py`, `app/sandbox_worker.py` |
| **SurrealDB** | Typed, time-aware fact store. Corrections supersede earlier facts with a reason, and the full history is viewable per transaction. | `app/facts.py` |
| **Arize** | OpenTelemetry/OpenInference traces for every step (ingest, categorize, compute, corrections). The categorization eval logs one span per transaction against hand-labeled ground truth. | `app/main.py`, `app/evals.py` |
| **Amazon Bedrock** | Claude models via LangChain for categorization, question wording, answer parsing, receipt vision fallback and the chat agent. Every output is validated by Pydantic before it becomes a fact. | `app/llm.py`, `app/agent.py` |

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node with pnpm, and a Daytona API key (or `LOCAL_SANDBOX=1`, see below).

```bash
cp .env.example .env          # fill in Bedrock, Daytona, Arize, SurrealDB values
uv sync
(cd web && pnpm install && pnpm build)
uv run uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and click **Try with sample data** to run the demo persona, Maya, a Brooklyn content creator.

- The first start builds the Daytona image. It installs OCR models and PolicyEngine and runs the golden check, which takes several minutes. Later starts reuse the named sandbox `taxagent-worker-v2`.
- Leave `SURREAL_URL` empty to use an in-memory SurrealDB.
- `LOCAL_SANDBOX=1` runs the same worker and engine on your machine with no isolation (dev only). OCR comes from the `dev` dependency group, which `uv sync` installs by default.

## Check it

```bash
uv run python -m app.engine                  # engine golden case (Maya): exact federal and NY numbers
uv run python scripts/api_flow.py            # drives a running server end to end: upload → interview → results → eval
```

`POST /api/eval/{session}` scores the categorization of a session against `demo/maya/labels_ground_truth.csv`. The agent never reads that file.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/upload` | Upload a `.zip` (≤ 50 MB); returns the session and first question |
| POST | `/api/answer` | Answer the current profile question |
| GET | `/api/results/{session}` | Payments, breakdown, source rows, guessed labels to review |
| POST | `/api/correct` | Relabel a transaction; `same_merchant: true` applies it to every guessed transaction at that merchant |
| GET | `/api/facts/{session}`, `/api/history/{session}/{key}` | Current facts and a fact's supersede history |
| POST | `/api/chat`, `/api/chat/resume` | Chat agent; any change it proposes waits for approval |
| POST | `/api/eval/{session}` | Categorization eval against ground truth |
| GET | `/api/demo-zip` | The sample upload |

## Layout

```
app/        FastAPI server, pipeline, engine, sandbox, facts, LLM, agent, evals
web/        React + Vite + shadcn/ui front end (served from web/dist by the server)
demo/       Synthetic persona generator and the Maya sample data (bank CSV, invoices, receipts, labels)
forms/      IRS 1040-ES and NYS IT-2105 instructions the payment rules are taken from
scripts/    End-to-end API driver and probes
```

## Scope and limits

- Tax year 2026, single filers, New York State + NYC only.
- The installment uses the regular safe harbor (smaller of 90% of this year or 100%/110% of last year). The annualized-income method is not implemented.
- MCTMT is detected and noted but not computed.
- These are estimates, not tax advice. All sample data is synthetic.
