"""Build the static site into public/.

Usage: python site/build.py
- public/index.html     full HTML document (GitHub Pages)
- public/artifact.html  same page without the document skeleton (claude.ai artifact preview)
- public/data/debates.json  all summarised debates, newest first
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.debate import build as build_debate, speakers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT = ROOT / "public"

HEAD = """<title>Klare Kamer</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Neutrale samenvattingen van debatten in de Belgische Kamer: het probleem, wie wat stemde, en de argumenten voor en tegen.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Literata:opsz,wght@7..72,500;7..72,600&family=Public+Sans:wght@400;600&display=swap">
<link rel="stylesheet" href="style.css">"""

BODY = """<div class="wrap">
  <header class="masthead">
    <a class="brand" href="#">Klare <span>Kamer</span></a>
    <nav><a href="#">Debatten</a><a href="#over">Hoe werkt dit?</a></nav>
  </header>
  <main id="app"><p class="empty">Debatten laden…</p></main>
</div>
<script src="app.js"></script>"""


def build(leg: int = 56) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "data").mkdir(exist_ok=True)
    debates = []
    for p in (ROOT / "data" / "debates" / str(leg)).glob("*.json"):
        d = json.loads(p.read_text())
        # facts are recomputed from the parsed reports, so parser fixes reach the site
        # without regenerating summaries
        facts = build_debate(d["doc"], leg)
        reports = {}
        for p in facts["committee"]:
            reports.setdefault(p["report"], {"id": p["report"], "url": p["url"].split("#")[0],
                                             "date": p["date"], "reading": p["reading"]})
        d.update(title=facts["title"], sessions=facts["sessions"], votes=facts["votes"],
                 docs=facts["docs"], speakers=speakers(facts), committee_reports=list(reports.values()))
        debates.append(d)
    debates.sort(key=lambda d: (d["sessions"][-1]["date"] or "", d["sessions"][-1]["session"]), reverse=True)
    (OUT / "data" / "debates.json").write_text(json.dumps(debates, ensure_ascii=False, separators=(",", ":")))
    for f in ("style.css", "app.js"):
        shutil.copy(SITE / f, OUT / f)
    (OUT / "index.html").write_text(
        f'<!doctype html>\n<html lang="nl">\n<head>\n<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{HEAD}\n</head>\n<body>\n{BODY}\n</body>\n</html>\n")
    (OUT / "artifact.html").write_text(f"{HEAD}\n{BODY}\n")
    print(f"{OUT}: {len(debates)} debates")


if __name__ == "__main__":
    build()
