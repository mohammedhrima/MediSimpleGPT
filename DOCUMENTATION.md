# ⚕ MediSimpleGPT — Developer Reference & Demo Guide
> Focus: MCP · FastAPI · Playwright · Ollama

Project name: **MediSimpleGPT**

Assistant persona name: **MediSimple**

| | |
|---|---|
| **Stack** | Python · FastAPI · Playwright · Ollama · React · TypeScript |
| **LLM** | granite3.1-dense:8b (local, via Ollama) |
| **Database** | SQLite via aiosqlite |
| **Browser** | Chromium via Playwright (headless=False) |

---

## 1. System Architecture

MediSimple has three independent layers. The React frontend talks only to the FastAPI backend via REST. The MCP server is a **separate process** that exposes browser automation tools to AI agents like Claude Desktop.

| Frontend (React + TypeScript) | Backend (FastAPI — api_server.py) | MCP Server (server.py) |
|---|---|---|
| App.tsx · hooks.ts · axios → REST API | Ollama · Playwright · SQLite · prompts.json | Exposes tools to AI agents via MCP protocol over stdio |

### Chat Request Flow — 7 Steps

Every message the user sends goes through this pipeline in order:

1. React sends `POST /chat` with `{query, session_id}`
2. **Step 1** — Confirm typo suggestion if previous AI message had "Did you mean:". Sets `just_confirmed = True` if a term was confirmed, which forces a fresh Wikipedia search and skips steps 2 and 4.
3. **Step 2** — Follow-up detection LLM call: is this the same topic as before? Runs **before** typo detection to protect follow-up messages (e.g. "explain it like I'm 5") from false-positive typo flags. Skipped if `just_confirmed`.
4. **Step 3** — Greeting check: if "hello/hi/hey" → reply directly, skip everything else.
5. **Step 4** — Typo detection LLM call: is the query a misspelled medical term? **Skipped entirely for follow-ups and confirmed terms.**
6. **Step 5** — If new topic: open Chromium, search Wikipedia, extract article text. Always runs after a confirmation regardless of history.
7. **Step 6** — Send context + history to Ollama → get simplified response.
8. **Step 7** — Save both messages to SQLite, return response to React.

> ⚠️ **Order matters** — Typo detection originally ran before follow-up detection. This caused follow-up messages like "give me more info, explain like I'm 5" to be incorrectly flagged as medical typos. The fix was to run follow-up detection first and gate typo detection behind it.

---

## 2. Backend — api_server.py

### 2.1 Imports

| Import | What it does in this project |
|---|---|
| `fastapi` | Web framework — defines REST endpoints (/chat, /connect, etc.) |
| `CORSMiddleware` | Lets React at localhost:5173 call FastAPI at localhost:8000 |
| `pydantic BaseModel` | Validates request bodies — like TypeScript interfaces but at runtime |
| `ollama` | Talks to the locally-running LLM (no internet required) |
| `aiosqlite` | Async SQLite — reads/writes conversation history without blocking |
| `playwright` | Controls a real Chromium browser to scrape Wikipedia |
| `asynccontextmanager` | Powers the lifespan pattern: run code on startup and shutdown |
| `pathlib.Path` | Cross-platform file paths — `Path("prompts.json")` works on any OS |
| `logging` | Prints timestamped logs to terminal while the server runs |

---

### 2.2 Lifespan — Startup & Shutdown

Old FastAPI used `@app.on_event("startup")` which is now deprecated. The modern pattern is a **lifespan context manager**. It guarantees cleanup runs even if the server crashes.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()     # ← runs ONCE on startup
    load_prompts()      # ← warm the cache
    yield               # ← server is live here
    # everything below runs on SHUTDOWN:
    await current_page.close()
    await browser.close()
    await playwright_instance.stop()

