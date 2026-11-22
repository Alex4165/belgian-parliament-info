# Klare Kamer (belgian-parliament-info)

Accessible summaries of debates in the Belgian Chamber of Representatives: what the problem is,
how each party voted, and the main arguments for and against. Response to the citizen initiative
[i-1086](https://dekamer.mijnopinie.belgium.be/initiatives/i-1086/versions/3), ask 2 ("toegankelijke informatie").

## Status

| Step | State |
|---|---|
| 1. Parse plenary reports into JSON | done: all 151 sessions of legislature 56 |
| 2. Summaries with Claude CLI, fixed format, source checks | done: 15 debates |
| 3. Static site | done (`site/` → `public/`) |
| 4. Nightly automation | workflow written; needs secret + Pages setting (below) |
| 5. Committee reports | done; French UI and expert hearings not yet |

## Design

**Facts vs. summary.** Everything that can be computed is computed, never generated:
who spoke, vote results, each party's vote (from the roll-call name lists × member list).
The model only writes text: plain title, problem, what changes, positions, arguments.

**Verification.** Every argument carries a verbatim quote plus the speech/page it comes from.
`summarize.check` verifies each quote word for word (punctuation-insensitive) in that source.
A quote found in exactly one other source gets its attribution repaired and logged (`repairs`);
anything else is listed under `checks` and shown on the page as a warning.

**Unit = document, not session.** A bill is debated in one session and voted in another;
jointly debated bills (e.g. 1789 + 1847) are merged. Key: document number.

**Sources**
- Plenary verbatim reports: `https://www.dekamer.be/doc/PCRI/html/56/ipNNNx.html`
  (provisional version first, later replaced by the definitive one with full translations)
- Committee reports ("VERSLAG" in the dossier): the Chamber's own written summary of the committee
  discussion, per member and party. PDF, bilingual columns. Many parties argue only here.
- Member list (name → party). The official open-data API (data.dekamer.be) holds only 2016 test data.

## Pipeline

```bash
pip install -r requirements.txt
python -m pipeline.update                 # fetch new/changed reports, parse, members, recheck
python -m pipeline.catalog                # list debated documents (pick what to summarise)
python -m pipeline.committee 1721         # fetch committee reports for a document
python -m pipeline.summarize 1721         # summarise with the claude CLI -> data/debates/56/1721.json
python -m pipeline.summarize --recheck    # re-verify stored summaries after parser changes
python site/build.py                      # -> public/ (open public/index.html via a local server)
python -m http.server -d public 8000
```

| Module | Does |
|---|---|
| `pipeline/fetch.py` | download a plenary report |
| `pipeline/parse_plenary.py` | report HTML → `data/plenary/56/ipNNN.json` (items, speeches, votes, named votes) |
| `pipeline/members.py` | member list → `data/members/56.json` |
| `pipeline/committee.py` | committee report PDFs → `data/committee/56/<id>.json` (text per page) |
| `pipeline/debate.py` | everything about one document: speeches, votes per party, committee pages |
| `pipeline/summarize.py` | prompt + JSON schema for `claude -p`, checks, repairs |
| `pipeline/catalog.py` | debated documents (≥2 parties spoke) |
| `pipeline/update.py` | nightly entry point |
| `site/` | static front end (vanilla JS, hash routes `#debat-1721`, `#over`) |

### Nightly (GitHub Actions)

`.github/workflows/nightly.yml` runs `pipeline.update --summarize 5`, commits `data/`, builds and
deploys to GitHub Pages. To enable:
1. Merge to the default branch (scheduled workflows only run there).
2. Settings → Secrets → Actions: add `ANTHROPIC_API_KEY` (without it only facts are updated).
3. Settings → Pages → Source: GitHub Actions.

## Known limits

- Party per member comes from the current member list (plus former members seen as speakers);
  party switches over time are not tracked.
- Very long committee reports are truncated to fit the model input (only the opening pages,
  usually the general discussion, are used). Affects e.g. 1243 and 1591.
- Expert hearings and Council of State opinions are not processed separately.
- Speech boundaries use a list of chair formulas; a stray procedural line may end up in a speech.
- Summaries are Dutch only; FR speeches are summarised in Dutch, quotes stay in the original language.
