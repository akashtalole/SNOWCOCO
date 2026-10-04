const API = "/api";

// ---------- Tabs ----------
document.querySelectorAll("nav.tabs button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav.tabs button").forEach(b => b.classList.remove("active"));
    document.querySelectorAll("main .panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "signals") loadSignals();
    if (btn.dataset.tab === "findings") loadFindings();
    if (btn.dataset.tab === "upi") loadUpiSignals();
  });
});

function escapeHtml(s) {
  return (s ?? "").toString()
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function citeChips(citations) {
  if (!citations || !citations.length) return "";
  return `<div class="cite-list">${citations.map(c =>
    `<span class="cite-chip" title="${escapeHtml(c.snippet)}">${escapeHtml(c.section_id)} · ${escapeHtml(c.title)}</span>`
  ).join("")}</div>`;
}

function formatINR(amount) {
  const n = Math.round(amount);
  const s = Math.abs(n).toString();
  let out;
  if (s.length <= 3) {
    out = s;
  } else {
    const last3 = s.slice(-3);
    let rest = s.slice(0, -3);
    const groups = [];
    while (rest.length > 2) { groups.unshift(rest.slice(-2)); rest = rest.slice(0, -2); }
    if (rest) groups.unshift(rest);
    out = groups.join(",") + "," + last3;
  }
  return (n < 0 ? "-" : "") + "₹" + out;
}

function renderNetworkSVG(nodes, edges) {
  const W = 720, H = 460, cx = W / 2, cy = H / 2;
  const hubs = nodes.filter(n => n.role === "hub");
  const sources = nodes.filter(n => n.role === "source");
  const cashouts = nodes.filter(n => n.role === "cashout");
  const pos = {};

  const hubR = hubs.length > 1 ? 65 : 0;
  hubs.forEach((n, i) => {
    const angle = (i / Math.max(hubs.length, 1)) * 2 * Math.PI - Math.PI / 2;
    pos[n.id] = hubs.length > 1
      ? {x: cx + hubR * Math.cos(angle), y: cy + hubR * Math.sin(angle)}
      : {x: cx, y: cy};
  });
  const outerR = Math.min(W, H) / 2 - 55;
  sources.forEach((n, i) => {
    const t = sources.length > 1 ? i / (sources.length - 1) : 0.5;
    const angle = Math.PI * 0.55 + t * Math.PI * 0.9;
    pos[n.id] = {x: cx + outerR * Math.cos(angle), y: cy + outerR * Math.sin(angle)};
  });
  cashouts.forEach((n, i) => {
    const t = cashouts.length > 1 ? i / (cashouts.length - 1) : 0.5;
    const angle = -Math.PI * 0.45 + t * Math.PI * 0.9;
    pos[n.id] = {x: cx + outerR * Math.cos(angle), y: cy + outerR * Math.sin(angle)};
  });

  const roleOf = {};
  nodes.forEach(n => { roleOf[n.id] = n.role; });

  const edgeEls = edges.map(e => {
    const a = pos[e.from], b = pos[e.to];
    if (!a || !b) return "";
    const cls = roleOf[e.from] === "hub" && roleOf[e.to] !== "hub" ? "edge-out" : "edge-in";
    return `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"
      class="net-edge ${cls}" marker-end="url(#arrow-${cls})">
      <title>${escapeHtml(e.from)} → ${escapeHtml(e.to)}: ${formatINR(e.amount)}</title>
    </line>`;
  }).join("");

  const nodeEls = nodes.map(n => {
    const p = pos[n.id];
    if (!p) return "";
    const r = n.role === "hub" ? 13 : 6;
    const titleExtra = n.account_id ? ` · ${n.account_id}` : "";
    return `<g class="net-node net-node-${n.role}" transform="translate(${p.x.toFixed(1)},${p.y.toFixed(1)})">
      <circle r="${r}"><title>${escapeHtml(n.label)} (${n.role}${escapeHtml(titleExtra)})</title></circle>
      ${n.role === "hub" ? `<text y="${-r - 6}" text-anchor="middle" class="net-label">${escapeHtml(n.account_id || n.label)}</text>` : ""}
    </g>`;
  }).join("");

  return `<div class="network-container">
    <svg viewBox="0 0 ${W} ${H}" class="network-svg">
      <defs>
        <marker id="arrow-edge-in" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" class="arrowhead-in" />
        </marker>
        <marker id="arrow-edge-out" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" class="arrowhead-out" />
        </marker>
      </defs>
      ${edgeEls}
      ${nodeEls}
    </svg>
  </div>`;
}

function signalCard(s, opts = {}) {
  const network = s.details && s.details.ring_nodes
    ? renderNetworkSVG(s.details.ring_nodes, s.details.ring_edges || [])
    : "";
  return `<div class="card" data-signal-id="${s.signal_id}">
    <h3>${escapeHtml(s.signal_type.replaceAll("_", " "))}
      <span class="badge ${s.severity}">${s.severity}</span>
    </h3>
    <div class="meta">${escapeHtml(s.account_id)} · ${escapeHtml(s.customer_name || s.customer_id)} · ${escapeHtml(s.signal_id)}</div>
    <div class="summary">${escapeHtml(s.summary)}</div>
    ${network}
    <div class="meta" style="margin-top:6px;">Evidence: ${(s.evidence_txn_ids || []).map(escapeHtml).join(", ")}</div>
    ${citeChips((s.citations || []).map(c => ({section_id: c, title: "", snippet: ""})))}
    ${opts.showGenerate ? `<div class="row-actions">
      <button class="btn generate-btn" data-signal-id="${s.signal_id}">Generate Finding</button>
    </div>` : ""}
  </div>`;
}

// ---------- Ask ----------
const SUGGESTIONS = [
  "Why was ACC-1001 flagged?",
  "List all signals",
  "What is the threshold for CTR reporting?",
  "Generate a finding for ACC-1002",
  "Show me high-risk jurisdiction activity",
  "Why was ACC-1009 flagged as a UPI mule hub?",
  "Show me the mule ring",
  "What triggers Enhanced Due Diligence?",
];
document.getElementById("suggestions").innerHTML = SUGGESTIONS.map(s =>
  `<span class="suggestion">${escapeHtml(s)}</span>`
).join("");
document.getElementById("suggestions").addEventListener("click", (e) => {
  if (e.target.classList.contains("suggestion")) {
    document.getElementById("ask-input").value = e.target.textContent;
    document.getElementById("ask-form").dispatchEvent(new Event("submit"));
  }
});

document.getElementById("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("ask-input");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  const log = document.getElementById("chat-log");
  const turnId = `turn-${Date.now()}`;
  log.insertAdjacentHTML("afterbegin", `<div class="chat-turn" id="${turnId}">
    <div class="chat-q"><b>You:</b> ${escapeHtml(question)}</div>
    <div class="card">Thinking…</div>
  </div>`);

  try {
    const res = await fetch(`${API}/ask`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question}),
    });
    const data = await res.json();
    const turn = document.getElementById(turnId);
    const signalsHtml = (data.signals || []).length
      ? `<div style="margin-top:10px;"><div class="meta">Evidence signals</div>${
          data.signals.map(s => signalCard(s, {showGenerate: true})).join("")}</div>`
      : "";
    const findingsHtml = (data.findings || []).length
      ? `<div style="margin-top:10px;" class="meta">Generated: ${
          data.findings.map(f => `<a href="#" class="view-finding" data-finding-id="${f.finding_id}" style="color:var(--accent)">${f.finding_id}</a>`).join(", ")
        }</div>`
      : "";
    turn.querySelector(".card").outerHTML = `<div class="card">
      <div class="summary">${escapeHtml(data.answer).replaceAll("\n", "<br/>")}</div>
      ${citeChips(data.citations)}
      ${signalsHtml}
      ${findingsHtml}
      <div class="chat-mode">answer mode: ${escapeHtml(data.mode)} · intent: ${escapeHtml(data.intent)}</div>
    </div>`;
  } catch (err) {
    const turn = document.getElementById(turnId);
    turn.querySelector(".card").outerHTML = `<div class="card">Error: ${escapeHtml(err.message)}</div>`;
  }
});

