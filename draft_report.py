#!/usr/bin/env python3
"""Render data/strategy.json into draft-report.html.

    python draft_report.py              # local file
    python draft_report.py --fragment   # out/draft-shared.html, for hosting

Reuses the styles and chart primitives from report.py so both reports stay
visually identical and only need fixing in one place.
"""

import argparse
import json
import sys
from pathlib import Path

from report import CSS, esc, legend, line_chart, magnitude_bars, table

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data" / "strategy.json"
OUT = ROOT / "draft-report.html"
POS = ("QB", "RB", "WR", "TE")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def build(d):
    me = d["username"]
    vor = d["scarcity"]["vor"]
    wv = d["waivers"]
    corr = d["correlations"]
    tb = d["top_vs_bottom"]
    p = ['<div class="wrap">']

    p.append("<h1>What actually wins this league</h1>")
    p.append(f'<p class="sub">{esc(d["seasons"][0])}-{esc(d["seasons"][-1])} · '
             f'{d["n"]} manager-seasons · 12-team PPR, two flex, five bench</p>')
    p.append('<p class="lede">Every draft strategy article is written for a generic league. '
             'This one measures <strong>yours</strong> — where the points actually are in '
             'your scoring, when positions leave your board, what your waiver wire can '
             'really replace, and which phase of your season decides who wins.</p>')

    # ---------------- KPIs
    p.append('<div class="kpis">')
    for label, value, meta in [
        ("Draft &rarr; points", f'{corr["draft"]["vs_points"]:+.2f}',
         "correlation, first 5 picks"),
        ("Waivers &rarr; wins", f'{corr["waivers"]["vs_wins"]:+.2f}',
         "essentially no relationship"),
        ("Scarcest position", f'RB', f'{vor["RB"]["vor"]:.0f} pts over replacement'),
        ("Most replaceable", "QB", f'{wv["QB"]["hit_rate"]:.0f}% waiver hit rate'),
    ]:
        p.append(f'<div class="kpi"><div class="label">{label}</div>'
                 f'<div class="value">{value}</div><div class="meta">{esc(meta)}</div></div>')
    p.append("</div>")

    # ---------------- 1. the draft is the game
    p.append("<h2>1. The season is decided in August</h2>")
    p.append('<p class="sub">Your league\'s best and worst finishers, averaged over five '
             'seasons. These are the four things a manager controls after the draft.</p>')
    p.append(table(
        ["Group", "#Lineup efficiency", "#Adds per season", "#Points from adds", "#Luck"],
        [["Top 4 finishers", f'{tb["top"]["efficiency"]:.1f}%', f'{tb["top"]["adds"]:.1f}',
          f'{tb["top"]["waiver_points"]:.0f}', f'{tb["top"]["luck"]:+.1f}'],
         ["Bottom 4 finishers", f'{tb["bottom"]["efficiency"]:.1f}%', f'{tb["bottom"]["adds"]:.1f}',
          f'{tb["bottom"]["waiver_points"]:.0f}', f'{tb["bottom"]["luck"]:+.1f}']]))
    p.append('<p class="note">The top and bottom of your league are indistinguishable on '
             'every in-season measure. Whatever separates them happened before week 1.</p>')

    p.append("<h3>What tracks winning</h3>")
    rows = []
    for key, label in [("draft", "Draft: points from first 5 picks"),
                       ("efficiency", "Lineup efficiency"),
                       ("waivers", "Waivers: points started from adds"),
                       ("luck", "Schedule luck")]:
        note = ("partly circular -- luck is defined as wins minus expected wins"
                if key == "luck" else "")
        rows.append([label, f'{corr[key]["vs_wins"]:+.2f}', f'{corr[key]["vs_points"]:+.2f}',
                     f'<span style="color:var(--muted)">{esc(note)}</span>'])
    p.append(table(["Factor", "#vs wins", "#vs points scored", ""], rows))
    p.append('<p class="note">Correlation runs from 0 (no relationship) to 1 (perfect). '
             'The draft is the only controllable factor with real signal.</p>')

    # ---------------- 2. scarcity
    p.append("<h2>2. Where the points actually are</h2>")
    p.append('<p class="sub">What a top-six player is worth above the last startable player '
             'at that position, once twelve teams have filled their lineups. This is the '
             'number that should drive a draft board.</p>')
    p.append('<div class="card">')
    p.append(magnitude_bars(
        sorted(((k, vor[k]["vor"]) for k in POS), key=lambda x: -x[1]),
        "RB", " pts", lambda v: f"{v:.0f}", "value over replacement by position"))
    p.append("</div>")
    p.append(table(
        ["Position", "#Top-6 season pts", "#Replacement", "#Value over replacement"],
        [[k, f'{vor[k]["top6"]:.0f}',
          f'{vor[k]["replacement"]:.0f} <span style="color:var(--muted)">'
          f'({k}{vor[k]["replacement_rank"]})</span>',
          f'<strong>{vor[k]["vor"]:.0f}</strong>'] for k in
         sorted(POS, key=lambda k: -vor[k]["vor"])]))
    p.append('<p class="note">An elite tight end is worth about a third of an elite running '
             'back here. Two flex spots push RB and WR replacement deep, which is what '
             'makes the top of those positions so valuable.</p>')

    # ---------------- 3. the edge
    p.append("<h2>3. Your league drafts quarterbacks too early</h2>")
    p.append('<p class="sub">Share of each round spent on each position, across 900 picks '
             'and five drafts.</p>')
    rounds = [str(r["round"]) for r in d["timing"]["round_mix"]]
    series = {pos: [r[pos] for r in d["timing"]["round_mix"]] for pos in POS}
    p.append('<div class="card">')
    p.append(legend([("QB", "var(--accent)", "1"), ("RB, WR, TE", "var(--muted)", "0.38")]))
    p.append(line_chart(rounds, series, "QB", "share of round by position",
                        lambda v: f"{v:.0f}%"))
    p.append("</div>")
    r3 = next(r for r in d["timing"]["round_mix"] if r["round"] == 3)
    p.append(f'<p class="note">A quarter of round three goes to quarterbacks '
             f'({r3["QB"]:.0f}%) — three of twelve teams spending a premium pick on the '
             f'position with the third-lowest value over replacement. Hover any grey line '
             f'to identify it.</p>')
    p.append('<p class="sub" style="margin-top:14px">The opportunity is not the quarterback '
             'points you save. It is that <strong>while three teams take a quarterback in '
             'round three, elite running backs and receivers fall to whoever does not.</strong></p>')

    # ---------------- 4. the backstop
    p.append("<h2>4. What your waiver wire can actually replace</h2>")
    p.append('<p class="sub">Every mid-season addition in five years, graded by what it went '
             'on to score in a starting lineup. A hit is 50+ points.</p>')
    p.append('<div class="card">')
    p.append(legend([("QB", "var(--accent)", "1"), ("Other positions", "var(--muted)", "0.38")]))
    p.append(magnitude_bars(
        sorted(((k, wv[k]["hit_rate"]) for k in POS), key=lambda x: -x[1]),
        "QB", "%", lambda v: f"{v:.0f}%", "waiver hit rate by position"))
    p.append("</div>")
    p.append(table(["Position", "#Adds", "#Avg points per add", "#Hit rate"],
                   [[k, f'{wv[k]["adds"]}', f'{wv[k]["per_add"]:.1f}',
                     f'{wv[k]["hit_rate"]:.0f}%'] for k in
                    sorted(POS, key=lambda k: -wv[k]["hit_rate"])]))
    p.append('<p class="note">Quarterback is the one position this league reliably replaces '
             'mid-season. Running back is not — which, with five bench spots and rolling '
             'waiver priority instead of bidding, is why a Zero RB draft does not fit here.</p>')

    # ---------------- 5. your drafts
    p.append("<h2>5. Your five drafts</h2>")
    p.append('<p class="sub">Classified against the common named strategies. Four different '
             'approaches in five years.</p>')
    rows = []
    for r in d["your_drafts"]:
        qb_flag = ' style="color:var(--neg)"' if r["qb_plan"] == "Early QB" else ""
        rows.append([
            esc(r["season"]), f'{r["slot"]}', esc(r["opening"]),
            esc(r["rb_plan"]), f'<span{qb_flag}>{esc(r["qb_plan"])}</span>',
            f'{r["top5_points"]:.0f}', f'{r["top5_hits"]}',
            f'{r["w"]}-{r["l"]}',
        ])
    p.append(table(["Season", "#Slot", "First 5 picks", "RB plan", "QB plan",
                    "#Pts from first 5", "#Top-24 hits", "#Record"], rows))
    early = sum(1 for r in d["your_drafts"] if r["qb_plan"] == "Early QB")
    worst = min(d["your_drafts"], key=lambda r: r["top5_points"])
    p.append(f'<p class="note">You took a quarterback inside round four in '
             f'{early} of {len(d["your_drafts"])} seasons. Your worst draft '
             f'({esc(worst["season"])}, {worst["top5_points"]:.0f} points and '
             f'{worst["top5_hits"]} top-24 hits from the first five picks) still finished '
             f'{worst["w"]}-{worst["l"]} on schedule luck alone.</p>')

    # ---------------- recommendation
    p.append("<h2>The plan this points to</h2>")
    p.append(table(
        ["Decision", "Call", "Because"],
        [["Running back", "<strong>Hero RB</strong> — one anchor early, then let it go",
          f'RB carries the highest value over replacement ({vor["RB"]["vor"]:.0f}) and is '
          f'the hardest position to replace mid-season ({wv["RB"]["hit_rate"]:.0f}% hit rate)'],
         ["Quarterback", "<strong>Round 8 or later</strong>, target rushing volume",
          f'Lowest cost to punt: {wv["QB"]["hit_rate"]:.0f}% waiver hit rate, and waiting '
          f'lets you take the talent three rivals pass on in round three'],
         ["Tight end", "<strong>Let it come to you</strong>",
          f'Elite TE is worth {vor["TE"]["vor"]:.0f} points over replacement, a third of '
          f'elite RB. Draft position showed no effect on wins'],
         ["Zero RB", "<strong>Rule it out</strong>",
          "Five bench spots leave no room to stash lottery tickets, and rolling priority "
          "means you cannot outbid anyone for the breakout it depends on"],
         ["Biggest single fix", "<strong>Stop reaching</strong>",
          "You draft at -4.1 slots per pick, 10th of 12. Structure is worth about a win; "
          "reaching costs more"]]))

    # ---------------- caveats
    p.append("<h2>What this cannot tell you</h2>")
    p.append('<p class="sub">Three limits worth holding onto.</p>')
    p.append(table(
        ["Limit", "What it means"],
        [["Sample size",
          f'{d["n"]} manager-seasons. The findings that show <em>no</em> effect (waivers, '
          f'efficiency) are the strongest, because they hold across the whole league. '
          f'The positional numbers are directional.'],
         ["Luck is partly circular",
          "Schedule luck is defined as wins minus expected wins, so of course it tracks "
          "wins. Ignore that correlation; the other three are honest."],
         ["Reconstructed scoring",
          "Sleeper retired its public stats endpoint, so player points are rebuilt from "
          "weekly league scoring and only count while a player was rostered. Replacement "
          "ranks sit inside the rostered pool, but deep ranks read low."]]))

    p.append('<p class="note" style="margin-top:36px">Generated from cached Sleeper data. '
             'No credentials were used to build this.</p>')
    p.append("</div><div id='tip'></div>")
    p.append("""<script>
const tip=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el=>{
  el.addEventListener('mouseenter',()=>{tip.textContent=el.dataset.tip;tip.style.opacity=1;});
  el.addEventListener('mousemove',e=>{
    tip.style.left=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-16)+'px';
    tip.style.top=(e.clientY+14)+'px';});
  el.addEventListener('mouseleave',()=>{tip.style.opacity=0;});
});
</script>""")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fragment", action="store_true")
    args = ap.parse_args()

    if not SRC.exists():
        raise SystemExit("No strategy.json. Run: python strategy.py")
    d = json.loads(SRC.read_text(encoding="utf-8"))
    body = build(d)
    title = "What actually wins this league"

    if args.fragment:
        doc = f"<title>{title}</title><style>{CSS}</style>{body}"
        doc = doc.encode("ascii", "xmlcharrefreplace").decode("ascii")
        out = ROOT / "out" / "draft-shared.html"
        out.parent.mkdir(exist_ok=True)
    else:
        doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>')
        out = OUT

    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}  ({len(doc)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
