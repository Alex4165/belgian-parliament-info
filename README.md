# belgian-parliament-info

Accessible summaries of debates in the Belgian Chamber of Representatives: what the problem is,
who takes which side, and the main arguments. Response to the citizen initiative
[i-1086](https://dekamer.mijnopinie.belgium.be/initiatives/i-1086/versions/3), ask 2 ("toegankelijke informatie").

## Plan

1. **Parse** plenary verbatim reports into structured JSON  ← current
2. Summarise 3 debates (Claude CLI) and agree on the format
3. Minimal static page for those debates
4. Automate (nightly)
5. Committee reports, French, search

## Pipeline

```bash
pip install -r requirements.txt
python -m pipeline.fetch 149 150 151                 # -> data/raw/56/ipNNNx.html (not committed)
python -m pipeline.parse_plenary data/raw/56/ip15*x.html   # -> data/plenary/56/ipNNN.json
```

Source: `https://www.dekamer.be/doc/PCRI/html/56/ipNNNx.html` (CRIV, legislature 56).
The official open-data API (data.dekamer.be) only holds 2016 test data.

## Output (`data/plenary/<leg>/ipNNN.json`)

- `source`: legislature, session number, URL, date, part of day, provisional flag
- `items[]`: agenda items
  - `number`, `section` (nl/fr), `title` (nl/fr), `subtitles` (joint items / interpellations)
  - `docs`: parliamentary document base numbers (e.g. `1721`), the key that links
    a debate in one session to its vote in a later one
  - `events[]` in order:
    - `speech`: `id`, `name`, `party`, `role` (`government`/`chair`/null), `lang`, `paragraphs`
    - `procedure`: chair formulas and other non-speech lines
    - `heading`: sub-sections (e.g. "Algemene bespreking")
    - `vote`: `number`, `subject`, `yes`/`no`/`abstain`/`total`, `result`, `reused`
      (when "the previous result applies")
    - `note`: italic remarks (applause, interruptions)
- `named_votes`: vote number → `yes`/`no`/`abstain` member names

## Known limits

- Named votes list members without party; a member→party map is still needed.
- Speech boundaries rely on a list of chair formulas; a stray procedural line may end up
  inside a speech.