document.getElementById("chat-log").addEventListener("click", async (e) => {
  if (e.target.classList.contains("generate-btn")) {
    e.target.disabled = true;
    e.target.textContent = "Generating…";
    const signalId = e.target.dataset.signalId;
    await fetch(`${API}/findings/generate`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({signal_id: signalId}),
    });
    e.target.textContent = "Finding generated ✓";
  }
  if (e.target.classList.contains("view-finding")) {
    e.preventDefault();
    document.querySelector('nav.tabs button[data-tab="findings"]').click();
  }
});

// ---------- Signals ----------
let allSignals = [];

function renderStatsStrip(el, items) {
  const order = ["High", "Medium", "Low"];
  const counts = {High: 0, Medium: 0, Low: 0};
  items.forEach(i => { if (counts[i.severity] !== undefined) counts[i.severity]++; });
  const max = Math.max(1, ...order.map(sev => counts[sev]));
  el.innerHTML = order.map(sev => {
    const count = counts[sev];
    const pct = Math.round((count / max) * 100);
    return `<div class="stat-row">
      <span class="stat-label">${sev}</span>
      <span class="stat-bar-track"><span class="stat-bar-fill ${sev}" style="width:${count ? pct : 0}%"></span></span>
      <span class="stat-count">${count}</span>
    </div>`;
  }).join("");
}