app = FastAPI(lifespan=lifespan)
```

> 📚 **Study This** — "What is a context manager in Python?" — An object with `__enter__` and `__exit__` methods (or async versions). The `async` keyword means it can await I/O. `yield` splits setup (before) from teardown (after). The `with` statement calls `__enter__` on entry and `__exit__` on exit — even if an exception is raised.

---

### 2.3 Global State & the `global` Keyword

Browser state is shared across all requests — one browser for the whole server. In Python you **must** use the `global` keyword to assign to a module-level variable inside a function.

```python
browser: Browser | None = None   # module-level

async def get_or_create_browser():
    global browser, playwright_instance  # needed to ASSIGN
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=False)
    return browser

# Browser | None is Python 3.10+ union type hint
# Same as Optional[Browser] in older Python
```

> ⚠️ **Watch Out** — Global state is fine for a single-user demo. In production with multiple users, you would need a browser pool — one browser context per user session. Otherwise two users could interfere with each other's pages.

---

### 2.4 Prompt System

Prompts live in `prompts.json` and are loaded once at startup into a cache dict. `get_prompt()` fills in variables using Python's built-in `str.format()`.

```python
def get_prompt(prompt_name: str, **variables) -> str:
    template = prompts[prompt_name]["template"]
    return template.format(**variables)
    # Template: "Explain {query} in simple terms"
    # Call:     get_prompt("simplify", query="diabetes")
    # Result:   "Explain diabetes in simple terms"
```

> 📚 **Study This** — "What does `**kwargs` mean?" — Double-star unpacks keyword arguments into a dictionary. `get_prompt("x", query="hi", context="...")` makes `variables = {"query": "hi", "context": "..."}`. Then `template.format(**variables)` passes them as named arguments to the format string. Interviewers test `*args` and `**kwargs` frequently.

---

### 2.5 The LLM Helper

```python
def llm(prompt: str, messages: list | None = None) -> str:
    if messages is None:
        messages = [{"role": "user", "content": prompt}]
    response = ollama.chat(model=MODEL, messages=messages)
    return response["message"]["content"]

# Single prompt:  llm("What is diabetes?")
# Multi-turn:     llm("", messages=[
#                     {"role":"user","content":"What is diabetes?"},
#                     {"role":"assistant","content":"Diabetes is..."},
#                     {"role":"user","content":"What causes it?"}
#                 ])
```

> ℹ️ **How It Works** — Ollama runs the LLM completely locally on your machine. No API key, no internet, no cost per call. It listens on `localhost:11434` by default. `granite3.1-dense:8b` means 8 billion parameters — fast enough on most modern hardware.

> ⚠️ **Watch Out** — `llm()` is a synchronous function called from an async FastAPI endpoint. This blocks the event loop for the duration of the LLM call. Fine for a single-user demo; in production, use `asyncio.to_thread()` or an async Ollama client to avoid blocking other requests.

---

### 2.6 The `just_confirmed` Flag

When a user confirms a typo suggestion (e.g. types "1" after seeing "Did you mean: 1. diabetes"), the backend sets `just_confirmed = True`. This flag controls two things:

```python
just_confirmed = False

# Step 1: confirmation detected → set flag
if result.startswith("CONFIRMED:"):
    query = confirmed_term       # replace "1" with "diabetes"
    just_confirmed = True

# Step 2: skip follow-up detection if just confirmed
if history and not just_confirmed:
    ...  # follow-up detection

# Step 4: skip typo detection if just confirmed
if not is_followup and not just_confirmed:
    ...  # typo detection

