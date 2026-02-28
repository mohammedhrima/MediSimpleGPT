from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ollama
import json
import logging
import aiosqlite
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
DB_PATH = "conversations.db"
PROMPTS_FILE = Path("prompts.json")
MODEL = "granite3.1-dense:8b"
MAX_QUERY_LENGTH = 500
WIKIPEDIA_BASE = "https://www.wikipedia.org"

# ─────────────────────────────────────────────
# Prompt cache (loaded once at startup)
# ─────────────────────────────────────────────
_prompts_cache: dict = {}


def load_prompts() -> dict:
    """Load and cache prompts from JSON file."""
    global _prompts_cache
    if not _prompts_cache:
        if PROMPTS_FILE.exists():
            _prompts_cache = json.loads(PROMPTS_FILE.read_text())
            logger.info(f"Loaded {len(_prompts_cache)} prompts")
        else:
            logger.error("prompts.json not found")
    return _prompts_cache


def get_prompt(prompt_name: str, **variables) -> str:
    """Return a filled prompt template."""
    prompts = load_prompts()
    if prompt_name not in prompts:
        logger.error(f"Prompt '{prompt_name}' not found")
        return ""
    template = prompts[prompt_name]["template"]
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.error(f"Missing variable {e} for prompt '{prompt_name}'")
        return ""


def llm(prompt: str, messages: list | None = None) -> str:
    """Call the LLM. Optionally pass a full message list for multi-turn conversations."""
    if messages is None:
        messages = [{"role": "user", "content": prompt}]
    response = ollama.chat(model=MODEL, messages=messages, stream=False)
    return response["message"]["content"]


# ─────────────────────────────────────────────
# Global browser state (single-user assumption)
# ─────────────────────────────────────────────
browser: Browser | None = None
current_page: Page | None = None          # renamed to avoid shadowing builtins
playwright_instance = None


async def get_or_create_browser() -> Browser:
    """Lazily initialize the browser."""
    global browser, playwright_instance
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=False)
        logger.info("Browser launched")
    return browser


async def new_page() -> Page:
    """Open a fresh page, closing the previous one to avoid leaks."""
    global current_page
    b = await get_or_create_browser()
    if current_page:
        try:
            await current_page.close()
        except Exception:
            pass
    current_page = await b.new_page()
    return current_page


# ─────────────────────────────────────────────
# Database helpers
# ─────────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def get_session_history(session_id: str, limit: int = 6) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


async def save_message(session_id: str, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        await db.commit()


# ─────────────────────────────────────────────
# Lifespan (replaces deprecated on_event)
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    load_prompts()          # warm the cache
    logger.info("Startup complete")
    yield
    # Cleanup
    global browser, playwright_instance, current_page
    if current_page:
        await current_page.close()
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()
    logger.info("Shutdown complete")


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────
class TaskRequest(BaseModel):
    instruction: str
    dom: str


class ExecuteRequest(BaseModel):
    actions: str
    url: str


# ─────────────────────────────────────────────
# DOM extraction helper
# ─────────────────────────────────────────────
DOM_SCRIPT = """() => {
    const elements = [];
    document.querySelectorAll('a, button, input, textarea, select, li').forEach((el, idx) => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            elements.push({
                index: idx,
                tag: el.tagName,
                text: el.innerText?.slice(0, 80) || el.value || '',
                type: el.type || '',
                id: el.id || '',
                name: el.name || '',
                class: el.className || '',
                placeholder: el.placeholder || '',
                href: el.href || '',
                ariaLabel: el.ariaLabel || '',
            });
        }
    });
    return elements;
}"""


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.post("/connect")
async def connect_browser(request: dict):
    """Connect to a website and return visible DOM elements."""
    url = request.get("url", "").strip()
    if not url:
        return {"error": "URL is required"}

    try:
        logger.info(f"Navigating to {url}")
        page = await new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)

        dom = await page.evaluate(DOM_SCRIPT)
        logger.info(f"Extracted {len(dom)} visible elements")
        return {"status": "connected", "dom": dom}

    except PlaywrightTimeout:
        logger.error(f"Timeout loading {url}")
        return {"error": "Page load timed out. Please check the URL and try again."}
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return {"error": str(e)}


