#!/usr/bin/env python3
"""Which weeks your roster falls apart, and how early you can see it coming.

    python byes.py
    python byes.py --me wburnett7

Every bye week is knowable in August and nothing in the toolset surfaced them.
They matter here in two specific ways: a week where you lose two starters is a
week you probably lose, and a bye that lands in weeks 13-14 costs a seeding
game rather than a regular one, because this league's playoffs start in week 15.

Byes are derived from the schedule rather than read from the player file --
Sleeper's player object has no bye field at all. A team is on bye in the week
it does not appear in the fixture list.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import season as season_mod
from model import RAW, Players, _load

ROOT = Path(__file__).resolve().parent
SCHEDULE = "https://api.sleeper.com/schedule/nfl/regular"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def schedule(season, refresh=False):
    """The season's fixtures, cached. Undocumented endpoint, so it degrades to
    whatever is already on disk rather than failing the whole tool."""
    dest = RAW / f"schedule_{season}.json"
    if dest.exists() and not refresh:
        try:
            return json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    req = urllib.request.Request(f"{SCHEDULE}/{season}",
                                 headers={"User-Agent": "ff-analyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as err:
        print(f"  ! schedule unavailable ({type(err).__name__})")
        return []
    if data:
        dest.write_text(json.dumps(data), encoding="utf-8")
    return data


def bye_weeks(season, refresh=False):
    """team -> the week it is idle. Empty if the schedule cannot be had."""
    games = schedule(season, refresh)
    if not games:
        return {}
    playing, teams = defaultdict(set), set()
    for g in games:
        w = g.get("week")
        for side in ("home", "away"):
            t = g.get(side)
            if t:
                playing[w].add(t)
                teams.add(t)
    out = {}
    for t in teams:
        idle = [w for w in sorted(playing) if t not in playing[w]]
        # Exactly one bye is the expected shape; anything else means the
        # fixture list is incomplete and is better reported than guessed at.
        if len(idle) == 1:
            out[t] = idle[0]
    return out


def roster_byes(st, players, rid, byes):
    """week -> the players of one roster who are idle that week."""
    out = defaultdict(list)
    raw = json.loads((RAW / "players_nfl.json").read_text(encoding="utf-8"))
    for pid in st.rosters.get(rid, []):
        team = (raw.get(pid) or {}).get("team")
        w = byes.get(team)
        if w:
            out[w].append({"player_id": pid, "name": players.name(pid),
                           "pos": players.position(pid), "team": team})
    return dict(out)


def starters_lost(week_players, slots):
    """How many of a week's idle players would have started.

    Approximate on purpose: it counts idle players at each starting position up
    to the number of slots, which is the question that matters -- how many
    holes am I filling -- without pretending to solve the lineup.
    """
    need = defaultdict(int)
    for s in slots:
        need[s] += 1
    flex = need.pop("FLEX", 0)
    idle = defaultdict(int)
    for p in week_players:
        idle[p["pos"]] += 1
    holes = 0
    spare = 0
    for pos, n in idle.items():
        starting = min(n, need.get(pos, 0))
        holes += starting
        spare += n - starting
    holes += min(spare, flex)
    return holes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season")
    ap.add_argument("--me", help="manager display name; defaults to you")
    ap.add_argument("--all", action="store_true", help="every manager's worst weeks")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    st = season_mod.load(season=a.season)
    players = Players()
    byes = bye_weeks(st.season, a.refresh)
    if not byes:
        raise SystemExit("No schedule cached, so byes cannot be derived.")

    idx = _load("index.json") or {}
    who = a.me or idx.get("username")
    playoff = st.playoff_start

    def report(rid, name):
        weeks = roster_byes(st, players, rid, byes)
        slots = st.roster_slots()
        rows = []
        for w in sorted(weeks):
            holes = starters_lost(weeks[w], slots)
            rows.append((w, holes, weeks[w]))
        return rows

    if a.all:
        print(f"{st.season} bye exposure, worst weeks per manager\n")
        for rid, m in st.s.managers.items():
            rows = report(rid, m["display_name"])
            worst = sorted(rows, key=lambda r: -r[1])[:2]
            s = ", ".join(f"wk{w} lose {h}" for w, h, _ in worst if h)
            print(f"  {m['display_name'][:20]:<22}{s or 'nothing severe'}")
        return

    rid = next((r for r, m in st.s.managers.items()
                if m["display_name"] == who), None)
    if rid is None:
        raise SystemExit(f"No manager called {who!r} in this league.")

    rows = report(rid, who)
    print(f"{st.season} bye weeks for {who}  "
          f"(playoffs start week {playoff})\n")
    print(f"  {'wk':<5}{'starters lost':<16}players")
    for w, holes, plist in rows:
        tag = f"{holes}" if holes else "-"
        names = ", ".join(f"{p['name']} ({p['pos']})" for p in plist)
        flag = ""
        if w >= playoff:
            flag = "  <- PLAYOFF WEEK"
        elif w == playoff - 1:
            flag = "  <- final seeding week"
        print(f"  {w:<5}{tag:<16}{names}{flag}")

    worst = max((h for _, h, _ in rows), default=0)
    if worst >= 2:
        bad = [w for w, h, _ in rows if h == worst]
        print(f"\n  Worst: week {', '.join(map(str, bad))}, losing {worst} "
              f"starters. Cover it before it arrives, not during.")
    counts = defaultdict(int)
    for _, _, plist in rows:
        for p in plist:
            counts[p["pos"]] += 1
    thin = [p for p in ("QB", "TE") if counts.get(p)]
    for p in thin:
        held = sum(1 for pid in st.rosters.get(rid, [])
                   if players.position(pid) == p)
        if held <= 1:
            w = next(w for w, _, pl in rows if any(x["pos"] == p for x in pl))
            print(f"  You roster one {p} and he is idle in week {w}: that is a "
                  f"guaranteed zero unless you add another.")


if __name__ == "__main__":
    main()
