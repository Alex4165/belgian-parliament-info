"""Nightly update: fetch new/changed plenary reports, parse, and summarise new debates.

Usage: python -m pipeline.update [--summarize N] [--since YYYY-MM-DD]

1. Read the list of plenary reports on dekamer.be and download any new session.
   Provisional reports ("Voorlopig verslag") are re-downloaded until the definitive
   version replaces them.
2. Parse what changed; refresh the member list.
3. If --summarize N > 0 and the `claude` CLI is available: summarise up to N debated
   documents (several parties spoke, final vote taken) that have no summary yet,
   newest first, optionally only those debated on/after --since.
4. Re-check all stored summaries against the current parse.
"""
import argparse
import json
import re
import shutil
import urllib.request
from pathlib import Path

from pipeline import members, parse_plenary, summarize
from pipeline.catalog import debated_docs
from pipeline.debate import build
from pipeline.fetch import RAW_DIR, fetch

LIST_URL = ("https://www.dekamer.be/kvvcr/showpage.cfm?section=/cricra&language=nl"
            "&cfm=dcricra.cfm?type=plen&cricra=cri&count=all")
ROOT = Path(__file__).resolve().parent.parent
LEG = 56


def latest_session() -> int:
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": "belgian-parliament-info/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode("latin-1")
    nums = [int(n) for n in re.findall(rf"/doc/PCRI/pdf/{LEG}/ip(\d+)\.pdf", t, re.I)]
    return max(nums)


def is_provisional(num: int) -> bool:
    p = parse_plenary.OUT_DIR / str(LEG) / f"ip{num:03d}.json"
    return not p.exists() or json.loads(p.read_text())["source"]["provisional"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summarize", type=int, default=0, help="max new debates to summarise")
    ap.add_argument("--since", default=None, help="only summarise debates on/after this date")
    a = ap.parse_args()

    last = latest_session()
    changed = []
    for n in range(1, last + 1):
        raw = RAW_DIR / str(LEG) / f"ip{n:03d}x.html"
        if not raw.exists() or is_provisional(n):
            before = raw.read_bytes() if raw.exists() else None
            fetch(n, LEG, force=True)
            if raw.read_bytes() != before:
                changed.append(raw)
    print(f"latest session {last}; {len(changed)} report(s) new or changed")
    if changed:
        parse_plenary.main([str(p) for p in changed])

    m = members.fetch()
    members.OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True))

    if a.summarize > 0:
        if not shutil.which("claude"):
            print("claude CLI not found: skipping summaries")
        else:
            done = {p.stem for p in (summarize.OUT_DIR / str(LEG)).glob("*.json")}
            todo = [d for d in debated_docs(LEG) if d["final_vote"] and d["doc"] not in done
                    and (not a.since or d["last_date"] >= a.since)]
            count = 0
            for d in todo:
                if count >= a.summarize:
                    break
                # jointly debated documents share one summary, named after the lowest number
                if build(d["doc"], LEG)["doc"] in done:
                    continue
                count += 1
                try:
                    path = summarize.summarize(d["doc"], LEG)
                    done.add(path.stem)
                    print(f"summarised {d['doc']} -> {path.name}")
                except Exception as e:  # keep going; one failing debate should not stop the run
                    print(f"failed {d['doc']}: {e}")

    summarize.recheck(LEG)


if __name__ == "__main__":
    main()
