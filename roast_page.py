#!/usr/bin/env python3
"""The historical scorecard as one self-contained file.

    python roast_page.py            # -> out/scorecard.html

Every completed draft, graded, with the header art and all five seasons of
verdicts baked in. No server, no tunnel, no laptop: the grades come from
cached data that cannot change, so there is nothing for a running process to
do. This is the version that keeps working when the machine is off.

Tonight's live draft is the one thing that genuinely needs draft.py running,
because it needs Sleeper's board as it happens.
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import draft as draft_mod
import scorecard as scorecard_mod
from report import CSS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "scorecard.html"
WORST_N = 10

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def build(seasons):
    data = {}
    for yr in seasons:
        picks = scorecard_mod.past_picks(yr)
        if not picks:
            continue
        worst, standings, best = scorecard_mod.scorecard(
            picks, yr, worst=WORST_N, best=WORST_N, outcomes=True)
        strip = ("pick_no", "round", "manager", "player", "pos", "adp",
                 "grade", "line", "outcome")
        data[yr] = {
            "picks": len(picks),
            "rows": [{k: r.get(k) for k in strip} for r in worst],
            "best": [{k: r.get(k) for k in strip} for r in best],
            "standings": standings,
        }
        print(f"  {yr}: {len(worst)} worst, {len(best)} best, "
              f"{len(standings)} managers")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fragment", action="store_true",
                    help="emit an artifact fragment rather than a full page")
    a = ap.parse_args()

    seasons = draft_mod.PAST_SEASONS
    print(f"building the scorecard for {', '.join(seasons)} ...")
    data = build(seasons)

    hero = ""
    art = ROOT / "assets" / "hero-scorecard.png"
    if art.exists():
        blob = base64.b64encode(art.read_bytes()).decode("ascii")
        hero = (f'<img src="data:image/png;base64,{blob}" '
                f'alt="Jalen Hurts, allegedly">')

    # The page's own script, with the data inlined. Deliberately a copy of the
    # served page's renderer rather than an import: this file has to keep
    # working with nothing else running, so it carries everything it needs.
    body = PAGE.replace("/*__DATA__*/", json.dumps(data)) \
               .replace("/*__SEASONS__*/", json.dumps(seasons)) \
               .replace("/*__HERO__*/", hero)

    if a.fragment:
        doc = f"<title>Jalen Hurts is a Running Back</title><style>{CSS}{EXTRA}</style>{body}"
    else:
        doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>Jalen Hurts is a Running Back</title>'
               f'<style>{CSS}{EXTRA}</style></head><body>{body}</body></html>')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT}  ({len(doc)/1024:.0f} KB)")


EXTRA = """
.wrap{max-width:1040px}
.hero{margin:0 0 6px}
.hero img{max-width:100%;max-height:420px;border-radius:12px;
  border:1px solid var(--hairline);display:block}
