"""Build dashboard/index.html: one self-contained page with the results inlined.

It opens by double-click with no server and no internet.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from pipedelta import __version__
from pipedelta.delta import compare

ROOT = Path(__file__).parent.parent
R = ROOT / "evaluation" / "results"
EX = ROOT / "examples"

LEVELS = ["none", "low", "medium", "high"]
LABEL = {"none": "No new power", "low": "Low", "medium": "Medium", "high": "High (blocked)"}


def load(name: str):
    return json.loads((R / name).read_text())


def esc(text: object) -> str:
    return html.escape(str(text))


def diff_block() -> str:
    before = (EX / "before.yml").read_text().splitlines()
    after = [
        line
        for line in (EX / "after-attack.yml").read_text().splitlines()
        if not line.startswith("#")
    ]
    rows = []
    for line in after:
        cls = "same" if line in before else "add"
        mark = " " if cls == "same" else "+"
        rows.append(f'<span class="{cls}"><i>{mark}</i>{esc(line)}</span>')
    return "".join(rows)


def findings_block() -> tuple[str, int]:
    findings = compare((EX / "before.yml").read_text(), (EX / "after-attack.yml").read_text())
    items = [
        f'<li><b class="lv lv-{f.level}">{f.level}</b><span>{esc(f.message)}</span></li>'
        for f in findings
    ]
    return "\n".join(items), len(findings)


def attack_rows(a1, a2) -> str:
    def cell(r):
        if not r["visible"]:
            return '<td class="st st-na">cannot see</td>'
        if r["blocked_at_default"]:
            return '<td class="st st-ok">blocked</td>'
        return f'<td class="st st-miss">missed ({esc(r["level"])})</td>'

    out = []
    for r1, r2 in zip(a1, a2, strict=True):
        out.append(
            f"<tr><td>{esc(r1['case'][:2])}</td><td>{esc(r1['title'])}</td>{cell(r1)}{cell(r2)}</tr>"
        )
    return "\n".join(out)


def bars(history) -> str:
    out = []
    for r in history:
        lv = r["levels"]
        n = sum(lv.get(k, 0) for k in LEVELS)
        segs = []
        for k in LEVELS:
            c = lv.get(k, 0)
            if not c:
                continue
            pct = 100 * c / n
            tip = f"{r['repo']}: {LABEL[k]}, {c} of {n} commits ({pct:.1f}%)"
            inner = f"{pct:.0f}%" if pct >= 9 else ""
            segs.append(
                f'<div class="seg seg-{k}" style="flex:{c} 1 0" tabindex="0" data-tip="{esc(tip)}">{inner}</div>'
            )
        out.append(
            f'<div class="row"><div class="name">{esc(r["repo"])}<small>{n} commits</small></div>'
            f'<div class="bar">{"".join(segs)}</div></div>'
        )
    return "\n".join(out)


def history_table(history) -> str:
    out = []
    tot = dict.fromkeys(LEVELS, 0)
    for r in history:
        lv = r["levels"]
        for k in LEVELS:
            tot[k] += lv.get(k, 0)
        cells = "".join(f"<td>{lv.get(k, 0)}</td>" for k in LEVELS)
        out.append(f"<tr><td>{esc(r['repo'])}</td>{cells}</tr>")
    cells = "".join(f"<td>{tot[k]}</td>" for k in LEVELS)
    out.append(f'<tr class="total"><td>Total</td>{cells}</tr>')
    return "\n".join(out)


def main() -> None:
    a1, a2 = load("attacks-v0.1.json"), load("attacks-v0.2.json")
    h1, h2 = load("history-v0.1.json"), load("history-v0.2.json")

    def blocked(rows):
        vis = [r for r in rows if r["visible"]]
        return sum(r["blocked_at_default"] for r in vis), len(vis)

    b1, nv = blocked(a1)
    b2, _ = blocked(a2)

    def hist(rows):
        high = sum(r["levels"].get("high", 0) for r in rows)
        n = sum(sum(r["levels"].values()) for r in rows)
        return high, n

    hi1, n1 = hist(h1)
    hi2, n2 = hist(h2)
    reasons: dict[str, int] = {}
    for r in h2:
        for k, v in r["high_reasons"].items():
            reasons[k] = reasons.get(k, 0) + v
    reason_rows = "\n".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])
    )
    items, count = findings_block()
    legend = "".join(f'<span><i class="seg-{k}"></i>{LABEL[k]}</span>' for k in LEVELS)

    page = TEMPLATE
    for key, value in {
        "VERSION": __version__,
        "DIFF": diff_block(),
        "FINDINGS": items,
        "COUNT": count,
        "B1": b1,
        "B2": b2,
        "NV": nv,
        "NALL": len(a2),
        "HI1": hi1,
        "HI2": hi2,
        "N2": n2,
        "P1": f"{100 * hi1 / n1:.1f}",
        "P2": f"{100 * hi2 / n2:.1f}",
        "ATTACKS": attack_rows(a1, a2),
        "BARS": bars(h2),
        "LEGEND": legend,
        "HTABLE": history_table(h2),
        "REASONS": reason_rows,
    }.items():
        page = page.replace("{{" + key + "}}", str(value))
    (ROOT / "dashboard" / "index.html").write_text(page)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PipeDelta</title>
<style>
:root{
  color-scheme:light;
  --page:#f3f5f8; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#d9dde3;
  --add:#e3f1e6; --add-ink:#14532d; --code:#f0f2f5;
  --seg-none:#86b6ef; --seg-low:#3987e5; --seg-medium:#1c5cab; --seg-high:#0d366b;
  --ok:#14532d; --miss:#8a2c0d; --na:#52514e;
}
@media (prefers-color-scheme:dark){
  :root{
    color-scheme:dark;
    --page:#111214; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --line:#34363a;
    --add:#17301f; --add-ink:#b7e4c2; --code:#232527;
    --seg-none:#184f95; --seg-low:#2a78d6; --seg-medium:#6da7ec; --seg-high:#b7d3f6;
    --ok:#8fd3a3; --miss:#f0a488; --na:#c3c2b7;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:2.6rem;line-height:1.1;margin:0 0 10px;letter-spacing:-.02em}
h2{font-size:1.45rem;margin:56px 0 6px;letter-spacing:-.01em}
p{margin:8px 0;max-width:70ch}
.lede{font-size:1.2rem;color:var(--ink2)}
.muted{color:var(--ink2)}
code,pre{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:.86rem}
.demo{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr);gap:0;margin-top:28px;background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.demo>div{padding:18px 20px;min-width:0}
.demo>div+div{border-left:1px solid var(--line)}
.demo h3{font-size:.95rem;margin:0 0 10px;color:var(--ink2);font-weight:600}
pre{margin:0;overflow-x:auto;line-height:1.5}
pre span{display:block;white-space:pre;padding-right:8px}
pre i{display:inline-block;width:1.4em;font-style:normal;color:var(--ink2)}
pre .add{background:var(--add);color:var(--add-ink)}
ul.find{list-style:none;margin:0;padding:0}
ul.find li{display:grid;grid-template-columns:4.6em 1fr;gap:10px;padding:8px 0;border-top:1px solid var(--line)}
ul.find li:first-child{border-top:0}
.lv{font-size:.8rem;font-weight:700;text-align:center;border:1.5px solid currentColor;border-radius:4px;height:1.7em;line-height:1.5em}
.lv-high{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.lv-medium{color:var(--ink)}
.lv-low{color:var(--ink2);font-weight:500}
.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.tile b{display:block;font-size:2rem;line-height:1.15;letter-spacing:-.02em}
.tile span{color:var(--ink2);font-size:.92rem}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin-top:16px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.93rem}
th,td{text-align:left;padding:7px 10px;border-top:1px solid var(--line);vertical-align:top}
thead th{border-top:0;color:var(--ink2);font-weight:600}
td:not(:first-child):not(:nth-child(2)),th:not(:first-child):not(:nth-child(2)){white-space:nowrap}
.st{font-weight:600}.st-ok{color:var(--ok)}.st-miss{color:var(--miss)}.st-na{color:var(--na);font-weight:400}
tr.total td{font-weight:700}
.num td:not(:first-child),.num th:not(:first-child){text-align:right}
.row{display:grid;grid-template-columns:130px 1fr;gap:12px;align-items:center;margin:9px 0}
.name{font-weight:600;font-size:.95rem}.name small{display:block;font-weight:400;color:var(--ink2);font-size:.78rem}
.bar{display:flex;gap:2px;height:26px}
.seg{min-width:3px;border-radius:0;color:#fff;font-size:.75rem;font-weight:600;display:flex;align-items:center;justify-content:center;cursor:default;outline-offset:2px}
.bar .seg:first-child{border-radius:4px 0 0 4px}.bar .seg:last-child{border-radius:0 4px 4px 0}
.seg-none{background:var(--seg-none);color:#0b0b0b}.seg-low{background:var(--seg-low)}.seg-medium{background:var(--seg-medium)}.seg-high{background:var(--seg-high)}
@media (prefers-color-scheme:dark){.seg-none,.seg-low{color:#fff}.seg-medium,.seg-high{color:#0b0b0b}}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.86rem;color:var(--ink2);margin:4px 0 14px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:6px 10px;border-radius:6px;font-size:.84rem;display:none;z-index:5;max-width:280px}
details{margin-top:12px}summary{cursor:pointer;color:var(--ink2);font-size:.92rem}
ul.plain{max-width:70ch;padding-left:1.2em}
ul.plain li{margin:6px 0}
footer{margin-top:56px;color:var(--ink2);font-size:.88rem}
@media (max-width:760px){
  h1{font-size:2rem}.demo{grid-template-columns:1fr}.demo>div+div{border-left:0;border-top:1px solid var(--line)}
  .tiles{grid-template-columns:1fr}.row{grid-template-columns:1fr;gap:4px}
}
</style>
</head>
<body>
<main>
<h1>PipeDelta</h1>
<p class="lede">When someone changes a project's GitHub Actions pipeline, PipeDelta tells the reviewer what new powers the pipeline just gained, in plain sentences.</p>

<div class="demo">
  <div>
    <h3>A pipeline change (green lines are new)</h3>
<pre>{{DIFF}}</pre>
  </div>
  <div>
    <h3>What PipeDelta reports: {{COUNT}} new powers</h3>
    <ul class="find">
{{FINDINGS}}
    </ul>
  </div>
</div>
<p class="muted">This example is a harmless imitation. The action and the address in it do not exist. The report on the right is the tool's real output for the change on the left.</p>

<h2>How well does it work?</h2>
<p>Two separate tests. Version 0.2 was written after looking at the version 0.1 results, so its attack score is not independent evidence.</p>
<div class="tiles">
  <div class="tile"><b>{{B1}} of {{NV}}</b><span>attack cases blocked by the first version, written before any testing</span></div>
  <div class="tile"><b>{{B2}} of {{NV}}</b><span>blocked by version 0.2, after two rules were added for the misses</span></div>
  <div class="tile"><b>{{P2}}%</b><span>of {{N2}} real past pipeline changes would have been blocked ({{P1}}% in the first version)</span></div>
</div>

<h2>Test 1: reconstructed attack cases</h2>
<p>{{NALL}} cases written for this project from public reports of real attacks, with placeholder addresses. They are not the original malicious files. In two of them nothing changes in the victim's workflow file, so no tool of this kind can see them.</p>
<div class="card">
<table>
<thead><tr><th>#</th><th>Case</th><th>Version 0.1</th><th>Version 0.2</th></tr></thead>
<tbody>
{{ATTACKS}}
</tbody>
</table>
</div>

<h2>Test 2: real pipeline history of eight projects</h2>
<p>Every past commit that changed a workflow file in eight well-known Python projects, replayed through PipeDelta {{VERSION}}. Each bar shows how those commits were rated. Only git history was read.</p>
<div class="card">
  <div class="legend">{{LEGEND}}</div>
{{BARS}}
  <details><summary>Show the numbers as a table</summary>
  <table class="num"><thead><tr><th>Project</th><th>No new power</th><th>Low</th><th>Medium</th><th>High (blocked)</th></tr></thead>
  <tbody>
{{HTABLE}}
  </tbody></table></details>
</div>
<p>These commits are not labelled, so {{P2}}% is a block rate, not a false-alarm rate. None of them is a known attack. About one in ten is too many for a strict gate on a busy project; today the tool fits best as an advisory comment.</p>
<div class="card">
<table class="num"><thead><tr><th>Why commits were blocked (high-level findings, version 0.2)</th><th>Findings</th></tr></thead>
<tbody>
{{REASONS}}
</tbody></table>
</div>

<h2>What it cannot do</h2>
<ul class="plain">
<li>It reads workflow files only. It does not look inside the outside actions or scripts a workflow calls.</li>
<li>It misses internet addresses that are built from variables.</li>
<li>It cannot see attacks that change no workflow file, such as a moved version tag.</li>
<li>A pull request that removes the PipeDelta check can switch it off unless the check is marked as required.</li>
<li>It has not been compared against existing scanners on the same cases.</li>
</ul>

<footer>PipeDelta {{VERSION}}. Numbers on this page are generated from <code>evaluation/results/</code> by <code>evaluation/build_dashboard.py</code>. Method and limits: <code>docs/EVALUATION.md</code>.</footer>
</main>
<div id="tip" role="status"></div>
<script>
const tip=document.getElementById('tip');
function show(e,el){tip.textContent=el.dataset.tip;tip.style.display='block';
  const r=el.getBoundingClientRect();const x=e.clientX||r.left+r.width/2,y=e.clientY||r.top;
  tip.style.left=Math.min(x+12,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=Math.max(8,y-tip.offsetHeight-10)+'px';}
document.querySelectorAll('.seg').forEach(el=>{
  el.addEventListener('mousemove',e=>show(e,el));
  el.addEventListener('focus',e=>show(e,el));
  el.addEventListener('mouseleave',()=>tip.style.display='none');
  el.addEventListener('blur',()=>tip.style.display='none');
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
