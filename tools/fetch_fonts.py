"""Fetch the game's three fonts (Latin subsets) once and write game/fonts.css with them inlined as base64,
so the page makes no third-party calls and works offline. Re-run only to change fonts."""
import base64, pathlib, re, urllib.request

URL = ("https://fonts.googleapis.com/css2?family=Pixelify+Sans:wght@500;700&family=Inter:wght@400;500;600"
       "&family=JetBrains+Mono:wght@500&display=swap")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
css = get(URL).decode()
out = []
for comment, block in re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S):
    if comment not in ("latin", "latin-ext"):
        continue
    url = re.search(r"url\((.*?)\)", block).group(1)
    data = base64.b64encode(get(url)).decode()
    out.append(f"/* {comment} */\n" + block.replace(url, "data:font/woff2;base64," + data))
path = pathlib.Path(__file__).resolve().parent.parent / "game" / "fonts.css"
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"wrote {path}: {len(out)} faces, {path.stat().st_size // 1024} KB")
