"""Assemble everything the plenary said and voted about one parliamentary document.

A debate is keyed by the document base number (e.g. 1721): the discussion and the vote
often happen in different sessions. Facts (speakers, votes, party breakdown) are computed
here, deterministically; only the summary text is left to the model.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from pipeline.committee import load_reports

ROOT = Path(__file__).resolve().parent.parent
PLENARY_DIR = ROOT / "data" / "plenary"
MEMBERS_DIR = ROOT / "data" / "members"


def load_sessions(leg: int) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((PLENARY_DIR / str(leg)).glob("ip*.json"))]


PARTY_LABELS = {"ONAFH": "Onafhankelijk", "INDEP-ONAFH": "Onafhankelijk"}


def member_parties(members: dict, sessions: list[dict]) -> dict:
    """Current member list, completed with former members seen as speakers ("First Last (Party)").
    Named votes use "Last First"; match on the set of name tokens."""
    by_tokens = {}
    for s in sessions:
        for item in s["items"]:
            for e in item["events"]:
                if e["type"] == "speech" and e["party"] and e["name"]:
                    by_tokens[frozenset(e["name"].lower().split())] = e["party"]
    out = {n: PARTY_LABELS.get(p, p) for n, p in members.items()}
    out["_by_tokens"] = by_tokens
    return out


def party_of(name: str, parties: dict) -> str:
    if name in parties:
        return parties[name]
    return parties["_by_tokens"].get(frozenset(name.lower().split()), "Onbekend")


def party_breakdown(named: dict, parties: dict) -> dict:
    out = defaultdict(lambda: {"yes": 0, "no": 0, "abstain": 0})
    for choice, names in named.items():
        for n in names:
            out[party_of(n, parties)][choice] += 1
    return dict(sorted(out.items()))


def party_stance(counts: dict) -> str:
    """'voor' / 'tegen' / 'onthouding' when a party votes as a bloc, else 'verdeeld'."""
    nonzero = {k: v for k, v in counts.items() if v}
    if len(nonzero) != 1:
        return "verdeeld"
    return {"yes": "voor", "no": "tegen", "abstain": "onthouding"}[next(iter(nonzero))]


def vote_kind(vote: dict) -> str:
    """'amendment', 'article' or 'whole' (the vote on the text as a whole)."""
    subject = (vote.get("subject") or "").lower()
    result = (vote["result"]["nl"] or "").lower()
    if "amendement" in subject or "amendement" in result:
        return "amendment"
    if re.match(r"stemming over (de |het )?artikel", subject) or re.search(r"neemt de kamer (de )?artikel", result):
        return "article"
    return "whole"


def related_docs(doc: str, sessions: list[dict]) -> list[str]:
    """Documents discussed jointly with `doc` in the same agenda item."""
    docs = {doc}
    for s in sessions:
        for item in s["items"]:
            if doc in item["docs"] and any(e["type"] == "speech" for e in item["events"]):
                docs |= set(item["docs"])
    return sorted(docs, key=int)


def build(doc: str, leg: int = 56) -> dict:
    all_sessions = load_sessions(leg)
    members = member_parties(json.loads((MEMBERS_DIR / f"{leg}.json").read_text()), all_sessions)
    docs = related_docs(doc, all_sessions)
    title, sessions, speeches, votes = None, [], [], []

    for s in all_sessions:
        src = s["source"]
        for item in s["items"]:
            if not set(docs) & set(item["docs"]):
                continue
            has_speech = any(e["type"] == "speech" for e in item["events"])
            if title is None or (has_speech and not title["_debated"]):
                title = {"nl": item["title"]["nl"], "fr": item["title"]["fr"],
                         "subtitles": item["subtitles"], "_debated": has_speech}
            if src["session"] not in [x["session"] for x in sessions]:
                sessions.append({"session": src["session"], "date": src["date"], "part": src["part"],
                                 "url": src["url"]})
            for e in item["events"]:
                if e["type"] == "speech" and e["role"] != "chair":
                    speeches.append({
                        "ref": f"{src['session']}/{e['id']}",
                        "session": src["session"], "date": src["date"],
                        "name": e["name"], "party": e["party"], "role": e["role"],
                        "lang": e["lang"], "text": "\n".join(e["paragraphs"]),
                        "translation": "\n".join(e["translation"]["paragraphs"]) if e.get("translation") else None,
                    })
                elif e["type"] == "vote":
                    named = s["named_votes"].get(str(e["number"]))
                    v = {
                        "ref": f"{src['session']}/vote {e['number']}",
                        "session": src["session"], "date": src["date"],
                        "subject": e.get("subject"), "item_title": item["title"]["nl"],
                        "result": e["result"],
                        **{k: e[k] for k in ("yes", "no", "abstain", "total")},
                        "reused": e.get("reused", False),
                        "docs": item["docs"],
                        "by_party": None,
                    }
                    if named:
                        v["by_party"] = {p: {"stance": party_stance(c), **c}
                                         for p, c in party_breakdown(named, members).items()}
                    v["kind"] = vote_kind(v)
                    v["final"] = v["kind"] == "whole"
                    votes.append(v)

    if title is None:
        raise SystemExit(f"document {doc} not found in parsed sessions")
    title.pop("_debated")

    committee = []
    for rep in load_reports(docs, leg):
        for i, text in enumerate(rep["pages"], start=1):
            if len(text) > 200:  # skip near-empty pages
                committee.append({"ref": f"{rep['id']}/p{i}", "report": rep["id"], "page": i,
                                  "url": f"{rep['url']}#page={i}", "date": rep["date"],
                                  "reading": rep["reading"], "text": text})

    return {
        "doc": docs[0], "docs": docs, "legislature": leg, "title": title, "sessions": sessions,
        "speeches": speeches, "votes": votes, "committee": committee,
    }


def speakers(debate: dict) -> list[dict]:
    seen = {}
    for s in debate["speeches"]:
        key = (s["name"], s["party"], s["role"])
        seen.setdefault(key, {"name": s["name"], "party": s["party"], "role": s["role"], "refs": []})
        seen[key]["refs"].append(s["ref"])
    return list(seen.values())


if __name__ == "__main__":
    import sys
    d = build(sys.argv[1])
    print(json.dumps({k: v for k, v in d.items() if k != "speeches"}, ensure_ascii=False, indent=1))
    print(len(d["speeches"]), "speeches,", sum(len(s["text"]) for s in d["speeches"]), "chars")
