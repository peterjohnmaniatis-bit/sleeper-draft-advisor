#!/usr/bin/env python3
"""In-season advice: waivers, start/sit, and who to call about a trade.

    python advise.py --season 2025 --through 10
    python advise.py --season 2025 --through 10 --only waivers

Three questions a manager actually asks each week:
  waivers   who is free in THIS league and worth a claim
  lineup    who should start next week
  trades    which of the eleven other rosters is a natural partner

Waivers are ranked on usage, not on last week's points. A player who saw 28%
of his team's targets is a better bet than one who scored 22 on two catches,
and the difference is the whole reason the usage layer exists.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict

import season as season_mod
from analyze import optimal_lineup
from model import Players, replacement_ranks
from trade import replacement_levels, season_projections
from usage import usage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = ("QB", "RB", "WR", "TE")


def trending(kind="add", hours=48, limit=200):
    """Platform-wide adds or drops. Documented, unauthenticated, and the one
    outside signal available: it says how contested a claim will be."""
    url = (f"https://api.sleeper.app/v1/players/nfl/trending/{kind}"
           f"?lookback_hours={hours}&limit={limit}")
    req = urllib.request.Request(url, headers={"User-Agent": "ff-analyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            rows = json.loads(r.read()) or []
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        # None, not {} -- an empty dict is indistinguishable from "fetched,
        # nobody is trending", which would read as "your claim is uncontested".
        return None
    return {str(x.get("player_id")): x.get("count", 0) for x in rows}


def week_projections(season, week):
    """Projected PPR points for one upcoming week."""
    url = (f"https://api.sleeper.com/projections/nfl/{season}/{week}"
           f"?season_type=regular")
    req = urllib.request.Request(url, headers={"User-Agent": "ff-analyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            rows = json.loads(r.read()) or []
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return {}
    out = {}
    for row in rows:
        pid = str(row.get("player_id") or "")
        stats = row.get("stats") or {}
        # Only record a player who HAS a projection. Defaulting a missing one
        # to zero makes "no projection" and "projected to score nothing"
        # indistinguishable, and the optimal lineup then happily starts a
        # player who is on bye.
        if pid and stats.get("pts_ppr") is not None:
            out[pid] = float(stats["pts_ppr"])
    return out


def starting_slots_by_pos(st):
    slots = defaultdict(float)
    for s in st.roster_slots():
        if s in SKILL:
            slots[s] += 1
        elif s == "FLEX":
            for p in ("RB", "WR", "TE"):
                slots[p] += 0.34
    return slots


def roster_need(st, rid, players):
    """How thin each position is, as a gentle multiplier.

    Deliberately narrow (0.85 to 1.25). An earlier version swung 0.5 to 2.0 and
    the need term simply overwhelmed usage -- eleven of fifteen suggestions came
    back tight ends because the roster happened to carry one. Need should break
    ties between similar players, not decide the ranking.
    """
    have = defaultdict(int)
    for pid in st.rosters.get(rid, []):
        pos = players.position(pid)
        if pos in SKILL:
            have[pos] += 1
    slots = starting_slots_by_pos(st)
    need = {}
    for pos in SKILL:
        want = slots.get(pos, 0) + 1
        ratio = want / max(1, have[pos])
        need[pos] = max(0.85, min(1.25, 0.85 + 0.4 * (ratio - 0.6)))
    return need


def waivers(st, players, use, trend, per_pos=5):
    """Free agents in this league, ranked on usage, GROUPED BY POSITION.

    Grouped deliberately. Blending positions into one list ranks quarterbacks
    first every time, because a quarterback plays essentially every snap by
    definition while a receiver who plays 70% is a genuine workhorse. The two
    numbers are not on the same scale and no weighting fixes that honestly --
    so the comparison is only made within a position, which is also the way the
    question actually gets asked: who is the best back available.
    """
    idx = __import__("model")._load("index.json") or {}
    me = next((rid for rid, m in st.s.managers.items()
               if m["display_name"] == idx.get("username")), None)
    need = roster_need(st, me, players) if me else {p: 1.0 for p in SKILL}

    by_pos = defaultdict(list)
    for pid in st.free_agents(players):
        u = use.get(pid)
        if not u or u["recent_games"] < 2:
            continue
        # A player who has not suited up recently is not a waiver target,
        # however good his September was. Without this the top two receivers
        # suggested for week 11 were two season-ending injuries whose last
        # game was week 4.
        if u.get("weeks_out", 0) >= 2:
            continue
        if u["pos"] == "QB":
            parts = [(u["r_pts"] or 0) * 1.0, (u["r_rz"] or 0) * 4]
        else:
            parts = [(u["r_touch_sh"] or 0) * 100, (u["r_snap"] or 0) * 25,
                     (u["r_rz"] or 0) * 6, (u["r_pts"] or 0) * 0.6]
        by_pos[u["pos"]].append({**u, "score": sum(parts),
                                 "trend": (trend or {}).get(pid, 0)})
    out = {}
    for pos, rows in by_pos.items():
        rows.sort(key=lambda r: -r["score"])
        out[pos] = rows[:per_pos]
    return me, out, need


def lineup_call(st, players, week, proj):
    """Best legal lineup for the coming week, and who it benches."""
    idx = __import__("model")._load("index.json") or {}
    me = next((rid for rid, m in st.s.managers.items()
               if m["display_name"] == idx.get("username")), None)
    if me is None:
        return None, [], []
    roster = st.rosters.get(me, [])
    # Missing projections default to 0 so a slot can still be filled, but the
    # caller is told which starters those are -- printing "0.0" next to a name
    # reads as "projected to do nothing" when it means "we have no number".
    entry = {"players": roster, "players_points": {p: proj.get(p, 0.0) for p in roster}}
    total, chosen = optimal_lineup(entry, players, st.roster_slots())
    starters = {c["player_id"] for c in chosen}
    bench = sorted((p for p in roster if p not in starters),
                   key=lambda p: -proj.get(p, 0.0))
    return total, chosen, bench


def trade_targets(st, players, proj, levels):
    """Which rosters are natural partners: they are deep where you are thin.

    A pricer tells you whether a proposed deal is fair. This answers the
    question before that one -- who to call.
    """
    idx = __import__("model")._load("index.json") or {}
    me = next((rid for rid, m in st.s.managers.items()
               if m["display_name"] == idx.get("username")), None)
    if me is None:
        return [], []

    slots = starting_slots_by_pos(st)

    def split(rid):
        """Starter strength and bench surplus, separately.

        Keeping these apart matters: an earlier version measured need by depth
        alone, so a roster with one elite quarterback and nothing behind him
        was reported as SHORT at quarterback. Strength is what you start;
        surplus is what you could trade without weakening that.
        """
        by = defaultdict(list)
        for pid in st.rosters.get(rid, []):
            pos = players.position(pid)
            if pos in SKILL:
                by[pos].append(proj.get(pid, 0.0) - levels.get(pos, 0.0))
        strength, surplus = {}, {}
        for pos in SKILL:
            vals = sorted(by.get(pos, []), reverse=True)
            keep = max(1, round(slots.get(pos, 1)))
            strength[pos] = sum(vals[:keep])
            surplus[pos] = sum(v for v in vals[keep:] if v > 0)
        return strength, surplus

    everyone = {rid: split(rid) for rid in st.s.managers}
    my_str, my_sur = everyone[me]

    # "Thin" means my starters are below the league median at that position,
    # not that my bench is short.
    median = {}
    for pos in SKILL:
        vals = sorted(everyone[r][0].get(pos, 0) for r in everyone)
        median[pos] = vals[len(vals) // 2]
    thin = [p for p in SKILL if my_str.get(p, 0) < median[p]]

    rows = []
    for rid in st.s.managers:
        if rid == me:
            continue
        their_str, their_sur = everyone[rid]
        fits = []
        for pos in thin:
            if their_sur.get(pos, 0) > 10:
                fits.append((pos, their_sur[pos]))
        # What they would want back: where they are below median and I am not.
        wants = [p for p in SKILL
                 if their_str.get(p, 0) < median[p] and my_sur.get(p, 0) > 10]
        if not fits:
            continue
        fits.sort(key=lambda x: -x[1])
        rows.append({"roster_id": rid, "name": st.names[rid],
                     "fit": sum(g for _, g in fits),
                     "they_spare": [p for p, _ in fits[:2]],
                     "they_want": wants[:2]})
    rows.sort(key=lambda r: -r["fit"])
    return rows[:5], thin


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season")
    ap.add_argument("--through", type=int)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--only", choices=["waivers", "lineup", "trades"])
    args = ap.parse_args()

    st = season_mod.load(args.through, args.season)
    players = Players()
    nxt = st.through + 1
    print(f"{st.season} -- advice for week {nxt} (through week {st.through})\n")

    if args.only in (None, "waivers"):
        use, _ = usage(st.season, st.through, players, args.window)
        trend = trending()
        me, groups, need = waivers(st, players, use, trend)
        print("WAIVER TARGETS -- free in your league, ranked on usage")
        for pos in ("RB", "WR", "TE", "QB"):
            rows = groups.get(pos) or []
            if not rows:
                continue
            flag = "  (you are thin here)" if need.get(pos, 1) >= 1.15 else ""
            print()
            print("  {}{}".format(pos, flag))
            print("    {:<24}{:<4}{:>7}{:>7}{:>7}{:>7}{:>8}".format(
                "player", "tm", "snap%", "tgt%", "rz/g", "pts/g", "adds"))
            for r in rows:
                pc = lambda v: "-" if v is None else format(v * 100, ".0f")
                nm = lambda v: "-" if v is None else format(v, ".1f")
                print("    {:<24}{:<4}{:>7}{:>7}{:>7}{:>7}{:>8}".format(
                    r["name"][:22], r["team"] or "-", pc(r["r_snap"]),
                    ("-" if r["pos"] == "QB" else pc(r["r_tgt_sh"])),
                    nm(r["r_rz"]), nm(r["r_pts"]),
                    ("n/a" if trend is None else (r["trend"] or "-"))))
        print()
        print("  Ranked within position on share of team volume, not on last")
        print("  week's points. 'adds' is how many Sleeper leagues picked him up")
        print("  in 48 hours -- the higher it is, the more contested your claim.")
        if trend is None:
            print("  The trending endpoint did not answer, so 'adds' reads n/a --")
            print("  that is unknown contention, not an uncontested claim.")
        print()

    if args.only in (None, "lineup"):
        proj = week_projections(st.season, nxt)
        if proj:
            total, chosen, bench = lineup_call(st, players, nxt, proj)
            if total is not None:
                print(f"START/SIT -- week {nxt}, projected {total:.1f}")
                for c in chosen:
                    pts = ("{:>7.1f}".format(c["points"])
                           if c["player_id"] in proj else "  no proj")
                    print("  {:<6}{:<24}{}".format(
                        c["slot"], players.name(c["player_id"])[:22], pts))
                missing = [p for p in bench if p not in proj]
                real = [p for p in bench if p in proj]
                if real:
                    print("  bench: " + ", ".join(
                        f"{players.name(p)} ({proj[p]:.0f})" for p in real[:6]))
                if missing:
                    print("  no projection (bye, injured or inactive): " +
                          ", ".join(players.name(p) for p in missing[:6]))
                print()
        else:
            print(f"START/SIT -- no projections available for week {nxt}\n")

    if args.only in (None, "trades"):
        sp = season_projections(st.season)
        ranks = replacement_ranks(st.s)
        levels = replacement_levels(sp, players, ranks)
        rows, thin = trade_targets(st, players, sp, levels)
        print("TRADE PARTNERS -- who is deep where your STARTERS are below median")
        print("  your weak spots: " + ("/".join(thin) if thin else "none -- "
              "your starting lineup is at or above league median everywhere"))
        if not rows:
            print("  No clear fits: nobody holds spare value at those positions.")
        for r in rows:
            print("  {:<20} spare {:<10} would want back {}".format(
                r["name"][:18], "/".join(r["they_spare"]),
                "/".join(r["they_want"]) or "unclear"))
        print("\n  A starting point for a conversation, not a proposed deal.")
        print("  Price any actual swap with trade.py before sending it.")


if __name__ == "__main__":
    main()
