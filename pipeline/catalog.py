"""List bills/resolutions that were debated in plenary (speeches by several parties).

Usage: python -m pipeline.catalog [--min-parties N]  -> prints doc, date, speeches, final vote
Used to pick which debates to summarise.
"""
import argparse
from collections import defaultdict

from pipeline.debate import load_sessions


def debated_docs(leg: int = 56, min_parties: int = 2) -> list[dict]:
    info = defaultdict(lambda: {"speeches": 0, "parties": set(), "dates": set(), "title": None,
                                "final_vote": False})
    for s in load_sessions(leg):
        for item in s["items"]:
            if not item["docs"]:
                continue
            key = item["docs"][0]
            d = info[key]
            for e in item["events"]:
                if e["type"] == "speech" and e["role"] != "chair":
                    d["speeches"] += 1
                    if e["party"]:
                        d["parties"].add(e["party"])
                    d["dates"].add(s["source"]["date"])
                    d["title"] = d["title"] or item["title"]["nl"]
                elif e["type"] == "vote" and "amendement" not in (e["result"]["nl"] or "").lower():
                    d["final_vote"] = True
    out = []
    for doc, d in info.items():
        if len(d["parties"]) >= min_parties and d["title"]:
            out.append({"doc": doc, "last_date": max(d["dates"]), "speeches": d["speeches"],
                        "parties": len(d["parties"]), "final_vote": d["final_vote"], "title": d["title"]})
    return sorted(out, key=lambda x: x["last_date"], reverse=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-parties", type=int, default=2)
    a = ap.parse_args()
    for d in debated_docs(min_parties=a.min_parties):
        print(f"{d['doc']:>5} {d['last_date']} {d['speeches']:>3}sp {d['parties']:>2}p "
              f"{'V' if d['final_vote'] else '-'} {d['title'][:90]}")
