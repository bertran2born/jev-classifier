/* Buildless, browser-local CSV viewer. Also exports its data helpers for Node tests. */
"use strict";
const JevData = (() => {
  const dimensions = {
    field: ["Domaine", "Domaine scientifique principal de l’étude."],
    primary_finding: ["Résultat principal", "Soutien à l’hypothèse scientifique explicite des auteurs, sans interprétation idéologique."],
    significance: ["Significativité", "Significativité statistique explicitement rapportée pour le résultat principal."],
    preregistration: ["Préenregistrement", "Éléments explicites sur le préenregistrement ou un plan d’analyse prospectif."],
    choice_timing: ["Choix analytiques", "Chronologie déclarée des décisions analytiques. Des analyses post hoc ne démontrent pas une manipulation."],
    multiple_testing: ["Tests multiples", "Éléments sur le contrôle de la multiplicité ; l’étiquette ne garantit pas la correction de chaque test."],
    robustness: ["Robustesse", "Présence explicite d’analyses de sensibilité, de réplications ou de variantes du modèle."],
    exclusions: ["Exclusions", "Description des critères d’exclusion. « Critères décrits » ne garantit pas leur pertinence."],
    interpretation: ["Interprétation", "Cohérence apparente entre les conclusions et les statistiques fournies dans les extraits."],
  };
  const labels = {
    genetics:"Génétique", psychology:"Psychologie", economics:"Économie", sociology_politics:"Sociologie / politique", medicine:"Médecine", education:"Éducation", climate:"Climat", other_unclear:"Autre / indéterminé",
    supports:"Soutient l’hypothèse", contradicts:"Contredit l’hypothèse", mixed:"Résultats mixtes", unclear:"Indéterminé",
    significant:"Significatif", not_significant:"Non significatif", yes_explicit:"Préenregistrement déclaré", no_explicit:"Absence déclarée", not_established:"Non établi",
    prespecified:"Prévus à l’avance", posthoc_explicit:"Post hoc explicite", both:"Prévus et post hoc", unknown:"Inconnu", corrected:"Correction rapportée", uncorrected_explicit:"Absence de correction déclarée", not_applicable:"Non applicable",
    reported:"Analyses rapportées", absent_explicit:"Absence déclarée", justified:"Critères décrits", unknown_or_na:"Inconnu / non applicable", aligned:"Concordante", overclaim:"Conclusion excessive",
    ok:"Classifié", error:"Erreur", needs_ocr:"OCR nécessaire", needs_review:"Texte insuffisant", dry_run:"Extraction seule",
  };
  const unknown = new Set(["other_unclear", "unclear", "not_established", "unknown", "unknown_or_na"]);
  function label(value) { return labels[value] || value || "Non renseigné"; }
  function number(value) {
    if (value == null || String(value).trim() === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  function probability(value) { const n = number(value); return n !== null && n >= 0 && n <= 1 ? n : null; }
  function parseCSV(text) {
    text = text.replace(/^\uFEFF/, "");
    if (!text.trim()) throw new Error("Le fichier CSV est vide.");
    const firstLine = text.split(/\r?\n/, 1)[0];
    const delimiter = firstLine.includes(",") ? "," : ";";
    const lines = []; let row = [], value = "", quoted = false, closed = false;
    function cell() { row.push(value); value = ""; closed = false; }
    function line() { cell(); if (row.some(v => v.trim())) lines.push(row); row = []; }
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i+1] === '"') { value += '"'; i++; }
        else if (c === '"') { quoted = false; closed = true; }
        else value += c;
      } else if (c === '"') {
        if (value || closed) throw new Error("CSV invalide : guillemet inattendu.");
        quoted = true;
      } else if (c === delimiter) cell();
      else if (c === "\n" || c === "\r") { line(); if (c === "\r" && text[i+1] === "\n") i++; }
      else {
        if (closed) throw new Error("CSV invalide : caractères après un champ entre guillemets.");
        value += c;
      }
    }
    if (quoted) throw new Error("CSV invalide : guillemet non fermé.");
    if (value || row.length || closed) line();
    const headers = (lines.shift() || []).map(h => h.trim());
    if (!headers.includes("pdf") || !headers.includes("status")) throw new Error("Colonnes requises absentes : pdf et status.");
    if (new Set(headers).size !== headers.length || headers.some(h => !h)) throw new Error("Les en-têtes doivent être uniques et non vides.");
    const records = lines.map((cells, i) => {
      if (cells.length !== headers.length) throw new Error(`Ligne de données ${i+1} : ${cells.length} colonnes au lieu de ${headers.length}.`);
      return Object.fromEntries(headers.map((h,j) => [h, cells[j]]));
    });
    return { headers, records };
  }
  function needsReview(row, threshold = 0.8) {
    if (row.review_flags || ["error","needs_ocr","needs_review"].includes(row.status)) return true;
    if (row.status !== "ok") return false;
    return Object.keys(dimensions).some(key => !row[key] || unknown.has(row[key]) || probability(row[key+"_prob"]) === null || probability(row[key+"_prob"]) < threshold);
  }
  function normalize(text) { return String(text).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  function searchText(row) {
    const translated = Object.keys(dimensions).map(k => label(row[k]));
    return normalize([...Object.values(row), ...translated, label(row.status)].join(" "));
  }
  function compare(a, b, key, direction) {
    const av = a[key], bv = b[key];
    const numeric = key.endsWith("_prob") || ["chars_sent", "pages_read", "input_tokens"].includes(key);
    const an = numeric ? number(av) : av, bn = numeric ? number(bv) : bv;
    if (an == null || an === "") return bn == null || bn === "" ? 0 : 1;
    if (bn == null || bn === "") return -1;
    return direction * (numeric ? an-bn : label(an).localeCompare(label(bn), "fr", {numeric:true}));
  }
  function toCSV(headers, records) {
    const escape = value => {
      let text = String(value ?? "");
      if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    return "\uFEFF" + [headers, ...records.map(r => headers.map(h => r[h]))].map(row => row.map(escape).join(",")).join("\r\n");
  }
  return {dimensions, labels, unknown, label, number, probability, parseCSV, needsReview, normalize, searchText, compare, toCSV};
})();
if (typeof module !== "undefined") module.exports = JevData;

