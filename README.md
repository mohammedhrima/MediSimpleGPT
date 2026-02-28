# DOM Handler - Autonomous Web Agent

AI agent that autonomously operates websites via Chrome DevTools Protocol.

## Setup (< 5 min)

```bash
make install
```

## Run

Terminal 1:
```bash
make backend
```

Terminal 2:
```bash
make frontend
```

## Architecture

- **Backend**: Python MCP server + FastAPI + Playwright (CDP)
- **Frontend**: React + TypeScript
- **LLM**: Ollama (granite3.1-dense:8b)

## How it works

1. Connect to website via CDP
2. Extract DOM structure
3. LLM plans action sequence
4. Execute actions autonomously
