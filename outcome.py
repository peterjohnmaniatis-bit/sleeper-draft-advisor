#!/usr/bin/env python3
"""How a pick actually turned out, and whether the manager deserves the blame.

    python outcome.py --season 2023

The scorecard grades PROCESS: how far ahead of the market you paid. That is
knowable the second the pick lands and it is the only thing gradeable during a
live draft. For a season that has already happened there is a second question --
did it work -- and the honest answer has to separate two things that look
identical in a box score:

    Justin Jefferson, 2023, drafted 1st overall, finished 97th.
    Bijan Robinson,   2023, drafted 7th overall, finished 34th.

Jefferson played ten games and was excellent in all of them. Robinson played
seventeen and was not. Charging a manager for the first is charging him for a
hamstring; charging him for the second is charging him for being wrong.

WHAT THIS CANNOT DO. Games played does not say WHY a player was absent. A
holdout, a benching and a torn ACL are the same number here. That is why
availability alone never excuses a pick -- it has to be paired with the player
producing when he WAS on the field. A player who lost his job because he was
bad shows up as few games AND poor per-game production, and is correctly still
blamed. The residual error is a player who was genuinely benched while playing
well, which is rare and which this will wrongly forgive.
"""

import argparse
import json
import sys
from pathlib import Path

from model import RAW, Players

ROOT = Path(__file__).resolve().parent

# Below this share of the season's games, a pick is a candidate for forgiveness.
AVAILABLE = 0.75
# ...but only if he was still producing at this share of his expected rate.
PRODUCING = 0.75
# Except this far down, where the production test itself becomes unusable.
# Aaron Rodgers tore his Achilles four snaps into 2023: one game, zero points,
# a per-game rate of 0.00, and the rule above blamed the manager for it. Nobody
# who plays a twentieth of a season has produced a judgeable sample. This
# knowingly forgives the rare healthy scratch -- Rashaad Penny, three games,
# genuinely benched -- which is the cheaper of the two mistakes.
UNJUDGEABLE = 0.30

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def games_played(season, through=18):
    """player_id -> weeks he was actually on the field.

    Counted from snaps and touches, never from points: a defence scores every
    week whether or not any human being is healthy, and a kicker who is quietly
    replaced still puts up numbers under the new man's id.
    """
    out = {}
    for wk in range(1, through + 1):
        f = RAW / "stats" / str(season) / f"{wk:02d}.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for pid, st in data.items():
            if not isinstance(st, dict):
                continue
            if ((st.get("off_snp") or 0) > 0 or (st.get("rec_tgt") or 0) > 0
                    or (st.get("rush_att") or 0) > 0
                    or (st.get("pass_att") or 0) > 0):
                out[pid] = out.get(pid, 0) + 1
    return out


def season_length(games):
    """The most games anyone managed, which is the season's real length."""
    return max(games.values(), default=17) or 17


def judge(pick, played, full):
    """Did it work, and is the manager answerable for it?

    Returns a dict, or None when there is nothing to judge (no outcome data).
    `blame` is False when the pick failed but the player was producing whenever
    he was available -- the shape of an injury rather than of a bad read.
    """
    pts, sur = pick.get("points"), pick.get("surplus")
    rank, pick_no = pick.get("value_rank"), pick.get("pick_no")
    if pts is None or sur is None or rank is None or not pick_no:
        return None

    # What the pick was supposed to return, recovered from the surplus.
    expected = pts - sur
    g = max(0, played)
    availability = g / full if full else 0.0
    ppg = (pts / g) if g else 0.0
    exp_ppg = (expected / full) if full else 0.0
    rate = (ppg / exp_ppg) if exp_ppg > 0 else 1.0

    # Finishing far below where he was taken is the failure; how far is the
    # size of it. Positive = fell short.
    miss = rank - pick_no

    shaded = miss > 0 and (
        availability <= UNJUDGEABLE
        or (availability < AVAILABLE and rate >= PRODUCING))
    return {
        "games": g, "full": full,
        "availability": round(availability, 2),
        "ppg": round(ppg, 1), "exp_ppg": round(exp_ppg, 1),
        "rate": round(rate, 2),
        "finished": rank, "miss": miss,
        "blame": not shaded,
        "shaded": shaded,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", required=True)
    ap.add_argument("--top", type=int, default=18)
    a = ap.parse_args()

    analysis = json.loads((ROOT / "data" / "analysis.json").read_text(encoding="utf-8"))
    yr = next(s for s in analysis["seasons"] if s["season"] == a.season)
    import glob
    files = sorted(glob.glob(str(RAW / a.season / "draft_*_picks.json")))
    ids = {p["pick_no"]: str(p.get("player_id") or "")
           for p in json.loads(Path(files[0]).read_text(encoding="utf-8"))
           if p.get("pick_no")}
    played = games_played(a.season)
    full = season_length(played)

    rows = []
    for p in yr["draft"]:
        j = judge(p, played.get(ids.get(p["pick_no"], ""), 0), full)
        if j:
            rows.append((p, j))
    rows.sort(key=lambda r: -r[1]["miss"])

    print(f"{a.season}: season length {full} games\n")
    print(f"  {'player':<24}{'pick':>5}{'fin':>5}{'gms':>5}{'ppg':>7}{'exp':>7}"
          f"{'rate':>7}  verdict")
    for p, j in rows[:a.top]:
        v = "INJURY-SHADED" if j["shaded"] else "blamed"
        print(f"  {p['player'][:22]:<24}{p['pick_no']:>5}{j['finished']:>5}"
              f"{j['games']:>5}{j['ppg']:>7.1f}{j['exp_ppg']:>7.1f}"
              f"{j['rate']:>7.2f}  {v}")
    n = sum(1 for _, j in rows if j["shaded"])
    print(f"\n  {n} of {len(rows)} picks shaded as unavailable-but-producing")


if __name__ == "__main__":
    main()
