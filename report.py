#!/usr/bin/env python3
"""Render data/analysis.json into a self-contained report.html.

    python report.py

Charts are inline SVG. No external requests, no third-party packages, so the
file works offline and can be opened straight from disk.
"""

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "data" / "analysis.json"
OUT = ROOT / "report.html"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Reference palette, used unchanged. Emphasis charts are one hue plus the
# de-emphasis gray; polarity charts use the documented blue<->red pair.
CSS = """
:root {
  color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --hairline:rgba(11,11,11,0.10);
  --accent:#2a78d6; --neg:#e34948; --good:#006300;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19;
    --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --hairline:rgba(255,255,255,0.10);
    --accent:#3987e5; --neg:#e66767; --good:#0ca30c;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19;
  --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --hairline:rgba(255,255,255,0.10);
  --accent:#3987e5; --neg:#e66767; --good:#0ca30c;
}

* { box-sizing:border-box; }
body {
  margin:0; padding:32px 20px 80px;
  background:var(--page); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
}
.wrap { max-width:1040px; margin:0 auto; }
h1 { font-size:30px; line-height:1.2; margin:0 0 6px; letter-spacing:-0.02em; }
h2 { font-size:20px; margin:44px 0 4px; letter-spacing:-0.01em; }
h3 { font-size:15px; margin:26px 0 8px; color:var(--ink-2); font-weight:600; }
.sub { color:var(--ink-2); margin:0 0 4px; }
.note { color:var(--muted); font-size:13px; margin:6px 0 0; }

.card {
  background:var(--surface); border:1px solid var(--hairline);
  border-radius:10px; padding:20px; margin-top:14px; overflow:hidden;
}
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-top:18px; }
.kpi { background:var(--surface); border:1px solid var(--hairline); border-radius:10px; padding:14px 16px; }
.kpi .label { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em; }
.kpi .value { font-size:30px; font-weight:600; letter-spacing:-0.02em; margin-top:4px; }
.kpi .meta { font-size:13px; color:var(--ink-2); margin-top:2px; }

table { border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums; }
th { text-align:left; font-weight:600; color:var(--ink-2); font-size:12px;
     text-transform:uppercase; letter-spacing:0.04em; padding:6px 10px 6px 0;
     border-bottom:1px solid var(--axis); white-space:nowrap; }
td { padding:7px 10px 7px 0; border-bottom:1px solid var(--grid); }
th.n, td.n { text-align:right; }
/* Mark the user's row with weight and the accent hue. Deliberately no
   ::after glyph -- CSS `content` does not parse HTML entities, so any
   non-ASCII there breaks the moment the file is entity-encoded. */
tr.me td { font-weight:600; }
tr.me td:first-child { color:var(--accent); }
.pos { color:var(--good); } .negv { color:var(--neg); }
.scroll { overflow-x:auto; }

.legend { display:flex; gap:16px; align-items:center; margin:0 0 10px; font-size:13px; color:var(--ink-2); }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.sw { width:12px; height:12px; border-radius:3px; display:inline-block; }

svg { display:block; width:100%; height:auto; }
svg text { font:12px system-ui,-apple-system,"Segoe UI",sans-serif; fill:var(--muted); }
svg text.lbl { fill:var(--ink-2); }
svg text.val { fill:var(--ink-2); font-variant-numeric:tabular-nums; }
[data-tip] { cursor:default; }
#tip {
  position:fixed; pointer-events:none; opacity:0; transition:opacity .1s;
  background:var(--ink); color:var(--page); padding:6px 9px; border-radius:6px;
  font-size:12px; line-height:1.4; max-width:260px; z-index:50; white-space:pre-line;
}
details { margin-top:10px; } summary { cursor:pointer; color:var(--ink-2); font-size:13px; }

.lede { margin:20px 0 0; color:var(--ink-2); max-width:62ch;
        font-size:16px; line-height:1.6; }
.lede strong { color:var(--ink); font-weight:600; }
:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:3px; }
@media (prefers-reduced-motion:reduce) { * { transition:none !important; animation:none !important; } }
@media (max-width:640px) { body { padding:20px 14px 60px; } h1 { font-size:24px; } }
"""


def esc(s):
    return html.escape(str(s))


def fmt(v, digits=1, sign=False):
    s = f"{v:+.{digits}f}" if sign else f"{v:.{digits}f}"
    return s


def cls(v):
    return "pos" if v > 0 else ("negv" if v < 0 else "")


