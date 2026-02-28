from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ollama
import json
import logging
import aiosqlite
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global browser state
browser: Browser | None = None
page: Page | None = None
playwright_instance = None

# Database
DB_PATH = "conversations.db"

# Load prompts
PROMPTS_FILE = Path("prompts.json")


def load_prompts():
    """Load prompts from JSON file"""
    if PROMPTS_FILE.exists():
        return json.loads(PROMPTS_FILE.read_text())
    logger.error("prompts.json not found")
    return {}


def get_prompt(prompt_name: str, **variables) -> str:
    """Get a prompt template and fill in variables"""
    prompts = load_prompts()
    if prompt_name not in prompts:
        logger.error(f"Prompt '{prompt_name}' not found")
        return ""
    
    template = prompts[prompt_name]["template"]
    return template.format(**variables)


async def init_db():
    """Initialize SQLite database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def get_session_history(session_id: str, limit: int = 6):
    """Get conversation history for a session"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


async def save_message(session_id: str, role: str, content: str):
    """Save a message to the database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        await db.commit()


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("Database initialized")


class TaskRequest(BaseModel):
    instruction: str
    dom: str


class ExecuteRequest(BaseModel):
    actions: str
    url: str


@app.post("/connect")
async def connect_browser(request: dict):
    """Connect to a website"""
    global browser, page, playwright_instance
    
    try:
        url = request.get('url')
        if not url:
            logger.error("No URL provided")
            return {"error": "URL is required"}
        
        logger.info(f"Connecting to {url}")
        
        if not playwright_instance:
            playwright_instance = await async_playwright().start()
            browser = await playwright_instance.chromium.launch(headless=False)
            logger.info("Browser launched")
        
        page = await browser.new_page()
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        logger.info(f"Page loaded: {url}")
        
        # Extract DOM
        dom = await page.evaluate("""() => {
            const elements = [];
            document.querySelectorAll('a, button, input, textarea, select, li').forEach((el, idx) => {
                const rect = el.getBoundingClientRect();
                elements.push({
                    index: idx,
                    tag: el.tagName,
                    text: el.innerText?.slice(0, 50) || el.value || '',
                    type: el.type || '',
                    id: el.id || '',
                    name: el.name || '',
                    class: el.className || '',
                    placeholder: el.placeholder || '',
                    href: el.href || '',
                    ariaLabel: el.ariaLabel || '',
                    visible: rect.width > 0 && rect.height > 0
                });
            });
            return elements.filter(el => el.visible);
        }""")
        
        logger.info(f"Extracted {len(dom)} visible elements")
        return {"status": "connected", "dom": dom}
        
    except PlaywrightTimeout:
        logger.error(f"Timeout loading {url}")
        return {"error": "Page load timeout"}
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return {"error": str(e)}


@app.post("/plan")
async def plan_task(request: TaskRequest):
    """Use LLM to plan actions based on DOM and instruction"""
    
    try:
        logger.info(f"Planning task: {request.instruction}")
        
        prompt = get_prompt("action_planning", dom=request.dom, instruction=request.instruction)
        
        response = ollama.chat(
            model='granite3.1-dense:8b',
            messages=[{'role': 'user', 'content': prompt}]
        )
        
        plan = response['message']['content']
        logger.info(f"Plan generated: {plan[:100]}...")
        return {"plan": plan}
        
    except Exception as e:
        logger.error(f"Planning error: {str(e)}")
        return {"error": str(e)}


@app.post("/execute")
async def execute_actions(request: ExecuteRequest):
    """Execute actions in the real browser"""
    global page
    
    try:
        if not page:
            logger.error("No browser connected")
            return {"error": "No browser connected"}
        
        logger.info("Executing actions")
        
        # Parse actions
        actions_text = request.actions
        start = actions_text.find('[')
        end = actions_text.rfind(']') + 1
        if start >= 0 and end > start:
            actions_text = actions_text[start:end]
        
        actions = json.loads(actions_text)
        results = []
        
        for i, action in enumerate(actions):
            action_type = action.get('type')
            selector = action.get('selector', '')
            value = action.get('value', '')
            
            logger.info(f"Action {i+1}: {action_type} {selector}")
            
            try:
                if action_type == 'fill':
                    await page.fill(selector, value)
                    await page.wait_for_timeout(500)
                    results.append(f"✓ Filled {selector}")
                    
                elif action_type == 'click':
                    await page.click(selector, timeout=5000)
                    results.append(f"✓ Clicked {selector}")
                    
                elif action_type == 'wait':
                    if selector:
                        await page.wait_for_selector(selector, state='visible', timeout=3000)
                        results.append(f"✓ Waited for {selector}")
                    else:
                        await page.wait_for_timeout(1000)
                        results.append("✓ Waited 1s")
                        
            except PlaywrightTimeout:
                error_msg = f"✗ Timeout: {action_type} {selector}"
                logger.error(error_msg)
                results.append(error_msg)
            except Exception as e:
                error_msg = f"✗ Error: {action_type} {selector} - {str(e)}"
                logger.error(error_msg)
                results.append(error_msg)
        
        logger.info(f"Execution complete: {len(results)} actions")
        return {"status": "success", "results": results}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {str(e)}")
        return {"status": "error", "message": "Invalid action format"}
    except Exception as e:
        logger.error(f"Execution error: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.post("/simplify")
async def simplify_article(request: dict):
    """Extract article content and simplify for non-medical audience"""
    global page
    
    try:
        if not page:
            logger.error("No browser connected")
            return {"error": "No browser connected"}
        
        logger.info("Extracting article content")
        
        # Extract main article content
        content = await page.evaluate("""() => {
            // Try common article selectors
            const selectors = [
                'article',
                '[role="main"]',
                '.article-content',
                '.content',
                'main',
                '#content'
            ];
            
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (el && el.innerText.length > 200) {
                    return el.innerText;
                }
            }
            
            // Fallback to body
            return document.body.innerText;
        }""")
        
        if not content or len(content) < 100:
            return {"error": "Could not extract article content"}
        
        # Limit content length
        content = content[:3000]
        logger.info(f"Extracted {len(content)} characters")
        
        # Simplify using LLM
        prompt = get_prompt("article_simplification", content=content)
        
        response = ollama.chat(
            model='granite3.1-dense:8b',
            messages=[{'role': 'user', 'content': prompt}],
            stream=False
        )
        
        simplified = response['message']['content']
        logger.info("Article simplified")
        
        return {"simplified": simplified}
        
    except Exception as e:
        logger.error(f"Simplification error: {str(e)}")
        return {"error": str(e)}


@app.post("/chat")
async def chat(request: dict):
    """Handle chat queries - search Wikipedia and simplify"""
    global browser, page, playwright_instance
    
    try:
        query = request.get('query', '')
        session_id = request.get('session_id', 'default')
        history = await get_session_history(session_id)
        
        if not query:
            return {"error": "Query is required"}
        
        logger.info(f"Chat query: {query}")
        
        # Check if this is a confirmation of a previous suggestion
        if len(history) > 0:
            last_assistant = next((msg for msg in reversed(history) if msg['role'] == 'assistant'), None)
            if last_assistant and 'Did you mean:' in last_assistant['content']:
                # Check if user is confirming
                confirmation_prompt = get_prompt("confirmation_detection", 
                                                query=query, 
                                                suggestion=last_assistant['content'])
                
                confirmation_response = ollama.chat(
                    model='granite3.1-dense:8b',
                    messages=[{'role': 'user', 'content': confirmation_prompt}],
                    stream=False
                )
                
                confirmation_result = confirmation_response['message']['content'].strip()
                
                if confirmation_result.startswith('CONFIRMED:'):
                    # Extract the confirmed term
                    confirmed_term = confirmation_result.replace('CONFIRMED:', '').strip()
                    logger.info(f"User confirmed: {confirmed_term}")
                    query = confirmed_term  # Replace query with confirmed term
                    
                    # Save confirmation to history
                    await save_message(session_id, 'user', f"Yes, I meant {confirmed_term}")
        
        # First, check for typos and ask for clarification
        typo_check_prompt = get_prompt("typo_detection", query=query)
        
        typo_response = ollama.chat(
            model='granite3.1-dense:8b',
            messages=[{'role': 'user', 'content': typo_check_prompt}],
            stream=False
        )
        
        typo_result = typo_response['message']['content'].strip()
        
        # If typo detected, ask for clarification
        if typo_result.startswith('TYPO:'):
            clarification = typo_result.replace('TYPO:', '').strip()
            logger.info(f"Typo detected: {clarification}")
            
            # Save to history
            await save_message(session_id, 'user', query)
            await save_message(session_id, 'assistant', clarification)
            
            return {"response": clarification}
        
        # Check if this is a follow-up question
        is_followup = len(history) > 0 and any(
            word in query.lower() 
            for word in ['more', 'explain', 'what', 'how', 'why', 'tell me', 'can you']
        )
        
        # Only search Wikipedia for new topics
        if not is_followup:
            # Initialize browser if needed
            if not playwright_instance:
                playwright_instance = await async_playwright().start()
                browser = await playwright_instance.chromium.launch(headless=False)
            
            # Navigate to Wikipedia
            page = await browser.new_page()
            await page.goto('https://www.wikipedia.org', wait_until='domcontentloaded', timeout=10000)
            logger.info("Connected to Wikipedia")
            
            # Search
            await page.fill('input[name="search"]', query)
            await page.wait_for_timeout(500)
            await page.press('input[name="search"]', 'Enter')
            await page.wait_for_load_state('domcontentloaded')
            logger.info(f"Searched for: {query}")
            
            # Extract article content
            content = await page.evaluate("""() => {
                const article = document.querySelector('#mw-content-text');
                if (article) {
                    const paragraphs = article.querySelectorAll('p');
                    let text = '';
                    for (let i = 0; i < Math.min(5, paragraphs.length); i++) {
                        text += paragraphs[i].innerText + '\\n\\n';
                    }
                    return text;
                }
                return document.body.innerText;
            }""")
            
            if not content or len(content) < 100:
                return {"response": "I couldn't find relevant information. Could you rephrase your question?"}
            
            content = content[:2000]
            logger.info(f"Extracted {len(content)} characters")
            
            # Build context with history
            context = f"Wikipedia article:\n{content}\n\n"
        else:
            # Use conversation history for follow-up
            context = "Previous conversation:\n"
            for msg in history[-4:]:  # Last 2 exchanges
                context += f"{msg['role']}: {msg['content']}\n"
            context += "\n"
        
        # Build conversation history for LLM
        messages = []
        for msg in history[-6:]:  # Last 3 exchanges
            messages.append({
                'role': 'user' if msg['role'] == 'user' else 'assistant',
                'content': msg['content']
            })
        
        # Add current query
        prompt = get_prompt("simplification", context=context, query=query)
        
        messages.append({'role': 'user', 'content': prompt})
        
        response = ollama.chat(
            model='granite3.1-dense:8b',
            messages=messages,
            stream=False
        )
        
        simplified = response['message']['content']
        logger.info("Response generated")
        
        # Save to conversation history
        await save_message(session_id, 'user', query)
        await save_message(session_id, 'assistant', simplified)
        
        return {"response": simplified}
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return {"response": "I encountered an error. Please try again."}


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Get conversation history for a session"""
    try:
        messages = await get_session_history(session_id, limit=100)
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        return {"messages": []}


@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """Clear conversation history for a session"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.commit()
        logger.info(f"Cleared history for session: {session_id}")
        return {"status": "cleared"}
    except Exception as e:
        logger.error(f"Error clearing history: {str(e)}")
        return {"error": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok", "browser_connected": page is not None}
