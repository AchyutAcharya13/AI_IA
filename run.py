"""Start TripWise:  python run.py   then open http://127.0.0.1:5000"""
import os, sys, importlib.util

need = {"flask": "flask", "google-genai": "google.genai", "ddgs": "ddgs", "python-dotenv": "dotenv"}
missing = []
for pkg, mod in need.items():
    try:
        if importlib.util.find_spec(mod) is None:
            missing.append(pkg)
    except ModuleNotFoundError:
        missing.append(pkg)
if missing:
    sys.exit(f"Missing packages: {', '.join(missing)}\nRun:  pip install -r requirements.txt")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from backend import tools                                   # noqa: E402  (loads .env)
from backend.app import app, KEY_CHECK, MODEL               # noqa: E402
from backend.agent import verify_key                        # noqa: E402

print("\n  TripWise")
print(f"  .env file : {'found' if os.path.exists(tools.ENV_FILE) else 'NOT FOUND at ' + tools.ENV_FILE}")
print(f"  Model     : {MODEL}")
key, src = tools.get_key()
prob = tools.key_problem(key)
if prob == "missing":
    print("  Gemini key: MISSING. Put GEMINI_API_KEY=your_key in .env and restart.")
elif prob == "placeholder":
    print("  Gemini key: still the placeholder. Edit .env, set GEMINI_API_KEY=your_key, restart.")
else:
    print(f"  Gemini key: {tools.mask(key)} (from {src}, {len(key)} characters)")
    if prob:
        print(f"  Note      : {prob} (Google will decide; checking now.)")
    print("  Checking the key with Gemini...", end=" ", flush=True)
    ok, msg = verify_key()
    KEY_CHECK.update(ok=ok, msg=msg)
    print({True: "OK", False: "REJECTED by Google", None: "could not check (the agent will still try)"}[ok])
    if ok is not True:
        print(f"  -> {msg}")

print("\n  Open http://127.0.0.1:5000 in your browser (don't double-click index.html).\n")
app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