# ------------------------------------------------------------------ charts

def line_chart(seasons, series, me, ylabel, fmt_val=lambda v: f"{v:.1f}"):
    """Emphasis form: every manager in de-emphasis gray, the user in accent.

    One highlighted line against context is the honest form here — twelve
    categorical hues would bury the only line the reader cares about.
    """
    W, H = 880, 300
    L, T, B = 46, 16, 34
    # The right margin has to clear the direct label sitting past the last
    # point, so it scales with the name rather than being a fixed guess.
    R = max(74, 22 + int(len(me) * 7.2))
    vals = [v for s in series.values() for v in s if v is not None]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    # Padding must not invent a negative axis for a quantity that cannot be
    # negative -- a share-of-round chart reading down to -6% is nonsense.
    if min(vals) >= 0:
        lo = max(lo, 0.0)

    def px(i):
        return L + (W - L - R) * (i / max(1, len(seasons) - 1))

    def py(v):
        return T + (H - T - B) * (1 - (v - lo) / (hi - lo))

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(ylabel)} by season">']

    # recessive gridlines + y ticks
    steps = 4
    for i in range(steps + 1):
        v = lo + (hi - lo) * i / steps
        y = py(v)
        out.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        out.append(f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end">{fmt_val(v)}</text>')

    for i, s in enumerate(seasons):
        out.append(f'<text x="{px(i):.1f}" y="{H-12}" text-anchor="middle">{esc(s)}</text>')

    # context lines first so the emphasis line sits on top. Each gets an
    # invisible fat stroke over it as a hit target, so "who is that line
    # above me?" is answerable on hover instead of unanswerable.
    for name, ys in series.items():
        if name == me:
            continue
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(ys) if v is not None)
        if not pts:
            continue
        out.append(f'<polyline points="{pts}" fill="none" stroke="var(--muted)" '
                   f'stroke-width="1.5" opacity="0.32" stroke-linejoin="round"/>')
        detail = "  ".join(f"{seasons[i]} {fmt_val(v)}"
                           for i, v in enumerate(ys) if v is not None)
        out.append(f'<polyline points="{pts}" fill="none" stroke="transparent" '
                   f'stroke-width="12" stroke-linejoin="round" '
                   f'data-tip="{esc(name)}&#10;{esc(detail)}"/>')

    ys = series.get(me, [])
    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(ys) if v is not None)
    if pts:
        out.append(f'<polyline points="{pts}" fill="none" stroke="var(--accent)" '
                   f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for i, v in enumerate(ys):
            if v is None:
                continue
            out.append(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="4.5" fill="var(--accent)" '
                       f'stroke="var(--surface)" stroke-width="2" '
                       f'data-tip="{esc(me)} · {esc(seasons[i])}&#10;{fmt_val(v)}"/>')
        last = next((i for i in range(len(ys) - 1, -1, -1) if ys[i] is not None), None)
        if last is not None:
            out.append(f'<text class="lbl" x="{px(last)+10:.1f}" y="{py(ys[last])+4:.1f}" '
                       f'style="fill:var(--accent);font-weight:600">{esc(me)}</text>')

    out.append("</svg>")
    return "".join(out)


def bar_path(x, y, w, h, side, r=4.0):
    """A bar rounded only on its data end. The end anchored to the baseline
    stays square, so bars read as growing off the axis rather than floating."""
    r = max(0.0, min(r, w / 2, h / 2))
    if r <= 0.5:
        return f"M{x:.1f},{y:.1f} h{w:.1f} v{h:.1f} h{-w:.1f} Z"
    if side == "right":
        return (f"M{x:.1f},{y:.1f} H{x+w-r:.1f} Q{x+w:.1f},{y:.1f} {x+w:.1f},{y+r:.1f} "
                f"V{y+h-r:.1f} Q{x+w:.1f},{y+h:.1f} {x+w-r:.1f},{y+h:.1f} H{x:.1f} Z")
    return (f"M{x+w:.1f},{y:.1f} H{x+r:.1f} Q{x:.1f},{y:.1f} {x:.1f},{y+r:.1f} "
            f"V{y+h-r:.1f} Q{x:.1f},{y+h:.1f} {x+r:.1f},{y+h:.1f} H{x+w:.1f} Z")


def _row_label(x, y, label, emph):
    style = ' style="font-weight:600"' if emph else ""
    return (f'<text class="lbl" x="{x:.1f}" y="{y:.1f}" text-anchor="end"{style}>'
            f'{esc(label[:16])}</text>')


def diverging_bars(rows, me, unit="", aria="values above and below zero"):
    """rows: [(label, value)] — polarity chart, blue above zero / red below."""
    W = 880
    rowh, gap, barh = 26, 2, 20
    L, R, T = 132, 56, 8
    # A rounded -0.04 prints as "-0.0", which reads as a real negative.
    rows = [(lbl, 0.0 if abs(v) < 0.05 else v) for lbl, v in rows]
    H = T + len(rows) * (rowh + gap) + 8
    mx = max(abs(v) for _, v in rows) or 1
    # The value sits past the end of each bar, so the bar's own span has to
    # stop short of the manager labels -- otherwise the longest negative bar
    # drives its value straight into the name beside it.
    GUTTER = 46
    zero = L + (W - L - R) / 2
    half = (W - L - R) / 2 - GUTTER

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">']
    out.append(f'<line x1="{zero}" y1="{T}" x2="{zero}" y2="{H-6}" '
               f'stroke="var(--axis)" stroke-width="1"/>')
    for i, (label, v) in enumerate(rows):
        y = T + i * (rowh + gap)
        w = max(abs(v) / mx * half, 2.0)
        positive = v >= 0
        x = zero if positive else zero - w
        color = "var(--accent)" if positive else "var(--neg)"
        out.append(_row_label(L - 10, y + rowh / 2 + 4, label, label == me))
        out.append(f'<path d="{bar_path(x, y, w, barh, "right" if positive else "left")}" '
                   f'fill="{color}" data-tip="{esc(label)}&#10;{v:+.1f}{esc(unit)}"/>')
        tx = (zero + w + 8) if positive else (zero - w - 8)
        out.append(f'<text class="val" x="{tx:.1f}" y="{y+rowh/2+4:.1f}" '
                   f'text-anchor="{"start" if positive else "end"}">{v:+.1f}</text>')
    out.append("</svg>")
    return "".join(out)


def magnitude_bars(rows, me, unit="", fmt_val=lambda v: f"{v:.0f}",
                   aria="magnitude by manager"):
    """rows: [(label, value)] sorted — one hue, user emphasized."""
    W = 880
    rowh, gap, barh = 26, 2, 20
    L, R, T = 132, 60, 8
    H = T + len(rows) * (rowh + gap) + 8
    mx = max(v for _, v in rows) or 1
    span = W - L - R

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">']
    for i, (label, v) in enumerate(rows):
        y = T + i * (rowh + gap)
        w = max(v / mx * span, 2.0)
        emph = label == me
        out.append(_row_label(L - 10, y + rowh / 2 + 4, label, emph))
        out.append(f'<path d="{bar_path(L, y, w, barh, "right")}" '
                   f'fill="{"var(--accent)" if emph else "var(--muted)"}" '
                   f'opacity="{"1" if emph else "0.38"}" '
                   f'data-tip="{esc(label)}&#10;{fmt_val(v)}{esc(unit)}"/>')
        out.append(f'<text class="val" x="{L+w+8:.1f}" y="{y+rowh/2+4:.1f}">{fmt_val(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def legend(items):
    parts = "".join(
        f'<span><i class="sw" style="background:{c};opacity:{o}"></i>{esc(t)}</span>'
        for t, c, o in items)
    return f'<div class="legend">{parts}</div>'


def table(headers, rows, me_col=0, me=None):
    head = "".join(f'<th class="{"n" if h.startswith("#") else ""}">{esc(h.lstrip("#"))}</th>' for h in headers)
    body = []
    for r in rows:
        klass = ' class="me"' if me and str(r[me_col]) == me else ""
        cells = "".join(
            f'<td class="{"n" if headers[i].startswith("#") else ""}">{c}</td>'
            for i, c in enumerate(r))
        body.append(f"<tr{klass}>{cells}</tr>")
    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


# ------------------------------------------------------------- aggregation

def aggregate(data):
    """Per-manager totals across every season they played."""
    agg = defaultdict(lambda: {
        "seasons": 0, "w": 0, "l": 0, "t": 0, "pf": 0.0,
        "expected_w": 0.0, "luck": 0.0,
        "actual": 0.0, "optimal": 0.0, "bench": 0.0,
        "waiver_adds": 0, "free_agent_adds": 0, "failed_claims": 0,
        "trades": 0, "acquired_started_points": 0.0,
        "titles": 0, "eff_by_season": {}, "luck_by_season": {}, "aka": [],
    })
    for s in data["seasons"]:
        for m in s["managers"].values():
            a = agg[m["display_name"]]
            a["seasons"] += 1
            for k in ("w", "l", "t", "waiver_adds", "free_agent_adds",
                      "failed_claims", "trades"):
                a[k] += m[k]
            a["pf"] += m["pf"]
            a["expected_w"] += m["expected_w"]
            a["luck"] += m["luck"]
            a["actual"] += m["actual_points"]
            a["optimal"] += m["optimal_points"]
            a["bench"] += m["points_left_on_bench"]
            a["acquired_started_points"] += m["acquired_started_points"]
            a["eff_by_season"][s["season"]] = m["efficiency"]
            a["luck_by_season"][s["season"]] = m["luck"]
            for old in (m.get("aka") or []):
                if old not in a["aka"]:
                    a["aka"].append(old)
    for a in agg.values():
        a["efficiency"] = round(a["actual"] / a["optimal"] * 100, 2) if a["optimal"] else 0.0
    return agg


def draft_by_manager(data):
    out = defaultdict(lambda: {"picks": 0, "surplus": 0, "best": None, "worst": None})
    for s in data["seasons"]:
        for p in s["draft"]:
            d = out[p["manager"]]
            d["picks"] += 1
            d["surplus"] += p["surplus"]
            tagged = {**p, "season": s["season"]}
            if d["best"] is None or p["surplus"] > d["best"]["surplus"]:
                d["best"] = tagged
            if d["worst"] is None or p["surplus"] < d["worst"]["surplus"]:
                d["worst"] = tagged
    for d in out.values():
        d["avg_surplus"] = round(d["surplus"] / d["picks"], 2) if d["picks"] else 0.0
    return out


# ---------------------------------------------------------------- sections

def build(data):
    me = data["username"]
    agg = aggregate(data)
    drafts = draft_by_manager(data)
    seasons = [s["season"] for s in data["seasons"]]
    mine = agg[me]
    n_seasons = len(seasons)

    p = []
    p.append('<div class="wrap">')
    p.append(f"<h1>Fantasy decision report — {esc(me)}</h1>")
    p.append(f'<p class="sub">{esc(seasons[0])}–{esc(seasons[-1])} · '
             f'{len(data["seasons"])} completed seasons · 12-team PPR</p>')
    p.append('<p class="lede">Every lineup, draft pick, waiver claim and trade this league has '
             'made since 2021, pulled from Sleeper and graded. <strong>Two questions drive '
             'it:</strong> how much of each manager\'s record came from decisions they '
             'controlled, and how much came from the schedule they happened to draw.</p>')

    # ---- KPI row
    eff_rank = sorted(agg.values(), key=lambda a: -a["efficiency"]).index(mine) + 1
    luck_rank = sorted(agg.values(), key=lambda a: -a["luck"]).index(mine) + 1
    p.append('<div class="kpis">')
    p.append(f'<div class="kpi"><div class="label">Record</div>'
             f'<div class="value">{mine["w"]}-{mine["l"]}</div>'
             f'<div class="meta">{fmt(mine["expected_w"],1)} expected</div></div>')
    p.append(f'<div class="kpi"><div class="label">Wins from luck</div>'
             f'<div class="value {cls(mine["luck"])}">{fmt(mine["luck"],1,True)}</div>'
             f'<div class="meta">{luck_rank} of {len(agg)} luckiest</div></div>')
    p.append(f'<div class="kpi"><div class="label">Lineup efficiency</div>'
             f'<div class="value">{fmt(mine["efficiency"],1)}%</div>'
             f'<div class="meta">{eff_rank} of {len(agg)} in league</div></div>')
    p.append(f'<div class="kpi"><div class="label">Points benched</div>'
             f'<div class="value">{mine["bench"]:.0f}</div>'
             f'<div class="meta">{mine["bench"]/n_seasons:.0f} per season</div></div>')
    p.append("</div>")

    # ---- efficiency trend
    p.append("<h2>Are you getting better at setting a lineup?</h2>")
    p.append('<p class="sub">Share of your own roster\'s available points that you actually started, '
             'week by week. 100% would mean never leaving a better option on the bench.</p>')
    series = {n: [a["eff_by_season"].get(s) for s in seasons] for n, a in agg.items()}
    p.append('<div class="card">')
    p.append(legend([("You", "var(--accent)", "1"), ("Other managers", "var(--muted)", "0.38")]))
    p.append(line_chart(seasons, series, me, "lineup efficiency %", lambda v: f"{v:.0f}%"))
    p.append("</div>")
    p.append('<p class="note">This is a hindsight measure, not a verdict on judgment. '
             'Benching a player who then goes off counts against you here even when '
             'starting him was the obvious call at the time.</p>')

    # ---- luck
    p.append("<h2>Record vs. deserved record</h2>")
    p.append('<p class="sub">Every week, we compute how you would have done against all eleven '
             'opponents instead of just the one you drew. The gap between real wins and '
             'that expectation is schedule luck.</p>')
    rows = sorted(((n, a["luck"]) for n, a in agg.items()), key=lambda x: -x[1])
    p.append('<div class="card">')
    p.append(legend([("Won more than deserved", "var(--accent)", "1"),
                     ("Won less than deserved", "var(--neg)", "1")]))
    p.append(diverging_bars(rows, me, " wins",
                            aria="wins above or below expectation, by manager"))
    p.append("</div>")

    # ---- bench
    p.append("<h2>Points left on the bench</h2>")
    p.append(f'<p class="sub">Total across {n_seasons} seasons. Lower is better.</p>')
    rows = sorted(((n, a["bench"]) for n, a in agg.items()), key=lambda x: x[1])
    p.append('<div class="card">')
    p.append(legend([("You", "var(--accent)", "1"), ("Other managers", "var(--muted)", "0.38")]))
    p.append(magnitude_bars(rows, me, " pts",
                            aria="total points left on the bench, by manager"))
    p.append("</div>")

    # ---- standings table
    p.append("<h2>Five-year table</h2>")
    trs = []
    for n, a in sorted(agg.items(), key=lambda kv: -kv[1]["efficiency"]):
        name = esc(n)
        if a["aka"]:
            name += (' <span style="color:var(--muted);font-weight:400">was '
                     + esc(", ".join(a["aka"])) + "</span>")
        trs.append([
            name, a["seasons"], f'{a["w"]}-{a["l"]}',
            f'{a["expected_w"]:.1f}',
            f'<span class="{cls(a["luck"])}">{a["luck"]:+.1f}</span>',
            f'{a["pf"]:.0f}', f'{a["efficiency"]:.1f}%', f'{a["bench"]:.0f}',
        ])
    p.append(table(["Manager", "#Seasons", "Record", "#Expected W", "#Luck",
                    "#Points for", "#Efficiency", "#Benched"], trs, 0, me))

    # ---- draft
    p.append("<h2>Drafting</h2>")
    p.append('<p class="sub">Each pick is graded by where it was taken against where that player '
             'finished among all drafted players that year. Positive means the manager '
             'consistently got production later than it should have been available.</p>')
    rows = sorted(((n, d["avg_surplus"]) for n, d in drafts.items()), key=lambda x: -x[1])
    p.append('<div class="card">')
    p.append(legend([("Beat their draft slot", "var(--accent)", "1"),
                     ("Fell short of it", "var(--neg)", "1")]))
    p.append(diverging_bars(rows, me, " slots per pick",
                            aria="average draft pick surplus, by manager"))
    p.append("</div>")
    p.append('<p class="note">Player value is reconstructed from weekly league scoring, since '
             'Sleeper retired its public stats endpoint. A player who sat unrostered for '
             'part of a season reads lower than his real output.</p>')

    trs = []
    for n, d in sorted(drafts.items(), key=lambda kv: -kv[1]["avg_surplus"]):
        b, w = d["best"], d["worst"]
        trs.append([
            esc(n),
            f'<span class="{cls(d["avg_surplus"])}">{d["avg_surplus"]:+.1f}</span>',
            f'{esc(b["player"])} <span style="color:var(--muted)">'
            f'{esc(b["season"])}, pick {b["pick_no"]}</span>' if b else "—",
            f'{esc(w["player"])} <span style="color:var(--muted)">'
            f'{esc(w["season"])}, pick {w["pick_no"]}</span>' if w else "—",
        ])
    p.append("<h3>Best and worst pick per manager</h3>")
    p.append(table(["Manager", "#Avg surplus", "Best value", "Biggest miss"], trs, 0, me))

    # ---- waivers
    p.append("<h2>Waivers and free agency</h2>")
    p.append('<p class="sub">This league uses rolling waiver priority, not FAAB bidding, so there '
             'are no bid amounts to compare. What we can see is volume, how often a claim '
             'was beaten to the punch, and what the additions actually produced in a '
             'starting lineup afterwards.</p>')
    trs = []
    for n, a in sorted(agg.items(), key=lambda kv: -kv[1]["acquired_started_points"]):
        moves = a["waiver_adds"] + a["free_agent_adds"]
        per = a["acquired_started_points"] / moves if moves else 0
        trs.append([
            esc(n), moves, a["failed_claims"],
            f'{a["acquired_started_points"]:.0f}', f'{per:.1f}',
            f'{moves / a["seasons"]:.0f}',
        ])
    p.append(table(["Manager", "#Adds", "#Lost claims", "#Points started from adds",
                    "#Per add", "#Adds per season"], trs, 0, me))

    # ---- trades
    all_trades = [(s["season"], t) for s in data["seasons"] for t in s["trades"]]
    p.append("<h2>Trades</h2>")
    p.append(f'<p class="sub">{len(all_trades)} trades in {n_seasons} seasons. This league '
             f'essentially does not trade, so there is not enough here to grade anyone.</p>')
    trs = []
    for season, t in all_trades:
        moved = "<br>".join(f'{esc(pl)} → {esc(to)}' for pl, to in t["adds"].items()) or "picks only"
        trs.append([esc(season), t["week"], esc(", ".join(t["rosters"])), moved,
                    t["picks"] or ""])
    p.append(table(["Season", "#Week", "Between", "Players moved", "#Picks"], trs))

    # ---- your worst calls
    p.append("<h2>Your most expensive start/sit calls</h2>")
    p.append('<p class="sub">The single biggest legal swap you could have made each week, '
             'largest first.</p>')
    calls = []
    for s in data["seasons"]:
        for m in s["managers"].values():
            if m["display_name"] == me:
                for c in m["worst_calls"]:
                    calls.append((s["season"], c))
    calls.sort(key=lambda x: -x[1]["swing"])
    trs = [[esc(season), c["week"], esc(c["slot"]),
            f'{esc(c["started"])} <span style="color:var(--muted)">{c["started_points"]:.1f}</span>',
            f'{esc(c["benched"])} <span style="color:var(--muted)">{c["benched_points"]:.1f}</span>',
            f'<span class="negv">{c["swing"]:.1f}</span>']
           for season, c in calls[:15]]
    p.append(table(["Season", "#Week", "Slot", "Started", "Should have started", "#Cost"], trs))

    p.append('<p class="note" style="margin-top:36px">Generated from cached Sleeper data. '
             'Sleeper\'s API is read-only and unauthenticated — no credentials were used '
             'to build this.</p>')
    p.append("</div><div id='tip'></div>")
    p.append("""<script>
const tip=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el=>{
  el.addEventListener('mouseenter',()=>{tip.textContent=el.dataset.tip;tip.style.opacity=1;});
  el.addEventListener('mousemove',e=>{
    tip.style.left=Math.min(e.clientX+14,innerWidth-messageWidth())+'px';
    tip.style.top=(e.clientY+14)+'px';});
  el.addEventListener('mouseleave',()=>{tip.style.opacity=0;});
});
function messageWidth(){return tip.offsetWidth+16;}
</script>""")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fragment", action="store_true",
                    help="write out/shared.html instead: same page without the "
                         "document wrapper, for hosting as a shareable link")
    args = ap.parse_args()

    if not ANALYSIS.exists():
        raise SystemExit("No analysis.json. Run: python analyze.py")
    data = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    body = build(data)
    title = f'Fantasy decision report — {esc(data["username"])}'

    if args.fragment:
        # The host supplies <!doctype>, <head> and <body>, so emit only the
        # title, the styles and the page content.
        doc = f"<title>{title}</title><style>{CSS}</style>{body}"
        # No <meta charset> of our own here, since the host owns <head>. League
        # names carry curly quotes and em dashes, so fold every non-ASCII
        # character to a numeric reference rather than trusting the default.
        doc = doc.encode("ascii", "xmlcharrefreplace").decode("ascii")
        out = ROOT / "out" / "shared.html"
        out.parent.mkdir(exist_ok=True)
    else:
        doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{title}</title>'
               f'<style>{CSS}</style></head><body>{body}</body></html>')
        out = OUT

    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}  ({len(doc)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
