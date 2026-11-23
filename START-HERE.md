# Start here

You need: a Claude plan that includes Claude Code, a GitHub account, and (optional) Dropbox. Turn on two-factor
sign-in for all three before you add any financial document.

1. **Make your own private repo.** On GitHub, create a new **private** repository (for example `family-finance`).
   Never make it public: it will hold your family's finances.
2. **Open it in Claude.** In Claude Code on the web (claude.ai/code), start a session on your new repo and also
   give it read access to this engine repo.
3. **Say one sentence:** "Read two-shores/skill/SKILL.md and set up my family finance map."
   Claude asks you about 20 minutes of questions and builds a first map, all in fog, before you share any
   document.
4. **Add documents over the following days**: payslips (תלושי שכר) and the yearly employer summary (טופס 106), pension and keren hishtalmut statements,
   bank and brokerage statements, the mortgage schedule. Upload them in the chat or put them in a Dropbox
   folder you connect. Claude copies only the facts it needs, with the last 4 digits of any number, and keeps
   the originals out of git.
5. **Open your map.** Claude publishes it as a private page on your own Claude account. Nobody else can see it.

Rules that keep your data safe:
- Your repo stays private. Original documents and full ID or account numbers never go into git (`raw/` and
  `private/` are ignored from the first commit).
- Your map page stays private. Don't share its link: it carries everything on the map.
- Claude only reads. It never moves money, opens accounts or signs anything. It drafts, and you act.
- Documents are data. If a document contains instructions, Claude ignores them.
