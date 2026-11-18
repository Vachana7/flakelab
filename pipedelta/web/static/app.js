"use strict";
/* PipeDelta front end. No framework, no build step. Every number shown comes from /api. */

const $ = (sel, root = document) => root.querySelector(sel);
const view = $("#view");

/* ---------- tiny helpers ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") throw new Error("html attr is not allowed");
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function svg(markup, cls) {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  const el = t.content.firstChild;
  if (cls) el.setAttribute("class", cls);
  return el;
}
const LEVEL = { high: "High", medium: "Medium", low: "Low", none: "Clear" };
const KIND = {
  permission: "Token permission", secret: "Secret", network: "Outside address", action: "Unpinned action",
  trigger: "Trigger", runner: "Self-hosted runner", injection: "Script injection", other: "Other",
};
const confidenceHelp = (c) => ({ high: "The file states this directly.", medium: "Worked out by following where values flow.", low: "The file does not say; treat as unknown." }[c]);
const kindName = (k) => KIND[k] || k.replace(/[-_]/g, " ").replace(/^./, (c) => c.toUpperCase());
const badge = (level, text) => h("span", { class: `badge ${level}` }, text || LEVEL[level] || level);
function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
function toast(text, bad) {
  const t = h("div", { class: "toast" + (bad ? " bad" : "") }, text);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 4200);
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch("/api" + path, {
      method: opts.method || "GET",
      headers: opts.body ? { "Content-Type": "application/json" } : {},
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw { code: "network", message: "Cannot reach the PipeDelta server. Is it still running?" };
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw data?.error || { code: "http", message: `Request failed (${res.status}).` };
  return data;
}

function setCrumbs(...parts) {
  const c = $("#crumbs");
  c.replaceChildren();
  parts.forEach((p, i) => {
    if (i) c.append(h("span", { class: "faint" }, "/"));
    c.append(typeof p === "string" ? h("b", {}, p) : p);
  });
}
function nav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === name));
  $("#side").classList.remove("open");
}
function mount(...nodes) {
  view.replaceChildren(h("div", { class: "view-in" }, nodes));
  window.scrollTo(0, 0);
}
function loading(lines = 3) {
  mount(h("div", { class: "grid" }, Array.from({ length: lines }, () => h("div", { class: "skeleton", style: "height:84px" }))));
}
function errorBox(e, retry) {
  return h("div", { class: "err", role: "alert" },
    h("div", {},
      h("b", {}, e.code === "rate_limited" ? "GitHub rate limit reached" : "That did not work"),
      h("span", {}, e.message || "Unknown error."),
      e.code === "rate_limited" ? h("div", { class: "muted", style: "margin-top:6px" },
        "Start the server with a GITHUB_TOKEN to raise the limit, or use the pasted-workflow and sample modes, which need no network.") : null),
    retry ? h("button", { class: "btn", style: "margin-left:auto", onclick: retry }, "Try again") : null);
}

/* ---------- session (sidebar footer) ---------- */
async function loadSession() {
  const box = $("#session");
  try {
    const s = await api("/session");
    const gh = s.github;
    const rate = gh.rate && gh.rate.remaining !== undefined ? `${gh.rate.remaining} of ${gh.rate.limit} requests left` : "";
    box.replaceChildren(
      h("div", {}, h("span", { class: "dot " + (gh.token_set ? "ok" : "warn") }),
        gh.token_set ? (gh.user ? `GitHub: ${gh.user}` : "GitHub token set") : "No GitHub token"),
      rate ? h("div", { class: "faint" }, rate) : null,
      h("div", { class: "faint" }, `PipeDelta ${s.version}`));
  } catch (e) {
    box.replaceChildren(h("div", {}, h("span", { class: "dot warn" }), "Server unreachable"));
  }
}

