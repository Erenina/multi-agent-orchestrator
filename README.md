---
title: Multi-Agent Orchestrator
emoji: 🧭
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Multi-Agent Orchestrator

**🚀 Live demo: [huggingface.co/spaces/eraxes/multi-agent-orchestrator](https://huggingface.co/spaces/eraxes/multi-agent-orchestrator)**

A **multi-agent system** built **from scratch** (no LangChain) on **Groq function-calling**. A **Planner** breaks your request into independent steps; an **Executor** carries out each step with its own tool-use loop; the Planner then reviews the results and either finishes with a cited answer or **revises the plan** and continues. You watch the whole thing — plan, execution, review — **live** in the browser.

This is the natural next step after a single-agent [ReAct research agent](https://github.com/Erenina/research-agent): here, *deciding what to do* (planning) and *deciding how to do it* (tool use) are split into two separate LLM roles instead of one loop doing both.

---

## How it works

```
QUESTION
   │
   ▼
┌───────────────┐
│   PLANNER     │  breaks the request into steps
└───────┬───────┘
        │ plan (forced function-call → guaranteed valid JSON)
        ▼
┌───────────────┐
│   EXECUTOR    │  runs EACH step with its own mini ReAct loop
│  (tool-use)   │  (web_search, read_url, calculator)
└───────┬───────┘
        │ step results (each step sees prior steps' results)
        ▼
┌───────────────┐
│   PLANNER     │  reviews: enough info? → finish
│   (review)    │  not enough? → replan (bounded retries)
└───────┬───────┘
        ▼
   FINAL ANSWER (with sources)
```

Both the plan and the review decision are produced via **forced function-calling** (`tool_choice` pinned to a specific tool) instead of free-text JSON — the model is structurally unable to return anything but valid, parseable arguments. Combined with the retry-on-`tool_use_failed` logic (bump temperature, try again) carried over from the research-agent project, this makes the orchestration robust to Llama's occasional malformed tool calls.

---

## Why two agents instead of one ReAct loop

| | Single-agent ReAct | This project |
|---|---|---|
| Who decides the next action | The same model, one step at a time | A dedicated **Planner** up front, then reviews in batches |
| Failure recovery | Just keeps looping until `max_steps` | Planner explicitly **replans** based on what's missing |
| Structured output | Plain tool calls | Tool calls **forced** to a specific schema (plan / finish / replan) |
| Step independence | N/A — one continuous context | Each step runs in its **own** bounded tool-use loop, but sees prior steps' results |

---

## Tools (shared with the research-agent project)

| Tool | What it does |
|------|--------------|
| `web_search` | DuckDuckGo search (no API key) — returns titles, URLs, snippets |
| `read_url`   | Fetches a page and extracts clean text |
| `calculator` | Safe arithmetic — AST-based, **no `eval()`** |

---

## Tech stack

| Layer   | Choice                                                     |
|---------|-------------------------------------------------------------|
| LLM     | Groq `llama-3.3-70b-versatile` (free, tool use)             |
| Planner | Forced function-calling for structured plan/review output   |
| Executor| Bounded ReAct loop per step (`orchestrator/executor.py`)    |
| API/UI  | FastAPI + Server-Sent Events + vanilla HTML/CSS/JS          |
| Search  | DuckDuckGo (`ddgs`) + BeautifulSoup for page text            |

---

## Project structure

```
multi-agent-orchestrator/
├── orchestrator/
│   ├── config.py       # settings (loaded from .env)
│   ├── llm.py          # Groq client + retry + forced/choice tool-calls
│   ├── tools.py        # web_search / read_url / calculator + JSON schemas
│   ├── planner.py       # plan / review — forced function-calling
│   ├── executor.py      # per-step ReAct loop
│   └── core.py          # orchestration: plan → execute → review → (replan|finish)
├── static/
│   └── index.html       # web UI — plan as live step cards via SSE
├── app.py                # FastAPI: GET /ask streams the orchestration trace
├── cli.py                 # command-line interface (same orchestrator)
├── Dockerfile             # Hugging Face Spaces (Docker)
├── requirements.txt
└── .env.example
```

---

## Setup

```bash
pip install -r requirements.txt

cp .env.example .env          # then set GROQ_API_KEY
#   free key (no card): https://console.groq.com

# Web UI (watch the plan + execution live):
uvicorn app:app --reload --port 8000     # http://localhost:8000

# …or the CLI:
python cli.py "2024 Nobel Barış Ödülü'nü kim kazandı ve hangi ülkeden?"
```

---

## Deploy (Hugging Face Spaces, free)

The repo is deploy-ready (`Dockerfile` + HF front matter in this README, `app_port: 7860`).

1. Create a **Docker** Space at https://huggingface.co/new-space
2. Add `GROQ_API_KEY` as a Space **secret** (Settings → Variables and secrets)
3. Push this repo to the Space's git remote — it builds and runs automatically

`.env` is git-/docker-ignored, so the key never enters the repo or image; it is injected at runtime from the Space secret.

---

## What I learned building this

- Splitting an agentic system into **separate planning and execution roles**, instead of one model doing both in a single loop.
- Using **forced function-calling** (`tool_choice` pinned to one tool) to get guaranteed-valid structured output from an LLM, without a fragile JSON-text parser.
- Designing a **replan loop**: the Planner reviews Executor results and can revise the remaining steps, bounded by a retry budget so it always converges.
- Passing **cross-step context** to the Executor — an early bug where step 2 couldn't "see" step 1's result (and silently guessed wrong) taught me that steps sharing a plan aren't actually independent.

*The interesting parts to read first: [`orchestrator/core.py`](orchestrator/core.py) (the orchestration loop) and [`orchestrator/planner.py`](orchestrator/planner.py) (forced-function-call planning/review).*
