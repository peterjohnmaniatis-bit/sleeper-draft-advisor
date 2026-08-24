#!/usr/bin/env python3
"""ADP -- what the market charges for a player, as opposed to what he is worth.

    python adp.py --season 2026            # the market board
    python adp.py --calibrate              # refit the error model on real drafts

The value board answers "who is best". It cannot answer "who will still be
there when I pick again", because it only knows our own ranking. A player we
rate third at his position is not scarce if the rest of the world rates him
thirtieth -- he will sit there for two more rounds. ADP is the missing axis.

Sleeper ships `adp_ppr` on every player in the season projections file, which
trade.py already downloads. Nothing read it until now.

The error model is fitted, not assumed. Every non-keeper pick from this
league's five completed drafts is matched to that season's preseason ADP, and
the spread of (actual pick - ADP) is measured in bands. See BANDS below.
"""

import argparse
import glob
import json
import math
import statistics
import sys
from pathlib import Path

from model import RAW, Players, _load

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Measured on 900 real picks across 2021-2025. Each row is
# (max ADP of the band, mean(actual - adp), sd(actual - adp)).
#
# Two things this table says that matter on draft night. The mean is ~0 through
# ADP 120, so the market is UNBIASED here for ten rounds -- ADP can be taken at
# face value. From 121 on the mean goes to -6: this league reaches by about six
# picks in the back half, so a late-round target goes earlier than the national
# number implies. And the spread widens from under two picks in round one to
# sixteen by round eleven, which is why a single ADP number should never be read
# as a deadline.
BANDS = [
    (12,   -0.2,   1.7),
    (24,    0.3,   4.6),
    (48,   -0.1,   5.7),
    (84,    0.4,   8.1),
    (120,   1.6,  12.9),
    (200,  -6.0,  15.9),
]
# Past ADP ~200 the relationship falls apart entirely (measured mean -102.9 on
# 22 picks): those are sleepers taken on conviction, where ADP carries no
# information. Rather than extrapolate a fitted line into noise, availability is
# simply reported as unknown out there.
ADP_HORIZON = 200


def load(season, refresh=False):
    """player_id -> average draft position (PPR). Reads the file trade.py
    already caches, so this adds no network call on draft night."""
    dest = RAW / f"projections_{season}_season.json"
    if not dest.exists():
        from trade import season_projections
        season_projections(season, refresh)
    rows = json.loads(dest.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = {}
    for r in rows:
        pid = str(r.get("player_id") or "")
        a = (r.get("stats") or {}).get("adp_ppr")
        if pid and a is not None:
            out[pid] = float(a)
    return out


def _band(adp):
    for hi, bias, sd in BANDS:
        if adp <= hi:
            return bias, sd
    return BANDS[-1][1], BANDS[-1][2]


def _phi(z):
    """Standard normal CDF via erf -- no scipy, and none needed."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def survival(adp, pick_no):
    """P(this player is still on the board when pick `pick_no` comes round).

    Models the pick he actually goes at as normal around his ADP, using the
    bias and spread measured from this league's own drafts. Returns None past
    the horizon, where ADP stops meaning anything -- None is rendered as "?"
    rather than as a number, because a fabricated 50% reads as knowledge.
    """
    if adp is None or adp > ADP_HORIZON:
        return None
    bias, sd = _band(adp)
    expected = adp + bias
    # P(goes after this pick). Continuity correction: a player taken exactly at
    # pick_no is gone, not available.
    return 1.0 - _phi((pick_no + 0.5 - expected) / sd)


def gap(adp, board_rank):
    """How far the market is behind our own board. Positive means the market
    rates him LOWER than we do, so he can be had later than his value implies;
    negative means he goes before we would rank him."""
    if adp is None or board_rank is None:
        return None
    return adp - board_rank


def calibrate(verbose=True):
    """Refit BANDS from the cached drafts. Run after a season completes."""
    pl = Players()
    pairs = []
    index = _load("index.json") or {}
    for s in index.get("seasons", []):
        yr = s["season"]
        f = RAW / f"projections_{yr}_season.json"
        files = sorted(glob.glob(str(RAW / yr / "draft_*_picks.json")))
        if not f.exists() or not files:
            continue
        am = load(yr)
        picks = json.loads(Path(files[0]).read_text(encoding="utf-8"))
        if not picks or any(p.get("pick_no") is None for p in picks):
            continue
        for p in picks:
            if p.get("is_keeper"):
                continue
            pid = str(p.get("player_id") or "")
            if pid in am:
                pairs.append((am[pid], p["pick_no"]))
    if verbose:
        print(f"{len(pairs)} non-keeper picks matched to a preseason ADP\n")
        print("   ADP band      n     bias      sd")
        lo = 0
        for hi, _, _ in BANDS:
            e = [act - a for a, act in pairs if lo < a <= hi]
            if e:
                print(f"  {lo+1:>4}-{hi:<5}{len(e):>6}{statistics.fmean(e):>9.1f}"
                      f"{statistics.pstdev(e):>8.1f}")
            lo = hi
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--calibrate", action="store_true",
                    help="refit the error bands on completed drafts")
    ap.add_argument("--pick", type=int, help="show survival to this pick number")
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()

    if a.calibrate:
        calibrate()
        return

    pl = Players()
    m = load(a.season)
    rows = sorted(((v, k) for k, v in m.items() if pl.position(k) in
                   ("QB", "RB", "WR", "TE")), key=lambda x: x[0])[:a.top]
    hdr = f"  {'adp':>6}  {'pos':<4}{'player':<26}"
    if a.pick:
        hdr += f"{'still there at ' + str(a.pick):>18}"
    print(f"{a.season} market board\n")
    print(hdr)
    for adp, pid in rows:
        line = f"  {adp:>6.1f}  {pl.position(pid):<4}{pl.name(pid)[:24]:<26}"
        if a.pick:
            s = survival(adp, a.pick)
            line += f"{('?' if s is None else format(s * 100, '.0f') + '%'):>18}"
        print(line)


if __name__ == "__main__":
    main()