# Step 5: Wikipedia always fetched after a confirmation
# (just_confirmed keeps is_followup = False, so this branch always runs)
```

Without this flag, two bugs occur: (1) the confirmed term gets re-checked for typos, and (2) the conversation history makes follow-up detection return `FOLLOW_UP`, so Wikipedia is skipped and the response has no medical context.

---

### 2.7 API Endpoints

| Endpoint | What it does |
|---|---|
| `POST /chat` | Full pipeline: confirm → follow-up → greeting → typo → Wikipedia → LLM → response |
| `POST /connect` | Opens browser to URL, returns visible DOM elements as JSON |
| `POST /plan` | LLM generates a JSON action plan from DOM + instruction |
| `POST /execute` | Runs a plan: fill, click, press, wait actions in the browser |
| `POST /simplify` | Extracts main content from current page and simplifies it |
| `GET /history/{id}` | Returns full conversation for a session from SQLite |
| `DELETE /history/{id}` | Deletes all messages for a session |
| `GET /health` | Returns server status and whether browser is active |

---

## 3. MCP Server — server.py

> ℹ️ **How It Works** — MCP = Model Context Protocol. An open standard created by Anthropic that lets AI models call external tools through a defined interface. Think: REST API, but designed specifically for AI agents to discover and use tools automatically.

### 3.1 What MCP Is and Why It Exists

Before MCP, connecting an AI model to your app meant building a completely custom integration every time. MCP standardizes the interface so any MCP-compatible AI (Claude, Cursor, etc.) can use any MCP server without custom code.

| Without MCP | With MCP |
|---|---|
| Custom REST calls, custom auth, custom JSON parsing — rebuilt for every AI integration | One server definition. Any MCP-compatible AI connects and discovers tools automatically |

---

### 3.2 MCP Core Concepts

#### Tools — Functions the AI Can Call

Every function decorated with `@mcp.tool()` becomes a callable tool. The AI sees the function name, docstring, and parameter types — and uses that to decide when and how to call the tool.

```python
@mcp.tool()
async def connect_browser(url: str) -> str:
    """Connect to a website via CDP"""
    #  ^^^ This docstring is what the AI reads.
    #  It decides to call this tool based on the description.
    #  Bad docstrings = AI calls wrong tools.
    ...
```

> 📚 **Study This** — "How does the AI know which tool to call?" — The MCP client sends the AI a list of all available tools with their names, docstrings, and parameter schemas (auto-generated from type hints). The LLM reads these and picks the best fit. This is why **docstrings in an MCP server are part of the API contract** — not just comments.

#### Resources — Read-Only Data for the AI

Resources are data the AI can read but not modify. Defined with `@mcp.resource()`. In your server, `tasks://list` lets the AI see saved tasks. To change tasks, it must call the `save_task()` tool.

```python
@mcp.resource("tasks://list")
def get_tasks() -> str:
    """Get all saved tasks"""
    return json.dumps(load_tasks(), indent=2)
# The URI "tasks://list" is like a read-only URL the AI can fetch
```

#### Transport — How MCP Communicates

Your server uses **stdio transport**. Claude Desktop launches `server.py` as a subprocess and communicates via stdin/stdout using JSON-RPC messages. You never see this layer — FastMCP handles it.

```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
    # Claude Desktop runs: python server.py
    # Then sends JSON-RPC messages like:
    # {"method":"tools/call","params":{"name":"connect_browser","arguments":{"url":"..."}}}
    # Your function runs and returns a result
    # FastMCP serializes it back to JSON-RPC for the client
```

> 📚 **Study This** — "What transports does MCP support?" — Two options: **stdio** (local process, stdin/stdout, used here) and **SSE/HTTP** (network, for remote or shared servers). Use stdio for local tools running on the same machine as the AI client. Use HTTP/SSE when the server is remote or needs to serve multiple clients simultaneously.

---

### 3.3 FastMCP vs Raw MCP SDK

FastMCP is a high-level wrapper that eliminates boilerplate. Here is the difference:

```python
# ── RAW SDK (lots of boilerplate) ──────────────────────────
server = Server("my-server")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [Tool(
        name="connect_browser",
        description="Connect to a website via CDP",
        inputSchema={"type":"object","properties":{"url":{"type":"string"}}}
    )]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "connect_browser":
        return await connect_browser(arguments["url"])

# ── FASTMCP (just decorate your function) ──────────────────
@mcp.tool()
async def connect_browser(url: str) -> str:
    """Connect to a website via CDP"""
    ...  # FastMCP generates all the schema/routing automatically
```

