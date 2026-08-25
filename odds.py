#!/usr/bin/env python3
"""Playoff odds by simulating the rest of the season.

    python odds.py --season 2025 --through 10
    python odds.py --season 2025 --through 10 --sims 20000

Each remaining matchup is replayed many times, drawing both teams' scores from
their own observed mean and spread this season. That gives playoff odds, a full
seed distribution, and how many wins each team still needs -- rather than a
single "you are 7-3" that says nothing about what happens next.

Two honest limits, both stated in the output: scores are drawn independently
(a real week has shared weather, shared bye weeks, correlated outcomes), and a
team's spread is estimated from a handful of games, so early-season numbers are
softer than they look.
"""

import argparse
import random
import statistics
import sys
from collections import defaultdict

import season as season_mod

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class OddsUnavailable(Exception):
    """Not enough season yet to simulate.

    A normal exception, deliberately: this used to be SystemExit, which is a
    BaseException, so `except Exception` in dashboard.py never caught it and the
    whole page died rather than the one section that could not be computed.
    """


class NoSchedule(OddsUnavailable):
    pass


class NotEnoughGames(OddsUnavailable):
    pass


def league_spots(st, override=None):
    """How many teams actually make this league's playoffs.

    Read from the league, not assumed. The default was 6; this league has
    carried playoff_teams=8 in every cached season, which understated bubble
    teams' odds by 20-40 points.
    """
    if override:
        return override
    return int((st.s.settings or {}).get("playoff_teams") or 6)


def bye_count(spots):
    """First-round byes implied by the bracket. An 8-team bracket has none --
    the old code hardcoded 'top 2', which described a bracket this league does
    not play."""
    size = 1
    while size < spots:
        size *= 2
    return max(0, size - spots)


def simulate(st, sims=10000, playoff_spots=6, seed=7):
    """Replay the remaining regular season `sims` times."""
    rng = random.Random(seed)
    byes_n = bye_count(playoff_spots)
    rosters = list(st.s.managers)
    params = {rid: st.mean_sd(rid) for rid in rosters}
    base = {rid: (st.results[rid]["w"], st.results[rid]["pf"]) for rid in rosters}
    remaining = [(wk, st.schedule.get(wk, {})) for wk in st.remaining_weeks()]
    games = sum(len(p) for _, p in remaining) // 2
    if not remaining or games == 0:
        raise NoSchedule(
            "No remaining schedule is cached, so there is nothing to simulate. "
            "Run: python pull.py --user <name>, or pass --through below the "
            "last played week.")
    if max((len(v) for v in st.scores.values()), default=0) < 2:
        raise NotEnoughGames(
            "Fewer than two scored weeks: there is no spread to draw from yet.")

    made = defaultdict(int)
    seeds = defaultdict(lambda: defaultdict(int))
    wins_dist = defaultdict(list)
    byes = defaultdict(int)

    for _ in range(sims):
        w = {rid: base[rid][0] for rid in rosters}
        pf = {rid: base[rid][1] for rid in rosters}
        for wk, pairings in remaining:
            done = set()
            for rid, opp in pairings.items():
                if rid in done or opp in done or opp not in params:
                    continue
                done.add(rid); done.add(opp)
                ma, sa = params[rid]
                mb, sb = params[opp]
                pa = rng.gauss(ma, sa)
                pb = rng.gauss(mb, sb)
                pf[rid] += pa; pf[opp] += pb
                if pa > pb:
                    w[rid] += 1
                elif pb > pa:
                    w[opp] += 1
        order = sorted(rosters, key=lambda r: (-w[r], -pf[r]))
        for i, rid in enumerate(order, 1):
            seeds[rid][i] += 1
            if i <= playoff_spots:
                made[rid] += 1
            if byes_n and i <= byes_n:
                byes[rid] += 1
        for rid in rosters:
            wins_dist[rid].append(w[rid])

    out = []
    for rid in rosters:
        ws = wins_dist[rid]
        out.append({
            "roster_id": rid, "name": st.names[rid],
            "record": f"{st.results[rid]['w']}-{st.results[rid]['l']}",
            "playoff_pct": made[rid] / sims * 100,
            "bye_pct": byes[rid] / sims * 100,
            "mean_wins": statistics.fmean(ws),
            "p10_wins": sorted(ws)[int(sims * 0.10)],
            "p90_wins": sorted(ws)[int(sims * 0.90)],
            "seeds": {k: v / sims * 100 for k, v in sorted(seeds[rid].items())},
        })
    out.sort(key=lambda r: -r["playoff_pct"])
    return out