@app.post("/plan")
async def plan_task(request: TaskRequest):
    """Use LLM to plan browser actions from DOM + instruction."""
    try:
        logger.info(f"Planning: {request.instruction}")
        prompt = get_prompt("action_planning", dom=request.dom, instruction=request.instruction)
        plan = llm(prompt)
        logger.info(f"Plan: {plan[:120]}...")
        return {"plan": plan}
    except Exception as e:
        logger.error(f"Planning error: {e}")
        return {"error": str(e)}


@app.post("/execute")
async def execute_actions(request: ExecuteRequest):
    """Execute a JSON action plan in the browser."""
    if not current_page:
        return {"error": "No browser connected. Call /connect first."}

    try:
        # Robustly extract JSON array from LLM output
        raw = request.actions
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start < 0 or end <= start:
            return {"status": "error", "message": "No JSON array found in actions"}

        actions: list[dict] = json.loads(raw[start:end])
        results = []

        for i, action in enumerate(actions):
            action_type = action.get("type", "")
            selector = action.get("selector", "")
            value = action.get("value", "")
            key = action.get("key", "Enter")

            logger.info(f"Action {i+1}/{len(actions)}: {action_type} | {selector}")

            try:
                if action_type == "fill":
                    await current_page.fill(selector, value, timeout=5000)
                    await current_page.wait_for_timeout(300)
                    results.append(f"✓ Filled '{selector}' with '{value}'")

                elif action_type == "click":
                    await current_page.click(selector, timeout=5000)
                    await current_page.wait_for_timeout(300)
                    results.append(f"✓ Clicked '{selector}'")

                elif action_type == "press":
                    await current_page.press(selector, key, timeout=5000)
                    results.append(f"✓ Pressed '{key}' on '{selector}'")

                elif action_type == "wait":
                    if selector:
                        await current_page.wait_for_selector(selector, state="visible", timeout=5000)
                        results.append(f"✓ Element visible: '{selector}'")
                    else:
                        await current_page.wait_for_timeout(800)
                        results.append("✓ Waited 800ms")

                else:
                    results.append(f"⚠ Unknown action type: '{action_type}'")

            except PlaywrightTimeout:
                results.append(f"✗ Timeout on {action_type} '{selector}'")
            except Exception as e:
                results.append(f"✗ Error on {action_type} '{selector}': {e}")

        logger.info(f"Execution complete: {len(results)} steps")
        return {"status": "success", "results": results}

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return {"status": "error", "message": f"Invalid action JSON: {e}"}
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/simplify")
async def simplify_article(request: dict):
    """Extract and simplify the current page's article content."""
    if not current_page:
        return {"error": "No browser connected."}

    try:
        content = await current_page.evaluate("""() => {
            const selectors = ['article', '[role=\"main\"]', '.article-content', '.content', 'main', '#content'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.innerText.length > 200) return el.innerText;
            }
            return document.body.innerText;
        }""")

        if not content or len(content) < 100:
            return {"error": "Could not extract meaningful article content from this page."}

        content = content[:4000]   # increased cap for richer context
        logger.info(f"Extracted {len(content)} chars for simplification")

        prompt = get_prompt("article_simplification", content=content)
        simplified = llm(prompt)
        return {"simplified": simplified}

    except Exception as e:
        logger.error(f"Simplification error: {e}")
        return {"error": str(e)}