> 📚 **Study This** — "What does `@mcp.tool()` do internally?" — It is a decorator. `@mcp.tool()` is shorthand for: `connect_browser = mcp.tool()(connect_browser)`. Inside, FastMCP uses Python's `inspect` module to read the function signature and type hints, builds the JSON schema, and registers it in an internal tool registry that the MCP protocol layer can query.

---

### 3.4 Your MCP Tools — Explained

#### `connect_browser`

```python
async def connect_browser(url: str) -> str:
    global browser, page, playwright_instance
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=False)
    page = await browser.new_page()
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    return f"Connected to {url}"
```

Launches a real visible Chromium window. `networkidle` waits until no network requests for 500ms — good for React/Vue SPAs that load data after the initial HTML.

#### `get_dom`

Injects JavaScript into the live page to extract all visible interactive elements. Returns JSON so the AI can reason about what it sees and decide which elements to interact with.

```python
# page.evaluate() runs JavaScript inside the real browser
# and returns the result to Python as a dict/list

# The JS script:
# 1. Finds all a, button, input, textarea, select, li
# 2. Gets each element's bounding rect (position + size)
# 3. Filters out elements with width=0 or height=0 (hidden)
# 4. Returns array of {index, tag, text, id, class, href, ...}
```

> 📚 **Study This** — "What is `page.evaluate()`?" — It executes JavaScript code inside the browser page and returns the result to Python. The JS runs in the browser context with full access to `document`, `window`, and DOM APIs. Your DOM extraction runs entirely in the browser — Python just receives the final JSON array. This is one of the most powerful Playwright features.

#### `click_best_result`

The smartest tool — calls `analyze_page()` to get search results, then scores each result against the search term using keyword matching.

```python
# Scoring algorithm (simplified TF matching):
score = sum(1 for word in search_lower.split() if word in text)
# search_term = "diabetes type 2"
# result: "Diabetes type 2 — causes and treatment" → score = 3
# result: "Diabetes insipidus"                     → score = 1
# → clicks the first result
```

> 📚 **Study This** — "What ranking algorithm does this use?" — Term frequency matching: count how many search words appear in the result text. A production system would use **BM25** (better term weighting), or **semantic search** (embeddings/cosine similarity) for meaning-based matching instead of exact keyword matching.

#### `execute_task` — Known Bug ⚠️

```python
# BUG: wait_for_element() is not defined anywhere in server.py
elif action["type"] == "wait":
    result = await wait_for_element(action.get("selector", "body"))
    #             ^^^^^^^^^^^^^^^^ NameError at runtime

# Fix: replace with page.wait_for_selector() or page.wait_for_timeout()
```

> ⚠️ **Watch Out** — If an interviewer runs this code and triggers a wait action, it crashes with `NameError`. Mentioning this bug **proactively** in the demo shows code awareness and attention to detail.

---

## 4. Playwright — Browser Automation

### 4.1 Core Concepts

| Concept | Explanation |
|---|---|
| `playwright_instance` | The Playwright engine process — start once, stop on shutdown |
| `browser` | A browser process (Chromium). One browser can have many pages |
| `page` | One browser tab. All interactions happen through page methods |
| `page.goto(url)` | Navigate to a URL — like typing in the address bar |
| `page.fill(sel, val)` | Type text into an input matching the CSS selector |
| `page.click(sel)` | Click an element matching the CSS selector |
| `page.press(sel, key)` | Press a keyboard key while focused on the element |
| `page.evaluate(js)` | Run JavaScript in the browser, return result to Python |
| `wait_for_load_state` | Wait until: `"load"`, `"domcontentloaded"`, or `"networkidle"` |
| `wait_for_selector` | Wait until a specific element appears/becomes visible |
| `wait_for_timeout` | Pause for a fixed number of milliseconds |

