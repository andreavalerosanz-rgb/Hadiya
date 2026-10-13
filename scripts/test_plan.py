"""python3 scripts/test_plan.py — which Trello cards make today's plan."""
import os, sys
from datetime import date
os.environ["FLOWS_DATA"] = "/tmp/hadiya-test-plan"
os.makedirs("/tmp/hadiya-test-plan", exist_ok=True)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server as s

card = lambda name, due=None, lst="t", start=None, cid="00000000", ok=False: {
    "id": cid, "name": name, "due": due, "start": start, "dueComplete": ok, "idList": lst, "shortUrl": ""}
boards = [{"name": "B", "lists": [{"id": "t", "name": "To Do"}, {"id": "g", "name": "En curso"}, {"id": "d", "name": "Hecho"}], "cards": [
    card("hoy-nueva", "2026-10-05T10:00:00Z", cid="ffffffff"),
    card("vencida", "2026-10-01T10:00:00Z"),
    card("hecha", "2026-10-05T10:00:00Z", ok=True),
    card("en lista hecho", "2026-10-05T10:00:00Z", lst="d"),
    card("hecha ayer", "2026-10-04T10:00:00Z", ok=True),
    card("en curso", lst="g"),
    card("empezada", start="2026-10-04T08:00:00Z"),
    card("semana", "2026-10-09T15:00:00Z"),
    card("lejos", "2026-11-05T10:00:00Z"),
    card("sin fecha")]}]
got = {t["name"]: (t["group"], t["new"]) for t in s.plan_tasks(boards, date(2026, 10, 5), 1e9)}
assert got == {"hoy-nueva": ("today", True), "vencida": ("overdue", False), "en curso": ("doing", False),
               "empezada": ("doing", False), "semana": ("week", False),
               "hecha": ("done", False), "en lista hecho": ("done", False)}, got
print("ok")
