#!/usr/bin/env python3
"""The one page you open each week, from week zero to the playoffs.

    python weekly.py                 # -> weekly.html
    python weekly.py --fragment      # -> out/weekly.html, for publishing

dashboard.py needed a mid-season league to say anything: usage wanted two
games, the odds simulator refused under two scored weeks, and at week zero it
wrote no file at all. This one is built the other way round -- it always
renders, and each section either shows what it knows or says plainly why it
cannot know it yet.

Recomputed over all 1,052 acquisitions: weeks 1-2 hold 15.2% of waiver value,
weeks 1-6 hold 45.8%, and weeks 11+ hold 25.2% -- not the front-loaded picture
an earlier pass claimed. Being useful in week 1 still matters, but because the
roster needs work in week 1, not because the wire dries up later.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import byes as byes_mod
import season as season_mod
import wire as wire_mod
from model import Players, _load, nfl_week
from report import CSS, esc, table

ROOT = Path(__file__).resolve().parent
POS_ORDER = ("RB", "WR", "TE", "QB", "K", "DEF")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Sleeper keeps the IR slot in settings.reserve_slots, NOT in roster_positions,
# which is why every tool here has been blind to it. It matters: a PUP or IR
# player parked there frees a bench spot, so the number of drops a roster needs
# is not simply (players - slots).
def reserve_info(st, players, rid, raw):
    lg = _load(f"{st.season}/league.json") or {}
    slots = int((lg.get("settings") or {}).get("reserve_slots") or 0)
    ELIGIBLE = {"ir", "pup", "out", "doubtful", "sus", "suspended"}
    cands = []
    for pid in st.rosters.get(rid, []):
        inj = ((raw.get(pid) or {}).get("injury_status") or "").lower()
        if inj in ELIGIBLE:
            cands.append({"name": players.name(pid), "pos": players.position(pid),
                          "status": inj.upper()})
    return slots, cands


def legality(st, players, rid):
    """Can this roster even field a legal lineup? Returns the holes.

    Checked first and shown first because it is the one thing that costs points
    with certainty rather than in expectation: an unfilled mandatory slot
    scores zero every single week until it is filled.
    """
    have = defaultdict(int)
    for pid in st.rosters.get(rid, []):
        have[players.position(pid)] += 1
    need = defaultdict(int)
    for s in st.roster_slots():
        if s != "FLEX":
            need[s] += 1
    holes = {p: need[p] - have.get(p, 0) for p in need if need[p] > have.get(p, 0)}
    return holes, dict(have), dict(need)


def build(st, players, me, holes, have, wire_rows, weight, week, bye_rows,
          playoff, guaranteed, reserve):
    p = ['<div class="wrap">']
    p.append(f"<h1>Week {week}</h1>")
    played = len(st.weeks)
    p.append(f'<p class="sub">{esc(st.season)} season &middot; '
             f'{played} week{"" if played == 1 else "s"} played &middot; '
             f'{len(st.remaining_weeks())} regular-season weeks left &middot; '
             f'playoffs start week {playoff}</p>')

    # -- guaranteed zeros first, then merely-empty slots. An empty K is a
    # problem you will obviously solve before Sunday; a bye week with no backup
    # at the position is one you will not notice until it has already cost you.
    if guaranteed:
        p.append('<h2>Guaranteed zeros ahead</h2>')
        p.append('<p class="sub">You roster exactly one player at these '
                 'positions and he has a bye. Nothing on the roster can cover '
                 'it, so the slot scores zero unless you add someone first.</p>')
        p.append(table(["Position", "#Week", "Player on bye"],
                       [[esc(g["pos"]), str(g["week"]), esc(g["name"])]
                        for g in guaranteed]))

    if holes:
        p.append('<h2>Your lineup is not legal</h2>')
        need = ", ".join(f"{n} {pos}" for pos, n in sorted(holes.items()))
        p.append(f'<p class="sub">You must start a {esc(need)} and do not have '
                 f'one. An empty mandatory slot scores zero every week until it '
                 f'is filled &mdash; across this league&rsquo;s history, teams '
                 f'started a kicker in 839 of 840 games and a defence in all '
                 f'840.</p>')
        r_slots, r_cands = reserve
        adds = sum(holes.values())
        spare = max(0, len(st.roster_slots()) + 5 - len(st.rosters.get(me, [])))
        drops = max(0, adds - spare)
        if r_slots and r_cands and drops:
            names = ", ".join(f'{esc(c["name"])} ({esc(c["status"])})'
                              for c in r_cands)
            p.append(f'<p class="note">You need {adds} add'
                     f'{"" if adds == 1 else "s"} and have {drops} spare '
                     f'spot{"" if drops == 1 else "s"} &mdash; but this league '
                     f'carries {r_slots} IR slot, which is in the league '
                     f'settings and not in the roster list, so no tool here '
                     f'has ever counted it. Currently eligible: {names}. '
                     f'Parking one there buys back a spot and reduces the '
                     f'drops by one.</p>')
        for pos in sorted(holes):
            rows = (wire_rows.get(pos) or [])[:5]
            if rows:
                p.append(f"<h3>Best {esc(pos)} available</h3>")
                p.append(table(["Player", "Tm", "#Score", "#Projected"],
                               [[esc(r["name"]), r["team"] or "-",
                                 f'{r["score"]:.0f}', f'{r["proj"]:.0f}']
                                for r in rows]))

    # -- byes
    p.append("<h2>Bye weeks</h2>")
    if bye_rows:
        worst = max((h for _, h, _ in bye_rows), default=0)
        p.append('<p class="sub">Knowable now, and cheaper to cover in advance '
                 'than in the week itself.</p>')
        rows = []
        for w, h, plist in bye_rows:
            tag = ""
            if w >= playoff:
                tag = " (playoff week)"
            elif w == playoff - 1:
                tag = " (final seeding week)"
            rows.append([f"Week {w}{tag}", str(h) if h else "-",
                         ", ".join(f'{esc(x["name"])} ({esc(x["pos"])})'
                                   for x in plist)])
        p.append(table(["Week", "#Starters lost", "Players"], rows))
        if worst >= 2:
            bad = ", ".join(str(w) for w, h, _ in bye_rows if h == worst)
            p.append(f'<p class="note">Worst is week {bad}, losing {worst} '
                     f'starters.</p>')
    else:
        p.append('<p class="sub">No schedule cached, so byes cannot be '
                 'derived yet.</p>')

    # -- the wire
    p.append("<h2>Waiver targets</h2>")
    if weight < 0.05:
        src = ("No games have been played, so this ranks on projected role, "
               "depth-chart position and last season&rsquo;s share of team "
               "volume.")
    elif weight < 1:
        src = (f"Ranked on {weight*100:.0f}% this season&rsquo;s usage and "
               f"{(1-weight)*100:.0f}% projections and last season, shifting "
               f"toward this season as games are played.")
    else:
        src = "Ranked on this season&rsquo;s usage &mdash; share of team volume."
    p.append(f'<p class="sub">Free in your league. {src}</p>')
    for pos in POS_ORDER:
        rows = (wire_rows.get(pos) or [])[:6]
        if not rows:
            continue
        p.append(f"<h3>{esc(pos)}</h3>")
        p.append(table(
            ["Player", "Tm", "#Score", "#Projected", "#Depth", "#Snap last yr", "Note"],
            [[esc(r["name"]), r["team"] or "-", f'{r["score"]:.0f}',
              f'{r["proj"]:.0f}', r["depth"] if r["depth"] else "-",
              wire_mod.pct(r["snap_prev"]),
              esc(r["injury"] or "")] for r in rows]))
    p.append('<p class="note">Score blends projected role, depth-chart position '
             'and share of team volume. It ranks who is worth a claim; it is not '
             'a points forecast.</p>')

    p.append('<p class="note" style="margin-top:32px">Built from Sleeper alone. '
             'Regenerated on a schedule; nothing here needs a server.</p>')
    p.append("</div>")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season")
    ap.add_argument("--week", type=int,
                    help="pin the week; a scheduled job should always pass this")
    ap.add_argument("--me")
    ap.add_argument("--fragment", action="store_true")
    a = ap.parse_args()

    st = season_mod.load(season=a.season)
    players = Players()
    idx = _load("index.json") or {}
    who = a.me or idx.get("username")
    me = next((rid for rid, m in st.s.managers.items()
               if m["display_name"] == who), None)
    if me is None:
        raise SystemExit(f"No manager called {who!r} in this league.")

    week = a.week if a.week is not None else max(1, nfl_week() or 1)
    print(f"building week {week} for {who} ...")

    holes, have, _need = legality(st, players, me)
    wire_rows, weight, _ = wire_mod.board(st, players, per_pos=8, week=week)

    bye_map = byes_mod.bye_weeks(st.season)
    bye_rows = []
    if bye_map:
        weeks = byes_mod.roster_byes(st, players, me, bye_map)
        slots = st.roster_slots()
        for w in sorted(weeks):
            bye_rows.append((w, byes_mod.starters_lost(weeks[w], slots), weeks[w]))

    # A position is a guaranteed zero when the roster holds exactly one of it
    # and he has a bye. Ranked above the empty K/DEF slots deliberately: an
    # empty mandatory slot is obvious and will be filled tonight, whereas this
    # sits eight weeks away and nothing else surfaces it.
    import json as _json
    raw = _json.loads((ROOT / "data" / "raw" / "players_nfl.json").read_text(encoding="utf-8"))
    held = defaultdict(list)
    for pid in st.rosters.get(me, []):
        held[players.position(pid)].append(pid)
    guaranteed = []
    for w, _h, plist in bye_rows:
        for x in plist:
            if len(held.get(x["pos"], [])) == 1:
                guaranteed.append({"pos": x["pos"], "week": w, "name": x["name"]})
    guaranteed.sort(key=lambda g: g["week"])
    reserve = reserve_info(st, players, me, raw)

    body = build(st, players, me, holes, have, wire_rows, weight, week,
                 bye_rows, st.playoff_start, guaranteed, reserve)
    title = f"Week {week} &mdash; {st.season}"
    if a.fragment:
        doc = f"<title>{title}</title><style>{CSS}</style>{body}"
        doc = doc.encode("ascii", "xmlcharrefreplace").decode("ascii")
        out = ROOT / "out" / "weekly.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(doc, encoding="ascii")
    else:
        doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{title}</title><style>{CSS}</style></head>'
               f'<body>{body}</body></html>')
        out = ROOT / "weekly.html"
        out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}  ({len(doc)/1024:.0f} KB)")
    if holes:
        print("  ! lineup not legal: missing " +
              ", ".join(f"{n} {p}" for p, n in sorted(holes.items())))


if __name__ == "__main__":
    main()
