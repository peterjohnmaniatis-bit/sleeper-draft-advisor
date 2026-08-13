#!/usr/bin/env python3
"""Price both sides of a proposed trade in this league's own terms.

    python trade.py --give "Chase" --get "Bijan, London"
    python trade.py --with <their-sleeper-handle> --give "Chase" --get "Bijan"

Without --with, players are priced on value over replacement alone. With it,
the tool also reports what each roster actually gains once lineups are refilled,
which is the number that decides whether a trade helps both sides.

Projections come from a Sleeper endpoint that is NOT in their public docs. It
works today and could vanish without notice; this tool degrades to an error
rather than silently guessing.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from analyze import optimal_lineup
from model import RAW, Players, Season, _load, replacement_ranks

ROOT = Path(__file__).resolve().parent

# Fallback only, for a 12-team league with two flex spots. Real values come
# from model.replacement_ranks(), computed from the league's own settings.
REPLACEMENT_RANK = {"QB": 12, "RB": 30, "WR": 36, "TE": 15}

# A bench player only matters on byes and injuries, so surplus there is
# discounted rather than counted at face value.
BENCH_WEIGHT = 0.25

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def season_projections(season, refresh=False):
    """Season-long PPR projections, cached for a day. player_id -> points."""
    dest = RAW / f"projections_{season}_season.json"
    fresh = dest.exists() and (time.time() - dest.stat().st_mtime) < 86400
    if not fresh or refresh:
        url = (f"https://api.sleeper.com/projections/nfl/{season}"
               f"?season_type=regular&grouping=season")
        req = urllib.request.Request(url, headers={"User-Agent": "fantasy-analyzer/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            if dest.exists():
                print(f"  ! projection fetch failed ({err}); using cached copy")
            else:
                raise SystemExit(
                    f"Could not reach Sleeper's projection endpoint ({err}).\n"
                    "It is undocumented and may have been withdrawn. Without it "
                    "this tool cannot price a trade.")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(raw), encoding="utf-8")

    out = {}
    for row in json.loads(dest.read_text(encoding="utf-8")):
        pid = str(row.get("player_id") or "")
        pts = ((row.get("stats") or {}).get("pts_ppr")) or 0.0
        if pid and pts:
            out[pid] = float(pts)
    return out


def replacement_levels(proj, players, ranks=None):
    """What a freely available starter is worth at each position this year.

    `ranks` lets a caller widen the position set -- the draft advisor needs K
    and DEF on its board, which are irrelevant to trade valuation.
    """
    ranks = ranks or REPLACEMENT_RANK
    by_pos = {}
    for pid, pts in proj.items():
        pos = players.position(pid)
        if pos in ranks:
            by_pos.setdefault(pos, []).append(pts)
    levels = {}
    for pos, rank in ranks.items():
        vals = sorted(by_pos.get(pos, []), reverse=True)
        levels[pos] = vals[rank - 1] if len(vals) >= rank else (vals[-1] if vals else 0.0)
    return levels


def build_index(players, proj, ranks=None):
    """Name -> player_id, limited to players carrying a projection."""
    ranks = ranks or REPLACEMENT_RANK
    index = {}
    for pid in proj:
        info = players.by_id.get(pid)
        if not info or info.get("position") not in ranks:
            continue
        key = re.sub(r"[^a-z ]", "", info["name"].lower())
        index.setdefault(key, []).append(pid)
    return index


def resolve(name, index, players, proj):
    """Match a typed name to one player, or explain the ambiguity."""
    q = re.sub(r"[^a-z ]", "", name.strip().lower())
    if not q:
        return None
    hits = index.get(q)
    if not hits:
        hits = [p for k, v in index.items() if q in k for p in v]
    if not hits:
        raise SystemExit(f"No projected player matches '{name}'.")
    if len(hits) > 1:
        # Prefer the highest projection -- typing "Chase" means Ja'Marr, not a
        # third-string namesake -- but say so when the call was close.
        hits.sort(key=lambda p: -proj.get(p, 0))
        top, second = proj.get(hits[0], 0), proj.get(hits[1], 0)
        if second > top * 0.6:
            opts = ", ".join(f"{players.name(p)} ({proj.get(p,0):.0f})" for p in hits[:5])
            raise SystemExit(f"'{name}' is ambiguous: {opts}. Be more specific.")
    return hits[0]


def roster_strength(pids, proj, slots, players, levels):
    """Projected value of a roster: its best legal lineup, plus discounted
    surplus on the bench. Reuses the lineup optimiser the reports already use."""
    entry = {"players": list(pids), "players_points": {p: proj.get(p, 0.0) for p in pids}}
    starters_pts, chosen = optimal_lineup(entry, players, slots)
    used = {c["player_id"] for c in chosen}
    bench = sum(max(0.0, proj.get(p, 0.0) - levels.get(players.position(p), 0.0))
                for p in pids if p not in used)
    return starters_pts + BENCH_WEIGHT * bench


def side_table(label, pids, proj, players, levels, surplus=0):
    """Print one side of the trade. `surplus` is how many of these players are
    extra bodies relative to the other side -- in a 2-for-1 the receiving team
    must still field one lineup, so the least valuable extras are discounted
    rather than counted at face value."""
    print(f"\n  {label}")
    print(f"    {'player':<26}{'pos':<5}{'proj':>8}{'VOR':>8}")
    scored = []
    for pid in pids:
        pts = proj.get(pid, 0.0)
        pos = players.position(pid)
        scored.append((pid, pts, pos, pts - levels.get(pos, 0.0)))
    scored.sort(key=lambda x: -x[3])

    discounted = {p for p, _, _, _ in scored[len(scored) - surplus:]} if surplus else set()
    total_p = total_v = 0.0
    for pid, pts, pos, vor in scored:
        mark = ""
        if pid in discounted:
            vor *= BENCH_WEIGHT
            mark = "  bench"
        total_p += pts
        total_v += vor
        print(f"    {players.name(pid)[:25]:<26}{pos:<5}{pts:>8.1f}{vor:>+8.0f}{mark}")
    print(f"    {'':<26}{'':<5}{'-'*8}{'-'*8}")
    print(f"    {'total':<26}{'':<5}{total_p:>8.1f}{total_v:>+8.0f}")
    return total_v


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--give", required=True, help="comma-separated players you send")
    ap.add_argument("--get", required=True, help="comma-separated players you receive")
    ap.add_argument("--with", dest="partner", help="the other manager's display name")
    ap.add_argument("--season", default=None, help="defaults to the newest cached season")
    ap.add_argument("--refresh", action="store_true", help="re-fetch projections")
    args = ap.parse_args()

    index_file = _load("index.json")
    if not index_file:
        raise SystemExit("No data. Run: python pull.py")
    seasons = sorted(s["season"] for s in index_file["seasons"])
    season = args.season or seasons[-1]

    players = Players()
    proj = season_projections(season, args.refresh)
    league = Season(season, next(x["league_id"] for x in index_file["seasons"]
                                 if x["season"] == season))
    ranks = replacement_ranks(league) or REPLACEMENT_RANK
    levels = replacement_levels(proj, players, ranks)
    name_index = build_index(players, proj, ranks)

    give = [resolve(n, name_index, players, proj) for n in args.give.split(",") if n.strip()]
    get = [resolve(n, name_index, players, proj) for n in args.get.split(",") if n.strip()]

    print("=" * 62)
    print(f"  TRADE EVALUATION -- {season} season projections")
    print("  replacement level: " +
          "  ".join(f"{p} {levels[p]:.0f}" for p in sorted(levels)))
    print("=" * 62)

    gap = len(get) - len(give)
    out_v = side_table("YOU GIVE", give, proj, players, levels, max(0, -gap))
    in_v = side_table("YOU GET", get, proj, players, levels, max(0, gap))
    net = in_v - out_v

    print("\n" + "-" * 62)
    if gap:
        bigger = "you" if gap > 0 else "they"
        print(f"  {abs(gap)} extra body to {bigger} -- roster spots are finite, so the")
        print(f"  least valuable {abs(gap)} shown above are discounted to bench weight.")
    print(f"  NET TO YOU{'':<32}{net:>+8.0f} VOR")

    # Roster context, once rosters exist. Pre-draft this is skipped.
    ctx = None
    if args.partner:
        s = league
        mine = next((m for m in s.managers.values()
                     if m["display_name"] == index_file["username"]), None)
        theirs = next((m for m in s.managers.values()
                       if m["display_name"].lower() == args.partner.lower()), None)
        if not theirs:
            raise SystemExit(f"No manager named '{args.partner}' in {season}.")
        rosters = {r["roster_id"]: (r.get("players") or [])
                   for r in (_load(f"{season}/rosters.json") or [])}
        a, b = rosters.get(mine["roster_id"], []), rosters.get(theirs["roster_id"], [])
        if a and b:
            slots = s.starting_slots
            a2 = [p for p in a if p not in give] + get
            b2 = [p for p in b if p not in get] + give
            ctx = (roster_strength(a2, proj, slots, players, levels)
                   - roster_strength(a, proj, slots, players, levels),
                   roster_strength(b2, proj, slots, players, levels)
                   - roster_strength(b, proj, slots, players, levels))
            print(f"\n  LINEUP IMPACT (what each roster actually gains)")
            print(f"    you{'':<39}{ctx[0]:>+8.0f} pts")
            print(f"    {theirs['display_name'][:25]:<42}{ctx[1]:>+8.0f} pts")
        else:
            print(f"\n  (rosters are empty pre-draft -- lineup impact skipped)")

    print("\n  VERDICT")
    if ctx and ctx[0] > 0 and ctx[1] > 0:
        print("    Both rosters improve. This is the kind of trade that should")
        print("    actually get accepted -- each side is fixing a different hole.")
    elif abs(net) < 15:
        print("    Close to even on talent. Fine to make if it fills a need,")
        print("    but neither side is winning it outright.")
    elif net > 0:
        print(f"    Favours you by {net:.0f} points of value over replacement.")
        print("    Expect pushback; consider what you can add to balance it.")
    else:
        print(f"    Favours them by {abs(net):.0f} points of value over replacement.")
        print("    Do not send this without getting something back.")

    print("\n  Note: projections come from an undocumented Sleeper endpoint and")
    print("  are a forecast, not a fact. Treat gaps under ~20 points as noise.")


if __name__ == "__main__":
    main()