if (typeof document !== "undefined") {
  const D = JevData, $ = id => document.getElementById(id);
  const state = {records:[], headers:[], filtered:[], sort:"pdf", direction:1, page:0, size:25, request:0};
  const fmt = new Intl.NumberFormat("fr-FR");
  const percent = p => p === null ? "Non renseignée" : new Intl.NumberFormat("fr-FR", {style:"percent", maximumFractionDigits:1}).format(p);
  const basename = path => (path || "Étude sans nom").replace(/\\/g,"/").split("/").pop();
  function el(tag, text, className) { const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node; }
  function option(value, text) { const node = el("option",text); node.value = value; return node; }
  function threshold() { return Number($("threshold").value)/100; }
  function badge(value) {
    let tone = "";
    if (["ok","reported","aligned","justified"].includes(value)) tone="green";
    if (["medicine","psychology","supports","significant","prespecified"].includes(value)) tone="purple";
    if (D.unknown.has(value) || ["error","needs_ocr","needs_review","both","posthoc_explicit","overclaim","uncorrected_explicit"].includes(value)) tone="amber";
    return el("span",D.label(value),"badge "+tone);
  }
  function probNode(value) {
    const p=D.probability(value), wrap=el("div",null,"probability"+(p!==null && p<threshold()?" low":""));
    const track=el("span",null,"prob-track"), fill=el("span",null,"prob-fill");
    fill.style.width = `${(p??0)*100}%`; fill.style.display="block"; track.append(fill);
    wrap.append(track,el("span",p===null?"Probabilité absente":percent(p)));
    wrap.title="Probabilité attribuée par Jev à cette étiquette"; return wrap;
  }
  function fillValues() {
    const key=$("dimension").value;
    $("value-filter").replaceChildren(option("","Toutes les classifications"));
    const values=[...new Set(state.records.map(r=>r[key]||""))].sort((a,b)=>D.label(a).localeCompare(D.label(b),"fr"));
    for (const v of values) $("value-filter").append(option(v || "__missing",D.label(v)));
  }
  function resetFilters() {
    for (const id of ["search","status-filter","field-filter","value-filter"]) $(id).value="";
    $("review-only").checked=false; state.page=0; render();
  }
  function loadText(text, source) {
    const parsed = D.parseCSV(text);
    state.records=parsed.records; state.headers=parsed.headers;
    $("source").textContent=`${source} · ${fmt.format(state.records.length)} étude(s)`;
    $("field-filter").replaceChildren(option("","Tous les domaines"));
    for (const v of [...new Set(state.records.map(r=>r.field).filter(Boolean))].sort()) $("field-filter").append(option(v,D.label(v)));
    fillValues(); resetFilters();
  }
  async function autoLoad() {
    const request=++state.request;
    $("reload").disabled=true;
    $("source").textContent="Chargement des résultats locaux…";
    const paths=["jev-audit-results/results.csv","results.csv","jev-audit-api-check/results.csv"];
    for (const path of paths) {
      try {
        const response=await fetch(path,{cache:"no-store"});
        if (!response.ok) continue;
        const text=await response.text();
        if (request!==state.request) return;
        loadText(text,path); $("reload").disabled=false; return;
      } catch (error) { /* Try the next known output, then offer file import. */ }
      if (request!==state.request) return;
    }
    if (request===state.request) {
      $("source").textContent=location.protocol==="file:" ? "Importez votre results.csv avec le bouton ci-dessus. Le chargement automatique nécessite le serveur local." : "Aucun CSV valide trouvé. Importez results.csv ou relancez après l’analyse.";
      $("reload").disabled=false;
    }
  }
  async function importFile(file) {
    if (!file) return;
    const request=++state.request;
    try { const text=await file.text(); if (request===state.request) loadText(text,file.name); }
    catch (error) { if (request===state.request) $("source").textContent=`Import impossible : ${error.message} Les données précédentes sont conservées.`; }
    finally { if (request===state.request) $("reload").disabled=false; $("csv-file").value=""; }
  }
  function render() {
    const limit=threshold(); $("threshold-value").value=percent(limit);
    $("total").textContent=fmt.format(state.records.length);
    $("classified").textContent=fmt.format(state.records.filter(r=>r.status==="ok").length);
    $("review").textContent=fmt.format(state.records.filter(r=>D.needsReview(r,limit)).length);
    $("issues").textContent=fmt.format(state.records.filter(r=>["error","needs_ocr","needs_review"].includes(r.status)).length);
    const query=D.normalize($("search").value).trim();
    const status=$("status-filter").value, field=$("field-filter").value, key=$("dimension").value, value=$("value-filter").value;
    state.filtered=state.records.filter(row => (!query || D.searchText(row).includes(query)) && (!status || row.status===status) && (!field || row.field===field) && (!value || (value==="__missing" ? !row[key] : row[key]===value)) && (!$("review-only").checked || D.needsReview(row,limit)));
    state.filtered.sort((a,b)=>D.compare(a,b,state.sort,state.direction));
    state.page=Math.min(state.page,Math.max(0,Math.ceil(state.filtered.length/state.size)-1));
    $("result-count").textContent=`${fmt.format(state.filtered.length)} sur ${fmt.format(state.records.length)} étude(s) · seuil de relecture ${percent(limit)}`;
    $("export").disabled=!state.filtered.length;
    renderChart(key); renderTable();
  }
  function renderChart(key) {
    $("distribution-label").textContent=D.dimensions[key][0]; $("chart").replaceChildren();
    const counts=new Map();
    for (const row of state.filtered) counts.set(row[key]||"",(counts.get(row[key]||"")||0)+1);
    for (const [value,count] of [...counts.entries()].sort((a,b)=>b[1]-a[1])) {
      const button=el("button",null,"chart-row"), text=el("span"), track=el("div",null,"chart-track"), bar=el("div",null,"chart-bar");
      text.append(el("span",D.label(value)),el("strong",fmt.format(count)));
      bar.style.width=`${100*count/state.filtered.length}%`; track.append(bar); button.append(text,track);
      button.title=`Filtrer : ${D.label(value)} (${count})`;
      button.addEventListener("click",()=>{$("value-filter").value=value||"__missing";state.page=0;render();}); $("chart").append(button);
    }
    if (!counts.size) $("chart").append(el("p","Aucune donnée dans la sélection.","filter-note"));
  }
  function renderTable() {
    const keys=[["pdf","Étude"],["status","Statut"],...Object.entries(D.dimensions).map(([key,[title]])=>[key,title])];
    const head=el("tr");
    for (const [key,title] of keys) {
      const th=el("th"), button=el("button",title+(state.sort===key?(state.direction===1?" ↑":" ↓"):" ↕"));
      th.scope="col"; th.setAttribute("aria-sort",state.sort===key?(state.direction===1?"ascending":"descending"):"none");
      button.addEventListener("click",()=>{state.direction=state.sort===key?-state.direction:1;state.sort=key;state.page=0;render();});th.append(button);head.append(th);
    }
    // Also allow sorting by the probability of the criterion being explored.
    const key=$("dimension").value+"_prob", th=el("th"), button=el("button","Probabilité du critère"+(state.sort===key?(state.direction===1?" ↑":" ↓"):" ↕"));
    th.scope="col";th.setAttribute("aria-sort",state.sort===key?(state.direction===1?"ascending":"descending"):"none");
    button.title=D.dimensions[$("dimension").value][0];button.addEventListener("click",()=>{state.direction=state.sort===key?-state.direction:-1;state.sort=key;state.page=0;render();});th.append(button);head.append(th);
    $("table-head").replaceChildren(head); $("table-body").replaceChildren();
    for (const row of state.filtered.slice(state.page*state.size,(state.page+1)*state.size)) {
      const tr=el("tr");
      for (const [key] of keys) {
        const td=el("td");
        if (key==="pdf") {
          const button=el("button",basename(row.pdf),"study-button");button.title=row.pdf;button.addEventListener("click",()=>showDetail(row));
          td.append(button,el("span",D.needsReview(row,threshold())?"◌ À relire · Voir la fiche →":"Voir la fiche →","study-sub"));
        } else {td.append(badge(row[key]));if(key!=="status")td.append(probNode(row[key+"_prob"]));}
        tr.append(td);
      }
      tr.append(el("td",percent(D.probability(row[$("dimension").value+"_prob"]))));$("table-body").append(tr);
    }
    $("empty").hidden=!!state.filtered.length;
    const start=state.filtered.length?state.page*state.size+1:0,end=Math.min((state.page+1)*state.size,state.filtered.length);
    $("page-info").textContent=`${start}–${end} sur ${fmt.format(state.filtered.length)} étude(s)`;
    $("previous").disabled=state.page===0;$("next").disabled=end>=state.filtered.length;
  }
  function localLink(path, label) {
    if (location.protocol==="file:") return null;
    // Only project PDF/excerpt paths, never arbitrary URLs supplied by a CSV.
    const normalized=(path||"").replace(/\\/g,"/");
    const match=normalized.match(/(?:^|\/)(pdfs\/[^\n]+\.pdf|jev-audit-[^/]+\/excerpts\/[^/]+\.txt)$/i);
    if (!match || match[1].split("/").some(s=>s===".." || s===".")) return null;
    const a=el("a",label,"button secondary");a.href=match[1].split("/").map(encodeURIComponent).join("/");a.target="_blank";a.rel="noopener";return a;
  }
  function showDetail(row) {
    const content=$("detail-content");content.replaceChildren(el("h2",basename(row.pdf)),badge(row.status));
    content.append(el("p","Les résultats ci-dessous sont les classifications de Jev sur les extraits transmis, sans justification textuelle fournie par le modèle."));
    if (D.needsReview(row,threshold())) content.append(el("p","À relire : une alerte, une information inconnue ou manquante, ou une probabilité inférieure au seuil nécessite votre attention.","detail-warning"));
    if (row.error) content.append(el("p",row.error,"detail-warning"));
    const links=el("div",null,"detail-links");
    for (const [path,label] of [[row.pdf,"Ouvrir le PDF ↗"],[row.excerpt_file,"Lire les extraits ↗"]]) {const a=localLink(path,label);if(a)links.append(a);}content.append(links);
    const grid=el("div",null,"detail-grid");
    for (const [key,[title,description]] of Object.entries(D.dimensions)) {
      const card=el("article",null,"detail-card");card.append(el("h3",title),badge(row[key]),probNode(row[key+"_prob"]),el("p",description));
      card.append(el("p",`Confiance renvoyée par Jev : ${percent(D.probability(row[key+"_confidence"]))}. Ce n’est pas un intervalle de confiance statistique.`));
      if (!row[key] || D.unknown.has(row[key]) || D.probability(row[key+"_prob"])===null || D.probability(row[key+"_prob"])<threshold()) card.append(el("p","Information à vérifier dans l’article et ses annexes.","detail-warning"));
      try {
        const probs=JSON.parse(row[key+"_all_probabilities"]||"{}");
        if (probs && typeof probs==="object" && !Array.isArray(probs) && Object.keys(probs).length) {
          const details=el("details"), dl=el("dl");details.append(el("summary","Toutes les réponses possibles"));
          for (const [value,prob] of Object.entries(probs).sort((a,b)=>(D.probability(b[1])??-1)-(D.probability(a[1])??-1))) dl.append(el("dt",D.label(value)),el("dd",percent(D.probability(prob))));
          details.append(dl);card.append(details);
        }
      } catch {card.append(el("p","Distribution de probabilités illisible dans le CSV."));}
      grid.append(card);
    }
    content.append(grid);
    const metadata=el("dl",null,"metadata");
    for (const [label,value] of [["Modèle",row.model],["Couverture",row.coverage==="selected_excerpts_only"?"Extraits sélectionnés uniquement":row.coverage],["Pages lues / total",`${row.pages_read||"?"} / ${row.pages_total||"?"}`],["Pages utilisées",row.pages_used],["Caractères envoyés",row.chars_sent],["Jetons d’entrée",row.input_tokens],["Alertes du script",row.review_flags||"Aucune — ce n’est pas une validation de l’étude"],["Fichier PDF",row.pdf],["Fichier d’extraits",row.excerpt_file],["Identifiant",row.id]]) metadata.append(el("dt",label),el("dd",value||"Non renseigné"));
    content.append(metadata);$("detail").showModal();$("detail").scrollTop=0;
  }
  for (const [key,[title]] of Object.entries(D.dimensions)) $("dimension").append(option(key,title));
  $("dimension").value="choice_timing";
  $("dimension").addEventListener("change",()=>{fillValues();state.page=0;render();});
  for(const id of ["search","status-filter","field-filter","value-filter","review-only","threshold"]) $(id).addEventListener("input",()=>{state.page=0;render();});
  $("reset").addEventListener("click",resetFilters);$("reload").addEventListener("click",autoLoad);
  $("csv-file").addEventListener("change",event=>importFile(event.target.files[0]));
  $("previous").addEventListener("click",()=>{state.page--;render();});$("next").addEventListener("click",()=>{state.page++;render();});
  $("close-detail").addEventListener("click",()=>$("detail").close());
  $("detail").addEventListener("click",event=>{if(event.target===$("detail")){const rect=$("detail").getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)$("detail").close();}});
  $("export").addEventListener("click",()=>{
    const url=URL.createObjectURL(new Blob([D.toCSV(state.headers,state.filtered)],{type:"text/csv;charset=utf-8"}));
    const a=el("a");a.href=url;a.download="jev-selection.csv";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  document.addEventListener("keydown",event=>{if(event.key==="/"&&!$("detail").open&&!/INPUT|TEXTAREA|SELECT/.test(event.target.tagName)){event.preventDefault();$("search").focus();}});
  for(const type of ["dragenter","dragover"]) document.addEventListener(type,event=>{event.preventDefault();$("dropzone").classList.add("dragging");});
  document.addEventListener("dragleave",event=>{if(!event.relatedTarget)$("dropzone").classList.remove("dragging");});
  document.addEventListener("drop",event=>{event.preventDefault();$("dropzone").classList.remove("dragging");importFile(event.dataTransfer.files[0]);});
  render();autoLoad();
}
