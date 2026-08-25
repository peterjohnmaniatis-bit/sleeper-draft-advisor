#!/usr/bin/env python3
"""The waiver wire, from week zero onward.

    python wire.py                     # this week's board
    python wire.py --week 1 --pos RB

The existing waiver ranking is built on usage -- snap share, target share,
red-zone looks -- which is the right signal and does not exist yet. It needs
two games before it says anything, so the tools were blind through weeks one
and two. That is exactly backwards for this league: 58.7% of all waiver value
ever created here came in weeks 1-6, and 21.5% in weeks 1-2 alone.

So this ranks on whatever is actually known this week, and shifts its weight as
the season supplies better evidence:

    week 0-1   season projections, depth-chart position, last year's usage
    week 2-4   those, blended with this year's usage as it accumulates
    week 5+    essentially this year's usage, which is what advise.py does

The blend is a single weight rather than a mode switch, so nothing lurches when
the fourth game is played.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import season as season_mod
from model import RAW, Players, _load, nfl_week
from trade import season_projections
from usage import usage

ROOT = Path(__file__).resolve().parent
SKILL = ("QB", "RB", "WR", "TE", "K", "DEF")
# Usage is trusted completely once a player has this many games this season.
FULL_TRUST = 4

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def player_meta():
    """depth chart, injury and market rank, straight from the player file."""
    raw = json.loads((RAW / "players_nfl.json").read_text(encoding="utf-8"))
    out = {}
    for pid, p in raw.items():
        out[pid] = {
            "depth": p.get("depth_chart_order"),
            "injury": p.get("injury_status"),
            "status": p.get("status"),
            "rank": p.get("search_rank"),
            "team": p.get("team"),
            "exp": p.get("years_exp"),
        }
    return out


def prior_usage(season, players):
    """Last season's snap and touch share, as the week-zero stand-in.

    A player who finished last year on 70% of snaps is a different proposition
    from one who finished on 12%, and in week one that is the only usage
    evidence in existence.
    """
    try:
        prev = str(int(season) - 1)
    except (TypeError, ValueError):
        return {}
    table, weeks = usage(prev, 18, players, window=6)
    return {pid: u for pid, u in (table or {}).items() if u.get("games")}


def score(pid, pos, proj, meta, now, prior, weight):
    """One free agent's score, on a 0-100ish scale.

    Deliberately not a points projection. It is a ranking of who is worth a
    claim, and the components are the things that actually separate a useful
    pickup from a name: projected role, where he sits on his own depth chart,
    and how much of his team's work he was doing when last observed.
    """
    m = meta.get(pid) or {}
    pts = proj.get(pid, 0.0)

    # Projected points, scaled inside the position so a kicker and a receiver
    # are not compared on a raw total.
    base = pts

    # Depth chart. Being the starter is most of what makes a free agent useful,
    # and it is knowable in week zero when nothing else is.
    d = m.get("depth")
    if d == 1:
        base *= 1.25
    elif d == 2:
        base *= 1.05
    elif d and d >= 4:
        base *= 0.75

    # Usage, this year's blended with last year's by how much of it exists.
    u_now = (now.get(pid) or {})
    u_old = (prior.get(pid) or {})
    share_now = u_now.get("r_touch_sh") or u_now.get("r_snap") or 0.0
    share_old = u_old.get("touch_sh") or u_old.get("snap") or 0.0
    share = weight * share_now + (1 - weight) * share_old
    base *= (1.0 + share)

    # Anything that keeps him off the field.
    inj = (m.get("injury") or "").lower()
    if inj in ("out", "ir", "pup", "doubtful", "suspended"):
        base *= 0.25
    elif inj == "questionable":
        base *= 0.9
    if (m.get("status") or "").lower() not in ("active", ""):
        base *= 0.5
    return base


def board(st, players, per_pos=8, week=None):
    """The claim-worthy free agents in this league, by position."""
    season = st.season
    week = week if week is not None else max(1, nfl_week() or 1)
    proj = season_projections(season)
    meta = player_meta()

    # This season's usage, if any exists yet.
    now, _ = usage(season, max(0, week - 1), players, window=4) if week > 1 else ({}, [])
    prior = prior_usage(season, players)
    played = max(0, week - 1)
    weight = min(1.0, played / FULL_TRUST)

    out = defaultdict(list)
    for pid in st.free_agents(players, positions=SKILL):
        pos = players.position(pid)
        s = score(pid, pos, proj, meta, now, prior, weight)
        if s <= 0:
            continue
        m = meta.get(pid) or {}
        u_now = (now.get(pid) or {})
        u_old = (prior.get(pid) or {})
        out[pos].append({
            "player_id": pid, "name": players.name(pid), "pos": pos,
            "team": m.get("team"), "score": round(s, 1),
            "proj": round(proj.get(pid, 0.0), 1),
            "depth": m.get("depth"), "injury": m.get("injury"),
            "snap_now": u_now.get("r_snap"), "snap_prev": u_old.get("snap"),
            "touch_now": u_now.get("r_touch_sh"), "touch_prev": u_old.get("touch_sh"),
        })
    for pos in out:
        out[pos].sort(key=lambda r: -r["score"])
        out[pos] = out[pos][:per_pos]
    return dict(out), weight, week


def pct(v):
    return "-" if v is None else f"{v*100:.0f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season")
    ap.add_argument("--week", type=int, help="defaults to the live NFL week")
    ap.add_argument("--pos")
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()

    st = season_mod.load(season=a.season)
    players = Players()
    rows, weight, week = board(st, players, a.top, a.week)

    src = ("projections and last season" if weight < 0.05 else
           f"{weight*100:.0f}% this season's usage, "
           f"{(1-weight)*100:.0f}% projections and last season")
    print(f"{st.season} week {week} waiver board  --  ranked on {src}\n")
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        if a.pos and pos != a.pos.upper():
            continue
        lst = rows.get(pos) or []
        if not lst:
            continue
        print(f"  {pos}")
        print("    {:<24}{:<4}{:>6}{:>7}{:>7}{:>8}{:>8}  {}".format(
            "player", "tm", "score", "proj", "depth", "snap25", "snap26", "note"))
        for r in lst:
            note = r["injury"] or ""
            print("    {:<24}{:<4}{:>6.0f}{:>7.0f}{:>7}{:>8}{:>8}  {}".format(
                r["name"][:22], r["team"] or "-", r["score"], r["proj"],
                r["depth"] if r["depth"] else "-",
                pct(r["snap_prev"]), pct(r["snap_now"]), note))
        print()
    print("  Score blends projected role, depth-chart position and share of")
    print("  team volume. It is a claim ranking, not a points forecast.")


if __name__ == "__main__":
    main()
