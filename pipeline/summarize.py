"""Summarise one debate with the Claude CLI and check the result against the source.

Usage: python -m pipeline.summarize 1721 [1789 674 ...]  -> data/debates/56/<doc>.json
       python -m pipeline.summarize --recheck            re-verify stored summaries

The model writes only text (problem, positions, arguments). Facts — who spoke, votes,
party stances — come from debate.build(). Every argument must carry a verbatim quote
from a referenced speech; quotes and refs are verified here and failures are recorded
under "checks" rather than silently dropped.
"""
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from pipeline.debate import build, speakers

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "debates"
PROMPT_VERSION = "1"
GOVERNMENT = "Regering"

ARGUMENT = {
    "type": "object",
    "properties": {
        "point": {"type": "string"},
        "actors": {"type": "array", "items": {"type": "string"}},
        "refs": {"type": "array", "items": {"type": "string"}},
        "quote": {"type": "string"},
        "quote_ref": {"type": "string"},
    },
    "required": ["point", "actors", "refs", "quote", "quote_ref"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "plain_title": {"type": "string"},
        "problem": {"type": "string"},
        "proposal": {"type": "array", "items": {"type": "string"}},
        "positions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "actor": {"type": "string"},
                "summary": {"type": "string"},
                "refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["actor", "summary", "refs"],
        }},
        "arguments_for": {"type": "array", "items": ARGUMENT},
        "arguments_against": {"type": "array", "items": ARGUMENT},
    },
    "required": ["plain_title", "problem", "proposal", "positions", "arguments_for", "arguments_against"],
}

SYSTEM = f"""Je bent een neutrale parlementaire verslaggever. Je maakt toegankelijke samenvattingen
van debatten in de Belgische Kamer voor burgers zonder politieke voorkennis.

Regels:
- Schrijf in eenvoudig Nederlands (B1-niveau), ook als sprekers Frans spraken.
- Gebruik uitsluitend wat in de aangeleverde toespraken staat. Geen eigen kennis, geen oordeel,
  geen bijvoeglijke naamwoorden die partij kiezen.
- "problem": 2–4 zinnen: welk maatschappelijk probleem wil de tekst aanpakken, volgens de indieners.
- "proposal": 2–5 korte punten: wat verandert er concreet.
- "positions": één item per partij die sprak, plus "{GOVERNMENT}" voor ministers. 1–2 zinnen
  over hun standpunt, met "refs" naar de toespraken. Gebruik partijnamen exact zoals aangeleverd.
- "arguments_for" / "arguments_against": de 3–6 belangrijkste argumenten aan elke kant.
  Voeg gelijkaardige argumenten van verschillende partijen samen (actors = alle partijen die het
  maakten). Behandel beide kanten even grondig en even neutraal.
- Elk argument heeft een "quote": een LETTERLIJK citaat (max. 30 woorden, in de originele taal,
  exact gekopieerd zonder wijzigingen) uit de toespraak in "quote_ref".
- refs hebben de vorm "150/19.05", exact zoals aangeleverd tussen vierkante haken.
- Het stemgedrag is aangeleverd als feit; spreek het niet tegen.
"""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"').replace("­", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def render_input(d: dict) -> str:
    lines = [f"# Debat over DOC {', '.join(d['docs'])}", "", f"Titel: {d['title']['nl']}"]
    for sub in d["title"]["subtitles"]["nl"]:
        lines.append(f"Samen besproken: {sub}")
    lines += ["", "## Stemmingen (feiten)"]
    for v in d["votes"]:
        if not v["final"]:
            continue
        lines.append(f"- [{v['ref']}] {v['item_title']}: {v['yes']} ja, {v['no']} nee, "
                     f"{v['abstain']} onthoudingen. {v['result']['nl']}")
        if v["by_party"]:
            lines.append("  Per partij: " + "; ".join(f"{p}: {x['stance']}" for p, x in v["by_party"].items()))
    lines += ["", "## Toespraken"]
    for s in d["speeches"]:
        who = s["name"] + (f" ({s['party']})" if s["party"] else f" ({GOVERNMENT})" if s["role"] == "government" else "")
        lines += ["", f"[{s['ref']}] {who} — {s['lang']}", s["text"]]
    return "\n".join(lines)


