"""Tools available to the TripWise agent."""
import os, re, json, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_FILE = os.path.join(BASE, ".env")
try:  # .env in the project root wins over any old value already set in the terminal/system
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)
except ImportError:
    pass


def get_key():
    """Return (key, source). Strips quotes/spaces that often sneak into .env files."""
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v.strip().strip('"').strip("'").strip(), name
    return "", None


def key_problem(key):
    """Return a plain-language problem with the key's format, or None if it looks like a Gemini key."""
    if not key:
        return "missing"
    if "paste_your_key" in key:
        return "placeholder"
    if key.startswith("sk-"):
        return "This is an OpenRouter/OpenAI key (starts with sk-). Gemini needs a Google AI Studio key, which starts with AIza."
    if not key.startswith("AIza") or len(key) != 39:
        return f"This doesn't look like a Gemini key: Gemini keys start with AIza and are 39 characters (yours is {len(key)})."
    return None


def mask(key):
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "(too short)"
DATA = os.path.join(BASE, "data")
EXPORTS = os.path.join(BASE, "exports")
MEMORY_FILE = os.path.join(DATA, "memory.json")
os.makedirs(EXPORTS, exist_ok=True)


def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression safely."""
    if not re.fullmatch(r"[0-9+\-*/(). %]+", expression or ""):
        return "Error: only digits and + - * / ( ) % are allowed"
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"Error: {e}"


def web_search(query: str) -> str:
    """Search the web (DuckDuckGo) for places, prices and travel info."""
    try:
        from ddgs import DDGS
        res = DDGS().text(query, max_results=4)
        return json.dumps([{"title": r["title"], "snippet": r["body"][:220]} for r in res])
    except Exception as e:
        return f"Search unavailable ({e}). Use prices.txt and your own knowledge, and say so."


def read_document(path: str) -> str:
    """Read a text/CSV/JSON file from the data folder only."""
    p = os.path.normpath(os.path.join(DATA, os.path.basename(path or "")))
    if not p.startswith(DATA) or not os.path.exists(p):
        files = ", ".join(os.listdir(DATA))
        return f"File not found. Available files: {files}"
    return open(p, encoding="utf-8").read()[:4000]


def _load_mem():
    return json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else {}


def get_memory() -> dict:
    return _load_mem()


def save_memory(key: str, value: str) -> str:
    """Save a preference or result to long-term memory (JSON)."""
    mem = _load_mem()
    mem[key] = value
    json.dump(mem, open(MEMORY_FILE, "w"), indent=2)
    return f"Saved '{key}' to long-term memory"


def check_budget(total_cost: float, budget: float) -> str:
    """Compare the plan cost with the budget."""
    try:
        total_cost, budget = float(total_cost), float(budget)
    except Exception:
        return "Error: numbers required"
    if total_cost <= budget:
        return f"WITHIN BUDGET: Rs {total_cost:.0f} <= Rs {budget:.0f} (spare Rs {budget - total_cost:.0f})"
    return f"OVER BUDGET by Rs {total_cost - budget:.0f}. Revise the plan (cheaper hotel/transport/activities) and recalculate."


def create_calendar_file(title: str, start_date: str, days: int) -> str:
    """Create an .ics calendar file (importable into Google Calendar) for the trip. start_date = YYYY-MM-DD."""
    try:
        d = datetime.date.fromisoformat(start_date)
        n = int(days)
    except Exception:
        return "Error: start_date must be YYYY-MM-DD and days an integer"
    end = d + datetime.timedelta(days=n)
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:40] + ".ics"
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//TripWise//EN\r\nBEGIN:VEVENT\r\n"
           f"UID:{name}@tripwise\r\nDTSTAMP:{datetime.datetime.utcnow():%Y%m%dT%H%M%SZ}\r\n"
           f"DTSTART;VALUE=DATE:{d:%Y%m%d}\r\nDTEND;VALUE=DATE:{end:%Y%m%d}\r\n"
           f"SUMMARY:{title}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    open(os.path.join(EXPORTS, name), "w", newline="").write(ics)
    return f"Calendar file created: {name} (download link: /exports/{name})"


FUNCS = {f.__name__: f for f in
         (calculator, web_search, read_document, save_memory, check_budget, create_calendar_file)}

# Gemini function declarations (JSON-schema style)
def _decl(name, desc, props, required):
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}

S, N = {"type": "string"}, {"type": "number"}
DECLARATIONS = [
    _decl("web_search", "Search the web for attractions, prices and travel info.", {"query": S}, ["query"]),
    _decl("calculator", "Evaluate arithmetic, e.g. '(1800*3)+(700*2*3)'. Use for ALL math.", {"expression": S}, ["expression"]),
    _decl("read_document", "Read a local file from the data folder, e.g. prices.txt.", {"path": S}, ["path"]),
    _decl("check_budget", "Compare total plan cost with the user's budget.", {"total_cost": N, "budget": N}, ["total_cost", "budget"]),
    _decl("save_memory", "Save a user preference or result to long-term memory.", {"key": S, "value": S}, ["key", "value"]),
    _decl("create_calendar_file", "Create an .ics calendar entry for the trip (start_date YYYY-MM-DD).",
          {"title": S, "start_date": S, "days": N}, ["title", "start_date", "days"]),
]