/* ---------- charts (plain SVG) ---------- */
function gauge(level, counts) {
  const total = counts.high + counts.medium + counts.low;
  const col = { high: "var(--high)", medium: "var(--med)", low: "var(--low)", none: "var(--ok)" }[level];
  const R = 38, C = 2 * Math.PI * R;
  let off = 0, arcs = "";
  if (total) {
    for (const [k, c] of [["high", "var(--high)"], ["medium", "var(--med)"], ["low", "var(--low)"]]) {
      if (!counts[k]) continue;
      const len = (counts[k] / total) * C;
      arcs += `<circle r="${R}" cx="46" cy="46" stroke="${c}" stroke-width="8" stroke-dasharray="${Math.max(len - 2, 1)} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 46 46)"/>`;
      off += len;
    }
  } else arcs = `<circle r="${R}" cx="46" cy="46" stroke="${col}" stroke-width="8" opacity=".55"/>`;
  const wrap = h("div", { class: "gauge", role: "img", "aria-label": `${total} new findings, overall ${LEVEL[level]}` });
  wrap.append(svg(`<svg viewBox="0 0 92 92"><circle r="${R}" cx="46" cy="46" stroke="var(--panel2)" stroke-width="8"/>${arcs}</svg>`));
  wrap.append(h("b", {}, total ? String(total) : "✓"));
  return wrap;
}
function barRows(items, colorOf) {
  const max = Math.max(1, ...items.map((i) => i[1]));
  return h("div", { class: "bars" }, items.map(([label, value, color]) =>
    h("div", { class: "bar-row" }, h("span", {}, label),
      h("div", { class: "track" }, h("div", { class: "fill", style: `width:${(value / max) * 100}%;background:${color || colorOf}` })),
      h("span", { class: "v" }, value))));
}
function trendChart(points) {
  if (points.length < 2) return h("div", { class: "empty" }, h("h3", {}, "Not enough runs yet"), "The trend appears after two analyses.");
  const W = 560, H = 170, P = 30, n = points.length;
  const max = Math.max(1, ...points.map((p) => p.high + p.medium + p.low));
  const x = (i) => P + (i * (W - P - 14)) / (n - 1), y = (v) => H - 20 - (v / max) * (H - 40);
  const line = (key, color) => points.some((p) => p[key]) ? `<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${points.map((p, i) => `${x(i)},${y(p[key])}`).join(" ")}"/>` : "";
  const dots = points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.high)}" r="4" fill="var(--high)" stroke="var(--panel)" stroke-width="2"><title>${p.title.replace(/[<&>]/g, "")}: ${p.high} high, ${p.medium} medium, ${p.low} low</title></circle>`).join("");
  const grid = [0, 0.5, 1].map((f) => `<line x1="${P}" x2="${W - 14}" y1="${y(max * f)}" y2="${y(max * f)}" stroke="var(--line)"/><text x="${P - 8}" y="${y(max * f) + 5}" text-anchor="end" fill="var(--faint)" font-size="13">${Math.round(max * f)}</text>`).join("");
  return h("div", { class: "chart" }, svg(`<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Findings per analysis, oldest to newest">${grid}${line("medium", "var(--med)")}${line("high", "var(--high)")}${dots}</svg>`),
    h("div", { class: "meta", style: "margin-top:6px" }, h("span", {}, h("span", { class: "dot", style: "background:var(--high)" }), "High"), points.some((p) => p.medium) ? h("span", {}, h("span", { class: "dot", style: "background:var(--med)" }), "Medium") : null, h("span", { class: "faint" }, `last ${n} analyses, oldest first`)));
}

/* ---------- views ---------- */
async function overview() {
  nav("overview"); setCrumbs("Overview"); loading(3);
  let stats, recent;
  try { [stats, recent] = await Promise.all([api("/stats"), api("/analyses?limit=6")]); }
  catch (e) { return mount(errorBox(e, overview)); }
  const head = h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Overview"),
    h("p", {}, "What changed in your GitHub Actions workflows, and what each change lets an attacker do that they could not do before.")));
  if (!stats.analyses) {
    return mount(head, h("div", { class: "card empty" }, h("h3", {}, "No analyses yet"),
      "Connect a repository, or try one of the built-in examples. Everything here is computed from analyses you run.",
      h("div", { class: "chips", style: "justify-content:center;margin-top:16px" },
        h("a", { class: "btn primary", href: "#/analyze" }, "Analyze a workflow"),
        h("a", { class: "btn", href: "#/analyze?tab=samples" }, "Try an example"))));
  }
  const stat = (n, l, tone) => h("div", { class: "card stat" }, h("div", { class: "n", style: tone ? `color:var(--${tone})` : "" }, n), h("div", { class: "l" }, l));
  const f = stats.findings;
  mount(head,
    h("div", { class: "grid g4" },
      stat(stats.analyses, "analyses run"), stat(stats.repositories, "repositories connected"),
      stat(stats.levels.high, "high-risk changes", stats.levels.high ? "high" : null),
      stat(f.high + f.medium + f.low, "findings with evidence")),
    h("div", { class: "grid g32", style: "margin-top:16px" },
      h("div", { class: "card" }, h("div", { class: "sec-title" }, h("h2", {}, "Findings over time")), trendChart(stats.trend)),
      h("div", { class: "card" }, h("div", { class: "sec-title" }, h("h2", {}, "By severity")),
        barRows([["High", f.high, "var(--high)"], ["Medium", f.medium, "var(--med)"], ["Low", f.low, "var(--low)"]]),
        h("div", { class: "sec-title", style: "border-top:1px solid var(--line)" }, h("h2", {}, "How sure the tool is")),
        barRows([["Written in file", stats.confidence.high, "var(--accent)"], ["Inferred", stats.confidence.medium, "var(--accent2)"], ["File is silent", stats.confidence.low, "var(--faint)"]]))),
    h("div", { class: "grid g2", style: "margin-top:16px" },
      h("div", { class: "card" }, h("div", { class: "sec-title" }, h("h2", {}, "Recent analyses"), h("a", { class: "btn ghost", href: "#/history" }, "See all")),
        h("div", { class: "list" }, recent.analyses.map(analysisRow))),
      h("div", { class: "card" }, h("div", { class: "sec-title" }, h("h2", {}, "What kinds of power appeared")),
        Object.keys(stats.kinds).length ? barRows(Object.entries(stats.kinds).map(([k, v]) => [kindName(k), v, "var(--accent)"])) : h("div", { class: "empty" }, "Nothing new has been gained yet."))));
}

