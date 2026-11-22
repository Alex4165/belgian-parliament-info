"""Fetch the current member list (name -> party) of the Chamber.

Usage: python -m pipeline.members   -> data/members/56.json
Names are in "Last First" form, as in the named-vote annex.
"""
import html
import json
import re
import urllib.request
from pathlib import Path

URL = "https://www.dekamer.be/kvvcr/showpage.cfm?section=/depute&language=nl&cfm=/site/wwwcfm/depute/cvlist54.cfm"
OUT = Path(__file__).resolve().parent.parent / "data" / "members" / "56.json"


def fetch() -> dict:
    req = urllib.request.Request(URL, headers={"User-Agent": "belgian-parliament-info/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    try:
        t = raw.decode("utf-8")
    except UnicodeDecodeError:
        t = raw.decode("cp1252", errors="replace")
    members = {}
    for row in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", t):
        cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"(?s)<td[^>]*>(.*?)</td>", row)]
        cells = [c for c in cells if c]
        if len(cells) >= 2 and "@" not in cells[1]:
            members[cells[0]] = cells[1]
    return members


if __name__ == "__main__":
    m = fetch()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True))
    print(f"{OUT}: {len(m)} members")
