#!/usr/bin/env python3
"""Build the Two Shores game page from the repo.

Reads issues/*.md (the quests) and game/world.json (the family's world: lands, places, trails, clocks, blimp, Ask Claude), fills
game/template.html (the engine) and writes game/dist/two-shores.html. Standard library only.
The game is a read-only view: this script never changes anything outside game/dist/.

  python3 game/build.py            build
  python3 game/build.py --check    build, and fail if a ticket has no place or a field is missing
"""
import datetime, json, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import history
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def field(text, name):
    m = re.search(rf"^{name}:[ \t]*(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def short_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{MONTHS[m - 1]} {d}" + ("" if y == TODAY.year else f", {y}")


def clock_text(raw):
    """What the game shows as a quest's deadline: a date, 'Overdue since <date>', or 'No deadline'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw.replace("**", "").strip())
    if not m:
        return "No deadline"
    late = datetime.date.fromisoformat(m.group(1)) < TODAY
    return ("Overdue since " if late else "") + short_date(m.group(1))


def clock_why(raw):
    """The reason written after the date in 'Clock:' (or the whole line when it has no date)."""
    raw = re.sub(r"^\d{4}-\d{2}(-\d{2})?[\s,;:]*", "", raw.replace("**", "").strip()).strip()
    if raw.startswith("(") and raw.endswith(")") and raw.count("(") == 1:
        raw = raw[1:-1]
    return "" if raw.lower() in ("", "none", "—", "-") or raw.lower().startswith("none") else raw


TURN = ["you"]  # set from world.json
WORDS = []  # [from, to] swaps from world.json "words", applied in order: a family's own names for things


def plain(text):
    """The game says 'quest', never 'ticket', and never shows a file name."""
    for a, b in WORDS:
        text = text.replace(a, b)
    text = re.sub(r"\bTickets\b", "Quests", re.sub(r"\bTicket\b", "Quest", text))
    text = re.sub(r"\btickets\b", "quests", re.sub(r"\bticket\b", "quest", text))
    text = re.sub(r"\b[Tt]he agent's\b", "Claude's", re.sub(r"\b[Tt]he agent\b(?!')", "Claude", text))
    text = re.sub(r"\bAgent\b", "Claude", text)
    return text.replace("`", "")


def answer_decided(text):
    """A ticket is decided when '## Answer' holds a dated decision."""
    m = re.search(r"^## Answer\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    body = (m.group(1) if m else "").strip()
    if not body or "unresolved" in body.lower()[:60]:
        return False
    # the answer must open with **Decided ...** or **Resolved ...** and a date; notes belong under ## Comments
    m = re.match(r"\*\*(?:Decided|Resolved)\b[^\n*]*?(\d{4}-\d{2}-\d{2})", body)
    try:
        return bool(m) and bool(datetime.date.fromisoformat(m.group(1)))
    except ValueError:
        return False


def disk_tickets():
    return {f.name: f.read_text(encoding="utf-8") for f in (ROOT / "issues").glob("[0-9]*-*.md")}


def read_tickets(files):
    """files: {file name: text} of issues/*.md, from disk or from a past commit."""
    out = {}
    for name in sorted(files):
        if not re.match(r"\d+-.*\.md$", name):
            continue
        text = files[name]
        n = int(name.split("-")[0])
        status = field(text, "Status").lower()
        turn_raw = field(text, "Turn")
        low = turn_raw.lower()
        who = ""
        if status.startswith("resolved") or low.startswith("done"):
            turn = "done"
        elif low.startswith("waiting") or low.startswith("moved") or low.startswith("parked"):
            turn = "wait"
            who = turn_raw.split(":", 1)[1].strip() if ":" in turn_raw else turn_raw
            who = re.sub(r"\s*\(.*$", "", who)
            if low.startswith("moved"):
                who = "the " + who + " agent"  # "moved: <owner>" hands the quest to another owner
        elif low.startswith("agent"):
            turn = "claude"
        elif low.startswith(TURN[0]):  # the word a family's tickets use for "the player's move" (world.json family.turn)
            turn = "you"
        else:
            turn = ""
        tier = field(text, "Tier")
        out[n] = {
            "n": n, "file": name,
            "title": text.splitlines()[0].lstrip("# ").strip(),
            "turn": turn, "who": who,
            "tier": int(tier) if tier.isdigit() else None,
            "next": plain(field(text, "Next step")),
            "clock": clock_text(field(text, "Clock")),
            "due": (re.match(r"\d{4}-\d{2}-\d{2}", field(text, "Clock").replace("**", "")) or [""])[0],
            "why": plain(clock_why(field(text, "Clock"))),
            "late": clock_text(field(text, "Clock")).startswith("Overdue"),
            "blocked": [int(x) for x in re.findall(r"\b\d{1,3}\b", field(text, "Blocked by").split("(")[0])],
            "resolved": status.startswith("resolved"),
            "decided": answer_decided(text),
        }
    return out


def section(text, name):
    m = re.search(rf"^## {name}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def read_records(root):
    """Decision records by slug: the one-line decision, its status, why, and how it runs."""
    out = {}
    for path in sorted((root / "decisions").glob("20*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.search(r"Status:\s*(.*)$", text, re.M)
        out[path.stem[11:]] = {"title": text.splitlines()[0].lstrip("# ").strip(),
                          "status": (m.group(1).strip() if m else ""),
                          "why": plain(section(text, "Why"))[:700], "run": plain(section(text, "Automation"))[:300]}
    return out


def sheet(p, tickets, records, problems):
    """What a place holds once the game is finished, row by row, each row's state read from its record and quest.
    In place: its quest is resolved, or its record says it is set. Decided: a record in force, or its quest decided.
    Open: neither, and the row shows the question still to answer."""
    def short(title):  # "Emergency fund: three months in savings" reads as "Three months in savings" under the row's own label
        t = title.split(": ", 1)[1] if ": " in title else title
        return t[:1].upper() + t[1:]

    def runs(text):  # how it runs, in plain words: no file pointers, no quest numbers, nothing for "none needed"
        text = re.sub(r"\s*\([^)]*\)", "", text)
        keep = [x for x in re.split(r"(?<=[.;])\s+", text)
                if x and x[0].isupper() and not re.search(r"\b(quest|ticket)s? \d|TODO|^None", x, re.I)]
        return re.sub(r";$", ".", " ".join(keep).replace("; ", ". ").strip())

    rows = []
    for r in p.get("sheet", []):
        rec = records.get(r.get("rec", "")) if r.get("rec") else None
        if r.get("rec") and records and not rec:
            problems.append(f"place {p['id']} row '{r['k']}' points at decisions/{r['rec']}.md, which does not exist")
        t = tickets.get(r.get("q"))
        if r.get("q") and not t:
            problems.append(f"place {p['id']} row '{r['k']}' points at ticket {r['q']}, which does not exist")
        live = rec and not rec["status"].lower().startswith("superseded")
        if (t and t["resolved"]) or (live and rec["status"].lower().startswith("set")):
            st = "inplace"
        elif live or (t and t["decided"]) or r.get("decided"):
            st = "decided"
        else:
            st = "open"
        rows.append({"k": r["k"], "v": plain(r.get("v") or (short(rec["title"]) if rec else "")), "st": st,
                     "check": plain(r.get("check", "")), "why": rec["why"] if rec else "",
                     "run": runs(rec["run"]) if rec and st != "inplace" else "", "q": r.get("q")})
    return rows


def compute(cfg, tickets):
    """The map's state: every place with its status and quests. Used for today and for each past commit."""
    problems, used = [], set()
    ignored = {int(k) for k in cfg.get("ignore", {})}
    finished = lambda n: tickets[n]["resolved"] or tickets[n]["decided"]
    # a quest whose blocker is still open is not anyone's move yet, whatever its Turn says
    for n, t in tickets.items():
        for b in t["blocked"]:
            if b not in tickets:
                problems.append(f"ticket {t['file']} is blocked by ticket {b}, which does not exist")
            elif b in ignored:
                problems.append(f"ticket {t['file']} is blocked by ticket {b}, which is off the map and can never finish")
        open_b = [b for b in t["blocked"] if b in tickets and not finished(b)]
        t["open_b"] = open_b
        if open_b and t["turn"] in ("you", "claude"):
            t["turn"], t["who"] = "wait", "quest " + ", ".join(str(b) for b in open_b)

    # a quest marked as the player's move whose next step says it waits on someone else: the Turn is stale
    WAITING = re.compile(r"\b(waits? on|waiting (on|for)|nothing for you)\b", re.I)
    for n, t in tickets.items():
        if t["turn"] == "you" and WAITING.search(t["next"] or ""):
            problems.append(f"ticket {t['file']} says it is the player's move but its Next step waits on someone else; "
                            "fix the Turn (waiting: <who>) or the Next step. Someone who only acts when the player "
                            "starts them is the player's move, not a wait")

    def cycle(n, seen):
        if n in seen:
            return True
        return any(cycle(b, seen | {n}) for b in tickets[n]["blocked"] if b in tickets)
    for n, t in tickets.items():
        if cycle(n, set()):
            problems.append(f"ticket {t['file']} is in a 'Blocked by' loop")
    places = []
    for p in cfg["places"]:
        qs = []
        for ref in p.get("quests", []):
            t = tickets.get(ref["n"])
            if not t:
                problems.append(f"place {p['id']} points at ticket {ref['n']}, which does not exist")
                continue
            used.add(t["n"])
            for k in ("turn", "tier", "next"):
                if t[k] in ("", None):
                    problems.append(f"ticket {t['file']} has no usable '{k}' field")
            qs.append({"n": t["n"], "t": ref.get("t") or t["title"], "turn": t["turn"] or "wait",
                       "who": plain(t["who"]), "tier": t["tier"] if t["tier"] is not None else 5,
                       "next": plain(ref.get("next") or t["next"]), "clock": t["clock"], "due": t["due"], "late": t["late"],
                       "why": t["why"], "blk": t["open_b"],
                       "state": "done" if t["resolved"] else ("decided" if t["decided"] else "open")})
        status = p["status"]
        if qs and status != "pillar":
            if all(q["state"] == "done" for q in qs):
                status = "done"
            elif all(q["state"] in ("done", "decided") for q in qs):
                status = "decided"
        out = {k: (plain(v) if isinstance(v, str) and k in ("what", "val", "src", "asof", "note") else v)
               for k, v in p.items() if k != "quests"}
        out.pop("sheet", None)
        out.update(status=status, base=p["status"], q=qs, sheet=sheet(p, tickets, cfg.get("_records", {}), problems))
        if not qs and p["status"] not in ("pillar",):
            problems.append(f"place {p['id']} has no quest, so it can never be decided")
        places.append(out)
    for n, t in tickets.items():
        if n not in used and n not in ignored:
            problems.append(f"ticket {t['file']} is not on any place (add it to game/world.json)")
    return places, used, ignored, problems, finished


def build(check=False):
    cfg = json.loads((GAME / "world.json").read_text(encoding="utf-8"))
    WORDS[:] = cfg.get("words", [])
    TURN[0] = cfg["family"].get("turn", "you").lower()
    cfg["_records"] = read_records(ROOT)
    tickets = read_tickets(disk_tickets())
    places, used, ignored, problems, finished = compute(cfg, tickets)

    storms = []
    for s in cfg["storms"]:
        days = (datetime.date.fromisoformat(s["date"]) - TODAY).days
        if s["at"] not in {p["id"] for p in cfg["places"]}:
            problems.append(f"storm '{s['what']}' is at '{s['at']}', which is not a place")
            continue
        # a storm is there only while something due by its date is still open
        due_open = any(t["due"] and t["due"] <= s["date"] and not finished(n) for n, t in tickets.items() if n in used)
        if days < 0 or not due_open:
            continue
        storms.append({"at": s["at"], "days": days, "date": s["date"], "what": s["what"], "dx": s["dx"], "dy": s["dy"], "min": s.get("min", 2),
                       "label": f"{short_date(s['date'])} · {s['what']} · {'today' if days == 0 else '1 day' if days == 1 else f'{days} days'}"})
    nxt = min(storms, key=lambda s: s["days"], default=None)
    next_clock = nxt["label"].split(" · ")[0] + " · " + nxt["label"].split(" · ")[2] if nxt else "none"

    # trails: each end is a place id, an airfield, or an [x, y] junction
    spots = {p["id"]: {"x": p["x"], "y": p["y"]} for p in cfg["places"]}
    spots.update({pt["id"]: {"x": pt["x"], "y": pt["y"]} for pt in cfg["map"].get("ports", [])})
    roads = []
    for a, b in cfg["roads"]:
        ends = []
        for e in (a, b):
            if isinstance(e, list):
                ends.append({"x": e[0], "y": e[1]})
            elif e in spots:
                ends.append(spots[e])
            else:
                problems.append(f"a trail ends at '{e}', which is not a place")
        if len(ends) == 2:
            roads.append(ends)

    js = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")  # no </script> break-out from data
    data = "\n".join([
        "/* generated by game/build.py: do not edit this page, edit the repo */",
        f"const P={js(places)};",
        "const byId=Object.fromEntries(P.map(p=>[p.id,p]));",
        f"const ROADS={js(roads)};",
        f"const WORLD={js({k: cfg[k] for k in ('family', 'lands', 'map', 'blimp', 'ask')})};",
        f"const STORMS={js(storms)};",
        f"const NEXT_CLOCK={js(next_clock)};",
        f"const CHANGES={js(history.changes(ROOT, compute, read_tickets))};",
    ])
    html = (GAME / "template.html").read_text(encoding="utf-8")
    assert "/*__DATA__*/" in html and "__SUBTITLE__" in html and "/*__FONTS__*/" in html
    sub = (f"The family's finances as a map. Built from the repo on {TODAY.day} {MONTHS[TODAY.month - 1]} "
           f"{TODAY.year}: {len(used)} quests on {len(places)} places.")
    fonts = GAME / "fonts.css"
    html = html.replace("/*__DATA__*/", data).replace("__SUBTITLE__", sub).replace("__TITLE__", cfg["family"]["title"])
    html = html.replace("/*__FONTS__*/", fonts.read_text(encoding="utf-8") if fonts.exists() else "")
    problems += engine_leaks()
    (GAME / "dist").mkdir(exist_ok=True)
    (GAME / "dist" / "two-shores.html").write_text(html, encoding="utf-8")
    print(f"built game/dist/two-shores.html: {len(places)} places, {len(used)} of {len(tickets)} tickets placed, "
          f"{len(ignored)} ignored on purpose")
    for pr in problems:
        print("PROBLEM:", pr)
    # the dependents sweep: when a ticket changes, every quest it blocks may have a new Turn or Next step
    try:
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD~3", "--", "issues"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.split()
    except Exception:
        changed = []
    changed_n = {int(pathlib.Path(f).name.split("-")[0]) for f in changed if re.match(r"\d+-", pathlib.Path(f).name)}
    for n, t in sorted(tickets.items()):
        hit = [b for b in t["blocked"] if b in changed_n]
        if hit and not t["resolved"]:
            print(f"SWEEP: ticket {t['file']} depends on ticket {', '.join(map(str, hit))}, which changed recently: "
                  "re-read its Turn, Next step and Blocked by")
    return 1 if (check and problems) else 0


