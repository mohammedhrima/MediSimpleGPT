# MediSimpleGPT

Local-first medical assistant chat app powered by Ollama, with Wikipedia-based retrieval and a Playwright-driven browser agent under the hood.

This repo contains:

- A **FastAPI backend** that:
  - Drives a real Chromium browser via **Playwright**.
  - Calls a local **Ollama** model for planning/simplification.
  - Stores chat history in a local **SQLite** database.
- A **React + Vite frontend** that provides the chat UI.

## Features

- **Medical Q&A chat**
  - Persists conversations per `session_id`.
  - Uses Wikipedia as a retrieval source for new topics.
  - Detects typos for short medical-term queries and asks for confirmation.
- **DOM-driven web automation**
  - `POST /connect` opens a browser and extracts a simplified list of visible elements.
  - `POST /plan` turns `{dom + instruction}` into a JSON action plan.
  - `POST /execute` executes those actions in the browser.
  - `POST /simplify` extracts “article-like” content from the current page and simplifies it.

## Tech stack

- **Backend**: Python, FastAPI, Uvicorn, Playwright, Ollama, SQLite (`aiosqlite`)
- **Frontend**: React, TypeScript, Vite, TanStack Query, Axios

## Prerequisites

- **Python**: `>= 3.13` (see `backend/pyproject.toml`)
- **uv** (Python package manager)
- **Node.js + npm** (for the frontend)
- **Ollama** installed and running locally
  - Backend model is currently hardcoded to `granite3.1-dense:8b` in `backend/api_server.py`.
  - You must have that model available in Ollama.

## Quickstart

### 1) Install

```bash
make install
```

This runs:

- `uv sync` for the backend
- `playwright install chromium` for the backend
- `npm install` for the frontend

### 2) Run

In two terminals:

```bash
make backend
```

```bash
make frontend
```

Then open:

- Frontend: `http://localhost:5173`
- Backend: `http://127.0.0.1:8000`

## Backend API

Base URL: `http://127.0.0.1:8000`

### Health

- `GET /health`
  - Returns backend status, whether a browser is connected, and the active model name.

### Chat (MediSimpleGPT)

- `POST /chat`
  - Body:
    - `query`: string
    - `session_id`: string (optional; frontend stores one in `localStorage`)
- `GET /history/{session_id}`
- `DELETE /history/{session_id}`

### Web agent

- `POST /connect`
  - Body:
    - `url`: string
  - Returns extracted DOM element summaries.

- `POST /plan`
  - Body:
    - `instruction`: string
    - `dom`: string
  - Returns an LLM-generated plan (intended to be a JSON array of actions).

- `POST /execute`
  - Body:
    - `actions`: string (LLM output containing a JSON array)
    - `url`: string

- `POST /simplify`
  - Extracts article-like content from the current page and simplifies it.

## Data & state

- **Chat history DB**: `backend/conversations.db` (SQLite)
- **Browser state**: the backend keeps a single global browser/page (single-user assumption).

## Project structure

```text
.
├─ backend/
│  ├─ api_server.py        # FastAPI server (main backend entrypoint)
│  ├─ server.py            # MCP server (stdio transport)
│  ├─ prompts.json         # Prompt templates
│  ├─ pyproject.toml       # Python deps
│  └─ uv.lock
├─ frontend/
│  ├─ src/
│  │  ├─ App.tsx           # MediSimpleGPT chat UI
│  │  └─ hooks/useAgent.ts # Helper hooks for connect/plan/execute/simplify
│  └─ package.json
└─ Makefile
```

## Useful commands

- `make install`
- `make backend`
- `make frontend`
- `make clean`

## Troubleshooting

- **Ollama errors / empty responses**
  - Make sure Ollama is running.
  - Make sure the model configured in `backend/api_server.py` exists in Ollama.

- **Playwright browser not launching**
  - Re-run `uv run playwright install chromium` in `backend/`.

- **CORS issues**
  - Backend CORS currently allows `http://localhost:5173` only.
