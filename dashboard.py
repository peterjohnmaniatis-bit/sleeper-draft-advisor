#!/usr/bin/env python3
"""The in-season dashboard: one page you open on Tuesday morning.

    python dashboard.py --season 2025 --through 10
    python dashboard.py --season 2025 --through 10 --fragment

Playoff odds, waiver targets, the lineup call, trade partners and usage
leaders -- everything the weekly decision needs, from Sleeper alone.
"""

import argparse
import sys
from pathlib import Path

import season as season_mod
from advise import (lineup_call, trade_targets, trending, waivers,
                    week_projections)
from model import Players, replacement_ranks
from odds import bye_count, league_spots, simulate
from report import CSS, esc, table
from trade import replacement_levels, season_projections
from usage import usage

ROOT = Path(__file__).resolve().parent
POS_ORDER = ("RB", "WR", "TE", "QB")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def odds_kpi(v):
    """Never round a simulated 99.8% up to a flat 100%: the KPI is the number
    most likely to be read alone, and 100% claims a certainty no run produced."""
    if 0 < v < 1:
        return "&lt;1%"
    if 99 < v < 100:
        return f"{v:.1f}%"
    return f"{v:.0f}%"


def pc(v, d=0):
    return "-" if v is None else format(v * 100, "." + str(d) + "f") + "%"


def nm(v, d=1):
    return "-" if v is None else format(v, "." + str(d) + "f")


