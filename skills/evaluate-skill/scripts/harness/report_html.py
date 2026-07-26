#!/usr/bin/env python3
"""Render a graded run as a self-contained HTML results page.

    python3 harness/report_html.py [runs/<id>] [--out results.html]

Everything comes from `scores.json` and `scoreboard.json`, so the page regenerates for any
run instead of being hand-maintained.

Two design notes, since they are load-bearing rather than taste:

- Scores cluster near the top of their range once a skill is any good, and bar charts of
  near-identical values invent a spread that is not in the data. Scores render as **meters
  against their 1.0 limit**, with the precision in the label. Only the check pass/fail
  breakdown, which has real spread, gets a proportional bar.
- The palette is one hue for magnitude plus reserved status colours for pass/fail state,
  validated against both surfaces. Light-mode status amber sits under 3:1, so every segment
  is directly labelled and the full table ships with the page.

`?theme=dark` forces the dark scheme, which is how the screenshots are captured.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))


def gather(run_dir: Path) -> dict:
    payload = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    board = []
    sb = ROOT / "scoreboard.json"
    if sb.exists():
        board = json.loads(sb.read_text(encoding="utf-8"))

    defs = {}
    for case_json in sorted((ROOT / "cases").glob("*/case.json")):
        c = json.loads(case_json.read_text(encoding="utf-8"))
        defs[c.get("id", case_json.parent.name)] = c

    passed = failed = gated = 0
    by_metric: dict = {}
    for c in payload["cases"]:
        for metric, bucket in (c.get("detail") or {}).items():
            m = by_metric.setdefault(metric, {"pass": 0, "fail": 0})
            for item in bucket["items"]:
                good = item["score"] >= (1.0 if item["kind"] == "check" else 0.6)
                m["pass" if good else "fail"] += 1
                if good:
                    passed += 1
                else:
                    failed += 1
        gated += len(c.get("gates_failed", []))

    return {"summary": payload["summary"], "weights": payload["weights"],
            "cases": payload["cases"], "run": run, "defs": defs, "board": board,
            "passed": passed, "failed": failed, "gated": gated, "by_metric": by_metric}


def meter(label: str, value, note: str = "", tip: str = "") -> str:
    pct, shown = (0, "—") if value is None else (round(100 * value, 1), f"{value:.2f}")
    note_html = f'<span class="meter-note">{html.escape(note)}</span>' if note else ""
    return (f'<div class="meter-row" data-tip="{html.escape(tip or label)}">'
            f'<div class="meter-label">{html.escape(label)}{note_html}</div>'
            f'<div class="meter-track"><div class="meter-fill" style="width:{pct}%"></div>'
            f'</div><div class="meter-value">{shown}</div></div>')


def render(d: dict) -> str:
    s, w = d["summary"], d["weights"]
    train = [c for c in d["cases"] if c["split"] == "train"]
    hold = [c for c in d["cases"] if c["split"] == "holdout"]
    total_checks = d["passed"] + d["failed"]

    def case_meters(group: list) -> str:
        out = []
        for c in sorted(group, key=lambda c: -c["score"]):
            defn = d["defs"].get(c["case"], {})
            note = "trigger probes" if c["kind"] == "trigger" else ""
            out.append(meter(c["case"], c["score"], note,
                             (defn.get("description") or c["case"])[:220]))
        return "".join(out)

    metric_rows = "".join(
        meter(k, s["metric_means"].get(k), f"weight {w[k]:.2f}",
              f"{k}: suite mean {s['metric_means'].get(k)}, weighted {w[k]:.2f}")
        for k in w)

    seg = []
    legend = []
    for key, label, cls, glyph, n in (
            ("pass", "Passed", "good", "✓", d["passed"]),
            ("fail", "Failed", "critical", "✕", d["failed"])):
        if n:
            pct = 100 * n / max(1, total_checks)
            inline = f'<span class="seg-label">{n}</span>' if pct >= 7 else ""
            seg.append(f'<div class="seg o-{cls}" style="flex:{n}" '
                       f'data-tip="{label}: {n} of {total_checks}">{inline}</div>')
        legend.append(f'<li><span class="key o-{cls}"></span><span class="glyph">{glyph}'
                      f'</span>{label}<span class="key-count'
                      f'{" zero" if not n else ""}">{n}</span></li>')
    checks_bar = f'<div class="stack">{"".join(seg)}</div><ul class="legend">' \
                 f'{"".join(legend)}</ul>'

    def rate(v: dict) -> str:
        total = v["pass"] + v["fail"]
        return "—" if not total else f"{100 * v['pass'] / total:.0f}%"

    metric_break = "".join(
        f"<tr><td>{k}</td><td>{v['pass']}</td><td>{v['fail']}</td><td>{rate(v)}</td></tr>"
        for k, v in sorted(d["by_metric"].items()))

    board_rows = "".join(
        f"<tr><td>{html.escape(str(e.get('label')))}</td>"
        f"<td>{'—' if e.get('train') is None else format(e['train'], '.4f')}</td>"
        f"<td>{'—' if e.get('holdout') is None else format(e['holdout'], '.4f')}</td>"
        f"<td>{e.get('skill_md_chars', '—')}</td>"
        f"<td class='verdict-{e['verdict']}'>{e['verdict']}</td>"
        f"<td class='dim'>{html.escape((e.get('reason') or '')[:190])}</td></tr>"
        for e in d["board"]) or "<tr><td colspan='6' class='dim'>no loop runs yet</td></tr>"

    fail_rows = []
    for c in d["cases"]:
        for f in c.get("failed_checks", []):
            fail_rows.append(f"<tr><td>{c['case']}</td><td><code>{html.escape(f['id'])}</code>"
                             f"</td><td>{f['metric']}</td>"
                             f"<td class='dim'>{html.escape(f['detail'][:120])}</td></tr>")
        for r in c.get("weak_rubric", []):
            fail_rows.append(f"<tr><td>{c['case']}</td><td><code>rubric:"
                             f"{html.escape(r['id'])}</code></td><td>{r['score']:.2f}</td>"
                             f"<td class='dim'>{html.escape(r['reason'][:120])}</td></tr>")
    fails = ("".join(fail_rows) or
             "<tr><td colspan='4' class='dim'>nothing failed — if that holds across runs, "
             "the cases are too easy</td></tr>")

    keys = list(w)
    thead = "".join(f"<th>{k}</th>" for k in keys)
    trows = []
    for c in sorted(d["cases"], key=lambda c: (c["split"], -c["score"])):
        cells = "".join(
            f"<td>{'—' if c['metrics'].get(k) is None else format(c['metrics'][k], '.2f')}</td>"
            for k in keys)
        trows.append(f"<tr><td>{c['case']}</td><td>{c['split']}</td>"
                     f"<td><b>{c['score']:.2f}</b></td>{cells}</tr>")

    weakest = min(((v, k) for k, v in s["metric_means"].items() if v is not None),
                  default=(None, "—"))
    return f"""<div class="viz-root" id="page">