### 4.2 Selectors

```python
# CSS by attribute (used in your code):
await page.fill('input[name="search"]', query)

# By ID:
await page.click("#submit-btn")

# Playwright text selector:
await page.click("button:has-text('Search')")

# By placeholder:
await page.fill('[placeholder="Search Wikipedia"]', query)
```

> 📚 **Study This** — "What is the difference between `domcontentloaded` and `networkidle`?" — `domcontentloaded` fires when the HTML is parsed and DOM is ready (fast, ~200ms). `networkidle` fires when there are no more than 0 network connections for 500ms (slow, ~2-5s, but thorough). Use `domcontentloaded` for simple pages, `networkidle` for React/Vue SPAs that load data after mount.

---

## 5. Python for Full-Stack Devs

You already know backend concepts. This section maps Python specifics to things you already know from JavaScript.

### 5.1 Async/Await

Same concept as JavaScript — Python uses `asyncio` under the hood instead of the Node.js event loop. FastAPI handles the event loop for you.

```python
# JavaScript:                    # Python:
async function getData() {        async def get_data():
  const r = await fetch(url)          async with aiohttp.ClientSession() as s:
  return r.json()                         async with s.get(url) as r:
}                                              return await r.json()
```

> 📚 **Study This** — "What is the GIL?" — Python's Global Interpreter Lock prevents true parallel execution of threads. This is why `async/await` (cooperative concurrency) is preferred for I/O-bound work — when one coroutine is waiting for I/O, others can run. For CPU-bound work, use `multiprocessing` to bypass the GIL.

### 5.2 Type Hints

```python
# TypeScript:                    # Python 3.10+:
function greet(                   def greet(
  name: string,                       name: str,
  count: number | null                count: int | None
): string { }                     ) -> str: ...

# Array of objects:               # Python:
Message[]                          list[dict]
Record<string, any>                dict[str, any]
```

### 5.3 Pydantic — Python's Zod

```python
# TypeScript + Zod:               # Python + Pydantic:
const TaskSchema = z.object({     class TaskRequest(BaseModel):
  instruction: z.string(),            instruction: str
  dom: z.string(),                    dom: str
})

# FastAPI validates incoming JSON automatically when you use BaseModel
# If instruction is missing from the request → 422 Unprocessable Entity
```

### 5.4 async with — Context Managers

```python
# async with guarantees cleanup even on error
async with aiosqlite.connect(DB_PATH) as db:
    # db is open here
    await db.execute("INSERT ...")
    await db.commit()
# db is automatically closed here — even if an exception was raised

# JavaScript equivalent:
# const db = await open(DB_PATH)
# try { ... } finally { await db.close() }
```

### 5.5 The `global` Keyword

```python
browser = None   # module-level variable

async def init():
    global browser   # required to ASSIGN to browser
    browser = await playwright.chromium.launch()

async def use():
    # No global needed here — just reading
    if browser:
        page = await browser.new_page()
```

---

## 6. Database — SQLite & aiosqlite

### 6.1 Schema

```sql
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,   -- browser localStorage ID
    role        TEXT    NOT NULL,   -- "user" or "assistant"
    content     TEXT    NOT NULL,   -- message text
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
)

-- To query conversation history:
SELECT role, content FROM messages
WHERE session_id = ?
ORDER BY id DESC LIMIT 6
-- Returns last 6 messages, Python reverses them to chronological order
```

### 6.2 Why Parameterized Queries

```python
# NEVER do this — SQL injection vulnerability:
db.execute(f"SELECT * FROM messages WHERE id = {user_input}")
# If user_input = "1; DROP TABLE messages" → database wiped

# ALWAYS do this — parameterized query:
db.execute("SELECT * FROM messages WHERE id = ?", (user_input,))
# The ? is a placeholder. The driver escapes user_input safely.
# Injection attempt becomes harmless literal text.
```