def clinch_needs(st, rows, sims=4000, playoff_spots=6, seed=11):
    """How many of their remaining games each team needs to win to be safe.

    Forces a team to win its FIRST `target` remaining games and re-simulates
    everyone else. That answers "win your next N and you are 95% safe" -- it is
    not a claim that any N of the remaining games suffice, which would need
    every combination evaluated. The output is labelled "win N" for that reason.
    """
    rng = random.Random(seed)
    n_left = len(st.remaining_weeks())
    # Hoisted: mean_sd walks every score in the league on each call, and the old
    # placement had it inside the innermost loop -- millions of recomputations
    # of a value that cannot change mid-run.
    params = {r: st.mean_sd(r) for r in st.s.managers}
    weeks = [(wk, st.schedule.get(wk, {})) for wk in st.remaining_weeks()]
    needs = {}
    for row in rows:
        rid = row["roster_id"]
        if n_left == 0:
            needs[rid] = None
            continue
        found = None
        for target in range(0, n_left + 1):
            hits = 0
            for _ in range(sims):
                w = {r: st.results[r]["w"] for r in st.s.managers}
                pf = {r: st.results[r]["pf"] for r in st.s.managers}
                mine = 0
                for wk, pairings in weeks:
                    done = set()
                    for a, b in pairings.items():
                        if a in done or b in done or b not in st.s.managers:
                            continue
                        done.add(a); done.add(b)
                        ma, sa = params[a]; mb, sb = params[b]
                        pa, pb = rng.gauss(ma, sa), rng.gauss(mb, sb)
                        if rid in (a, b):
                            # Forced result, but still DRAWN scores -- the higher
                            # of the two simply goes to whoever the forced
                            # outcome says won. Adding each team's mean instead
                            # gave both a spreadless points-for total, and
                            # points-for is the standings tiebreak.
                            other = b if a == rid else a
                            win = mine < target
                            mine += 1 if win else 0
                            w[rid if win else other] += 1
                            hi, lo = max(pa, pb), min(pa, pb)
                            pf[rid] += hi if win else lo
                            pf[other] += lo if win else hi
                            continue
                        pf[a] += pa; pf[b] += pb
                        if pa > pb:
                            w[a] += 1
                        elif pb > pa:
                            w[b] += 1
                order = sorted(st.s.managers, key=lambda r: (-w[r], -pf[r]))
                if order.index(rid) < playoff_spots:
                    hits += 1
            if hits / sims >= 0.95:
                found = target
                break
        needs[rid] = found
    return needs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season")
    ap.add_argument("--through", type=int)
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--spots", type=int, default=None,
                    help="override the league's playoff_teams setting")
    ap.add_argument("--clinch", action="store_true", help="also compute wins needed")
    args = ap.parse_args()

    if args.sims < 1:
        raise SystemExit("--sims must be at least 1")
    st = season_mod.load(args.through, args.season)
    spots = league_spots(st, args.spots)
    nbye = bye_count(spots)
    left = st.remaining_weeks()
    bye_txt = f", top {nbye} get a bye" if nbye else " (no first-round byes)"
    print(f"{st.season} through week {st.through} -- {len(left)} weeks left "
          f"({', '.join(map(str, left)) or 'none'})")
    print(f"simulating {args.sims:,} seasons, top {spots} make the playoffs{bye_txt}")
    print()

    try:
        rows = simulate(st, args.sims, spots)
    except OddsUnavailable as err:
        raise SystemExit(str(err))
    needs = clinch_needs(st, rows, playoff_spots=spots) if args.clinch else {}

    cols = ["manager", "rec", "playoff%"] + (["bye%"] if nbye else []) + \
           ["wins (10-90)", "need"]
    fmt = "  {:<20}{:>7}{:>10}" + ("{:>8}" if nbye else "") + "{:>13}{:>9}"
    print(fmt.format(*cols))
    for r in rows:
        n = needs.get(r["roster_id"])
        need = "-" if not args.clinch else ("safe" if n == 0 else
                                            (f"win {n}" if n is not None else "n/a"))
        vals = [r["name"][:18], r["record"], f"{r['playoff_pct']:.1f}%"]
        if nbye:
            vals.append(f"{r['bye_pct']:.1f}%")
        vals += [f"{r['p10_wins']}-{r['p90_wins']}", need]
        print(fmt.format(*vals))

    print("\n  Scores are drawn independently from each team's own mean and")
    print("  spread. Real weeks are correlated -- byes, weather, one defence")
    print("  facing two of your starters -- so treat these as directional.")
    if len(st.weeks) < 6:
        print("  Fewer than six games played: the spread estimates are soft.")


if __name__ == "__main__":
    main()
