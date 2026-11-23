# Two Shores: a family finance map, built from your own records

Two Shores turns a family's finances into a walkable map. Every place is one real thing: an account, a duty, an
insurance, a goal. Every quest is one decision still to make. The map is a read-only view of plain text files
that your own Claude keeps up to date. It never moves money and it holds no data until you add yours.

What is here:
- `game/`: the engine. `build.py` reads your `game/world.json` and `issues/*.md` and writes one HTML page.
  Python 3 standard library only. `python3 game/build.py --check` lists every problem until the map is clean.
- `game/example/`: an invented family (one land, shekels, Hebrew names, a mortgage). `sh tools/build_example.sh`
  builds it so you can see the game before adding anything of your own.
- `skill/`: the setup guide your Claude follows (`SKILL.md`) and the list of Israeli quests it starts from
  (`catalogue-il.md`).
- `starter/`: the files your own private repo starts with (the agent's brief and a `.gitignore`).

Start with `START-HERE.md`.

This is a personal tool, not financial, tax or legal advice. Where a decision needs a professional
(an accountant, a lawyer, a pension advisor), the quests say so.
