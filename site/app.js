// Klare Kamer — renders data/debates.json. Routes: "" (list), "#debat-<doc>", "#over".
(function () {
  "use strict";

  const app = document.getElementById("app");
  let debates = [];

  const MONTHS = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
  const STANCE_LABEL = { voor: "voor", tegen: "tegen", onthouding: "onthouding", verdeeld: "verdeeld" };
  const STANCE_ORDER = { voor: 0, verdeeld: 1, onthouding: 2, tegen: 3 };
  const DOSSIER = (doc) =>
    `https://www.dekamer.be/kvvcr/showpage.cfm?section=/flwb&language=nl&cfm=/site/wwwcfm/flwb/flwbn.cfm?legislist=legisnr&dossierID=${doc}`;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    return `${d} ${MONTHS[m - 1]} ${y}`;
  };

  function finalVotes(d) { return d.votes.filter((v) => v.final && !v.reused); }
  // the final vote on the debate's primary document (joint debates have one per document)
  function mainVote(d) {
    const f = finalVotes(d);
    return f.filter((v) => v.docs.includes(d.doc)).pop() || f[f.length - 1];
  }
  function outcomeWord(v) {
    const r = (v.result.nl || "").toLowerCase();
    if (r.includes("verworpen") || r.includes("niet bereikt")) return "Verworpen";
    if (r.includes("aan") || r.includes("aangenomen")) return "Aangenomen";
    return "Gestemd";
  }
  function stanceChips(v) {
    if (!v || !v.by_party) return "";
    const parties = Object.entries(v.by_party).sort((a, b) => STANCE_ORDER[a[1].stance] - STANCE_ORDER[b[1].stance] || a[0].localeCompare(b[0]));
    return `<div class="strip" aria-label="Stemgedrag per partij">${parties
      .map(([p, x]) => `<span class="chip s-${x.stance}" title="${esc(p)}: ${STANCE_LABEL[x.stance]}">${esc(p)}</span>`)
      .join("")}</div>`;
  }
  function outcomeLine(v) {
    if (!v) return `<p class="outcome muted">Geen eindstemming gevonden</p>`;
    return `<p class="outcome"><b>${outcomeWord(v)}</b> op ${fmtDate(v.date)} · ${v.yes} voor · ${v.no} tegen · ${v.abstain} onthouding</p>`;
  }

  // ---------- list ----------
  function renderList(query) {
    const q = (query || "").trim().toLowerCase();
    const items = debates.filter((d) => !q || d._haystack.includes(q));
    app.innerHTML = `
      <div class="intro">
        <h1>Wat bespreekt de Kamer, en wie vindt wat?</h1>
        <p>Korte, neutrale samenvattingen van debatten in de plenaire vergadering van de Kamer van volksvertegenwoordigers:
        welk probleem een tekst wil oplossen, hoe elke partij stemde en welke argumenten er voor en tegen zijn gegeven.</p>
        <p class="small muted">Onafhankelijk proefproject, geen officiële website van de Kamer. Samenvattingen zijn gemaakt met AI op basis van het
        integraal verslag; elk citaat is automatisch nagekeken. <a href="#over">Hoe werkt dit?</a></p>
      </div>
      <div class="search">
        <label for="q">Zoek een debat</label>
        <input id="q" type="search" placeholder="bv. pensioen, leefloon, N-VA" value="${esc(query || "")}" autocomplete="off">
      </div>
      <p class="small muted" style="margin-bottom:.75rem">${items.length} van ${debates.length} debatten</p>
      <ul class="list">
        ${items.map((d) => {
          const v = mainVote(d);
          return `<li><a class="card" href="#debat-${esc(d.doc)}">
            <span class="eyebrow">DOC 56 ${esc(d.docs.join(", "))} · ${fmtDate(d.sessions[d.sessions.length - 1].date)}</span>
            <h2>${esc(d.summary.plain_title)}</h2>
            <span class="official">${esc(d.title.nl)}</span>
            ${outcomeLine(v)}
            ${stanceChips(v)}
          </a></li>`;
        }).join("") || `<li class="empty">Geen debatten gevonden voor “${esc(query)}”.</li>`}
      </ul>`;
    const input = document.getElementById("q");
    input.addEventListener("input", () => {
      const pos = input.selectionStart;
      renderList(input.value);
      const again = document.getElementById("q");
      again.focus();
      try { again.setSelectionRange(pos, pos); } catch (e) { /* ignore */ }
    });
  }

  // ---------- debate ----------
  function refLink(d, ref) {
    const [session, id] = ref.split("/");
    const s = d.sessions.find((x) => String(x.session) === session);
    const who = d._refNames[ref] || "";
    const label = `${who ? who + " · " : ""}PLEN ${session} · ${id}`;
    return s ? `<a href="${esc(s.url)}" target="_blank" rel="noopener" title="Integraal verslag CRIV 56 PLEN ${esc(session)}, tussenkomst ${esc(id)}">${esc(label)}</a>` : esc(label);
  }

  function renderVote(v, showTitle) {
    const t = v.yes + v.no + v.abstain || 1;
    const pct = (n) => (100 * n / t).toFixed(2) + "%";
    const parties = v.by_party ? Object.entries(v.by_party).sort((a, b) => STANCE_ORDER[a[1].stance] - STANCE_ORDER[b[1].stance] || a[0].localeCompare(b[0])) : [];
    return `<div class="vote">
      ${showTitle ? `<p class="small"><b>${esc(v.item_title)}</b></p>` : ""}
      ${outcomeLine(v)}
      <div class="bar" role="img" aria-label="${v.yes} voor, ${v.no} tegen, ${v.abstain} onthoudingen">
        <span class="y" style="width:${pct(v.yes)}"></span><span class="n" style="width:${pct(v.no)}"></span><span class="a" style="width:${pct(v.abstain)}"></span>
      </div>
      <div class="legend"><span><i style="background:var(--yes)"></i>${v.yes} voor</span><span><i style="background:var(--no)"></i>${v.no} tegen</span><span><i style="background:var(--abs)"></i>${v.abstain} onthouding</span></div>
      ${parties.length ? `<div class="parties">${parties.map(([p, x]) => `
        <div class="party"><span class="name">${esc(p)}</span><span class="chip s-${x.stance}">${STANCE_LABEL[x.stance]}</span>
        <span class="counts" title="voor / tegen / onthouding">${x.yes}/${x.no}/${x.abstain}</span></div>`).join("")}</div>` : `<p class="small muted">Geen naamstemming: stemgedrag per partij niet beschikbaar.</p>`}
    </div>`;
  }

  function renderArg(d, a) {
    return `<div class="arg">
      <p>${esc(a.point)}</p>
      <div class="strip">${a.actors.map((x) => `<span class="chip actor">${esc(x)}</span>`).join("")}</div>
      <blockquote>“${esc(a.quote)}”</blockquote>
      <span class="src">${refLink(d, a.quote_ref)}</span>
    </div>`;
  }

  function renderDebate(doc) {
    const d = debates.find((x) => x.doc === doc);
    if (!d) { app.innerHTML = `<a class="back" href="#">← Alle debatten</a><p class="empty">Debat ${esc(doc)} niet gevonden.</p>`; return; }
    const s = d.summary;
    const v = mainVote(d);
    const fv = finalVotes(d);
    const stanceOf = (actor) => (v && v.by_party && v.by_party[actor]) ? v.by_party[actor].stance : null;
    const positions = [...s.positions].sort((a, b) => {
      const sa = stanceOf(a.actor), sb = stanceOf(b.actor);
      if (a.actor === "Regering") return -1;
      if (b.actor === "Regering") return 1;
      return (STANCE_ORDER[sa] ?? 9) - (STANCE_ORDER[sb] ?? 9);
    });
    const spoke = new Set(s.positions.map((p) => p.actor));
    const silent = v && v.by_party ? Object.keys(v.by_party).filter((p) => !spoke.has(p)) : [];
    const checks = d.checks || [];
    const quotes = s.arguments_for.length + s.arguments_against.length;

    app.innerHTML = `
      <a class="back" href="#">← Alle debatten</a>
      <div class="head">
        <span class="eyebrow">DOC 56 ${esc(d.docs.join(", "))} · plenaire vergadering ${d.sessions.map((x) => fmtDate(x.date)).filter((x, i, a) => a.indexOf(x) === i).join(", ")}</span>
        <h1>${esc(s.plain_title)}</h1>
        <p class="official">Officiële titel: ${esc(d.title.nl)}${d.title.subtitles.nl.length ? " — samen besproken met: " + d.title.subtitles.nl.map(esc).join("; ") : ""}</p>
      </div>

      <section>
        <h2>Waarover gaat het?</h2>
        <p class="problem">${esc(s.problem)}</p>
        <h3>Wat verandert er?</h3>
        <ul class="changes">${s.proposal.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      </section>

      <section>
        <h2>Hoe stemde de Kamer?</h2>
        ${fv.length ? fv.map((x) => renderVote(x, fv.length > 1)).join("") : `<p class="muted">Er is (nog) geen eindstemming over deze tekst in de verwerkte verslagen.</p>`}
      </section>

      <section>
        <h2>Wie vindt wat?</h2>
        <div class="positions">${positions.map((p) => {
          const st = stanceOf(p.actor);
          return `<div class="position"><header><strong>${esc(p.actor)}</strong>${st ? `<span class="chip s-${st}">stemde ${STANCE_LABEL[st]}</span>` : ""}</header>
            <p>${esc(p.summary)}</p><div class="refs">${p.refs.map((r) => refLink(d, r)).join("")}</div></div>`;
        }).join("")}</div>
        ${silent.length ? `<p class="silent">Spraken niet in het plenaire debat: ${silent.map((p) => `${esc(p)} (stemde ${STANCE_LABEL[v.by_party[p].stance]})`).join(", ")}.
          Hun argumenten staan mogelijk in het <a href="${DOSSIER(d.doc)}" target="_blank" rel="noopener">commissieverslag</a>.</p>` : ""}
      </section>

      <section>
        <h2>De belangrijkste argumenten</h2>
        <div class="args">
          <div class="side for"><h3>Voor</h3>${s.arguments_for.map((a) => renderArg(d, a)).join("")}</div>
          <div class="side against"><h3>Tegen</h3>${s.arguments_against.map((a) => renderArg(d, a)).join("")}</div>
        </div>
      </section>

      <section class="method">
        <h2>Bronnen en controle</h2>
        <p>${checks.length ? `<span class="warn">${checks.length} controle(s) mislukt</span>` : `<span class="ok">Alle ${quotes} citaten letterlijk teruggevonden</span>`} in het integraal verslag.
          Samenvatting gemaakt met AI (${esc(d.meta.generator)}, versie ${esc(d.meta.prompt_version)}) op ${fmtDate(d.meta.generated_at.slice(0, 10))}.</p>
        ${checks.length ? `<ul>${checks.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
        ${(d.repairs || []).length ? `<p>Automatisch gecorrigeerd: ${d.repairs.length} citaat stond bij de verkeerde spreker en is aan de juiste toespraak gekoppeld.</p>` : ""}
        <ul>
          ${d.sessions.map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">Integraal verslag CRIV 56 PLEN ${x.session}</a> (${fmtDate(x.date)})</li>`).join("")}
          ${d.docs.map((x) => `<li><a href="${DOSSIER(x)}" target="_blank" rel="noopener">Dossier ${esc(x)} op dekamer.be</a> (wetsontwerp, amendementen, commissieverslag)</li>`).join("")}
        </ul>
        <details><summary>Sprekers in dit debat (${d.speakers.length})</summary>
          <ul>${d.speakers.map((p) => `<li>${esc(p.name || "Voorzitter")}${p.party ? ` (${esc(p.party)})` : p.role === "government" ? " (regering)" : ""} — ${p.refs.length} tussenkomst(en)</li>`).join("")}</ul>
        </details>
      </section>`;
    window.scrollTo(0, 0);
  }

  function renderAbout() {
    app.innerHTML = `
      <a class="back" href="#">← Alle debatten</a>
      <div class="head"><h1>Hoe werkt dit?</h1></div>
      <section>
        <p>Dit is een proefproject als antwoord op het burgerinitiatief voor transparante informatie over het werk van de Kamer
        (<a href="https://dekamer.mijnopinie.belgium.be/initiatives/i-1086/versions/3" target="_blank" rel="noopener">i-1086</a>), punt 2: toegankelijke informatie over debatten.</p>
        <h3>Waar komen de gegevens vandaan?</h3>
        <p>Uit het integraal verslag van de plenaire vergaderingen (CRIV) op dekamer.be. Een programma leest elk verslag in:
        agendapunten, wie sprak (en voor welke partij), en de stemmingen met de naamlijsten.</p>
        <h3>Wat is feit en wat is samenvatting?</h3>
        <ul class="changes">
          <li><b>Feit</b>: de stemresultaten, het stemgedrag per partij (berekend uit de naamstemming) en wie sprak.</li>
          <li><b>Samenvatting (AI)</b>: het probleem, wat er verandert, de standpunten en de argumenten.
          Het model mag alleen gebruiken wat in de toespraken staat.</li>
          <li><b>Controle</b>: bij elk argument staat een letterlijk citaat. Een programma kijkt na of dat citaat echt in die toespraak staat.</li>
        </ul>
        <h3>Beperkingen</h3>
        <ul class="changes">
          <li>Alleen het plenaire debat. Veel inhoudelijke discussie gebeurt in de commissies; partijen die in de plenaire niet spraken, hebben hier geen argumenten.</li>
          <li>Partijen worden afgeleid uit de huidige ledenlijst; wie van fractie wisselde, kan verkeerd staan bij oude stemmingen.</li>
          <li>AI kan nuances missen. Lees bij twijfel het verslag via de bronlinks.</li>
        </ul>
      </section>`;
  }

  function route() {
    const h = location.hash.replace(/^#/, "");
    if (h.startsWith("debat-")) renderDebate(h.slice(6));
    else if (h === "over") renderAbout();
    else renderList("");
  }

  fetch("data/debates.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      debates = data.map((d) => {
        d._refNames = {};
        d.speakers.forEach((p) => p.refs.forEach((r) => { d._refNames[r] = p.name || "Voorzitter"; }));
        const parties = d.summary.positions.map((p) => p.actor).join(" ");
        d._haystack = [d.summary.plain_title, d.title.nl, d.summary.problem, parties, d.docs.join(" ")].join(" ").toLowerCase();
        return d;
      });
      route();
      window.addEventListener("hashchange", route);
    })
    .catch((e) => { app.innerHTML = `<p class="empty">De gegevens konden niet geladen worden (${esc(e.message)}). Herlaad de pagina.</p>`; });
})();
