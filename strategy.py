#!/usr/bin/env python3
"""Draft-strategy analysis: what actually wins in this specific league.

Classifies every manager-season against the common named draft strategies,
then measures the league itself -- positional scarcity in its own scoring,
when positions leave the board, what waivers can actually replace, and which
phase of the season correlates with winning.

    python strategy.py      # writes data/strategy.json + a console summary
"""

import json
import sys
from collections import defaultdict

from model import RAW, load_all
from analyze import player_season_points

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POS = ("QB", "RB", "WR", "TE")

# Replacement level = the last player at each position who still starts once
# all 12 teams fill QB/RB/RB/WR/WR/TE/FLEX/FLEX. The two flex slots push RB
# and WR replacement much deeper than their base requirement.
REPLACEMENT = {"QB": 12, "RB": 30, "WR": 36, "TE": 15}


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(num / (dx * dy), 3) if dx and dy else 0.0


def classify_draft(picks):
    """Label one manager-season against the common named strategies."""
    by_round = defaultdict(list)
    for p in picks:
        by_round[p["round"]].append(p["position"])

    def first(pos):
        return next((r for r in sorted(by_round) if pos in by_round[r]), 99)

    def count_through(pos, r_max):
        return sum(1 for r in range(1, r_max + 1)
                   for x in by_round.get(r, []) if x == pos)

    rb1, rb3, rb5 = first("RB"), count_through("RB", 3), count_through("RB", 5)
    qb1, te1 = first("QB"), first("TE")

    if rb5 == 0:
        rb_plan = "Zero RB"
    elif rb3 >= 2:
        rb_plan = "Robust RB"
    elif rb1 <= 2 and rb5 <= 1:
        rb_plan = "Hero RB"
    else:
        rb_plan = "Balanced"

    return {
        "rb_plan": rb_plan,
        "qb_plan": "Early QB" if qb1 <= 4 else ("Mid QB" if qb1 <= 7 else "Late QB"),
        "te_plan": "Elite TE" if te1 <= 3 else ("Mid TE" if te1 <= 7 else "Late TE"),
        "first_qb_round": qb1,
        "opening": "-".join(by_round.get(r, ["--"])[0] for r in range(1, 6)),
    }


def scarcity(seasons, players):
    """Season points by positional rank, averaged across seasons.

    Reconstructed from weekly league scoring, so a player only accrues points
    while someone rosters him. The replacement ranks below are all comfortably
    inside the rostered pool; ranks far past them read artificially low.
    """
    ranks = (1, 3, 6, 12, 18, 24, 30, 36, 48)
    acc = {p: defaultdict(list) for p in POS}
    for s in seasons:
        totals = player_season_points(s)
        by_pos = defaultdict(list)
        for pid, pts in totals.items():
            if players.position(pid) in POS:
                by_pos[players.position(pid)].append(pts)
        for pos, vals in by_pos.items():
            vals.sort(reverse=True)
            for r in ranks:
                if len(vals) >= r:
                    acc[pos][r].append(vals[r - 1])

    curves = {p: {r: round(sum(v) / len(v), 1) for r, v in acc[p].items()} for p in POS}
    vor = {}
    for p in POS:
        repl_rank = REPLACEMENT[p]
        nearest = max(r for r in curves[p] if r <= repl_rank)
        vor[p] = {
            "top6": curves[p][6],
            "replacement": curves[p][nearest],
            "replacement_rank": repl_rank,
            "vor": round(curves[p][6] - curves[p][nearest], 1),
        }
    return {"ranks": list(ranks), "curves": curves, "vor": vor}