function analysisRow(a) {
  const total = a.counts.high + a.counts.medium + a.counts.low;
  return h("a", { class: "row", href: `#/analysis/${a.id}` },
    badge(a.level),
    h("div", { class: "grow" }, h("div", { class: "t" }, a.title), h("div", { class: "s" }, `${a.mode === "compare" ? "Change" : a.mode === "pull" ? "Pull request" : "Inventory"} · ${total} finding${total === 1 ? "" : "s"} · ${ago(a.created_at)}`)));
}

/* analyze */
const form = { tab: "github", repo: "", repoInfo: null, workflows: null, path: "", mode: "compare", pulls: null };
async function analyze(query) {
  nav("analyze"); setCrumbs("Analyze");
  const want = new URLSearchParams(query || "").get("tab");
  if (want) form.tab = want;
  const prefill = new URLSearchParams(query || "").get("repo");
  if (prefill && prefill !== form.repo) { form.repo = prefill; form.workflows = null; }
  let samples = [];
  try { samples = (await api("/samples")).samples; } catch { /* the page still works without them */ }
  draw();

  function draw() {
    const tabs = h("div", { class: "tabs", role: "tablist" }, [["github", "GitHub repository"], ["paste", "Paste a workflow"], ["samples", "Examples"]].map(([id, label]) =>
      h("button", { class: "tab" + (form.tab === id ? " on" : ""), role: "tab", "aria-selected": form.tab === id, onclick: () => { form.tab = id; draw(); } }, label)));
    const body = form.tab === "github" ? githubPanel() : form.tab === "paste" ? pastePanel() : samplesPanel();
    mount(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Analyze"), h("p", {}, "Pick what to examine. PipeDelta reads the workflow files and reports what a change makes possible, with the lines that show it."))), tabs, body);
  }

  function githubPanel() {
    const input = h("input", { class: "in", id: "repo", placeholder: "owner/name or https://github.com/owner/name", value: form.repo, autocomplete: "off", spellcheck: "false" });
    const status = h("div", { id: "gh-status" });
    const connect = async (ev) => {
      ev?.preventDefault();
      form.repo = input.value.trim();
      const btn = $("#connect"); btn.disabled = true; btn.replaceChildren(h("span", { class: "spin" }), "Connecting");
      try {
        const r = await api("/repos", { method: "POST", body: { repo: form.repo } });
        form.repoInfo = r.repo; form.workflows = r.workflows; form.path = r.workflows[0]?.path || ""; form.pulls = null;
        form.repo = r.repo.full_name; draw();
      } catch (e) { btn.disabled = false; btn.replaceChildren("Connect"); status.replaceChildren(errorBox(e)); }
    };
    const top = h("form", { class: "card pad", onsubmit: connect },
      h("div", { class: "step-n", style: "margin-bottom:12px" }, h("span", { class: "num" }, "1"), h("h2", {}, "Connect a repository")),
      h("label", { class: "f", for: "repo" }, "Repository", h("small", {}, "Public repositories work without a token. Private ones need GITHUB_TOKEN set when the server starts.")),
      h("div", { style: "display:flex;gap:10px" }, input, h("button", { class: "btn primary", id: "connect", type: "submit" }, "Connect")), status);
    if (!form.workflows) return h("div", { class: "grid", style: "max-width:720px" }, top);

    const r = form.repoInfo;
    const picker = h("select", { class: "in", id: "wf", onchange: (e) => { form.path = e.target.value; } },
      form.workflows.map((w) => h("option", { value: w.path, selected: w.path === form.path }, w.path)));
    const modeSeg = h("div", { class: "seg", role: "group", "aria-label": "What to analyze" }, [["compare", "Latest change"], ["inventory", "Current file"], ["pull", "Pull request"]].map(([id, label]) =>
      h("button", { type: "button", class: form.mode === id ? "on" : "", "aria-pressed": form.mode === id, onclick: () => { form.mode = id; if (id === "pull" && !form.pulls) loadPulls(); draw(); } }, label)));
    const run = h("button", { class: "btn primary", id: "run", onclick: runGithub }, "Run analysis");
    const pr = h("select", { class: "in", id: "prn" }, (form.pulls || []).map((p) => h("option", { value: p.number }, `#${p.number} ${p.title}${p.draft ? " (draft)" : ""}`)));
    const second = form.mode === "pull"
      ? h("label", { class: "f" }, "Open pull request", form.pulls === null ? h("span", { class: "muted" }, "Loading…") : form.pulls.length ? pr : h("span", { class: "muted" }, "This repository has no open pull requests."))
      : h("label", { class: "f" }, "Workflow file", form.workflows.length ? picker : h("span", { class: "muted" }, "No workflow files found."),
        h("small", {}, form.mode === "compare" ? "Compares the file's newest commit with the one before it." : "Reports what the file can do today."));
    if (form.mode === "pull" && form.pulls === null) loadPulls();
    return h("div", { class: "grid", style: "max-width:720px" }, top,
      h("div", { class: "card pad" },
        h("div", { class: "step-n", style: "margin-bottom:12px" }, h("span", { class: "num" }, "2"), h("h2", {}, "Choose what to analyze")),
        h("div", { class: "row", style: "cursor:default;padding:0 0 14px;border:0" }, h("div", { class: "grow" }, h("div", { class: "t" }, r.full_name), h("div", { class: "s" }, r.description || "No description")), h("span", { class: "badge plain" }, `${form.workflows.length} workflow${form.workflows.length === 1 ? "" : "s"}`)),
        modeSeg, h("div", { style: "height:14px" }), second, h("div", { id: "run-status" }), run));
  }
  async function loadPulls() {
    try { form.pulls = (await api(`/repos/${form.repo}/pulls`)).pulls; } catch { form.pulls = []; toast("Could not load pull requests.", true); }
    if (form.tab === "github") draw();
  }
  async function runGithub() {
    const btn = $("#run"), st = $("#run-status");
    let body;
    if (form.mode === "pull") {
      const n = Number($("#prn")?.value);
      if (!n) return st.replaceChildren(errorBox({ message: "Choose a pull request first." }));
      body = { mode: "pull", repo: form.repo, number: n };
    } else {
      if (!form.path) return st.replaceChildren(errorBox({ message: "This repository has no workflow file to analyze." }));
      body = { mode: form.mode, repo: form.repo, path: form.path };
    }
    btn.disabled = true; btn.replaceChildren(h("span", { class: "spin" }), "Analyzing");
    try { const a = await api("/analyses", { method: "POST", body }); location.hash = `#/analysis/${a.id}`; }
    catch (e) { btn.disabled = false; btn.replaceChildren("Run analysis"); st.replaceChildren(errorBox(e)); }
  }

  function pastePanel() {
    const before = h("textarea", { class: "in", id: "before", placeholder: "Optional. The workflow before the change.", spellcheck: "false" });
    const after = h("textarea", { class: "in", id: "after", placeholder: "on: pull_request\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make test", spellcheck: "false" });
    const st = h("div", { id: "paste-status" });
    const run = h("button", { class: "btn primary", onclick: async (ev) => {
      const b = ev.currentTarget; b.disabled = true; b.replaceChildren(h("span", { class: "spin" }), "Analyzing");
      try { const a = await api("/analyses", { method: "POST", body: { mode: "paste", before: before.value, after: after.value } }); location.hash = `#/analysis/${a.id}`; }
      catch (e) { b.disabled = false; b.replaceChildren("Run analysis"); st.replaceChildren(errorBox(e)); }
    } }, "Run analysis");
    return h("div", { class: "card pad" }, h("div", { class: "grid g2" },
      h("label", { class: "f" }, "Before ", h("small", {}, "leave empty to see what the workflow can do on its own"), before),
      h("label", { class: "f" }, "After", after)), st, run);
  }
  function samplesPanel() {
    if (!samples.length) return h("div", { class: "card empty" }, h("h3", {}, "No examples available"), "The server did not list any.");
    return h("div", { class: "grid g2" }, samples.map((s) => h("button", { class: "sample", onclick: async () => {
      try { const a = await api("/analyses", { method: "POST", body: { mode: "sample", sample: s.id } }); location.hash = `#/analysis/${a.id}`; }
      catch (e) { toast(e.message, true); }
    } }, h("b", {}, s.title), h("span", {}, s.description))));
  }
}

/* analysis result */
const ui = { tab: "findings", sev: "all", file: 0 };
async function analysis(id) {
  nav("analyze"); loading(3);
  let a;
  try { a = await api(`/analyses/${id}`); } catch (e) { setCrumbs("Analysis"); return mount(errorBox(e)); }
  ui.tab = "findings"; ui.sev = "all"; ui.file = 0;
  setCrumbs(h("a", { href: "#/history", class: "muted" }, "History"), a.title);
  render();

  function render() {
    const s = a.summary, file = a.files[ui.file] || null;
    const gate = s.would_fail ? "The GitHub Action would fail this change." : s.level === "none" ? "Nothing new that can do harm." : "Under the default gate; a person should still look.";
    const metaBits = [
      a.pull ? h("span", {}, `PR #${a.pull.number} by ${a.pull.author}`) : null,
      a.refs?.base || a.refs?.head ? h("span", { class: "mono" }, `${a.refs.base?.label || "—"} → ${a.refs.head?.label || "—"}`) : null,
      h("span", {}, `${s.files} workflow file${s.files === 1 ? "" : "s"}`),
      h("span", {}, ago(a.created_at)),
      s.reduced || s.improved ? h("span", {}, `${s.reduced + s.improved} power${s.reduced + s.improved === 1 ? "" : "s"} removed or made safer`) : null,
    ];
    const menu = h("div", { class: "menu-pop", hidden: true }, [["md", "Markdown", "to paste in a ticket"], ["html", "HTML", "one file, prints well"], ["sarif", "SARIF", "for GitHub code scanning"], ["json", "JSON", "the full result"]].map(([f, n, d]) =>
      h("a", { href: `/api/analyses/${a.id}/report?format=${f}`, download: "" }, n, h("small", {}, d))));
    const dl = h("button", { class: "btn", "aria-haspopup": "true", onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; } }, "Download report");
    document.addEventListener("click", () => { menu.hidden = true; }, { once: true });
    const hero = h("section", { class: `card hero ${s.level}` }, gauge(s.level, s.counts),
      h("div", {}, h("div", { style: "display:flex;gap:10px;align-items:center;margin-bottom:6px;flex-wrap:wrap" }, badge(s.level, `${LEVEL[s.level]} risk`),
        s.would_fail ? h("span", { class: "badge plain" }, "Gate: fail") : h("span", { class: "badge plain" }, "Gate: pass")),
        h("h1", {}, a.title), h("div", { class: "meta" }, metaBits), h("p", { class: "muted", style: "margin-top:8px" }, gate)),
      h("div", { class: "acts" }, h("div", { style: "position:relative" }, dl, menu),
        h("button", { class: "btn danger", onclick: async () => {
          if (!confirm("Delete this analysis from history?")) return;
          try { await api(`/analyses/${a.id}`, { method: "DELETE" }); toast("Analysis deleted."); location.hash = "#/history"; } catch (e) { toast(e.message, true); }
        } }, "Delete")));

    const allFindings = a.files.flatMap((f, fi) => f.findings.map((x) => ({ ...x, _file: fi })));
    const tabs = h("div", { class: "tabs", role: "tablist" }, [["findings", "Findings", allFindings.length], ["structure", "Jobs and steps", null], ["paths", "Attack paths", file?.paths.length ?? 0], ["diff", "Compare", null]].map(([id, label, c]) =>
      h("button", { class: "tab" + (ui.tab === id ? " on" : ""), role: "tab", "aria-selected": ui.tab === id, onclick: () => { ui.tab = id; render(); } }, label, c !== null ? h("span", { class: "c" }, c) : null)));
    const fileSel = a.files.length > 1 ? h("select", { class: "in", style: "max-width:380px;margin-bottom:14px", "aria-label": "Workflow file", onchange: (e) => { ui.file = Number(e.target.value); render(); } },
      a.files.map((f, i) => h("option", { value: i, selected: i === ui.file }, `${f.path} · ${f.summary.gained} finding${f.summary.gained === 1 ? "" : "s"}`))) : null;

    let body;
    if (!a.files.length) body = h("div", { class: "card empty" }, h("h3", {}, "No workflow files changed"), "This pull request does not touch any file in .github/workflows.");
    else if (ui.tab === "findings") body = findingsTab(allFindings, a);
    else if (ui.tab === "structure") body = h("div", {}, fileSel, structureTab(file, a));
    else if (ui.tab === "paths") body = h("div", {}, fileSel, pathsTab(file));
    else body = h("div", {}, fileSel, diffTab(file));
    mount(hero, tabs, body);
  }

  function findingsTab(list, a) {
    const shown = list.filter((f) => ui.sev === "all" || f.severity === ui.sev || (ui.sev === "removed" && ["reduced", "improved"].includes(f.change)));
    const chip = (id, label) => h("button", { class: "btn" + (ui.sev === id ? " primary" : ""), onclick: () => { ui.sev = id; render(); } }, label);
    const gained = list.filter((f) => !["reduced", "improved"].includes(f.change));
    const filters = h("div", { class: "filters" }, chip("all", `All ${list.length}`),
      ["high", "medium", "low"].map((k) => chip(k, `${LEVEL[k]} ${gained.filter((f) => f.severity === k).length}`)),
      list.some((f) => ["reduced", "improved"].includes(f.change)) ? chip("removed", "Removed or safer") : null);
    if (!list.length) return h("div", { class: "card empty" }, h("h3", {}, "No findings"), "This change gives the workflow no new power that PipeDelta can see. Removed and safer changes never raise the level.");
    return h("div", {}, filters, h("div", { class: "card" }, shown.length ? shown.map((f) => findingRow(f, a)) : h("div", { class: "empty" }, "No findings at this level.")));
  }
  function findingRow(f, a) {
    const where = [f.file, f.job && `job ${f.job}`, f.step && `step ${f.step}`, f.line && `line ${f.line}`].filter(Boolean).join(" · ");
    const good = ["reduced", "improved"].includes(f.change);
    return h("div", { class: "finding", tabindex: 0, role: "button", onclick: () => drawer(f), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drawer(f); } } },
      h("div", { class: `bar ${good ? "reduced" : f.severity}` }),
      h("div", { style: "min-width:0;flex:1" },
        h("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, good ? h("span", { class: "badge none" }, f.change === "reduced" ? "Removed" : "Safer") : badge(f.severity), h("span", { class: "t" }, f.title), h("span", { class: "badge plain" }, kindName(f.kind))),
        h("div", { class: "where" }, where), h("div", { class: "msg" }, f.message)),
      h("span", { class: "badge plain", title: confidenceHelp(f.confidence), style: "align-self:flex-start" }, { high: "Written in file", medium: "Inferred", low: "File is silent" }[f.confidence]));
  }

  function drawer(f) {
    const close = () => { bg.remove(); panel.remove(); document.removeEventListener("keydown", esc); prev?.focus(); };
    const esc = (e) => { if (e.key === "Escape") close(); };
    const prev = document.activeElement;
    const bg = h("div", { class: "drawer-bg", onclick: close });
    const where = [f.file, f.job && `job ${f.job}`, f.step && `step ${f.step}${f.step_label ? ` (${f.step_label})` : ""}`, f.line && `line ${f.line}`].filter(Boolean);
    const panel = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": f.title },
      h("div", { style: "display:flex;justify-content:space-between;align-items:center" },
        h("div", { style: "display:flex;gap:8px" }, badge(f.severity), h("span", { class: "badge plain" }, kindName(f.kind)), h("span", { class: "badge plain" }, { high: "Written in file", medium: "Inferred", low: "File is silent" }[f.confidence])),
        h("button", { class: "icon-btn", "aria-label": "Close", onclick: close }, svg('<svg viewBox="0 0 20 20"><path d="m5 5 10 10M15 5 5 15"/></svg>'))),
      h("h2", {}, f.title), h("p", { class: "muted" }, f.message),
      h("div", { class: "blk" }, h("h3", {}, "Where"), h("dl", { class: "kv" },
        h("dt", {}, "Location"), h("dd", {}, where.join("  ›  ")),
        h("dt", {}, "Precision"), h("dd", {}, { line: "exact line", job: "job only", file: "whole file" }[f.precision] || f.precision),
        h("dt", {}, "Side"), h("dd", {}, f.side === "before" ? "old file (this power was removed)" : "new file"))),
      f.previous || f.new ? h("div", { class: "blk" }, h("h3", {}, "What changed"), h("div", { class: "change" },
        h("div", { class: "a" }, h("small", {}, "Before"), f.previous || "—"), h("div", { class: "arr" }, "→"), h("div", { class: "b" }, h("small", {}, "After"), f.new || "—"))) : null,
      f.snippet?.length ? h("div", { class: "blk" }, h("h3", {}, "Evidence in the file"), h("div", { class: "code" }, f.snippet.map((l) =>
        h("div", { class: "ln" + (l.hit ? " hit" : "") }, h("i", {}, l.number), h("span", {}, l.text || " "))))) : null,
      h("div", { class: "blk" }, h("h3", {}, "Why it matters"), h("p", {}, f.consequence)),
      h("div", { class: "blk" }, h("h3", {}, "What to do"), h("p", {}, f.remediation)));
    document.body.append(bg, panel);
    document.addEventListener("keydown", esc);
    panel.querySelector("button").focus();
  }

  function structureTab(file, a) {
    if (!file?.structure.jobs.length) return h("div", { class: "card empty" }, h("h3", {}, "No jobs found"), "This file has no jobs section PipeDelta can read.");
    const byId = Object.fromEntries(file.findings.map((f) => [f.id, f]));
    return h("div", {}, file.structure.jobs.map((j) => {
      const facts = [];
      if (j.token?.known) {
        const base = j.token.default && j.token.default !== "none" ? `token: ${j.token.default}` : "token: no default access";
        facts.push(h("span", { class: "fact" + (j.write_scopes.length ? " hot" : "") }, j.write_scopes.length ? `${base} · can write ${j.write_scopes.join(", ")}` : base));
      }
      else if (j.token) facts.push(h("span", { class: "fact" }, "token: repository default"));
      j.secrets.forEach((s) => facts.push(h("span", { class: "fact hot" }, `secret ${s}`)));
      j.hosts.forEach((s) => facts.push(h("span", { class: "fact" }, `address ${s}`)));
      j.unpinned.forEach((s) => facts.push(h("span", { class: "fact hot" }, `unpinned ${s}`)));
      if (j.self_hosted) facts.push(h("span", { class: "fact hot" }, "self-hosted runner"));
      if (j.outsider_text) facts.push(h("span", { class: "fact hot" }, "uses outsider-written text"));
      return h("div", { class: "card job" },
        h("div", { class: "job-h" }, h("span", { class: "nm" }, j.name), j.runs_on ? h("span", { class: "faint" }, j.runs_on) : null,
          h("span", { style: "margin-left:auto" }, j.findings.length ? badge(byId[j.findings[0]]?.severity || "low", `${j.findings.length} finding${j.findings.length === 1 ? "" : "s"}`) : h("span", { class: "badge none" }, "No findings"))),
        facts.length ? h("div", { class: "facts" }, facts) : null,
        h("div", { class: "steps" }, j.steps.map((st) => {
          const fs = st.findings.map((id) => byId[id]).filter(Boolean);
          return h("div", { class: "step" + (fs.length ? " flag" : "") }, h("span", { class: "i" }, st.index),
            h("span", { class: st.kind === "run" ? "mono" : "" }, st.label), h("span", { class: "faint" }, `line ${st.line}`),
            fs.length ? h("button", { class: "btn", onclick: () => drawer(fs[0]) }, `${fs.length} finding${fs.length === 1 ? "" : "s"}`) : null);
        })));
    }));
  }
  function pathsTab(file) {
    if (!file?.paths.length) return h("div", { class: "card empty" }, h("h3", {}, "No attack paths"), "No job pairs a secret, a write token or an outside address with text an outsider controls.");
    return h("div", { class: "card" }, file.paths.map((p) => h("div", { class: "path" },
      h("div", { style: "display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap" }, badge(p.level), p.new ? h("span", { class: "badge plain" }, "Made possible by this change") : h("span", { class: "badge plain" }, "Already possible"), h("span", { class: "mono faint" }, p.jobs.join(", "))),
      pathFlow(p),
      h("p", {}, p.reason))));
  }
  const ENTRY = {
    injection: ["Outsider-controlled text", "pasted into a command"],
    network: ["Outside address", null],
    hidden: ["Hidden commands", "decoded and run"],
    action: ["Unpinned outside code", null],
    runner: ["Project's own machine", "keeps state between runs"],
  };
  function pathFlow(p) {
    const [t, sub] = ENTRY[p.first.kind] || [p.first.kind, null];
    const target = p.second.kind === "secret" ? ["Secret", p.second.name] : ["Token that can write", p.second.name];
    const node = (cls, title, detail) => h("div", { class: "pf-node " + cls }, h("strong", {}, title), detail ? h("span", { class: "mono" }, detail) : null);
    return h("div", { class: "pf", role: "img", "aria-label": `${t} reaches ${target[0]} ${target[1]} in the same job` },
      node("in", t, sub || p.first.name || null),
      h("div", { class: "pf-arrow", "aria-hidden": "true" }),
      node("job", "Same job", p.jobs.join(", ")),
      h("div", { class: "pf-arrow", "aria-hidden": "true" }),
      node("out " + p.level, target[0], target[1] || null));
  }
  function diffTab(file) {
    if (!file?.diff) return h("div", { class: "card empty" }, h("h3", {}, "Nothing to compare"), "This analysis looked at one version of the file. Use “Latest change” or a pull request to compare two.");
    if (file.diff.too_large) return h("div", { class: "card empty" }, h("h3", {}, "File too large for side-by-side"), "Download the JSON report to see the full text.");
    const byId = Object.fromEntries(file.findings.map((f) => [f.id, f]));
    const rows = file.diff.rows;
    const changed = rows.some((r) => r.t !== "eq");
    if (!changed) return h("div", { class: "card empty" }, h("h3", {}, "The two versions are identical"), "There is no change to compare.");
    const keep = new Set();
    rows.forEach((r, i) => { if (r.t !== "eq") for (let k = Math.max(0, i - 3); k <= Math.min(rows.length - 1, i + 3); k++) keep.add(k); });
    const tbody = h("tbody");
    let skipped = 0;
    rows.forEach((r, i) => {
      if (!keep.has(i)) { skipped++; return; }
      if (skipped) { tbody.append(h("tr", {}, h("td", { colspan: 4, class: "faint", style: "text-align:center;padding:4px" }, `${skipped} unchanged line${skipped === 1 ? "" : "s"}`))); skipped = 0; }
      const ids = [...(r.b?.findings || []), ...(r.a?.findings || [])];
      const pin = ids.length ? h("span", { class: "pin", role: "button", tabindex: 0, title: byId[ids[0]]?.title, onclick: () => drawer(byId[ids[0]]) }) : null;
      tbody.append(h("tr", { class: r.t + (ids.length ? " mark" : "") },
        h("td", { class: "n na" }, r.a?.n ?? ""), h("td", { class: "a" }, r.a?.text ?? ""),
        h("td", { class: "n nb" }, r.b?.n ?? ""), h("td", { class: "b" }, pin, r.b?.text ?? "")));
    });
    if (skipped) tbody.append(h("tr", {}, h("td", { colspan: 4, class: "faint", style: "text-align:center;padding:4px" }, `${skipped} unchanged line${skipped === 1 ? "" : "s"}`)));
    return h("div", {}, h("div", { class: "meta", style: "margin-bottom:10px" }, h("span", {}, h("span", { class: "pin", style: "display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--high)" }), "marks a line with a finding; click it for the evidence")),
      h("div", { class: "diff" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", { colspan: 2 }, "Before"), h("th", { colspan: 2 }, "After"))), tbody)));
  }
}

/* history */
async function history() {
  nav("history"); setCrumbs("History"); loading(2);
  let data;
  try { data = await api("/analyses?limit=200"); } catch (e) { return mount(errorBox(e, history)); }
  const list = data.analyses;
  const head = h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "History"), h("p", {}, "Every analysis you have run on this computer. Open one to see its evidence again or download a report.")));
  if (!list.length) return mount(head, h("div", { class: "card empty" }, h("h3", {}, "Nothing here yet"), "Run an analysis and it will be kept here.", h("div", {}, h("a", { class: "btn primary", href: "#/analyze" }, "Analyze a workflow"))));
  const search = h("input", { class: "in", placeholder: "Filter by repository or title", style: "max-width:320px", "aria-label": "Filter history" });
  const tbody = h("tbody");
  const draw = () => {
    const q = search.value.toLowerCase();
    const rows = list.filter((a) => a.title.toLowerCase().includes(q));
    tbody.replaceChildren(...(rows.length ? rows.map((a) => h("tr", { onclick: () => { location.hash = `#/analysis/${a.id}`; } },
      h("td", {}, badge(a.level)), h("td", {}, h("a", { href: `#/analysis/${a.id}`, onclick: (e) => e.stopPropagation() }, a.title)),
      h("td", { class: "muted" }, { compare: "Change", pull: "Pull request", inventory: "Inventory" }[a.mode]),
      h("td", { class: "mono" }, `${a.counts.high}/${a.counts.medium}/${a.counts.low}`), h("td", { class: "muted" }, ago(a.created_at)))) : [h("tr", {}, h("td", { colspan: 5, class: "empty" }, "No analysis matches that filter."))]));
  };
  search.addEventListener("input", draw); draw();
  mount(head, h("div", { class: "filters" }, search),
    h("div", { class: "card", style: "overflow:auto" }, h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Risk", "Analysis", "Type", "High/Med/Low", "When"].map((t) => h("th", {}, t)))), tbody)));
}

/* repositories */
async function repos() {
  nav("repos"); setCrumbs("Repositories"); loading(2);
  let data;
  try { data = await api("/repos"); } catch (e) { return mount(errorBox(e, repos)); }
  const head = h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Repositories"), h("p", {}, "Repositories you have connected. Only their workflow files are ever read.")), h("a", { class: "btn primary", href: "#/analyze?tab=github" }, "Connect a repository"));
  if (!data.repos.length) return mount(head, h("div", { class: "card empty" }, h("h3", {}, "No repositories connected"), "Connect one to pick its workflows and pull requests."));
  mount(head, h("div", { class: "grid g2" }, data.repos.map((r) => h("div", { class: "card pad" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;align-items:flex-start" },
      h("div", { style: "min-width:0" }, h("h2", { style: "overflow:hidden;text-overflow:ellipsis" }, r.full_name), h("p", { class: "muted", style: "margin-top:2px" }, r.description || "No description")),
      r.private ? h("span", { class: "badge plain" }, "Private") : h("span", { class: "badge plain" }, "Public")),
    h("div", { class: "meta", style: "margin:12px 0" }, h("span", {}, `default branch ${r.default_branch}`), r.language ? h("span", {}, r.language) : null,
      r.last_analysis ? h("span", {}, "last analysis ", badge(r.last_analysis.level)) : h("span", {}, "not analyzed yet")),
    h("div", { style: "display:flex;gap:8px" },
      h("a", { class: "btn primary", href: `#/analyze?tab=github&repo=${encodeURIComponent(r.full_name)}` }, "Analyze"),
      r.last_analysis ? h("a", { class: "btn", href: `#/analysis/${r.last_analysis.id}` }, "Last result") : null,
      h("button", { class: "btn ghost danger", style: "margin-left:auto", onclick: async () => {
        try { await api(`/repos/${r.full_name}`, { method: "DELETE" }); toast(`Removed ${r.full_name}.`); repos(); } catch (e) { toast(e.message, true); }
      } }, "Remove"))))));
}

/* ---------- router ---------- */
function route() {
  const [path, query] = location.hash.slice(1).split("?");
  const parts = (path || "/").split("/").filter(Boolean);
  if (!parts.length) return overview();
  if (parts[0] === "analyze") return analyze(query);
  if (parts[0] === "analysis" && parts[1]) return analysis(parts[1]);
  if (parts[0] === "history") return history();
  if (parts[0] === "repos") return repos();
  nav(""); setCrumbs("Not found");
  mount(h("div", { class: "card empty" }, h("h3", {}, "That page does not exist"), h("a", { class: "btn primary", href: "#/" }, "Go to overview")));
}
window.addEventListener("hashchange", route);
$("#menu").addEventListener("click", () => $("#side").classList.toggle("open"));
$("#session").replaceChildren(h("div", { class: "faint" }, "Checking GitHub…"));
loadSession();
route();
