"""
TripWise - ReAct-style Agentic AI Travel Planner (IA II, Activity 1)
Framework : ReAct loop (Reasoning -> Action -> Observation) on OpenRouter free API
Tools     : web_search, calculator, read_document, save_memory (JSON)
Memory    : short-term = message context; long-term = memory.json
Logs      : logs/agent_trace.log + logs/trace.json

Setup : pip install openai ddgs
        get free key at https://openrouter.ai/keys
        export OPENROUTER_API_KEY=sk-or-...        (Windows: set OPENROUTER_API_KEY=...)
Run   : python tripwise_agent.py "Plan a 3-day Goa trip for 2 people under Rs 25000"
        python tripwise_agent.py --baseline "Plan a 3-day Goa trip for 2 people under Rs 25000"
Optional: set MODEL=other/free-model:free if the default is rate-limited.
"""
import os, sys, json, re, logging, time
from openai import OpenAI

MODEL = os.getenv("MODEL", "meta-llama/llama-3.3-70b-instruct:free")
MEMORY_FILE = "memory.json"
os.makedirs("logs", exist_ok=True)
logging.basicConfig(filename="logs/agent_trace.log", level=logging.INFO,
                    format="%(asctime)s | %(message)s")
TRACE = []

def log(tag, msg):
    line = f"[{tag}] {msg}"
    print(line, flush=True)
    logging.info(line)
    TRACE.append({"tag": tag, "msg": str(msg)})

# ------------------------- TOOLS -------------------------
def calculator(expression):
    if not re.fullmatch(r"[0-9+\-*/(). %]+", expression):
        return "Error: only arithmetic allowed"
    try:
        return str(eval(expression))
    except Exception as e:
        return f"Error: {e}"

def web_search(query):
    try:
        from ddgs import DDGS
        res = DDGS().text(query, max_results=4)
        return json.dumps([{"title": r["title"], "snippet": r["body"][:200]} for r in res])
    except Exception as e:
        return f"Search failed: {e}"

def read_document(path):
    try:
        return open(path, encoding="utf-8").read()[:3000]
    except Exception as e:
        return f"Error: {e}"

def save_memory(key, value):
    mem = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else {}
    mem[key] = value
    json.dump(mem, open(MEMORY_FILE, "w"), indent=2)
    return f"Saved '{key}' to long-term memory"

FUNCS = {"calculator": calculator, "web_search": web_search,
         "read_document": read_document, "save_memory": save_memory}

def schema(name, desc, props):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object",
                           "properties": {k: {"type": "string"} for k in props},
                           "required": props}}}

TOOLS = [
    schema("calculator", "Evaluate an arithmetic expression, e.g. '(1800*3)+(700*2*3)'.", ["expression"]),
    schema("web_search", "Search the web for places, prices and travel info.", ["query"]),
    schema("read_document", "Read a local text file such as prices.txt.", ["path"]),
    schema("save_memory", "Save a user preference or final result to long-term memory.", ["key", "value"]),
]

SYSTEM = """You are TripWise, an autonomous travel-planning agent using the ReAct strategy.
1. Start with a short numbered PLAN.
2. Then act step by step: read prices.txt, use web_search for attractions/costs, and use the
   calculator for ALL arithmetic (never compute in your head).
3. After each observation, decide the next action.
4. Compare the total with the budget; if over, revise the plan and recalculate.
5. Save the user's preferences with save_memory.
6. Finish with a day-wise itinerary and a cost table. Mention the final total vs budget."""

# ------------------------- LLM AGENT -------------------------
def run_agent(goal, max_steps=12):
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])
    mem = open(MEMORY_FILE).read() if os.path.exists(MEMORY_FILE) else "{}"
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Long-term memory: {mem}\nGoal: {goal}"}]
    log("GOAL", goal)
    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages,
                                              tools=TOOLS, tool_choice="auto")
        msg = resp.choices[0].message
        messages.append(msg)
        if msg.content:
            log(f"THOUGHT s{step}", msg.content.strip())
        if not msg.tool_calls:
            log("FINAL ANSWER", msg.content)
            json.dump(TRACE, open("logs/trace.json", "w"), indent=2)
            return msg.content
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            log(f"ACTION s{step}", f"{tc.function.name}({args})")
            out = FUNCS[tc.function.name](**args)
            log(f"OBSERVATION s{step}", str(out)[:400])
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(out)})
        time.sleep(1)
    json.dump(TRACE, open("logs/trace.json", "w"), indent=2)
    return "Stopped: max steps reached"

# ------------------------- CLASSICAL RULE-BASED BASELINE -------------------------
def rule_based_agent(goal):
    g = goal.lower()
    days = int(m.group(1)) if (m := re.search(r"(\d+)\s*-?\s*day", g)) else 2
    people = int(m.group(1)) if (m := re.search(r"(\d+)\s*people", g)) else 1
    budget = int(m.group(1).replace(",", "")) if (m := re.search(r"(?:rs|inr)\.?\s*([\d,]+)", g)) else 0
    total = days * people * 3000          # fixed rule: Rs 3000 / person / day
    verdict = "within budget" if total <= budget else "over budget (cannot re-plan)"
    out = f"[RULE-BASED] {days}d x {people}p x Rs3000 = Rs{total}; budget Rs{budget} -> {verdict}"
    log("BASELINE", out)
    return out

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--baseline":
        rule_based_agent(" ".join(a[1:]))
    else:
        run_agent(" ".join(a) or "Plan a 3-day Goa trip for 2 people under Rs 25000")