@app.post("/chat")
async def chat(request: dict):
    """Main chat endpoint — detects typos, searches Wikipedia, returns simplified answers."""
    query: str = request.get("query", "").strip()
    session_id: str = request.get("session_id", "default")

    if not query:
        return {"error": "Query is required"}

    # Hard limit on input length
    if len(query) > MAX_QUERY_LENGTH:
        return {"response": "Your question is a bit long. Could you shorten it so I can help better?"}

    try:
        history = await get_session_history(session_id)

        # ── Step 1: Confirmation check (if last reply contained a suggestion) ──
        just_confirmed = False  # flag to force Wikipedia search, bypassing follow-up detection
        if history:
            last_assistant = next((m for m in reversed(history) if m["role"] == "assistant"), None)
            if last_assistant and "Did you mean:" in last_assistant["content"]:
                confirm_prompt = get_prompt(
                    "confirmation_detection",
                    suggestion=last_assistant["content"],
                    query=query,
                )
                result = llm(confirm_prompt).strip()
                if result.startswith("CONFIRMED:"):
                    confirmed_term = result.replace("CONFIRMED:", "").strip()
                    logger.info(f"Confirmed term: {confirmed_term}")
                    await save_message(session_id, "user", query)
                    query = confirmed_term  # proceed with the corrected term
                    just_confirmed = True  # must fetch Wikipedia fresh, not treat as follow-up

        # ── Step 2: Follow-up detection (runs before typo check to protect follow-up messages) ──
        is_followup = False
        if history and not just_confirmed:  # confirmed terms always need a fresh Wikipedia fetch
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
            followup_prompt = get_prompt("followup_detection", history=history_text, query=query)
            followup_result = llm(followup_prompt).strip()
            is_followup = followup_result == "FOLLOW_UP"
            logger.info(f"Follow-up: {is_followup}")

        # ── Step 3: Greeting detection — respond directly, skip Wikipedia entirely ──
        GREETINGS = {
            "hi", "hello", "hey", "hiya", "howdy", "greetings", "sup", "whats up",
            "what's up", "good morning", "good afternoon", "good evening", "good day",
            "morning", "afternoon", "evening", "yo", "helo", "hii", "hiii", "heya",
        }
        if query.lower().strip("! .,?") in GREETINGS:
            greeting_reply = (
                "Hello! I'm **MediSimple**, your friendly medical information assistant.\n\n"
                "I can help you understand medical conditions, symptoms, medications, and health "
                "topics in plain, simple language. Just ask me anything — like *What is diabetes?* "
                "or *How does the heart work?*\n\n"
                "What would you like to know about today?"
            )
            await save_message(session_id, "user", query)
            await save_message(session_id, "assistant", greeting_reply)
            return {"response": greeting_reply}

        # ── Step 4: Typo detection (skip for follow-ups and confirmed terms) ──
        # Follow-up messages like "explain it to me like I'm 5" can false-positive as typos.
        if not is_followup and not just_confirmed:
            typo_prompt = get_prompt("typo_detection", query=query)
            typo_result = llm(typo_prompt).strip()

            if typo_result.startswith("TYPO:"):
                clarification = typo_result.replace("TYPO:", "").strip()
                logger.info(f"Typo flagged: {clarification}")
                await save_message(session_id, "user", query)
                await save_message(session_id, "assistant", clarification)
                return {"response": clarification}

        # ── Step 5: Fetch Wikipedia for new topics ──
        if not is_followup:
            page = await new_page()
            try:
                await page.goto(WIKIPEDIA_BASE, wait_until="domcontentloaded", timeout=15000)
                await page.fill('input[name="search"]', query)
                await page.wait_for_timeout(400)
                await page.press('input[name="search"]', "Enter")
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                logger.info(f"Wikipedia searched for: {query}")

                content = await page.evaluate("""() => {
                    const article = document.querySelector('#mw-content-text');
                    if (!article) return document.body.innerText;
                    const paras = article.querySelectorAll('p');
                    let text = '';
                    for (let i = 0; i < Math.min(8, paras.length); i++) {
                        text += paras[i].innerText + '\\n\\n';
                    }
                    return text;
                }""")

            except PlaywrightTimeout:
                logger.error("Wikipedia load timeout")
                return {"response": "I had trouble reaching Wikipedia. Please try again in a moment."}

            if not content or len(content) < 100:
                return {"response": "I couldn't find reliable information on that topic. Could you rephrase your question?"}

            context = f"Wikipedia article:\n{content[:2500]}\n\n"

        else:
            # Build context from recent conversation
            context = "Previous conversation:\n"
            for msg in history[-4:]:
                context += f"{msg['role'].capitalize()}: {msg['content']}\n"
            context += "\n"

        # ── Step 6: Build LLM message list and generate response ──
        messages = [
            {"role": ("user" if m["role"] == "user" else "assistant"), "content": m["content"]}
            for m in history[-6:]
        ]
        messages.append({
            "role": "user",
            "content": get_prompt("simplification", context=context, query=query),
        })

        response_text = llm("", messages=messages)
        logger.info("Response generated")

        # ── Step 7: Persist ──
        await save_message(session_id, "user", query)
        await save_message(session_id, "assistant", response_text)

        return {"response": response_text}

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return {"response": "Something went wrong on my end. Please try again."}


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    try:
        messages = await get_session_history(session_id, limit=100)
        return {"messages": messages}
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        return {"messages": []}


@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.commit()
        return {"status": "cleared"}
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        return {"error": str(e)}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "browser_connected": current_page is not None,
        "model": MODEL,
    }