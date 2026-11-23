"""What changed: the map's progress, worked out from the repo's git history at build time.

Nothing is stored. For every commit of the last 30 days that touched a ticket, the map or a decision record,
the map's state is rebuilt from that commit's files (with the same code that builds today's map) and compared
with the state before it. Each difference becomes one line on the game's "What changed" page.
If git or the history is missing, the page simply has nothing to show.
"""
import json, re, subprocess

RANK = {"fog": 0, "sighted": 1, "mapped": 2, "decided": 3, "done": 4}
NAME = {"fog": "In fog", "sighted": "Sighted", "mapped": "Mapped", "decided": "Decided", "done": "Done"}
WORLD = ["game/world.json", "game/places.json"]  # the world file today, then its older name, so history survives the rename
PATHS = ["issues", *WORLD, "decisions"]


class Git:
    def __init__(self, root):
        self.root, self.cache = root, {}
        self.cat = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def run(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout

    def blob(self, sha):
        if sha not in self.cache:
            self.cat.stdin.write((sha + "\n").encode())
            self.cat.stdin.flush()
            size = int(self.cat.stdout.readline().split()[2])
            self.cache[sha] = self.cat.stdout.read(size).decode("utf-8", "replace")
            self.cat.stdout.read(1)
        return self.cache[sha]

    def tree(self, rev):
        """{path: blob sha} for the paths the map is built from."""
        out = {}
        for line in self.run("ls-tree", "-r", rev, "--", *PATHS).splitlines():
            meta, path = line.split("\t", 1)
            out[path] = meta.split()[2]
        return out

    def close(self):
        self.cat.stdin.close()
        self.cat.wait()


def snapshot(git, rev, compute, read_tickets):
    tree = git.tree(rev)
    world = next((w for w in WORLD if w in tree), None)
    if not world:
        return None
    files = {p.split("/", 1)[1]: git.blob(sha) for p, sha in tree.items() if p.startswith("issues/")}
    try:
        places = compute(json.loads(git.blob(tree[world])), read_tickets(files))[0]
    except Exception:  # an old commit the current code cannot read: skip it rather than fail the build
        return None
    quests, where = {}, {}
    for p in places:
        for q in p["q"]:
            quests.setdefault(q["n"], dict(q, p=p["id"]))
    decisions = {}
    for path, sha in tree.items():
        if path.startswith("decisions/") and path.endswith(".md") and not path.endswith("README.md"):
            text = git.blob(sha)
            title = text.splitlines()[0].lstrip("# ").strip() if text.strip() else path
            m = re.search(r"^Date:.*?Tickets?:\s*(\d+)", text, re.M)
            n = int(m.group(1)) if m else None
            decisions[path] = (title, n)
    blobs = {int(p.split("/")[1].split("-")[0]): sha for p, sha in tree.items()
             if p.startswith("issues/") and p.split("/")[1].split("-")[0].isdigit()}
    return {"places": {p["id"]: p for p in places}, "quests": quests, "decisions": decisions, "blobs": blobs}


def who(q):
    return {"you": "your move", "claude": "Claude's move", "done": "done"}.get(q["turn"]) or \
        ("waiting on " + q["who"] if q.get("who") else "waiting")


def diff(a, b):
    ev, touched = [], set()
    qa, qb = a["quests"], b["quests"]
    for n, q in sorted(qb.items()):
        label = f"Quest {n}: {q['t']}"
        old = qa.get(n)
        if not old:
            ev.append({"k": "new", "p": q["p"], "txt": label}); touched.add(n); continue
        if old["state"] != q["state"]:
            k = {"decided": "decided", "done": "done"}.get(q["state"], "reopened")
            ev.append({"k": k, "p": q["p"], "txt": label}); touched.add(n); continue
        if old["turn"] == "you" and q["turn"] != "you":
            ev.append({"k": "off", "p": q["p"], "txt": f"{label} (now {who(q)})"}); touched.add(n)
        elif old["turn"] != "you" and q["turn"] == "you":
            ev.append({"k": "yours", "p": q["p"], "txt": label}); touched.add(n)
    for pid, p in b["places"].items():
        o = a["places"].get(pid)
        if not o or p["status"] == "pillar":
            continue
        if o["status"] != p["status"] and o["status"] in RANK and p["status"] in RANK:
            up = RANK[p["status"]] > RANK[o["status"]]
            ev.append({"k": "place" if up else "placedown", "p": pid,
                       "txt": f"{p['name']}: {NAME[o['status']]} → {NAME[p['status']]}"})
        # a new number, not a reworded line: the value's digits or its date changed
        digits = lambda v: re.sub(r"\D", "", v or "")
        if p.get("val") and digits(p["val"]) and (digits(o.get("val")) != digits(p["val"]) or
                                                   (p.get("asof") or "") > (o.get("asof") or "")):
            ev.append({"k": "fact", "p": pid,
                       "txt": f"{p['name']}: {p['val']}" + (f", as of {p['asof']}" if p.get("asof") else "")})
    for path, (title, n) in sorted(b["decisions"].items()):
        if path not in a["decisions"]:
            q = b["quests"].get(n)
            ev.append({"k": "record", "p": q["p"] if q else "",
                       "txt": title + (f" (quest {n})" if n else "")})
            if n:
                touched.add(n)
    work = [n for n, sha in sorted(b["blobs"].items())
            if n in qb and n not in touched and a["blobs"].get(n) not in (None, sha)]
    # a commit that edits many tickets at once is housekeeping (wording, fields), not work on them
    if len(work) <= 3:
        ev += [{"k": "work", "p": qb[n]["p"], "txt": f"Quest {n}: {qb[n]['t']}"} for n in work]
    return ev


def changes(root, compute, read_tickets, days=30, limit=150):
    try:
        git = Git(root)
        log = git.run("log", f"--since={days}.days", "--reverse", "--format=%H%x1f%cI%x1f%an%x1f%s", "--", *PATHS)
        commits = [line.split("\x1f") for line in log.splitlines() if line.strip()][-limit:]
        if not commits:
            return []
        try:
            prev = snapshot(git, commits[0][0] + "^", compute, read_tickets)
        except subprocess.CalledProcessError:
            prev = None
        out = []
        for sha, when, author, subject in commits:
            cur = snapshot(git, sha, compute, read_tickets)
            if cur is None:
                continue
            ev = diff(prev, cur) if prev else []
            if ev:
                out.append({"h": sha[:7], "t": when, "s": subject, "ev": ev})
            prev = cur
        git.close()
        return out[::-1]
    except (OSError, subprocess.CalledProcessError):
        return []
