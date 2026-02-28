from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Browser, Page
import json
from pathlib import Path

mcp = FastMCP("dom-handler")

# State
browser: Browser | None = None
page: Page | None = None
playwright_instance = None

# Task storage
TASKS_FILE = Path("tasks.json")


def load_tasks():
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text())
    return []


def save_tasks(tasks):
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


@mcp.resource("tasks://list")
def get_tasks() -> str:
    """Get all saved tasks"""
    return json.dumps(load_tasks(), indent=2)


@mcp.tool()
async def connect_browser(url: str) -> str:
    """Connect to a website via CDP"""
    global browser, page, playwright_instance
    
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=False)
    
    page = await browser.new_page()
    await page.goto(url)
    await page.wait_for_load_state('networkidle')
    
    return f"Connected to {url}"


@mcp.tool()
async def get_dom() -> str:
    """Get the current page DOM structure"""
    if not page:
        return json.dumps({"error": "No browser connected"})
    
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
    
    return json.dumps(dom)


@mcp.tool()
async def click_element(selector: str) -> str:
    """Click an element by CSS selector"""
    if not page:
        return "No browser connected"
    
    await page.click(selector, timeout=5000)
    return f"Clicked {selector}"


@mcp.tool()
async def fill_input(selector: str, value: str) -> str:
    """Fill an input field"""
    if not page:
        return "No browser connected"
    
    await page.fill(selector, value)
    await page.wait_for_timeout(500)
    return f"Filled {selector} with {value}"


@mcp.tool()
async def analyze_page() -> str:
    """Analyze if page is a search results page and extract relevant links"""
    if not page:
        return json.dumps({"error": "No browser connected"})
    
    analysis = await page.evaluate("""() => {
        // Detect if it's a search results page
        const hasResults = document.querySelectorAll('ol li, ul li, .result, .search-result').length > 3;
        const hasSearchBox = document.querySelector('input[type="search"], input[name*="search"], input[name*="query"]') !== null;
        
        // Extract search result links
        const results = [];
        document.querySelectorAll('a').forEach((link, idx) => {
            const text = link.innerText?.trim() || '';
            const href = link.href || '';
            const parent = link.closest('li, .result, .search-result');
            
            // Filter for actual result links (not navigation)
            if (text.length > 20 && href.startsWith('http') && parent) {
                results.push({
                    index: idx,
                    title: text.slice(0, 100),
                    url: href,
                    snippet: parent.innerText?.slice(0, 200) || ''
                });
            }
        });
        
        return {
            isSearchPage: hasResults && hasSearchBox,
            resultCount: results.length,
            results: results.slice(0, 10)  // Top 10 results
        };
    }""")
    
    return json.dumps(analysis)


@mcp.tool()
async def click_best_result(search_term: str) -> str:
    """Analyze search results and click the most relevant link"""
    if not page:
        return "No browser connected"
    
    # Get analysis
    analysis_str = await analyze_page()
    analysis = json.loads(analysis_str)
    
    if not analysis.get('isSearchPage'):
        return "Not a search results page"
    
    results = analysis.get('results', [])
    if not results:
        return "No results found"
    
    # Find best match (simple keyword matching)
    search_lower = search_term.lower()
    best_match = None
    best_score = 0
    
    for result in results:
        text = (result['title'] + ' ' + result['snippet']).lower()
        score = sum(1 for word in search_lower.split() if word in text)
        if score > best_score:
            best_score = score
            best_match = result
    
    if best_match:
        await page.goto(best_match['url'])
        return f"Clicked: {best_match['title']}"
    
    return "No relevant result found"


@mcp.tool()
def save_task(name: str, url: str, instruction: str, actions: str) -> str:
    """Save a task for reuse"""
    tasks = load_tasks()
    tasks.append({
        "name": name,
        "url": url,
        "instruction": instruction,
        "actions": json.loads(actions)
    })
    save_tasks(tasks)
    return f"Saved task: {name}"


@mcp.tool()
async def execute_task(name: str) -> str:
    """Execute a saved task"""
    tasks = load_tasks()
    task = next((t for t in tasks if t['name'] == name), None)
    
    if not task:
        return f"Task {name} not found"
    
    await connect_browser(task['url'])
    
    results = []
    for action in task['actions']:
        if action['type'] == 'fill':
            result = await fill_input(action['selector'], action['value'])
        elif action['type'] == 'click':
            result = await click_element(action['selector'])
        elif action['type'] == 'wait':
            result = await wait_for_element(action.get('selector', 'body'))
        results.append(result)
    
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