<header>
  <p class="eyebrow">Skill eval · <code>{html.escape(s['target_skill'])}</code></p>
  <h1>How well does <code>{html.escape(s['target_skill'])}</code> do its job?</h1>
  <p class="sub">{len(d['cases'])} cases · {total_checks} graded checks and rubric criteria ·
  model <b>{html.escape(str(d['run'].get('model')))}</b>, one sample per case ·
  ${s['total_cost_usd']:.2f}</p>
</header>

<section class="hero-band">
  <div class="hero">
    <p class="hero-label">Adjusted suite score</p>
    <p class="hero-figure">{s['adjusted_score']:.4f}</p>
    <p class="hero-sub">train {_d(s['train_score'])} · holdout {_d(s['holdout_score'])} ·
    penalty {s['context_penalty']:.4f}</p>
  </div>
  <div class="tiles">
    <div class="tile"><p class="tile-label">Checks passed</p>
      <p class="tile-value">{d['passed']}<span class="tile-unit"> of
      {total_checks}</span></p>
      <p class="tile-delta dim">deterministic + rubric</p></div>
    <div class="tile"><p class="tile-label">Gate failures</p>
      <p class="tile-value">{d['gated']}</p>
      <p class="tile-delta {'dim' if d['gated'] else 'good'}">
      {'a case scored zero' if d['gated'] else '✓ nothing unacceptable happened'}</p></div>
    <div class="tile"><p class="tile-label">Weakest metric</p>
      <p class="tile-value">{'—' if weakest[0] is None else f'{weakest[0]:.2f}'}</p>
      <p class="tile-delta dim">{weakest[1]}</p></div>
    <div class="tile"><p class="tile-label">Skill context cost</p>
      <p class="tile-value">{s['skill_cost']['description_tokens']}<span class="tile-unit">
      tok</span></p>
      <p class="tile-delta dim">description, in context every turn</p></div>
  </div>
</section>