function filteredSignals() {
  const sev = document.getElementById("signals-severity-filter").value;
  const q = document.getElementById("signals-search").value.trim().toLowerCase();
  return allSignals.filter(s => {
    if (sev && s.severity !== sev) return false;
    if (q) {
      const hay = `${s.account_id} ${s.customer_id} ${s.customer_name || ""} ${s.summary}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderSignalsList() {
  const el = document.getElementById("signals-list");
  const filtered = filteredSignals();
  if (!filtered.length) {
    el.innerHTML = `<div class="empty">No signals match the current filter.</div>`;
    return;
  }
  el.innerHTML = filtered.map(s => signalCard(s, {showGenerate: true})).join("");
}

async function loadSignals() {
  const el = document.getElementById("signals-list");
  el.innerHTML = `<div class="empty">Loading signals…</div>`;
  const res = await fetch(`${API}/signals`);
  const signals = await res.json();
  const order = {High: 0, Medium: 1, Low: 2};
  signals.sort((a, b) => order[a.severity] - order[b.severity]);
  allSignals = signals;
  renderStatsStrip(document.getElementById("signals-stats"), signals);
  if (!signals.length) {
    el.innerHTML = `<div class="empty">No signals detected.</div>`;
    return;
  }
  renderSignalsList();
}

document.getElementById("signals-severity-filter").addEventListener("change", renderSignalsList);
document.getElementById("signals-search").addEventListener("input", renderSignalsList);

document.getElementById("signals-list").addEventListener("click", async (e) => {
  if (e.target.classList.contains("generate-btn")) {
    e.target.disabled = true;
    e.target.textContent = "Generating…";
    const signalId = e.target.dataset.signalId;
    const res = await fetch(`${API}/findings/generate`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({signal_id: signalId}),
    });
    const f = await res.json();
    e.target.textContent = `Finding ${f.finding_id} ✓`;
  }
});

// ---------- Findings ----------
let allFindings = [];

function filteredFindings() {
  const sev = document.getElementById("findings-severity-filter").value;
  const q = document.getElementById("findings-search").value.trim().toLowerCase();
  return allFindings.filter(f => {
    if (sev && f.severity !== sev) return false;
    if (q) {
      const hay = `${f.account_id} ${f.customer_id} ${f.customer_name || ""} ${f.narrative || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function findingCard(f) {
  return `
    <div class="card" data-finding-id="${f.finding_id}">
      <h3>${escapeHtml(f.finding_id)} — ${escapeHtml(f.signal_type.replaceAll("_", " "))}
        <span class="badge ${f.severity}">${f.severity}</span>
        <span class="badge status status-badge">${escapeHtml(f.status)}</span>
      </h3>
      <div class="meta">${escapeHtml(f.account_id)} · ${escapeHtml(f.customer_name)} · ${escapeHtml(f.created_at)}</div>
      <div class="summary">${escapeHtml(f.narrative)}</div>
      <div class="row-actions">
        <label class="meta">Status:
          <select class="status-select" data-finding-id="${f.finding_id}">
            ${["Open", "Under Review", "Filed", "Closed"].map(st =>
              `<option value="${st}" ${st === f.status ? "selected" : ""}>${st}</option>`).join("")}
          </select>
        </label>
        <button class="btn secondary view-report-btn" data-finding-id="${f.finding_id}">View Report</button>
      </div>
      <div class="report-container" style="display:none;margin-top:10px;"></div>
    </div>
  `;
}

function renderFindingsList() {
  const el = document.getElementById("findings-list");
  const filtered = filteredFindings();
  if (!filtered.length) {
    el.innerHTML = `<div class="empty">No findings match the current filter.</div>`;
    return;
  }
  el.innerHTML = filtered.map(findingCard).join("");
}

async function loadFindings() {
  const el = document.getElementById("findings-list");
  el.innerHTML = `<div class="empty">Loading findings…</div>`;
  const res = await fetch(`${API}/findings`);
  const findings = await res.json();
  findings.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  allFindings = findings;
  if (!findings.length) {
    el.innerHTML = `<div class="empty">No findings generated yet. Go to the Signals tab and click "Generate Finding" on a signal, or ask the Copilot to generate one.</div>`;
    return;
  }
  renderFindingsList();
}

document.getElementById("findings-severity-filter").addEventListener("change", renderFindingsList);
document.getElementById("findings-search").addEventListener("input", renderFindingsList);

function renderHistoryTimeline(history) {
  if (!history || !history.length) return "";
  const items = history.map(h =>
    `<div class="history-item"><span class="history-at">${escapeHtml(h.at)}</span>${escapeHtml(h.event)}: ${escapeHtml(h.detail)}</div>`
  ).join("");
  return `<div class="history-timeline"><h4>Status History</h4>${items}</div>`;
}

function renderNotesSection(finding) {
  const notes = finding.notes || [];
  const items = notes.length
    ? notes.map(n =>
        `<div class="note-item"><div class="note-meta">${escapeHtml(n.at)} · ${escapeHtml(n.author)}</div>${escapeHtml(n.note)}</div>`
      ).join("")
    : `<div class="meta">No notes yet.</div>`;
  return `<div class="notes-section" data-finding-id="${finding.finding_id}">
    <h4>Notes</h4>
    <div class="notes-items">${items}</div>
    <div class="note-add-row">
      <input type="text" class="note-input" placeholder="Add a note…" />
      <button class="btn add-note-btn" data-finding-id="${finding.finding_id}">Add Note</button>
    </div>
  </div>`;
}

async function renderReportContainer(container, findingId) {
  const [mdRes, findingRes] = await Promise.all([
    fetch(`${API}/findings/${findingId}/report.md`),
    fetch(`${API}/findings/${findingId}`),
  ]);
  const md = await mdRes.text();
  const finding = await findingRes.json();
  const network = finding.network && finding.network.nodes
    ? renderNetworkSVG(finding.network.nodes, finding.network.edges || [])
    : "";
  container.innerHTML = `${network}<pre class="markdown-report">${escapeHtml(md)}</pre>
    ${renderHistoryTimeline(finding.history)}
    ${renderNotesSection(finding)}`;
}

document.getElementById("findings-list").addEventListener("click", async (e) => {
  if (e.target.classList.contains("view-report-btn")) {
    const findingId = e.target.dataset.findingId;
    const card = e.target.closest(".card");
    const container = card.querySelector(".report-container");
    if (container.style.display === "block") {
      container.style.display = "none";
      e.target.textContent = "View Report";
      return;
    }
    container.innerHTML = `<div class="empty">Loading report…</div>`;
    container.style.display = "block";
    e.target.textContent = "Hide Report";
    await renderReportContainer(container, findingId);
  }
  if (e.target.classList.contains("add-note-btn")) {
    const findingId = e.target.dataset.findingId;
    const notesSection = e.target.closest(".notes-section");
    const input = notesSection.querySelector(".note-input");
    const note = input.value.trim();
    if (!note) return;
    e.target.disabled = true;
    await fetch(`${API}/findings/${findingId}/notes`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({note}),
    });
    const container = e.target.closest(".report-container");
    await renderReportContainer(container, findingId);
  }
});

document.getElementById("findings-list").addEventListener("change", async (e) => {
  if (e.target.classList.contains("status-select")) {
    const findingId = e.target.dataset.findingId;
    await fetch(`${API}/findings/${findingId}/status`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({status: e.target.value}),
    });
    const card = e.target.closest(".card");
    card.querySelector(".status-badge").textContent = e.target.value;
    const finding = allFindings.find(f => f.finding_id === findingId);
    if (finding) finding.status = e.target.value;
    const container = card.querySelector(".report-container");
    if (container.style.display === "block") {
      await renderReportContainer(container, findingId);
    }
  }
});

// ---------- UPI Mule Network ----------
async function loadUpiSignals() {
  const el = document.getElementById("upi-list");
  el.innerHTML = `<div class="empty">Loading UPI signals…</div>`;
  const res = await fetch(`${API}/signals`);
  const signals = await res.json();
  const upiSignals = signals.filter(s => s.signal_type.startsWith("upi_"));
  const order = {High: 0, Medium: 1, Low: 2};
  const typeOrder = {upi_mule_ring: 0, upi_mule_hub: 1, upi_new_beneficiary_high_value: 2,
                      upi_dormant_reactivation: 3};
  upiSignals.sort((a, b) =>
    (typeOrder[a.signal_type] ?? 9) - (typeOrder[b.signal_type] ?? 9) ||
    order[a.severity] - order[b.severity]);
  renderStatsStrip(document.getElementById("upi-stats"), upiSignals);
  if (!upiSignals.length) {
    el.innerHTML = `<div class="empty">No UPI mule-network signals detected.</div>`;
    return;
  }
  el.innerHTML = upiSignals.map(s => signalCard(s, {showGenerate: true})).join("");
}

document.getElementById("upi-list").addEventListener("click", async (e) => {
  if (e.target.classList.contains("generate-btn")) {
    e.target.disabled = true;
    e.target.textContent = "Generating…";
    const signalId = e.target.dataset.signalId;
    const res = await fetch(`${API}/findings/generate`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({signal_id: signalId}),
    });
    const f = await res.json();
    e.target.textContent = `Finding ${f.finding_id} ✓`;
  }
});
