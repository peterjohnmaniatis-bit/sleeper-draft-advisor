#!/usr/bin/env python3
"""Scouting report on one or more managers in this league.

    python scout.py wburnett7 JasonMarano
    python scout.py wburnett7 --html      # also writes scout-report.html

Everything comes from what those managers have actually done across five
seasons: how they draft, how they work the wire, how they trade, and how they
have fared against you.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict

from analyze import optimal_lineup
from model import RAW, load_all

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROUND_BUCKETS = [("1-3", 1, 3), ("4-6", 4, 6), ("7-10", 7, 10), ("11-15", 11, 15)]
POS = ("QB", "RB", "WR", "TE")


def profile(data, seasons, players, name, me):
    p = {"name": name, "seasons": [], "draft": [], "trades": [],
         "adds": 0, "lost": 0, "add_pts": 0.0}
    for s in data["seasons"]:
        m = next((x for x in s["managers"].values()
                  if x["display_name"] == name), None)
        if not m:
            continue
        p["seasons"].append({
            "season": s["season"], "w": m["w"], "l": m["l"],
            "exp": m["expected_w"], "luck": m["luck"], "pf": m["pf"],
            "eff": m["efficiency"], "bench": m["points_left_on_bench"],
        })
        p["adds"] += m["waiver_adds"] + m["free_agent_adds"]
        p["lost"] += m["failed_claims"]
        p["add_pts"] += m["acquired_started_points"]
        p["draft"] += [{**d, "season": s["season"]}
                       for d in s["draft"] if d["manager"] == name]
        for t in s["trades"]:
            if name in t["rosters"]:
                p["trades"].append({**t, "season": s["season"]})

    n = len(p["seasons"]) or 1
    p["n"] = len(p["seasons"])
    p["w"] = sum(x["w"] for x in p["seasons"])
    p["l"] = sum(x["l"] for x in p["seasons"])
    p["exp"] = sum(x["exp"] for x in p["seasons"])
    p["luck"] = sum(x["luck"] for x in p["seasons"])
    p["pf"] = sum(x["pf"] for x in p["seasons"])
    p["eff"] = sum(x["eff"] for x in p["seasons"]) / n
    p["bench"] = sum(x["bench"] for x in p["seasons"])
    p["surplus"] = (sum(d["surplus"] for d in p["draft"]) / len(p["draft"])
                    if p["draft"] else 0.0)

    # positional shape of their draft, by round bucket
    p["shape"] = {}
    for label, lo, hi in ROUND_BUCKETS:
        c = Counter(d["position"] for d in p["draft"]
                    if d["position"] in POS and lo <= d["round"] <= hi)
        tot = sum(c.values()) or 1
        p["shape"][label] = {k: round(c[k] / tot * 100) for k in POS}

    # when they first take each position, averaged
    firsts = defaultdict(list)
    for season in {d["season"] for d in p["draft"]}:
        picks = sorted([d for d in p["draft"] if d["season"] == season],
                       key=lambda d: d["pick_no"])
        for pos in POS:
            hit = next((d["round"] for d in picks if d["position"] == pos), None)
            if hit:
                firsts[pos].append(hit)
    p["first_round"] = {k: round(sum(v) / len(v), 1) for k, v in firsts.items()}

    ranked = sorted(p["draft"], key=lambda d: d["surplus"])
    p["worst_pick"] = ranked[0] if ranked else None
    p["best_pick"] = ranked[-1] if ranked else None
    return p


def head_to_head(seasons, players, a, b):
    """Record and lineup effort when these two actually played each other."""
    rec = {"w": 0, "l": 0, "pf": 0.0, "pa": 0.0, "eff": [], "opp_eff": []}
    for s in seasons:
        slots = s.starting_slots
        for wk in s.scored_weeks():
            entries = s.weeks[wk]
            groups = defaultdict(list)
            for rid, e in entries.items():
                if e.get("matchup_id") is not None:
                    groups[e["matchup_id"]].append(rid)
            for sides in groups.values():
                if len(sides) != 2:
                    continue
                names = [s.display(r) for r in sides]
                if a not in names or b not in names:
                    continue
                ra = sides[names.index(a)]
                rb = sides[names.index(b)]
                pa_, pb_ = (entries[ra].get("points") or 0.0), (entries[rb].get("points") or 0.0)
                rec["pf"] += pa_; rec["pa"] += pb_
                rec["w" if pa_ > pb_ else "l"] += 1
                for rid, key in ((ra, "eff"), (rb, "opp_eff")):
                    opt, _ = optimal_lineup(entries[rid], players, slots)
                    if opt > 0:
                        rec[key].append((entries[rid].get("points") or 0) / opt * 100)
    return rec


def league_rank(data, name, key, reverse=True):
    agg = defaultdict(list)
    for s in data["seasons"]:
        for m in s["managers"].values():
            agg[m["display_name"]].append(m[key])
    avg = {k: sum(v) / len(v) for k, v in agg.items()}
    order = sorted(avg, key=lambda k: -avg[k] if reverse else avg[k])
    return order.index(name) + 1, len(order)


def render(p, data, h2h, me):
    print("\n" + "=" * 74)
    print(f"  {p['name'].upper()}   ({p['n']} seasons)")
    print("=" * 74)
    print(f"  record {p['w']}-{p['l']}   expected {p['exp']:.1f} wins   "
          f"luck {p['luck']:+.1f}   points {p['pf']:.0f}")
    er, en = league_rank(data, p["name"], "efficiency")
    print(f"  lineup efficiency {p['eff']:.1f}%  (#{er} of {en})   "
          f"points benched {p['bench']:.0f}")
    print(f"  draft surplus {p['surplus']:+.1f} slots per pick")
    print(f"  waivers: {p['adds']} adds, {p['lost']} claims lost, "
          f"{p['add_pts']:.0f} pts started "
          f"({p['add_pts']/max(1,p['adds']):.1f} per add)")

    print(f"\n  season by season")
    print(f"    {'yr':<6}{'rec':>7}{'exp':>7}{'luck':>7}{'PF':>8}{'eff':>8}{'bench':>8}")
    for x in p["seasons"]:
        print(f"    {x['season']:<6}{str(x['w'])+'-'+str(x['l']):>7}{x['exp']:>7.1f}"
              f"{x['luck']:>+7.1f}{x['pf']:>8.0f}{x['eff']:>7.1f}%{x['bench']:>8.0f}")

    print(f"\n  draft shape (share of their picks by position)")
    print(f"    {'rounds':<9}" + "".join(f"{k:>7}" for k in POS))
    for label, _, _ in ROUND_BUCKETS:
        print(f"    {label:<9}" + "".join(f"{p['shape'][label][k]:>6}%" for k in POS))
    print(f"    first taken (avg round): " +
          "   ".join(f"{k} {v}" for k, v in sorted(p["first_round"].items())))
    if p["best_pick"]:
        b, w = p["best_pick"], p["worst_pick"]
        print(f"    best  {b['player']} ({b['season']}, pick {b['pick_no']}, "
              f"finished #{b['value_rank']})")
        print(f"    worst {w['player']} ({w['season']}, pick {w['pick_no']}, "
              f"finished #{w['value_rank']})")

    print(f"\n  trades ({len(p['trades'])})")
    for t in p["trades"]:
        other = [r for r in t["rosters"] if r != p["name"]]
        print(f"    {t['season']} wk{t['week']:<3} with {', '.join(other)}")
    if not p["trades"]:
        print("    none")

    e = sum(h2h["eff"]) / len(h2h["eff"]) if h2h["eff"] else 0
    # h2h["w"] counts the SCOUTED manager's wins, so state who leads rather
    # than assuming -- a fixed "in your favour" label lies half the time.
    lead = ("you lead" if h2h["l"] > h2h["w"] else
            "they lead" if h2h["w"] > h2h["l"] else "level")
    print(f"\n  head to head vs {me}")
    print(f"    you {h2h['l']}-{h2h['w']} ({lead})   "
          f"their points {h2h['pf']:.0f} vs your {h2h['pa']:.0f}")
    print(f"    their lineup efficiency in those games: {e:.1f}% "
          f"(their overall {p['eff']:.1f}%)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("managers", nargs="+", help="display names to scout")
    args = ap.parse_args()

    index, seasons, players = load_all()
    data = json.loads((RAW.parent / "analysis.json").read_text(encoding="utf-8"))
    me = data["username"]
    known = {m["display_name"] for s in data["seasons"]
             for m in s["managers"].values()}

    for name in args.managers:
        match = next((k for k in known if k.lower() == name.lower()), None)
        if not match:
            print(f"\nNo manager '{name}'. Known: {', '.join(sorted(known))}")
            continue
        p = profile(data, seasons, players, match, me)
        render(p, data, head_to_head(seasons, players, match, me), me)


if __name__ == "__main__":
    main()