def call_claude(prompt: str) -> dict:
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "",
           "--system-prompt", SYSTEM, "--json-schema", json.dumps(SCHEMA)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    out = json.loads(r.stdout)
    if out.get("structured_output"):
        return out["structured_output"]
    text = out.get("result", "")
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def check(summary: dict, d: dict) -> list[str]:
    texts = {s["ref"]: norm(s["text"] + "\n" + (s.get("translation") or "")) for s in d["speeches"]}
    actors = {s["party"] for s in d["speeches"] if s["party"]} | {GOVERNMENT}
    by_ref = {s["ref"]: s for s in d["speeches"]}
    problems = []
    for p in summary["positions"]:
        if p["actor"] not in actors:
            problems.append(f"position: unknown actor {p['actor']!r}")
        problems += [f"position {p['actor']}: unknown ref {r}" for r in p["refs"] if r not in texts]
    for side in ("arguments_for", "arguments_against"):
        for i, a in enumerate(summary[side]):
            tag = f"{side}[{i}]"
            problems += [f"{tag}: unknown actor {x!r}" for x in a["actors"] if x not in actors]
            problems += [f"{tag}: unknown ref {r}" for r in a["refs"] if r not in texts]
            q = norm(a["quote"]).strip(" .\"'…")
            if a["quote_ref"] not in texts or q not in texts[a["quote_ref"]]:
                found = [r for r, t in texts.items() if q in t]
                if len(found) == 1:
                    # verbatim quote, wrong speech: fix the attribution, and say so
                    problems.append(f"{tag}: quote attributed to {a['quote_ref']}, "
                                    f"corrected to {found[0]} (repaired)")
                    a["quote_ref"] = found[0]
                    if found[0] not in a["refs"]:
                        a["refs"].append(found[0])
                else:
                    problems.append(f"{tag}: quote not found verbatim in {a['quote_ref']}")
                    continue
            speaker = by_ref[a["quote_ref"]]
            actor = speaker["party"] or (GOVERNMENT if speaker["role"] == "government" else None)
            if actor and actor not in a["actors"]:
                problems.append(f"{tag}: quoted speaker's party {actor} not among actors")
    spoke = {s["party"] for s in d["speeches"] if s["party"]}
    covered = {p["actor"] for p in summary["positions"]}
    problems += [f"positions: missing party {p}" for p in sorted(spoke - covered)]
    return problems


def summarize(doc: str, leg: int = 56) -> Path:
    d = build(doc, leg)
    summary = call_claude(render_input(d))
    out = {
        "doc": d["doc"], "docs": d["docs"], "legislature": leg,
        "title": d["title"], "sessions": d["sessions"],
        "speakers": speakers(d),
        "votes": d["votes"],  # refreshed by site/build.py
        "summary": summary,
        "meta": {"generator": "claude-cli", "prompt_version": PROMPT_VERSION,
                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }
    apply_checks(out, d)
    path = OUT_DIR / str(leg) / f"{d['doc']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return path


def apply_checks(out: dict, d: dict) -> None:
    """Run checks; repairs are kept permanently under "repairs", open problems under "checks"."""
    problems = check(out["summary"], d)
    repairs = [p for p in problems if p.endswith("(repaired)")]
    out["repairs"] = sorted(set(out.get("repairs", [])) | set(repairs))
    out["checks"] = [p for p in problems if not p.endswith("(repaired)")]


def recheck(leg: int = 56) -> None:
    """Re-run the source checks on stored summaries (after parser changes), without the model."""
    for path in sorted((OUT_DIR / str(leg)).glob("*.json")):
        out = json.loads(path.read_text())
        apply_checks(out, build(out["doc"], leg))
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(f"{path.name}: {len(out['checks'])} check failures")


if __name__ == "__main__":
    if sys.argv[1:] == ["--recheck"]:
        recheck()
        sys.exit()
    for doc in sys.argv[1:]:
        p = summarize(doc)
        c = json.loads(p.read_text())["checks"]
        print(f"{p}: {len(c)} check failures")
        for x in c:
            print("  -", x)
