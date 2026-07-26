#!/usr/bin/env python3
"""Render a graded run as a self-contained HTML results page.

    python3 harness/report_html.py [runs/<id>] [--out results.html]

Everything comes from `scores.json`, `scoreboard.json` and the case labels, so the page
regenerates for any run instead of being a hand-maintained snapshot. The grader-calibration
figures are computed on the spot from the synthetic auditors in `selftest.py` — no API calls.

Design notes, since they are load-bearing rather than taste:

- Most numbers here cluster between 0.85 and 1.00. Bar charts of near-identical values fake
  a spread that is not in the data, so scores render as **meters against their 1.0 limit**
  and the precision lives in the label. The two figures with real spread — suite composition
  and grader calibration — get the forms that suit them.
- Light-mode aqua, yellow and magenta sit under 3:1 on the light surface, so the palette's
  relief rule applies: every segment is directly labelled and the full table view ships with
  the page.
- `?theme=dark` forces the dark scheme, which is how the README screenshots are captured.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import selftest  # noqa: E402
from evallib import cases as C, metrics as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

VERDICT_SLOT = {"KEEP": 1, "CUT": 2, "MERGE": 3, "MOVE": 4, "TRIM": 5}
OUTCOME_META = [
    ("exact", "Exact match", "good", "✓"),
    ("cautious", "Cautious — right family, softer verdict", "warning", "~"),
    ("missed", "Missed a no-op", "serious", "!"),
    ("destructive", "Cut a load-bearing directive", "critical", "✕"),
]
METRIC_LABEL = {
    "safety": "Safety — load-bearing lines kept",
    "recall": "Recall — no-ops found",
    "preservation": "Preservation — nouns survive",
    "compliance": "Compliance — report and process",
    "code_accuracy": "Code accuracy — right N/L code",
    "calibration": "Calibration — cut size fits file",
}


def gather(run_dir: Path) -> dict:
    payload = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    all_cases = {c["id"]: c for c in C.load_cases(ROOT)}

    truth = Counter()
    traps = 0
    for case in all_cases.values():
        for lab in C.load_labels(case):
            truth[lab["truth"].upper()] += 1
            if lab.get("severity") == "trap":
                traps += 1

    outcomes = Counter()
    traps_cut = 0
    for c in payload["cases"]:
        for p in c.get("details", {}).get("per_label", []):
            if p["credit"] == 1.0:
                outcomes["exact"] += 1
            elif p["credit"] > 0:
                outcomes["cautious"] += 1
            elif p["truth"] == "KEEP" and p["got"] == "CUT":
                outcomes["destructive"] += 1
            else:
                outcomes["missed"] += 1
            if p["severity"] == "trap" and p["got"] == "CUT" and p["truth"] != "CUT":
                traps_cut += 1

    calibration = {}
    audit = [c for c in all_cases.values() if c.get("kind", "audit") == "audit"]
    for mode in ("perfect", "lazy", "butcher", "vandal"):
        vals = []
        for case in audit:
            labels = C.load_labels(case)
            vals.append(M.score_case(case, labels, selftest.synth(case, labels, mode))["score"])
        calibration[mode] = sum(vals) / len(vals)

    board = []
    sb = ROOT / "scoreboard.json"
    if sb.exists():
        board = json.loads(sb.read_text(encoding="utf-8"))

    judged = (run_dir / "judge.json").exists()
    return {"summary": payload["summary"], "cases": payload["cases"], "run": run_meta,
            "case_defs": all_cases, "truth": truth, "traps": traps, "traps_cut": traps_cut,
            "outcomes": outcomes, "calibration": calibration, "board": board,
            "judged": judged}


# --------------------------------------------------------------------------- components


def meter(label: str, value, note: str = "", tip: str = "") -> str:
    if value is None:
        pct, shown = 0, "—"
    else:
        pct, shown = round(100 * value, 1), f"{value:.2f}"
    return f"""<div class="meter-row" data-tip="{html.escape(tip or label)}">
  <div class="meter-label">{label}{f'<span class="meter-note">{note}</span>' if note else ''}</div>
  <div class="meter-track"><div class="meter-fill" style="width:{pct}%"></div></div>
  <div class="meter-value">{shown}</div>