.gr{display:inline-flex;align-items:center;justify-content:center;width:30px;
  height:30px;border-radius:8px;font-weight:700;font-size:15px;color:#fff;flex:0 0 30px}
.gr.A{background:#0ca30c}.gr.B{background:#2a78d6}.gr.C{background:#c98500}
.gr.D{background:#e07020}.gr.F{background:#b02020}
.feed{display:flex;flex-direction:column;gap:8px;margin-top:12px}
.ev{display:flex;gap:12px;align-items:flex-start;background:var(--surface);
  border:1px solid var(--hairline);border-radius:10px;padding:11px 13px}
.ev .bd{flex:1;min-width:0}
.ev .hd{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.ev .hd b{color:var(--ink-2)}
.ev .ln{margin:3px 0 0;font-size:15px;line-height:1.45}
.tbl{width:100%;border-collapse:collapse;font-size:14px;
  font-variant-numeric:tabular-nums;margin-top:10px}
.tbl th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-2);border-bottom:1px solid var(--axis);padding:6px 10px 6px 0}
.tbl td{padding:8px 10px 8px 0;border-bottom:1px solid var(--grid)}
.tbl td.n,.tbl th.n{text-align:right}
.seasons{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0 0}
.seasons .lbl{font-size:12px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);margin-right:4px}
.seasons button{font:inherit;font-size:13px;padding:4px 12px;border-radius:999px;
  border:1px solid var(--hairline);background:var(--surface);color:var(--ink-2);cursor:pointer}
.seasons button:hover{border-color:var(--accent)}
.seasons button.sel{background:var(--accent);border-color:var(--accent);
  color:#fff;font-weight:600}
"""

PAGE = """<div class="wrap">
<div class="hero">/*__HERO__*/</div>
<h1>Jalen Hurts is a Running Back</h1>
<p class="sub" id="sub"></p>
<div class="seasons" id="seasons"></div>
<div id="main"></div>
<p class="note" style="margin-top:34px">Grades compare <b>where a player was
taken at his position against where he finished at it</b>. The third back off
the board is expected to be RB3; finishing RB19 is the miss and finishing RB1
is the steal. Position pools are used deliberately &mdash; quarterbacks
outscore everyone by construction, so ranking on overall points returns a
&ldquo;best picks&rdquo; list that is nothing but quarterbacks. Reaching past a
player&rsquo;s market price is not penalised separately: paying up moves your
own slot earlier and so raises the bar you are measured against. Players who
missed the season are removed entirely. Each year shows its ten worst and ten
best picks; the standings are computed over the whole draft.</p>
<p class="note">Static, from cached data. Nothing here needs a server.</p>
</div>
<script>
const DATA = /*__DATA__*/;
const SEASONS = /*__SEASONS__*/;
const esc = t => String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
var YEAR = (new URLSearchParams(location.search)).get('season') || SEASONS[0];

function feed(rows){
  return '<div class="feed">'+rows.map(function(r){
    var o = r.outcome || {};
    return '<div class="ev"><span class="gr '+r.grade+'">'+r.grade+'</span>'+
      '<div class="bd"><div class="hd">R'+r.round+' pick '+r.pick_no+' &middot; '+
        '<b>'+esc(r.manager)+'</b> &middot; '+esc(r.player)+' ('+esc(r.pos)+')'+
        (o.pos_taken ? ' &middot; taken '+esc(r.pos)+o.pos_taken+
                       ' &rarr; finished '+esc(r.pos)+o.pos_rank : '')+
      '</div><p class="ln">'+esc(r.line)+'</p></div></div>';
  }).join('')+'</div>';
}

function table(st){
  return '<h2>Standings, worst first</h2><table class="tbl">'+
    '<tr><th>Manager</th><th class="n">Picks</th><th class="n">GPA</th>'+
    '<th>Worst pick</th></tr>'+
    st.map(function(m){
      var w = m.worst, o = (w && w.outcome) || {};
      return '<tr><td>'+esc(m.manager)+'</td><td class="n">'+m.picks+'</td>'+
        '<td class="n">'+m.gpa.toFixed(2)+'</td><td>'+
        (w ? esc(w.player)+(o.pos_taken ? ' ('+esc(w.pos)+o.pos_taken+' &rarr; '+
             esc(w.pos)+o.pos_rank+')' : '') : '&mdash;')+'</td></tr>';
    }).join('')+'</table>';
}

function setYear(v){
  YEAR = v;
  var u = new URL(location); u.searchParams.set('season', v);
  history.replaceState(null, '', u);
  render();
}

function render(){
  var d = DATA[YEAR];
  document.getElementById('seasons').innerHTML =
    '<span class="lbl">Draft</span>'+SEASONS.map(function(y){
      return '<button data-y="'+esc(y)+'" onclick="setYear(this.dataset.y)"'+
        (YEAR===y?' class="sel"':'')+'>'+esc(y)+'</button>';
    }).join('');
  if(!d){ document.getElementById('main').innerHTML = ''; return; }
  document.getElementById('sub').textContent =
    YEAR+' draft \\u2014 the '+d.rows.length+' worst and '+d.best.length+
    ' best of '+d.picks+' picks';
  document.getElementById('main').innerHTML = table(d.standings)+
    '<h2>The '+d.rows.length+' worst picks of that draft</h2>'+feed(d.rows)+
    '<h2>The '+d.best.length+' best picks of that draft</h2>'+
    '<p class="note" style="margin:0 0 4px">The ones who most outperformed the '+
    'slot they cost. Grudgingly acknowledged.</p>'+feed(d.best);
}
render();
</script>
"""


if __name__ == "__main__":
    main()