def build(st, players, use, groups, need, odds_rows, lineup, partners, thin,
          proj, nxt, me, sims, spots, bye, trend):
    p = ['<div class="wrap">']
    p.append(f"<h1>Week {nxt} &mdash; what to do</h1>")
    p.append(f'<p class="sub">{esc(st.season)} season &middot; through week '
             f'{st.through} &middot; {len(st.remaining_weeks())} regular-season '
             f'weeks left</p>')

    mine = next((r for r in odds_rows if r["roster_id"] == me), None)
    total, chosen, bench = lineup
    p.append('<div class="kpis">')
    if mine:
        seed = {r["roster_id"]: r["seed"] for r in st.standings()}.get(me, "-")
        p.append(f'<div class="kpi"><div class="label">Your record</div>'
                 f'<div class="value">{mine["record"]}</div>'
                 f'<div class="meta">seed {seed} in the standings</div></div>')
        p.append(f'<div class="kpi"><div class="label">Playoff odds</div>'
                 f'<div class="value">{odds_kpi(mine["playoff_pct"])}</div>'
                 f'<div class="meta">{mine["p10_wins"]}-{mine["p90_wins"]} wins likely</div></div>')
    if total is not None:
        p.append(f'<div class="kpi"><div class="label">Best lineup</div>'
                 f'<div class="value">{total:.0f}</div>'
                 f'<div class="meta">projected week {nxt}</div></div>')
    p.append(f'<div class="kpi"><div class="label">Thin at</div>'
             f'<div class="value">{"/".join(thin) if thin else "&mdash;"}</div>'
             f'<div class="meta">starters below league median</div></div>')
    p.append("</div>")

    # -- lineup
    if total is not None and chosen:
        p.append(f"<h2>Start these in week {nxt}</h2>")
        rows = [[c["slot"], esc(players.name(c["player_id"])),
                 f'{c["points"]:.1f}' if c["player_id"] in proj else "no proj"]
                for c in chosen]
        p.append(table(["Slot", "Player", "#Projected"], rows))
        real = [b for b in bench if b in proj]
        gone = [b for b in bench if b not in proj]
        if real:
            p.append('<p class="note">Bench: ' + ", ".join(
                f"{esc(players.name(b))} ({proj[b]:.0f})" for b in real[:8]) + "</p>")
        if gone:
            p.append('<p class="note">No projection &mdash; bye, injured or '
                     'inactive: ' + ", ".join(esc(players.name(b))
                                              for b in gone[:8]) + "</p>")

    # -- waivers
    p.append("<h2>Waiver targets</h2>")
    p.append('<p class="sub">Free in your league, ranked <strong>within '
             'position</strong> on share of team volume rather than on last '
             'week&rsquo;s points. Blending positions would rank quarterbacks '
             'first every time, since they play every snap by definition.</p>')
    for pos in POS_ORDER:
        rows = groups.get(pos) or []
        if not rows:
            continue
        flag = ('  <span style="color:var(--neg)">you are thin here</span>'
                if need.get(pos, 1) >= 1.15 else "")
        p.append(f"<h3>{pos}{flag}</h3>")
        p.append(table(
            ["Player", "Tm", "#Snap", "#Tgt share", "#RZ/g", "#Pts/g", "#Adds 48h"],
            [[esc(r["name"]), r["team"] or "-", pc(r["r_snap"]),
              "-" if pos == "QB" else pc(r["r_tgt_sh"]),
              nm(r["r_rz"]), nm(r["r_pts"]),
              "n/a" if trend is None else (f'{r["trend"]:,}' if r["trend"] else "-")]
             for r in rows]))
    if trend is None:
        p.append('<p class="note">Sleeper&rsquo;s trending endpoint did not '
                 'answer, so Adds reads n/a &mdash; that is unknown contention, '
                 'not an uncontested claim.</p>')
    else:
        p.append('<p class="note">Adds is how many Sleeper leagues picked him up '
                 'in 48 hours &mdash; the higher it is, the more contested your '
                 'claim.</p>')

    # -- odds
    p.append("<h2>Playoff odds</h2>")
    p.append(f'<p class="sub">Every remaining matchup replayed {sims:,} times, '
             f'drawing each team&rsquo;s score from a mean shrunk toward the '
             f'league average and a spread widened for how few games it rests '
             f'on. Top {spots} make the playoffs'
             f'{f", top {bye} get a bye" if bye else " and there are no byes"}.</p>')
    cols = ["Manager", "Record", "#Playoff"] + (["#Bye"] if bye else []) +            ["#Wins 10-90"]
    orows = []
    for r in odds_rows:
        row = [esc(r["name"]) + (" &larr;" if r["roster_id"] == me else ""),
               r["record"], f'{r["playoff_pct"]:.1f}%']
        if bye:
            row.append(f'{r["bye_pct"]:.1f}%')
        row.append(f'{r["p10_wins"]}-{r["p90_wins"]}')
        orows.append(row)
    p.append(table(cols, orows))
    p.append('<p class="note">Scores are drawn independently. Real weeks are '
             'correlated &mdash; byes, weather, one defence facing two of your '
             'starters &mdash; so read these as directional, not exact.</p>')

    # -- trades
    p.append("<h2>Trade partners</h2>")
    if thin:
        p.append(f'<p class="sub">Your starters sit below the league median at '
                 f'<strong>{"/".join(thin)}</strong>. These rosters hold spare '
                 f'value there.</p>')
    else:
        p.append('<p class="sub">Your starting lineup is at or above league '
                 'median everywhere, so there is no obvious hole to fill.</p>')
    if partners:
        p.append(table(["Manager", "Has spare", "Would want back"],
                       [[esc(r["name"]), "/".join(r["they_spare"]),
                         "/".join(r["they_want"]) or "unclear"] for r in partners]))
    p.append('<p class="note">A starting point for a conversation, not a '
             'proposed deal. Price any actual swap with trade.py first.</p>')

    # -- usage leaders
    p.append("<h2>Usage leaders</h2>")
    p.append('<p class="sub">Across the whole league, rostered or not. Volume '
             'is far steadier week to week than points, so this is the better '
             'read on who is about to matter.</p>')
    for pos in ("RB", "WR", "TE"):
        # Sort on a column the reader can actually see. Ranking receivers by
        # touch share while showing target share put a 45% target share sixth
        # in a list headed by 42%, which just looks broken.
        key = "r_touch_sh" if pos == "RB" else "r_tgt_sh"
        rows = sorted((u for u in use.values()
                       if u["pos"] == pos and u["recent_games"] >= 2),
                      key=lambda u: -(u[key] or 0))[:8]
        if not rows:
            continue
        p.append(f"<h3>{pos}</h3>")
        # Air yards are a receiver measurement. A back's catches come at or
        # behind the line, so his air share sits at zero and his air-per-catch
        # runs negative -- both correct, both unreadable as a column of numbers.
        # Backs get volume and red zone instead.
        if pos == "RB":
            p.append(table(["Player", "Tm", "#Snap", "#Touch share",
                            "#Tgt share", "#RZ/g", "#Pts/g"],
                           [[esc(r["name"]), r["team"] or "-", pc(r["r_snap"]),
                             pc(r["r_touch_sh"]), pc(r["r_tgt_sh"]),
                             nm(r["r_rz"]), nm(r["r_pts"])] for r in rows]))
        else:
            p.append(table(["Player", "Tm", "#Snap", "#Tgt share", "#Air share",
                            "#Air/catch", "#RZ/g", "#Pts/g"],
                           [[esc(r["name"]), r["team"] or "-", pc(r["r_snap"]),
                             pc(r["r_tgt_sh"]), pc(r["r_air_sh"]),
                             nm(r["r_air_per_catch"]), nm(r["r_rz"]),
                             nm(r["r_pts"])] for r in rows]))

    p.append('<p class="note" style="margin-top:32px">Built from Sleeper alone. '
             'The weekly stats and projection endpoints are undocumented and '
             'could change without notice; everything here caches locally.</p>')
    p.append("</div>")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season")
    ap.add_argument("--through", type=int)
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--spots", type=int, default=None,
                    help="override the league's playoff_teams setting")
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--fragment", action="store_true")
    args = ap.parse_args()

    st = season_mod.load(args.through, args.season)
    players = Players()
    nxt = st.through + 1
    print(f"building week {nxt} dashboard for {st.season} ...")

    use, _ = usage(st.season, st.through, players, args.window)
    trend = trending()
    me, groups, need = waivers(st, players, use, trend)
    spots = league_spots(st, args.spots)
    bye = bye_count(spots)
    odds_rows = simulate(st, args.sims, spots)
    proj = week_projections(st.season, nxt)
    lineup = lineup_call(st, players, nxt, proj) if proj else (None, [], [])
    sp = season_projections(st.season)
    levels = replacement_levels(sp, players, replacement_ranks(st.s))
    partners, thin = trade_targets(st, players, sp, levels)

    body = build(st, players, use, groups, need, odds_rows, lineup, partners,
                 thin, proj, nxt, me, args.sims, spots, bye, trend)
    title = f"Week {nxt} dashboard &mdash; {st.season}"
    if args.fragment:
        doc = f"<title>{title}</title><style>{CSS}</style>{body}"
        doc = doc.encode("ascii", "xmlcharrefreplace").decode("ascii")
        out = ROOT / "out" / "dashboard.html"
        out.parent.mkdir(exist_ok=True)
    else:
        doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{title}</title><style>{CSS}</style></head>'
               f'<body>{body}</body></html>')
        out = ROOT / "dashboard.html"
    out.write_text(doc, encoding="ascii" if args.fragment else "utf-8")
    print(f"wrote {out}  ({len(doc)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