</div>"""


def stacked(items: list, total: int, kind: str) -> str:
    """items: [(key, label, css-class, glyph, count)] -> stacked bar + legend.

    A zero count draws no segment but keeps its legend row: "0 load-bearing lines cut" is
    the most important number on the page and dropping the row would hide it.
    """
    segs, legend = [], []
    for key, label, cls, glyph, count in items:
        legend.append(f'<li><span class="key {kind}-{cls}"></span>'
                      f'<span class="glyph">{glyph}</span>{label}'
                      f'<span class="key-count{" zero" if not count else ""}">{count}'
                      f'</span></li>')
        if not count:
            continue
        pct = 100 * count / total
        inline = f'<span class="seg-label">{count}</span>' if pct >= 7 else ""
        segs.append(f'<div class="seg {kind}-{cls}" style="flex:{count}" '
                    f'data-tip="{html.escape(label)}: {count} of {total}">{inline}</div>')
    return (f'<div class="stack">{"".join(segs)}</div>'
            f'<ul class="legend">{"".join(legend)}</ul>')


def table_view(data: dict) -> str:
    head = ("<tr><th>Case</th><th>Split</th><th>Score</th>"
            + "".join(f"<th>{k.replace('_', ' ')}</th>" for k in M.WEIGHTS)
            + "<th>Cut size</th></tr>")
    rows = []
    for c in sorted(data["cases"], key=lambda c: (c["split"], -c["score"])):
        cells = []
        for k in M.WEIGHTS:
            v = c["metrics"].get(k)
            cells.append("—" if v is None else f"{v:.2f}")
        red = c.get("details", {}).get("reduction_pct")
        band = data["case_defs"].get(c["case"], {}).get("expect", {}).get("reduction_pct")
        cut = "—" if red is None else (f"{red}%" + (f" <span class='dim'>of {band[0]}–{band[1]}%"
                                                   f"</span>" if band else ""))
        rows.append(f"<tr><td>{c['case']}</td><td>{c['split']}</td>"
                    f"<td><b>{c['score']:.2f}</b></td>"
                    + "".join(f"<td>{x}</td>" for x in cells) + f"<td>{cut}</td></tr>")
    return f"<table><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table>"


def render(data: dict) -> str:
    s, run = data["summary"], data["run"]
    train = [c for c in data["cases"] if c["split"] == "train"]
    hold = [c for c in data["cases"] if c["split"] == "holdout"]
    total_labels = sum(data["truth"].values())

    def case_meters(group: list) -> str:
        out = []
        for c in sorted(group, key=lambda c: -c["score"]):
            defn = data["case_defs"].get(c["case"], {})
            note = "trigger probes" if c["kind"] == "trigger" else defn.get("target", "")
            tip = (defn.get("description", "") or "")[:220]
            out.append(meter(c["case"], c["score"], note, tip))
        return "".join(out)

    metric_rows = "".join(
        meter(METRIC_LABEL[k], s["metric_means"].get(k), f"weight {M.WEIGHTS[k]:.2f}",
              f"{k}: mean {s['metric_means'].get(k)} across the suite, weighted "
              f"{M.WEIGHTS[k]:.2f}")
        for k in M.WEIGHTS)

    truth_items = [(v, v, f"v{VERDICT_SLOT[v]}", "", data["truth"].get(v, 0))
                   for v in ("KEEP", "CUT", "MERGE", "MOVE", "TRIM")]
    outcome_items = [(k, lbl, cls, glyph, data["outcomes"].get(k, 0))
                     for k, lbl, cls, glyph in OUTCOME_META]
    graded_labels = sum(data["outcomes"].values())

    cal_rows = "".join(
        meter(name, data["calibration"][key], desc, tip) for key, name, desc, tip in [
            ("perfect", "perfect", "the labels, rendered faithfully",
             "An auditor that reproduces the ground truth exactly"),
            ("lazy", "lazy", "finds nothing, keeps everything",
             "Scores well on safety and nothing else — conservative failure"),
            ("butcher", "butcher", "cuts everything, traps included",
             "Destroys every load-bearing line — must rank below lazy"),
            ("vandal", "vandal", "edits the original in place",
             "Hard gate: unusable output, zero regardless of classification"),
        ])

    def num(v) -> str:
        return "—" if v is None else f"{v:.4f}"

    board_rows = "".join(
        f"<tr><td>{html.escape(str(e.get('label')))}</td>"
        f"<td>{num(e.get('train'))}</td><td>{num(e.get('holdout'))}</td>"
        f"<td>{e.get('skill_md_chars', '—')}</td>"
        f"<td class='verdict-{e['verdict']}'>{e['verdict']}</td>"
        f"<td class='dim'>{html.escape((e.get('reason') or '')[:190])}</td></tr>"
        for e in data["board"])

    judged_note = ("Rewrite fidelity judged by model; the judge's score multiplies "
                   "preservation." if data["judged"] else
                   "Deterministic graders only — <code>judge.py</code> has not run on this "
                   "run.")

    return f"""<div class="viz-root" id="page">
