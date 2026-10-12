"""TripWise: ReAct-style agent on Google Gemini (function calling), manual loop so every step is observable."""
import os, json, time, logging, datetime
from . import tools

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_STEPS = 12
LOG_DIR = os.path.join(tools.BASE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(filename=os.path.join(LOG_DIR, "agent_trace.log"), level=logging.INFO,
                    format="%(asctime)s | %(message)s", encoding="utf-8")


def friendly_error(e: Exception) -> str:
    """Turn raw Gemini/SDK errors into an instruction the user can act on."""
    m = str(e)
    low = m.lower()
    if "api key not valid" in low or "api_key_invalid" in low:
        key, src = tools.get_key()
        return (f"Gemini rejected the API key {tools.mask(key)} (read from {src}). Create a new key at "
                "aistudio.google.com/apikey, paste it into .env as GEMINI_API_KEY=AIza... and restart the server.")
    if "permission_denied" in low or "service_disabled" in low:
        return ("This key isn't allowed to use Gemini (it may be a Google Cloud key without the Generative Language API). "
                "Create a key at aistudio.google.com/apikey instead.")
    if "429" in m or "resource_exhausted" in low or "quota" in low:
        return "Gemini free-tier rate limit reached. Wait about a minute, or set GEMINI_MODEL=gemini-2.5-flash-lite in .env and restart."
    if "not found" in low and "model" in low:
        return f"Model '{MODEL}' is not available for this key. Set GEMINI_MODEL=gemini-2.5-flash-lite in .env and restart."
    if "getaddrinfo" in low or "connection" in low or "timed out" in low:
        return "The server could not reach Gemini. Check this computer's internet connection."
    return f"Gemini call failed: {m[:300]}"

SYSTEM = """You are TripWise, an autonomous travel-planning agent using the ReAct strategy
(Reason -> Act -> Observe -> repeat).
1. Begin with a short numbered PLAN as text.
2. Act step by step with tools: read_document('prices.txt') for base prices, web_search for attractions/costs,
   calculator for ALL arithmetic (never compute in your head).
3. After every observation, briefly reason about the next action.
4. Call check_budget(total, budget). If OVER BUDGET, revise the plan (cheaper options) and recalculate. Repeat until within budget.
5. Call save_memory for the user's preferences (destination, budget, style).
6. Optionally call create_calendar_file if the user gives a start date.
7. Finish with the FINAL ITINERARY in Markdown: a day-wise plan, a cost table (item | cost), total vs budget.
Long-term memory from earlier sessions is provided; use it."""


def _client():
    from google import genai
    key, _ = tools.get_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey")
    return genai.Client(api_key=key)


def verify_key():
    """One cheap call to Gemini to check the key. Returns (ok, message)."""
    key, src = tools.get_key()
    prob = tools.key_problem(key)
    if prob in ("missing", "placeholder"):
        return False, prob
    try:
        from google import genai
        client = genai.Client(api_key=key)   # keep a reference, or the client closes before the request
        client.models.get(model=MODEL)
        return True, f"Gemini accepted the key {tools.mask(key)} (from {src})"
    except Exception as e:
        low = str(e).lower()
        rejected = any(s in low for s in ("api key not valid", "api_key_invalid", "permission_denied", "service_disabled", "unauthenticated"))
        # None = could not verify (network, rate limit, model name): don't block the agent for that
        return (False if rejected else None), friendly_error(e) + f"  [key used: {tools.mask(key)} from {src}]"


def _emit(kind, **data):
    ev = {"type": kind, "t": datetime.datetime.now().strftime("%H:%M:%S"), **data}
    logging.info(json.dumps(ev, ensure_ascii=False)[:1500])
    return ev


def run_agent(goal: str, client=None, max_steps: int = MAX_STEPS):
    """Generator yielding trace events: goal, thought, action, observation, final, error."""
    from google.genai import types
    client = client or _client()
    mem = json.dumps(tools.get_memory())
    yield _emit("goal", text=goal, memory=mem)

    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(function_declarations=tools.DECLARATIONS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.4)
    contents = [types.Content(role="user", parts=[types.Part(text=f"Long-term memory: {mem}\n\nGoal: {goal}")])]
    tool_calls = 0

    for step in range(1, max_steps + 1):
        resp = None
        for attempt in range(3):  # retry on rate limit / transient errors
            try:
                resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
                break
            except Exception as e:
                fatal = "api key" in str(e).lower() or "permission_denied" in str(e).lower()
                if attempt == 2 or fatal:
                    yield _emit("error", text=friendly_error(e))
                    return
                time.sleep(4 * (attempt + 1))
        if not resp.candidates or resp.candidates[0].content is None:
            reason = resp.candidates[0].finish_reason if resp.candidates else "no candidates"
            yield _emit("error", text=f"Gemini returned no content (finish reason: {reason}). Try rephrasing the goal.")
            return
        cand = resp.candidates[0]
        parts = cand.content.parts or []
        contents.append(cand.content)  # keep full model turn (incl. thought signatures)
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
        text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()

        if not calls:
            yield _emit("final", step=step, text=text or "(empty response)", tool_calls=tool_calls, steps=step)
            return
        if text:
            yield _emit("thought", step=step, text=text)

        responses = []
        for fc in calls:
            args = dict(fc.args or {})
            tool_calls += 1
            yield _emit("action", step=step, tool=fc.name, args=args)
            fn = tools.FUNCS.get(fc.name)
            try:
                out = fn(**args) if fn else f"Unknown tool {fc.name}"
            except Exception as e:
                out = f"Tool error: {e}"
            yield _emit("observation", step=step, tool=fc.name, text=str(out)[:1200])
            responses.append(types.Part.from_function_response(name=fc.name, response={"result": str(out)}))
        contents.append(types.Content(role="user", parts=responses))

    yield _emit("error", text="Stopped: maximum number of steps reached")