<section>
  <h2>Per case</h2>
  <p class="note">Score out of 1.00. Holdout cases never enter the improvement digest.</p>
  <h3>Train</h3><div class="meters">{case_meters(train)}</div>
  {'<h3>Holdout</h3><div class="meters">' + case_meters(hold) + '</div>' if hold else ''}
</section>

<section>
  <h2>Where the score comes from</h2>
  <p class="note">Suite means per metric, out of 1.00, with the weight each carries.</p>
  <div class="meters">{metric_rows}</div>
</section>

<section class="two-col">
  <div>
    <h2>Checks</h2>
    <p class="note">{total_checks} graded assertions and criteria across all cases.</p>
    {checks_bar}
  </div>
  <div>
    <h2>By metric</h2>
    <p class="note">Where the failures are concentrated.</p>
    <div class="scroll"><table><thead><tr><th>Metric</th><th>Pass</th><th>Fail</th>
    <th>Rate</th></tr></thead><tbody>{metric_break}</tbody></table></div>
  </div>
</section>

<section>
  <h2>What failed</h2>
  <div class="scroll"><table><thead><tr><th>Case</th><th>Check</th><th>Metric</th>
  <th>Detail</th></tr></thead><tbody>{fails}</tbody></table></div>
</section>

<section>
  <h2>Improvement loop</h2>
  <p class="note">A candidate is accepted only if it gains on train without regressing on
  holdout. Rejections stay in the record.</p>
  <div class="scroll"><table class="board"><thead><tr><th>Candidate</th><th>Train</th>
  <th>Holdout</th><th>SKILL.md</th><th>Verdict</th><th>Why</th></tr></thead>
  <tbody>{board_rows}</tbody></table></div>
</section>

<section>
  <h2>Table view</h2>
  <p class="note">Every number on this page, unrounded in <code>scores.json</code>.</p>
  <div class="scroll"><table><thead><tr><th>Case</th><th>Split</th><th>Score</th>{thead}
  </tr></thead><tbody>{''.join(trows)}</tbody></table></div>
</section>