<header>
  <p class="eyebrow">Eval suite · <code>eliminate-no-op</code></p>
  <h1>Does the skill actually find dead weight — without deleting anything live?</h1>
  <p class="sub">{len(data['cases'])} labelled cases · {total_labels} ground-truth
  directives · {data['traps']} of them traps a careless audit removes.
  Model <b>{html.escape(str(run.get('model')))}</b>, one sample per case,
  ${s['total_cost_usd']:.2f}. {judged_note}</p>
</header>

<section class="hero-band">
  <div class="hero">
    <p class="hero-label">Adjusted suite score</p>
    <p class="hero-figure">{s['adjusted_score']:.4f}</p>
    <p class="hero-sub">train {s['train_score']:.4f} · holdout {s['holdout_score']:.4f}
    · penalty {s['context_penalty']:.4f}</p>
  </div>
  <div class="tiles">
    <div class="tile"><p class="tile-label">Load-bearing lines cut</p>
      <p class="tile-value">{data['traps_cut']}<span class="tile-unit"> of
      {data['traps']}</span></p>
      <p class="tile-delta good">✓ safety {s['metric_means']['safety']:.2f}</p></div>
    <div class="tile"><p class="tile-label">No-ops found</p>
      <p class="tile-value">{s['metric_means']['recall']:.2f}</p>
      <p class="tile-delta dim">recall, weighted 0.25</p></div>
    <div class="tile"><p class="tile-label">Weakest metric</p>
      <p class="tile-value">{min((v, k) for k, v in s['metric_means'].items() if v)[0]:.2f}</p>
      <p class="tile-delta dim">{min((v, k) for k, v in s['metric_means'].items() if v)[1]
        .replace('_', ' ')}</p></div>
    <div class="tile"><p class="tile-label">Skill context cost</p>
      <p class="tile-value">{s['skill_cost']['description_tokens']}<span class="tile-unit">
      tok</span></p>
      <p class="tile-delta dim">description, in context every turn</p></div>
  </div>
</section>

<section>
  <h2>Per case</h2>
  <p class="note">Score out of 1.00. Holdout cases never enter the improvement digest.</p>
  <h3>Train</h3>
  <div class="meters">{case_meters(train)}</div>
  <h3>Holdout</h3>
  <div class="meters">{case_meters(hold)}</div>
</section>

<section>
  <h2>Where the score comes from</h2>
  <p class="note">Suite means, out of 1.00. Safety carries the most weight on purpose:
  deleting a line that was quietly preventing a bug costs more than leaving three
  redundant ones.</p>
  <div class="meters">{metric_rows}</div>
</section>

<section class="two-col">
  <div>
    <h2>What the suite is made of</h2>
    <p class="note">{total_labels} labelled directives by correct verdict.</p>
    {stacked(truth_items, total_labels, "v")}
  </div>
  <div>
    <h2>How the run classified them</h2>
    <p class="note">{graded_labels} graded verdicts across all cases.</p>
    {stacked(outcome_items, graded_labels, "o")}
  </div>
</section>

<section>
  <h2>Does the instrument discriminate?</h2>
  <p class="note">Four synthetic auditors graded against the same labels, no API calls.
  If the ranking ever collapses, the graders are broken — <code>selftest.py</code> asserts
  this ordering on every change.</p>
  <div class="meters">{cal_rows}</div>
</section>

<section>
  <h2>Improvement loop</h2>
  <p class="note">A candidate is accepted only if it gains on train without regressing on
  holdout. Rejections are kept in the record.</p>
  <div class="scroll"><table class="board">
    <thead><tr><th>Candidate</th><th>Train</th><th>Holdout</th><th>SKILL.md</th>
    <th>Verdict</th><th>Why</th></tr></thead>
    <tbody>{board_rows}</tbody>
  </table></div>
</section>

<section>
  <h2>Table view</h2>
  <p class="note">Every number on this page, unrounded in <code>scores.json</code>.</p>
  <div class="scroll">{table_view(data)}</div>
</section>

<footer>
  <p>Run <code>{html.escape(run.get('run_id', '?'))}</code> ·
  {html.escape(str(run.get('started')))} ·
  regenerate with <code>python3 harness/report_html.py</code></p>