> 📚 **Study This** — "What is SQL injection and how do you prevent it?" — SQL injection happens when user input is inserted directly into a SQL string, letting attackers run arbitrary SQL. Prevention: always use parameterized queries (`?` placeholders). The database driver escapes the values so they can never be interpreted as SQL code. Your codebase already does this correctly.

---

## 7. Interview Prep — Likely Questions

### MCP Questions

**Q: What is MCP and why was it created?**
A: Model Context Protocol is an open standard by Anthropic for connecting AI models to external tools and data sources. It standardizes what was previously custom-built each time — one server definition works with any MCP-compatible AI client.

**Q: What are the three MCP primitives?**
A: **Tools** (functions the AI can call that change state), **Resources** (read-only data the AI can access, like a GET endpoint), and **Prompts** (reusable prompt templates the user or AI can invoke).

**Q: How does the AI decide which tool to use?**
A: The MCP client sends the AI a list of tools with their names, docstrings, and parameter schemas. The LLM reads these descriptions and picks the tool that best matches the task. This is why clear, specific docstrings in `server.py` are critical — they are the API contract the AI reads.

**Q: What is the difference between stdio and HTTP transport?**
A: `stdio` launches the server as a subprocess and communicates via stdin/stdout JSON-RPC — simpler, more secure, local only. HTTP/SSE exposes the server over a network port — needed when the server is remote or must serve multiple clients at once.

**Q: What does `@mcp.tool()` do?**
A: It is a decorator that registers the function as an MCP tool. FastMCP introspects the function signature, type hints, and docstring to auto-generate the JSON schema. It is equivalent to: `connect_browser = mcp.tool()(connect_browser)`.

---

### FastAPI / Python Questions

**Q: What is a decorator in Python?**
A: A function that wraps another function. `@app.post("/chat")` is equivalent to: `chat = app.post("/chat")(chat)`. It adds behavior (routing, registration) without modifying the original function body.

**Q: What does CORS middleware do?**
A: Adds headers to responses that tell browsers to allow cross-origin requests. Without it, the browser blocks requests from `localhost:5173` (React) to `localhost:8000` (FastAPI) because different ports count as different "origins".

**Q: Sync vs async functions in FastAPI?**
A: Async functions run directly on the event loop — use for I/O (DB, HTTP, browser). Sync functions block the thread — FastAPI runs them in a thread pool. Prefer `async` when using `aiosqlite`, Playwright, or `aiohttp`.

**Q: What would you change to make this production-ready?**
A: Replace global browser with a per-session browser pool; add authentication (JWT or OAuth); switch from SQLite to PostgreSQL; add rate limiting; use streaming LLM responses; wrap synchronous `llm()` calls in `asyncio.to_thread()` to avoid blocking the event loop; deploy frontend/backend separately; add error tracking (Sentry).

**Q: Why does the pipeline run follow-up detection before typo detection?**
A: To avoid false positives. Typo detection is tuned for short medical terms (1–4 words). Follow-up messages like "explain it to me like I'm 5" are longer but contain non-standard phrasing that can confuse the typo detector. By checking follow-up status first and gating typo detection behind it, we ensure the typo check only runs on fresh, standalone queries where it is actually useful.

---

### Playwright Questions

**Q: What is `page.evaluate()`?**
A: Executes JavaScript in the browser page and returns the result to Python. The JS runs in the browser context with full DOM access. In your project it extracts visible elements and Wikipedia text — all the actual scraping happens in the browser, Python just receives the result.

**Q: What is the difference between headless and headful?**
A: `headless=True` runs the browser with no visible window (faster, used in CI/CD). `headless=False` (your project) opens a real visible browser window — great for demos and debugging because you can watch exactly what the automation is doing.

**Q: What is `networkidle`?**
A: A load state that waits until there have been 0 network connections for at least 500ms. Used for SPAs that make AJAX calls after the initial HTML loads. Slower than `domcontentloaded` but more reliable for dynamic pages.

---

*End of Document*