ENGINE = ["game/build.py", "game/history.py", "game/template.html"]
MONEY = re.compile(r"[$₪€£]\s?\d|\d[\d,.]*\s?(?:₪|NIS|USD|ILS)\b")


def engine_leaks():
    """The engine holds no family: no line of the private canary list (names, places, last-4s, amounts; one per
    line, never committed) and no money figure may appear in the engine files. Family words live in world.json."""
    problems = []
    canary = ROOT / "private" / "canaries.txt"
    words = [w.strip() for w in canary.read_text(encoding="utf-8").splitlines()
             if w.strip() and not w.startswith("#")] if canary.exists() else []
    for rel in ENGINE:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for w in words:
            m = re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.I)
            if m:
                problems.append(f"{rel} holds a private word from private/canaries.txt (line {text[:m.start()].count(chr(10)) + 1}); "
                                "move it to world.json")
        for m in MONEY.finditer(text):
            problems.append(f"{rel} holds a money figure '{m.group(0)}' (line {text[:m.start()].count(chr(10)) + 1}); "
                            "figures belong in world.json or the ledger")
    if not canary.exists():  # a fresh clone has no private/: say so, without failing every build
        print("NOTE: private/canaries.txt is missing here, so the engine was checked for money figures only")
    return problems


# "today" is the family's own day: world.json names its time zone
TODAY = datetime.datetime.now(ZoneInfo(json.loads((GAME / "world.json").read_text(encoding="utf-8"))
                                       ["family"].get("tz", "UTC"))).date()
if __name__ == "__main__":
    sys.exit(build(check="--check" in sys.argv))