<footer><p>Run <code>{html.escape(d['run'].get('run_id', '?'))}</code> ·
{html.escape(str(d['run'].get('started')))} · regenerate with
<code>python3 harness/report_html.py</code></p></footer>
</div>"""


def _d(v) -> str:
    return "—" if v is None else f"{v:.4f}"


CSS = """
:root { color-scheme: light dark; }
body { margin: 0; background: #f9f9f7; }
@media (prefers-color-scheme: dark) {
  html:where(:not([data-theme="light"])) body { background: #0d0d0d; }
}
html[data-theme="dark"] body { background: #0d0d0d; }
html[data-theme="light"] body { background: #f9f9f7; }

.viz-root {
  color-scheme: light;
  --surface-1: #fcfcfb; --plane: #f9f9f7;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --ring: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --track: #cde2fb;
  --good: #0ca30c; --critical: #d03b3b; --good-text: #006300;
  background: var(--plane); color: var(--ink);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 40px 28px 56px; max-width: 1080px; margin: 0 auto;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --plane: #0d0d0d; --ink: #fff; --ink-2: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --ring: rgba(255,255,255,0.10);
    --series-1: #3987e5; --track: #184f95; --good-text: #0ca30c;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1: #1a1a19; --plane: #0d0d0d; --ink: #fff; --ink-2: #c3c2b7;
  --muted: #898781; --grid: #2c2c2a; --ring: rgba(255,255,255,0.10);
  --series-1: #3987e5; --track: #184f95; --good-text: #0ca30c;
}

.eyebrow { color: var(--muted); font-size: 12.5px; letter-spacing: .06em;
  text-transform: uppercase; margin: 0 0 10px; }
h1 { font-size: 27px; line-height: 1.25; margin: 0 0 10px; font-weight: 650;
  letter-spacing: -0.01em; max-width: 26em; }
h1 code { font-size: .92em; }
.sub { color: var(--ink-2); margin: 0; max-width: 60em; }
h2 { font-size: 15.5px; margin: 0 0 4px; font-weight: 650; }
h3 { font-size: 12px; margin: 18px 0 8px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: .07em; }
.note { color: var(--ink-2); font-size: 13.5px; margin: 0 0 16px; max-width: 62em; }
header { margin-bottom: 28px; }
section { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px;
  padding: 20px 22px 22px; margin-bottom: 16px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 34px; }
@media (max-width: 720px) { .two-col { grid-template-columns: 1fr; } }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .92em; }
.dim { color: var(--muted); }

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
.tile-value { font-size: 25px; font-weight: 600; margin: 0; }
.tile-unit { font-size: 13px; font-weight: 400; color: var(--ink-2); }
.tile-delta { font-size: 12px; margin: 3px 0 0; color: var(--ink-2); }
.tile-delta.good { color: var(--good-text); font-weight: 550; }

.meters { display: flex; flex-direction: column; gap: 9px; }
.meter-row { display: grid; grid-template-columns: minmax(150px, 25em) 1fr 46px; gap: 14px;
  align-items: center; }
@media (max-width: 620px) { .meter-row { grid-template-columns: 1fr 70px; }
  .meter-track { grid-column: 1 / -1; } }
.meter-label { font-size: 13.5px; }
.meter-note { color: var(--muted); font-size: 12px; margin-left: 8px; }
.meter-track { background: var(--track); height: 10px; border-radius: 4px; }
.meter-fill { background: var(--series-1); height: 10px; border-radius: 0 4px 4px 0; }
.meter-value { text-align: right; font-variant-numeric: tabular-nums; font-size: 13px;
  color: var(--ink-2); }

.stack { display: flex; gap: 2px; height: 24px; margin-bottom: 14px; }
.seg { min-width: 3px; display: flex; align-items: center; justify-content: center; }
.seg:first-child { border-radius: 4px 0 0 4px; }
.seg:last-child { border-radius: 0 4px 4px 0; }
.seg-label { font-size: 11.5px; font-weight: 600; color: #0b0b0b;
  font-variant-numeric: tabular-nums; }
.o-good { background: var(--good); } .o-critical { background: var(--critical); }
.o-critical .seg-label { color: #fff; }
.legend { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column;
  gap: 5px; }
.legend li { display: flex; align-items: center; font-size: 13px; color: var(--ink-2); }
.key { width: 10px; height: 10px; border-radius: 3px; margin-right: 9px; flex: none; }
.glyph { width: 15px; color: var(--muted); font-size: 12px; }
.key-count { margin-left: auto; font-variant-numeric: tabular-nums; color: var(--muted); }
.key-count.zero { color: var(--good-text); font-weight: 650; }

.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; font-weight: 600; color: var(--muted); font-size: 11.5px;
  text-transform: uppercase; letter-spacing: .05em; padding: 0 12px 7px 0;
  border-bottom: 1px solid var(--grid); white-space: nowrap; }
td { padding: 7px 12px 7px 0; border-bottom: 1px solid var(--grid);
  font-variant-numeric: tabular-nums; }
td:first-child { font-variant-numeric: normal; }
.board td:last-child { min-width: 20em; font-size: 12.5px; }
.verdict-accepted { color: var(--good-text); font-weight: 600; }
.verdict-rejected { color: var(--ink-2); }
.verdict-baseline { color: var(--muted); }
footer { color: var(--muted); font-size: 12.5px; margin-top: 22px; }
footer p { margin: 0; }
#tip { position: fixed; z-index: 9; pointer-events: none; opacity: 0; transition: opacity .09s;
  background: var(--surface-1); color: var(--ink); border: 1px solid var(--ring);
  border-radius: 7px; padding: 7px 10px; font: 12.5px/1.4 system-ui, sans-serif;
  max-width: 320px; box-shadow: 0 3px 12px rgba(0,0,0,.14); }
"""

JS = """
(function () {
  var p = new URLSearchParams(location.search).get('theme');
  if (p === 'dark' || p === 'light') document.documentElement.dataset.theme = p;
  var tip = document.createElement('div');
  tip.id = 'tip'; document.body.appendChild(tip);
  document.addEventListener('mousemove', function (e) {
    var el = e.target.closest('[data-tip]');
    if (!el || !el.dataset.tip) { tip.style.opacity = '0'; return; }
    tip.textContent = el.dataset.tip; tip.style.opacity = '1';
    var r = tip.getBoundingClientRect();
    tip.style.left = Math.min(e.clientX + 14, innerWidth - r.width - 10) + 'px';
    tip.style.top = Math.max(e.clientY - r.height - 12, 8) + 'px';
  });
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.tabIndex = 0; el.setAttribute('aria-label', el.dataset.tip);
  });
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
    title = f"{data['summary']['target_skill']} — eval results"
    page = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{html.escape(title)}</title>\n<style>{CSS}</style></head>\n"
            f"<body>{render(data)}<script>{JS}</script></body></html>\n")
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page)} bytes) from {run_dir.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
