<div align="center">
  <img src="frontend/public/favicon.svg" alt="MediSimpleGPT Logo" width="80" height="80">
  
  # MediSimpleGPT
  
  Local-first medical assistant chat app powered by Ollama, with Wikipedia-based retrieval and a Playwright-driven browser agent under the hood.
</div>

## Table of Contents

- [Quick Start](#quick-start)
- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Useful Commands](#useful-commands)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

**Already have all dependencies?** Jump straight to running the app:

```bash
# 1. Clone and setup
git clone <repository-url>
cd MediSimpleGPT
make install

# 2. Start Ollama (in separate terminal)
ollama serve

# 3. Run the application (in two terminals)
make backend   # Terminal 1: http://127.0.0.1:8000
make frontend  # Terminal 2: http://localhost:5173
```

**Need to install dependencies?** → [Go to Prerequisites](#prerequisites)

**Having issues?** → [Go to Troubleshooting](#troubleshooting)

---

## Overview

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
  - Handles conversational queries like "summarize our discussion" or "what are the pain points".
- **DOM-driven web automation**
  - `POST /connect` opens a browser and extracts a simplified list of visible elements.
  - `POST /plan` turns `{dom + instruction}` into a JSON action plan.
  - `POST /execute` executes those actions in the browser.
  - `POST /simplify` extracts “article-like” content from the current page and simplifies it.

## Tech Stack

- **Backend**: Python, FastAPI, Uvicorn, Playwright, Ollama, SQLite (`aiosqlite`)
- **Frontend**: React, TypeScript, Vite, TanStack Query, Axios

## Prerequisites

### System Requirements

- **Python**: `>= 3.13` (see `backend/pyproject.toml`)
- **Node.js**: `>= 18.0.0` (for npm and Vite)
- **Operating System**: macOS, Linux, or Windows

### Installing Dependencies

#### 1. **Python 3.13+**

**macOS**:
```bash
# Using Homebrew (recommended)
brew install python@3.13

# Or download from python.org
# Visit: https://www.python.org/downloads/
```

**Linux (Ubuntu/Debian)**:
```bash
# Add deadsnakes PPA for latest Python versions
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-pip
```

**Windows**:
```bash
# Download from python.org and run installer
# Visit: https://www.python.org/downloads/
# Make sure to check "Add Python to PATH" during installation
```

#### 2. **uv (Python Package Manager)**

**All Platforms**:
```bash
# Using pip (after Python is installed)
pip install uv

# Or using curl (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using PowerShell (Windows)
powershell -c "irm https://astral.sh/uv/install.sh | iex"

# Or using Homebrew (macOS)
brew install uv
```

**Verify installation**:
```bash
uv --version
```

#### 3. **Node.js and npm**

**macOS**:
```bash
# Using Homebrew (recommended)
brew install node

# Or download from nodejs.org
# Visit: https://nodejs.org/
```

**Linux (Ubuntu/Debian)**:
```bash
# Using NodeSource repository (recommended)
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Or using snap
sudo snap install node --classic
```

**Windows**:
```bash
# Download from nodejs.org and run installer
# Visit: https://nodejs.org/
# npm is included with Node.js
```

**Verify installation**:
```bash
node --version
npm --version
```

#### 4. **Ollama**

**macOS**:
```bash
# Using Homebrew (recommended)
brew install ollama

# Or download from ollama.com
# Visit: https://ollama.com
```

**Linux**:
```bash
# Using curl
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows**:
```bash
# Download from ollama.com
# Visit: https://ollama.com
```

**Start Ollama service**:
```bash
ollama serve
```

**Download the required model**:
```bash
ollama pull granite3.1-dense:8b
```

**Verify installation**:
```bash
ollama list
# You should see granite3.1-dense:8b in the list
```

> **Note**: You can change the model by setting `OLLAMA_MODEL` in `.env`. The default is `granite3.1-dense:8b`.

### Quick Dependency Check

After installing all dependencies, verify everything is working:

```bash
# Check Python
python3 --version  # Should be 3.13+

# Check uv
uv --version

# Check Node.js and npm
node --version      # Should be 18+
npm --version

# Check Ollama
ollama list         # Should show your installed models
```

## Configuration

The application uses a single environment file for configuration:

- `.env` - All configuration variables
- `.env.example` - Example configuration file

Key configuration options:

- **OLLAMA_MODEL**: The Ollama model to use (default: `granite3.1-dense:8b`)
- **OLLAMA_HOST**: Ollama server URL (default: `http://localhost:11434`)
- **VITE_API_BASE_URL**: Backend API URL for frontend (default: `http://127.0.0.1:8000`)
- **BROWSER_HEADLESS**: Run browser in headless mode (default: `false`)
- **MAX_QUERY_LENGTH**: Maximum query length (default: `500`)

The `make install` command will automatically create `.env` file from the example if it doesn't exist.

## Running the Application

### 1. Install Dependencies

```bash
make install
```

This runs:

- `uv sync` for the backend
- `playwright install chromium` for the backend
- `npm install` for the frontend

### 2. Start the Services

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

## API Documentation

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

## Data & State

- **Chat history DB**: `backend/conversations.db` (SQLite)
- **Browser state**: the backend keeps a single global browser/page (single-user assumption).

## Project Structure

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

## Useful Commands

- `make install` - Install all dependencies and setup environment
- `make setup-env` - Create .env files from examples
- `make backend` - Start the backend server
- `make frontend` - Start the frontend development server
- `make clean` - Clean build artifacts and dependencies

## Environment Variables

All configuration is managed through a single `.env` file at the project root:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `granite3.1-dense:8b` | Ollama model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `HOST` | `127.0.0.1` | Backend server host |
| `PORT` | `8000` | Backend server port |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL for CORS |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend API URL (frontend) |
| `VITE_MAX_QUERY_LENGTH` | `500` | Maximum query length (frontend) |
| `DB_PATH` | `backend/conversations.db` | SQLite database file path |
| `MAX_QUERY_LENGTH` | `500` | Maximum query length (backend) |
| `WIKIPEDIA_BASE` | `https://www.wikipedia.org` | Wikipedia base URL |
| `BROWSER_HEADLESS` | `false` | Run browser in headless mode |
| `BROWSER_TIMEOUT` | `15000` | Browser navigation timeout (ms) |
| `PAGE_TIMEOUT` | `10000` | Page load timeout (ms) |
| `ACTION_TIMEOUT` | `5000` | Browser action timeout (ms) |
| `LOG_LEVEL` | `INFO` | Logging level |

## Troubleshooting

### Installation Issues

- **Python version errors**
  - Ensure you have Python 3.13+: `python3 --version`
  - On some systems, use `python3.13` instead of `python3`
  - Make sure Python is in your PATH

- **uv installation issues**
  - If `pip install uv` fails, try the curl method: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Restart your terminal after installation
  - On Windows, you may need to add uv to your PATH manually

- **Node.js/npm issues**
  - Use Node.js LTS version (18+) for best compatibility
  - If npm is slow, try using a different registry: `npm config set registry https://registry.npmjs.org/`
  - Clear npm cache if having issues: `npm cache clean --force`

- **Ollama installation issues**
  - Make sure Ollama service is running: `ollama serve`
  - If model download fails, check your internet connection and try again
  - On Linux, you may need to add your user to the ollama group

### Runtime Issues

- **Ollama errors / empty responses**
  - Make sure Ollama is running: `ollama serve`
  - Verify the model exists: `ollama list` (should show your configured model)
  - If model is missing: `ollama pull <model-name>` (e.g., `ollama pull granite3.1-dense:8b`)
  - Check Ollama is accessible: `curl http://localhost:11434/api/tags`
  - Verify `OLLAMA_MODEL` in `.env` matches an available model

- **Environment configuration issues**
  - Ensure `.env` file exists: `make setup-env` will create it from example
  - Check `.env` has correct values for your setup
  - Restart services after changing environment variables

- **Playwright browser not launching**
  - Re-run `uv run python -m playwright install chromium` in `backend/`
  - Make sure you have sufficient permissions to launch browsers
  - Try setting `BROWSER_HEADLESS=true` in `.env` if having display issues

- **CORS issues**
  - Update `FRONTEND_URL` in `.env` to match your frontend URL
  - Default allows `http://localhost:5173` only

- **Backend startup issues**
  - Ensure all dependencies are installed: `cd backend && uv sync`
  - Check Python version: `python --version` (should be >= 3.13)
  - Verify uv is installed: `uv --version`
  - Check environment variables are loaded correctly
