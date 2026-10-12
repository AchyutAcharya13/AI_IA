"""Classical rule-based agent (for Part C comparison): fixed rules, no tools, no re-planning."""
import re


def rule_based_agent(goal: str) -> dict:
    g = goal.lower()
    m = re.search(r"(\d+)\s*-?\s*day", g); days = int(m.group(1)) if m else 2
    m = re.search(r"(\d+)\s*(?:people|persons|travell?ers|adults)", g); people = int(m.group(1)) if m else 1
    m = re.search(r"(?:rs|inr|₹)\.?\s*([\d,]+)", g); budget = int(m.group(1).replace(",", "")) if m else 0
    rate = 3000  # hard-coded rule: Rs 3000 / person / day
    total = days * people * rate
    ok = total <= budget
    return {"rule": f"{days} days x {people} people x Rs {rate} (fixed)", "total": total, "budget": budget,
            "verdict": "Within budget" if ok else "Over budget - this agent cannot re-plan or suggest alternatives",
            "tools_used": 0, "steps": 1}