</footer>
</div>"""


CSS = """
:root { color-scheme: light dark; }
.viz-root {
  color-scheme: light;
  --surface-1: #fcfcfb; --plane: #f9f9f7;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --baseline: #c3c2b7; --ring: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --track: #cde2fb;
  --v1: #2a78d6; --v2: #eb6834; --v3: #1baf7a; --v4: #eda100; --v5: #e87ba4;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b;
  --good-text: #006300;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --plane: #0d0d0d;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --ring: rgba(255,255,255,0.10);
    --series-1: #3987e5; --track: #184f95;
    --v1: #3987e5; --v2: #d95926; --v3: #199e70; --v4: #c98500; --v5: #d55181;
    --good-text: #0ca30c;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1: #1a1a19; --plane: #0d0d0d;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --baseline: #383835; --ring: rgba(255,255,255,0.10);
  --series-1: #3987e5; --track: #184f95;
  --v1: #3987e5; --v2: #d95926; --v3: #199e70; --v4: #c98500; --v5: #d55181;
  --good-text: #0ca30c;
}

/* The page plane lives on <body>, outside .viz-root's token scope, so it needs its own
   theme rules — otherwise a dark page sits on a light plane below the last card. */
body { margin: 0; background: #f9f9f7; }
@media (prefers-color-scheme: dark) {
  html:where(:not([data-theme="light"])) body { background: #0d0d0d; }
}
html[data-theme="dark"] body { background: #0d0d0d; }
html[data-theme="light"] body { background: #f9f9f7; }
.viz-root {
  background: var(--plane); color: var(--ink);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 40px 28px 56px; max-width: 1080px; margin: 0 auto;
}
header { margin-bottom: 28px; }
.eyebrow { color: var(--muted); font-size: 12.5px; letter-spacing: .06em;
  text-transform: uppercase; margin: 0 0 10px; }
h1 { font-size: 27px; line-height: 1.25; margin: 0 0 10px; font-weight: 650;
  letter-spacing: -0.01em; max-width: 26em; }
.sub { color: var(--ink-2); margin: 0; max-width: 60em; }
h2 { font-size: 15.5px; margin: 0 0 4px; font-weight: 650; letter-spacing: -0.005em; }
h3 { font-size: 12px; margin: 18px 0 8px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: .07em; }
.note { color: var(--ink-2); font-size: 13.5px; margin: 0 0 16px; max-width: 62em; }
section { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px;
  padding: 20px 22px 22px; margin-bottom: 16px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 34px; }
@media (max-width: 720px) { .two-col { grid-template-columns: 1fr; } }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .92em; }
.dim { color: var(--muted); }

/* hero + tiles */
.hero-band { display: grid; grid-template-columns: minmax(230px, 300px) 1fr; gap: 30px;
  align-items: center; }
@media (max-width: 720px) { .hero-band { grid-template-columns: 1fr; } }
.hero-label { color: var(--muted); font-size: 12.5px; margin: 0 0 2px;
  text-transform: uppercase; letter-spacing: .06em; }
.hero-figure { font-size: 58px; line-height: 1; font-weight: 600; margin: 0 0 8px;
  letter-spacing: -0.02em; }
.hero-sub { color: var(--ink-2); font-size: 13px; margin: 0; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
@media (max-width: 900px) { .tiles { grid-template-columns: repeat(2, 1fr); } }
.tile { border-left: 1px solid var(--grid); padding-left: 14px; }
.tile-label { color: var(--muted); font-size: 12px; margin: 0 0 4px; }
.tile-value { font-size: 25px; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
.tile-unit { font-size: 13px; font-weight: 400; color: var(--ink-2); }
.tile-delta { font-size: 12px; margin: 3px 0 0; color: var(--ink-2); }
.tile-delta.good { color: var(--good-text); font-weight: 550; }

/* meters */
.meters { display: flex; flex-direction: column; gap: 9px; }
.meter-row { display: grid; grid-template-columns: minmax(150px, 25em) 1fr 46px;
  gap: 14px; align-items: center; }
@media (max-width: 620px) { .meter-row { grid-template-columns: 1fr 70px; }
  .meter-track { grid-column: 1 / -1; } }
.meter-label { font-size: 13.5px; color: var(--ink); }
.meter-note { color: var(--muted); font-size: 12px; margin-left: 8px; }
.meter-track { background: var(--track); height: 10px; border-radius: 4px; }
.meter-fill { background: var(--series-1); height: 10px; border-radius: 0 4px 4px 0;
  min-width: 0; }
.meter-value { text-align: right; font-variant-numeric: tabular-nums; font-size: 13px;
  color: var(--ink-2); }

/* stacked bar */
.stack { display: flex; gap: 2px; height: 24px; margin-bottom: 14px; }
.seg { min-width: 3px; display: flex; align-items: center; justify-content: center; }
.seg:first-child { border-radius: 4px 0 0 4px; }
.seg:last-child { border-radius: 0 4px 4px 0; }
.seg-label { font-size: 11.5px; font-weight: 600; color: #fff;
  font-variant-numeric: tabular-nums; }
.v-v1 { background: var(--v1); } .v-v2 { background: var(--v2); }
.v-v3 { background: var(--v3); } .v-v4 { background: var(--v4); }
.v-v5 { background: var(--v5); }
.o-good { background: var(--good); } .o-warning { background: var(--warning); }
.o-serious { background: var(--serious); } .o-critical { background: var(--critical); }
/* ink, not white, wherever white on the fill lands under ~4.5:1 at this text size */
.v-v2 .seg-label, .v-v4 .seg-label, .v-v5 .seg-label,
.o-good .seg-label, .o-warning .seg-label, .o-serious .seg-label { color: #0b0b0b; }
.legend { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column;
  gap: 5px; }
.legend li { display: flex; align-items: center; font-size: 13px; color: var(--ink-2); }
.key { width: 10px; height: 10px; border-radius: 3px; margin-right: 9px; flex: none; }
.glyph { width: 15px; color: var(--muted); font-size: 12px; }
.key-count { margin-left: auto; font-variant-numeric: tabular-nums; color: var(--muted); }
.key-count.zero { color: var(--good-text); font-weight: 650; }

/* tables */
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; font-weight: 600; color: var(--muted); font-size: 11.5px;
  text-transform: uppercase; letter-spacing: .05em; padding: 0 12px 7px 0;
  border-bottom: 1px solid var(--grid); white-space: nowrap; }
td { padding: 7px 12px 7px 0; border-bottom: 1px solid var(--grid);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
td:first-child, .board td:last-child { font-variant-numeric: normal; }
.board td:last-child { white-space: normal; min-width: 22em; font-size: 12.5px; }
.verdict-accepted { color: var(--good-text); font-weight: 600; }
.verdict-rejected { color: var(--ink-2); }
.verdict-baseline { color: var(--muted); }

footer { color: var(--muted); font-size: 12.5px; margin-top: 22px; }
footer p { margin: 0; }

#tip { position: fixed; z-index: 9; pointer-events: none; opacity: 0;
  transition: opacity .09s; background: var(--surface-1); color: var(--ink);
  border: 1px solid var(--ring); border-radius: 7px; padding: 7px 10px;
  font: 12.5px/1.4 system-ui, sans-serif; max-width: 320px;
  box-shadow: 0 3px 12px rgba(0,0,0,.14); }
@media print { #tip { display: none; } }
"""

JS = """
(function () {
  var p = new URLSearchParams(location.search).get('theme');
  if (p === 'dark' || p === 'light') document.documentElement.dataset.theme = p;

  var tip = document.createElement('div');
  tip.id = 'tip';
  document.body.appendChild(tip);
  function show(e, text) {
    tip.textContent = text;
    tip.style.opacity = '1';
    var r = tip.getBoundingClientRect();
    var x = Math.min(e.clientX + 14, innerWidth - r.width - 10);
    var y = Math.max(e.clientY - r.height - 12, 8);
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  document.addEventListener('mousemove', function (e) {
    var el = e.target.closest('[data-tip]');
    if (el && el.dataset.tip) show(e, el.dataset.tip);
    else tip.style.opacity = '0';
  });
  // keyboard parity: focusable rows announce the same text
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.tabIndex = 0;
    el.setAttribute('aria-label', el.dataset.tip);
  });

  // Published so the screenshot script can size the window to the content instead of
  // guessing: `chrome --dump-dom | grep data-page-height`.
  document.documentElement.dataset.pageHeight =
    Math.ceil(document.getElementById('page').getBoundingClientRect().height) + 40;
})();
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import grade
    run_dir = Path(args.run_dir).resolve() if args.run_dir else grade.newest_run(ROOT)
    if not run_dir or not (run_dir / "scores.json").exists():
        print("error: no graded run found — run grade.py first", file=sys.stderr)
        return 1

    data = gather(run_dir)
    out = Path(args.out) if args.out else ROOT / "results.html"
    page = (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            f"<title>eliminate-no-op — eval results</title>\n<style>{CSS}</style></head>\n"
            f"<body>{render(data)}<script>{JS}</script></body></html>\n")
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page)} bytes) from {run_dir.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
