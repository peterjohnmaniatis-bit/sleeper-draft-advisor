#!/usr/bin/env python3
"""Five seasons of receipts, per manager, for the live draft scorecard.

    python grudges.py            # -> data/grudges.json
    python grudges.py --show     # print what it found

The scorecard is only worth reading if it is specific. "Bad pick" is noise;
"you reached fourteen picks for a tight end who finished 41st, which is the
third year running you have done exactly this" is not. That sentence needs
history, so this mines it once and caches it.

Identity is keyed on user_id, never on display name -- accounts rename between
seasons (CLAUDE.md trap 2) and grouping by name would split one manager's
record in two and let him off half his own history.
"""

import argparse
import glob
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from adp import load as adp_load
from model import RAW, _load

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "grudges.json"
EARLY_QB_ROUND = 4          # "early" for a position this league overvalues
BIG_REACH = 10              # picks ahead of market before it counts as a reach

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def build():
    analysis = json.loads((ROOT / "data" / "analysis.json").read_text(encoding="utf-8"))
    per = defaultdict(lambda: {
        "name": None, "aka": set(), "picks": 0, "reaches": [], "busts": [],
        "pos_round": defaultdict(list), "early_qb": [], "seasons": set(),
    })

    for season in analysis["seasons"]:
        yr = season["season"]
        adp = adp_load(yr)
        # Match the live draft feed: the cached picks carry player_id, which
        # analysis.json does not, so join on (round, pick_no).
        files = sorted(glob.glob(str(RAW / yr / "draft_*_picks.json")))
        ids = {}
        if files:
            for p in json.loads(Path(files[0]).read_text(encoding="utf-8")):
                if p.get("pick_no"):
                    ids[p["pick_no"]] = str(p.get("player_id") or "")

        for pick in season["draft"]:
            uid = str(pick.get("user_id") or "")
            if not uid:
                continue
            m = per[uid]
            m["name"] = pick["manager"]
            m["aka"].add(pick["manager"])
            m["seasons"].add(yr)
            m["picks"] += 1
            pos, rnd = pick.get("position"), pick.get("round")
            if pos:
                m["pos_round"][pos].append(rnd)
                if pos == "QB" and rnd and rnd <= EARLY_QB_ROUND:
                    m["early_qb"].append({"season": yr, "round": rnd,
                                          "player": pick["player"],
                                          "surplus": pick.get("surplus")})
            a = adp.get(ids.get(pick["pick_no"], ""))
            if a is not None:
                over = round(a - pick["pick_no"], 1)   # +ve = taken early
                rec = {"season": yr, "pick": pick["pick_no"], "round": rnd,
                       "player": pick["player"], "pos": pos,
                       "over": over, "adp": round(a, 1),
                       "surplus": pick.get("surplus"),
                       "finished": pick.get("value_rank")}
                m["reaches"].append(rec)
            # A pick that cost real points, regardless of where it was taken.
            sur = pick.get("surplus")
            if sur is not None and rnd and rnd <= 6 and sur < -40:
                m["busts"].append({"season": yr, "round": rnd,
                                   "player": pick["player"], "pos": pos,
                                   "surplus": sur,
                                   "finished": pick.get("value_rank")})

    league_over = [r["over"] for m in per.values() for r in m["reaches"]]
    league_mean = statistics.fmean(league_over) if league_over else 0.0

    out = {"league_mean_over": round(league_mean, 1), "managers": {}}
    for uid, m in per.items():
        overs = [r["over"] for r in m["reaches"]]
        worst = sorted((r for r in m["reaches"] if r["over"] >= BIG_REACH),
                       key=lambda r: -r["over"])[:6]
        # The ones that both reached AND flopped. This is the good stuff.
        damning = sorted((r for r in m["reaches"]
                          if r["over"] >= BIG_REACH and (r["surplus"] or 0) < -20),
                         key=lambda r: (r["surplus"] or 0))[:6]
        first_qb = {}
        for r in m["reaches"]:
            if r["pos"] == "QB":
                s = r["season"]
                if s not in first_qb or r["round"] < first_qb[s]:
                    first_qb[s] = r["round"]
        # Kept per season so a historical scorecard can rebuild the average
        # from only the seasons that had already happened. Grading the 2025
        # draft while quoting a 2025 flop is a time-travelling insult.
        by_season = defaultdict(list)
        for r in m["reaches"]:
            by_season[r["season"]].append(r["over"])
        out["managers"][uid] = {
            "name": m["name"],
            "overs_by_season": {k: v for k, v in by_season.items()},
            "aka": sorted(x for x in m["aka"] if x != m["name"]),
            "seasons": sorted(m["seasons"]),
            "picks": m["picks"],
            "mean_over": round(statistics.fmean(overs), 1) if overs else None,
            "worst_reaches": worst,
            "damning": damning,
            "busts": sorted(m["busts"], key=lambda b: b["surplus"])[:6],
            "early_qb": m["early_qb"],
            "first_qb_round": first_qb,
            # How early they habitually take each position, as a median round.
            "median_round": {p: int(statistics.median(v))
                             for p, v in m["pos_round"].items() if v},
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    data = build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {OUT}  ({len(data['managers'])} managers, "
          f"league mean over-draft {data['league_mean_over']:+.1f})")
    if a.show:
        for uid, m in sorted(data["managers"].items(),
                             key=lambda kv: -(kv[1]["mean_over"] or 0)):
            print(f"\n  {m['name']}  ({m['picks']} picks, "
                  f"mean {m['mean_over']:+.1f} vs market)")
            for r in m["damning"][:2]:
                print(f"     {r['season']} R{r['round']} {r['player'][:22]:<24}"
                      f" {r['over']:+.0f} early, finished {r['finished']}, "
                      f"surplus {r['surplus']}")
            if m["early_qb"]:
                yrs = ", ".join(f"{q['season']} R{q['round']}" for q in m["early_qb"])
                print(f"     early QB: {yrs}")


if __name__ == "__main__":
    main()