def draft_timing(data):
    """When each position leaves the board, from this league's own drafts."""
    picks, mix = defaultdict(list), defaultdict(lambda: defaultdict(int))
    for s in data["seasons"]:
        for p in s["draft"]:
            if p["position"] in POS:
                picks[p["position"]].append(p["pick_no"])
                mix[p["round"]][p["position"]] += 1

    rounds = []
    for r in range(1, 11):
        total = sum(mix[r].values()) or 1
        rounds.append({"round": r,
                       **{p: round(mix[r][p] / total * 100, 1) for p in POS}})
    median = {p: sorted(v)[len(v) // 2] for p, v in picks.items()}
    counts = {p: len(v) for p, v in picks.items()}
    return {"round_mix": rounds, "median_pick": median, "counts": counts}


def waiver_value(data):
    """What a mid-season add is actually worth, by position."""
    acc = defaultdict(lambda: {"adds": 0, "points": 0.0, "hits": 0})
    for s in data["seasons"]:
        for a in s["acquisitions"]:
            if a["position"] in POS:
                d = acc[a["position"]]
                d["adds"] += 1
                d["points"] += a["started_points"]
                if a["started_points"] >= 50:
                    d["hits"] += 1
    return {p: {"adds": d["adds"],
                "per_add": round(d["points"] / d["adds"], 1) if d["adds"] else 0,
                "hit_rate": round(d["hits"] / d["adds"] * 100, 1) if d["adds"] else 0}
            for p, d in acc.items()}


def what_correlates(data):
    """Which phase of the season tracks winning, across every manager-season."""
    early = defaultdict(float)
    for s in data["seasons"]:
        for p in s["draft"]:
            if p["round"] <= 5:
                early[(s["season"], p["manager"])] += p["points"]

    wins, pf, cols = [], [], defaultdict(list)
    for s in data["seasons"]:
        for m in s["managers"].values():
            wins.append(m["w"])
            pf.append(m["pf"])
            cols["draft"].append(early[(s["season"], m["display_name"])])
            cols["waivers"].append(m["acquired_started_points"])
            cols["efficiency"].append(m["efficiency"])
            cols["luck"].append(m["luck"])

    corr = {k: {"vs_wins": pearson(v, wins), "vs_points": pearson(v, pf)}
            for k, v in cols.items()}

    groups = {"top": [], "bottom": []}
    for s in data["seasons"]:
        ranked = sorted(s["managers"].values(), key=lambda m: (-m["w"], -m["pf"]))
        groups["top"] += ranked[:4]
        groups["bottom"] += ranked[-4:]
    summary = {}
    for label, grp in groups.items():
        n = len(grp)
        summary[label] = {
            "efficiency": round(sum(m["efficiency"] for m in grp) / n, 1),
            "adds": round(sum(m["waiver_adds"] + m["free_agent_adds"] for m in grp) / n, 1),
            "waiver_points": round(sum(m["acquired_started_points"] for m in grp) / n),
            "luck": round(sum(m["luck"] for m in grp) / n, 1),
        }
    return {"correlations": corr, "top_vs_bottom": summary, "n": len(wins)}


def main():
    index, seasons, players = load_all()
    data = json.loads((RAW.parent / "analysis.json").read_text(encoding="utf-8"))
    me = data["username"]

    your_drafts, all_drafts = [], []
    for s in data["seasons"]:
        by_mgr = defaultdict(list)
        for p in s["draft"]:
            by_mgr[p["manager"]].append(p)
        for mgr, picks in by_mgr.items():
            picks.sort(key=lambda p: p["pick_no"])
            m = next(x for x in s["managers"].values() if x["display_name"] == mgr)
            row = {
                "season": s["season"], "manager": mgr, "slot": picks[0]["pick_no"],
                **classify_draft(picks),
                "top5_points": round(sum(p["points"] for p in picks[:5]), 1),
                "top5_hits": sum(1 for p in picks[:5] if p["value_rank"] <= 24),
                "surplus": round(sum(p["surplus"] for p in picks) / len(picks), 1),
                "w": m["w"], "l": m["l"], "pf": m["pf"],
            }
            all_drafts.append(row)
            if mgr == me:
                your_drafts.append(row)

    result = {
        "username": me,
        "seasons": [s["season"] for s in data["seasons"]],
        "your_drafts": sorted(your_drafts, key=lambda r: r["season"]),
        "all_drafts": all_drafts,
        "scarcity": scarcity(seasons, players),
        "timing": draft_timing(data),
        "waivers": waiver_value(data),
        **what_correlates(data),
    }

    out = RAW.parent / "strategy.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {out}")

    v = result["scarcity"]["vor"]
    print("\n  VOR (top-6 minus replacement):  " +
          "   ".join(f"{p} {v[p]['vor']:.0f}" for p in POS))
    w = result["waivers"]
    print("  waiver hit rate:                " +
          "   ".join(f"{p} {w[p]['hit_rate']:.0f}%" for p in POS))
    c = result["correlations"]
    print("  correlation with wins:          " +
          "   ".join(f"{k} {c[k]['vs_wins']:+.2f}" for k in ("draft", "efficiency", "waivers")))


if __name__ == "__main__":
    main()
