#!/usr/bin/env python3
"""Weekly usage: how a player is actually used, not just what he scored.

    python usage.py --season 2025 --through 10
    python usage.py --season 2025 --through 10 --pos WR --window 4

Snap share, target share, air-yards share and red-zone opportunity, computed
from Sleeper's weekly stats. Volume is far steadier week to week than fantasy
points, which is why usage is the better waiver and start/sit signal.

The stats endpoint is NOT in Sleeper's public docs -- it was withdrawn at their
data provider's request -- so it may change without notice. Everything caches
locally and degrades to whatever weeks it already holds.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

from model import RAW, Players

STATS = "https://api.sleeper.app/v1/stats/nfl/regular"
SKILL = ("QB", "RB", "WR", "TE")
THROTTLE = 0.1

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def week_stats(season, week, refresh=False):
    """One week of league-wide player stats, cached on disk."""
    dest = RAW / "stats" / str(season) / f"{week:02d}.json"
    if dest.exists() and not refresh:
        try:
            return json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    req = urllib.request.Request(f"{STATS}/{season}/{week}",
                                 headers={"User-Agent": "ff-analyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as err:
        print(f"  ! week {week} stats: {type(err).__name__} -- skipped")
        return {}
    time.sleep(THROTTLE)
    if not data:
        # Never cache an empty payload. Doing so makes one transient failure
        # permanent -- the week silently vanishes from usage on every later run
        # and nothing ever refetches it.
        print(f"  ! week {week} stats: empty response -- not cached")
        return {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data), encoding="utf-8")
    return data


def week_teams(season, week, refresh=False):
    """player_id -> the team he played for THAT week.

    Necessary, not incidental. The stats rows carry no team at all, and the
    player file only knows where everyone plays *now* -- so grouping a past
    season by it puts A.J. Brown on New England and computes every team share
    against the wrong denominator. The projections endpoint is per-season and
    does carry team, so it is the honest source for a historical week.
    """
    dest = RAW / "teams" / str(season) / f"{week:02d}.json"
    if dest.exists() and not refresh:
        try:
            return json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    url = (f"https://api.sleeper.com/projections/nfl/{season}/{week}"
           f"?season_type=regular")
    req = urllib.request.Request(url, headers={"User-Agent": "ff-analyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            rows = json.loads(r.read())
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as err:
        print(f"  ! week {week} teams: {type(err).__name__} -- week dropped")
        return {}
    time.sleep(THROTTLE)
    out = {}
    for row in rows or []:
        pid = str(row.get("player_id") or "")
        tm = row.get("team") or (row.get("player") or {}).get("team")
        if pid and tm:
            out[pid] = tm
    if not out:
        print(f"  ! week {week} teams: empty -- week dropped, not cached")
        return {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out), encoding="utf-8")
    return out


def load_weeks(season, through, refresh=False):
    """Returns {week: (stats, player_id -> team)}.

    A week with no team map is dropped rather than kept, because without it
    every share for that week would be computed against a missing denominator.
    Dropping is loud -- week_teams prints -- so a hole is visible rather than
    quietly shrinking the sample.
    """
    out = {}
    for wk in range(1, through + 1):
        s = week_stats(season, wk, refresh)
        if not s:
            continue
        teams = week_teams(season, wk, refresh)
        if teams:
            out[wk] = (s, teams)
    return out


def _num(d, key):
    try:
        return float(d.get(key))
    except (TypeError, ValueError):
        return 0.0


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


SHARE_KEYS = ("snap", "tgt_sh", "touch_sh", "air_sh", "rz_sh", "air_per_catch")
COUNT_KEYS = ("tgt", "car", "rz", "pts")


def usage(season, through, players, window=4, refresh=False):
    """Per-player usage shares over the last `window` weeks and the season.

    Every share is measured against that player's OWN team's totals in the same
    week, so a bye or a missed game cannot dilute it -- only weeks he actually
    played count toward an average.
    """
    weeks = load_weeks(season, through, refresh)
    if not weeks:
        return {}, []

    team_tot = defaultdict(lambda: defaultdict(float))
    for wk, (stats, teams) in weeks.items():
        for pid, s in stats.items():
            if not isinstance(s, dict):
                continue
            info = players.by_id.get(pid)
            tm = teams.get(pid)
            if not info or info.get("position") not in SKILL or not tm:
                continue
            t = team_tot[(wk, tm)]
            t["tgt"] += _num(s, "rec_tgt")
            t["car"] += _num(s, "rush_att")
            # Air yards can be negative on a behind-the-line catch. Left signed,
            # the team denominator shrinks and shares run negative or past 100%.
            t["air"] += max(0.0, _num(s, "rec_air_yd"))
            t["rz"] += _num(s, "rec_rz_tgt") + _num(s, "rush_rz_att")

    rows = defaultdict(list)
    seen_team = {}
    for wk, (stats, teams) in weeks.items():
        for pid, s in stats.items():
            if not isinstance(s, dict):
                continue
            info = players.by_id.get(pid)
            tm = teams.get(pid)
            if not info or info.get("position") not in SKILL or not tm:
                continue
            seen_team[pid] = tm
            t = team_tot[(wk, tm)]
            tgt, car = _num(s, "rec_tgt"), _num(s, "rush_att")
            snaps, tm_snaps = _num(s, "off_snp"), _num(s, "tm_off_snp")
            if snaps <= 0 and tgt <= 0 and car <= 0:
                continue                    # did not play; never average this in
            share = lambda n, d: (n / d) if d > 0 else None
            rows[pid].append({
                "wk": wk,
                "snap": share(snaps, tm_snaps),
                "tgt": tgt, "car": car,
                "tgt_sh": share(tgt, t["tgt"]),
                "touch_sh": share(tgt + car, t["tgt"] + t["car"]),
                "air_sh": share(max(0.0, _num(s, "rec_air_yd")), t["air"]),
                # rec_air_yd counts air yards on CATCHES, not on all targets,
                # so dividing by targets mixes depth with catch rate and is not
                # aDOT. Per catch is the only honest reading of this field.
                "air_per_catch": share(_num(s, "rec_air_yd"), _num(s, "rec")),
                "rz": _num(s, "rec_rz_tgt") + _num(s, "rush_rz_att"),
                "rz_sh": share(_num(s, "rec_rz_tgt") + _num(s, "rush_rz_att"), t["rz"]),
                "pts": _num(s, "pts_ppr"),
            })

    last_played_week = max(weeks) if weeks else through
    out = {}
    for pid, played in rows.items():
        played.sort(key=lambda r: r["wk"])
        # The window is CALENDAR weeks, not "his last N appearances". Taking
        # played[-window:] meant a player whose last game was week 4 got his
        # September form shown in the same columns as everyone else's current
        # form -- which put two season-ending injuries at the top of the waiver
        # list. Now a player who has not played recently simply has fewer
        # recent games, and the downstream >= 2 filter drops him.
        recent = [w for w in played if w["wk"] > through - window]
        info = players.by_id.get(pid, {})
        last_wk = played[-1]["wk"]
        rec = {"player_id": pid, "name": info.get("name", pid),
               "pos": info.get("position"), "team": seen_team.get(pid),
               "games": len(played), "recent_games": len(recent),
               "last_week": last_wk, "weeks": [w["wk"] for w in played],
               "weeks_out": max(0, last_played_week - last_wk)}
        for prefix, src in (("", played), ("r_", recent)):
            for k in SHARE_KEYS + COUNT_KEYS:
                rec[prefix + k] = _avg([w[k] for w in src])
        # Is his role growing or shrinking relative to the full season?
        rec["snap_trend"] = (rec["r_snap"] - rec["snap"]
                             if rec["r_snap"] is not None and rec["snap"] is not None
                             and len(played) > len(recent) else None)
        if not recent:                       # no games inside the window at all
            for k in SHARE_KEYS + COUNT_KEYS:
                rec["r_" + k] = None
        out[pid] = rec
    return out, sorted(weeks)


def pct(v, digits=0):
    return "-" if v is None else format(v * 100, "." + str(digits) + "f")


def num(v, digits=1):
    return "-" if v is None else format(v, "." + str(digits) + "f")


def signed(v, digits=0):
    """Never print "-0". A trend of -0.4 points rounds to a minus sign attached
    to nothing, which reads as a decline the number does not support."""
    if v is None:
        return "-"
    out = format(v * 100, "+." + str(digits) + "f")
    return out.replace("-0", "+0") if float(out) == 0 else out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", required=True)
    ap.add_argument("--through", type=int, required=True)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--pos")
    ap.add_argument("--sort", default="r_touch_sh")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    players = Players()
    print(f"loading {args.season} weeks 1-{args.through} ...")
    table, weeks = usage(args.season, args.through, players, args.window, args.refresh)
    if not table:
        raise SystemExit("no weekly stats available for that season")
    print(f"  {len(weeks)} weeks cached, {len(table)} players with usage\n")

    rows = [r for r in table.values()
            if (not args.pos or r["pos"] == args.pos.upper()) and r["recent_games"] >= 2]
    rows.sort(key=lambda r: -(r.get(args.sort) if r.get(args.sort) is not None else -1))

    hdr = ("player", "pos", "tm", "gms", "out", "snap%", "tgt%", "touch%",
           "air%", "rz/g", "air/c", "pts/g", "trend")
    fmt = "  {:<24}{:<4}{:<4}{:>4}{:>5}{:>7}{:>7}{:>8}{:>7}{:>6}{:>6}{:>7}{:>7}"
    print(fmt.format(*hdr))
    for r in rows[:args.top]:
        print(fmt.format(
            r["name"][:22], r["pos"], r["team"] or "-", r["games"],
            r["weeks_out"] or "-",
            pct(r["r_snap"]), pct(r["r_tgt_sh"]), pct(r["r_touch_sh"]),
            pct(r["r_air_sh"]), num(r["r_rz"]), num(r["r_air_per_catch"]),
            num(r["r_pts"]), signed(r["snap_trend"])))


if __name__ == "__main__":
    main()
