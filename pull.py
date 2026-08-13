#!/usr/bin/env python3
"""Download and cache this league's full Sleeper history.

Sleeper's API is read-only and unauthenticated, so there are no credentials in
this file and nothing to configure beyond a username. See README.md.

    python pull.py                 # use cache, refresh only in-progress seasons
    python pull.py --refresh       # force a full re-download
    python pull.py --user someone  # a different Sleeper handle
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.sleeper.app/v1"
UA = "fantasy-football-analyzer/1.0 (personal use, low volume)"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"

# Sleeper's documented ceiling is 1000 calls/minute. This keeps us near 700,
# which is polite and still finishes a six-season pull in about a minute.
THROTTLE = 0.085

# Weeks 1-18 covers the regular season and every playoff format the league
# has used. Requests past the end of a season come back empty, which is fine.
WEEKS = range(1, 19)

_calls = 0


def get(path):
    """GET one endpoint. Returns parsed JSON, or None for 404/empty."""
    global _calls
    req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
            _calls += 1
            time.sleep(THROTTLE)
            return json.loads(body) if body else None
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            if err.code == 429:  # rate limited; back off and retry
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return None


def cached(relpath, path, refresh=False):
    """Fetch `path` unless data/raw/`relpath` already holds it."""
    dest = RAW / relpath
    if dest.exists() and not refresh:
        return json.loads(dest.read_text(encoding="utf-8"))
    data = get(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data), encoding="utf-8")
    return data


def league_chain(user_id, season):
    """Every league the user is in this season, each walked back through
    previous_league_id to its first year. Returns a list of chains, newest
    season first within each chain."""
    chains = []
    for league in get(f"user/{user_id}/leagues/nfl/{season}") or []:
        chain, node = [], league
        while node:
            chain.append(node)
            prev = node.get("previous_league_id")
            if not prev or prev in ("0", ""):
                break
            node = get(f"league/{prev}")
        chains.append(chain)
    return chains


def pull_league(league, refresh):
    """Pull one season of one league into data/raw/<season>/."""
    lid, season = league["league_id"], league["season"]

    # A season still in progress changes week to week, so never trust its cache.
    force = refresh or league.get("status") != "complete"

    cached(f"{season}/league.json", f"league/{lid}", force)
    cached(f"{season}/users.json", f"league/{lid}/users", force)
    cached(f"{season}/rosters.json", f"league/{lid}/rosters", force)
    cached(f"{season}/winners_bracket.json", f"league/{lid}/winners_bracket", force)
    cached(f"{season}/losers_bracket.json", f"league/{lid}/losers_bracket", force)
    cached(f"{season}/traded_picks.json", f"league/{lid}/traded_picks", force)

    drafts = cached(f"{season}/drafts.json", f"league/{lid}/drafts", force) or []
    for draft in drafts:
        did = draft["draft_id"]
        cached(f"{season}/draft_{did}_picks.json", f"draft/{did}/picks", force)

    for week in WEEKS:
        cached(f"{season}/matchups_{week:02d}.json",
               f"league/{lid}/matchups/{week}", force)
        cached(f"{season}/transactions_{week:02d}.json",
               f"league/{lid}/transactions/{week}", force)


def pull_players(refresh):
    """The full NFL player dictionary, ~5MB. Sleeper asks that this be fetched
    at most once per day, so it gets its own staleness rule."""
    dest = RAW / "players_nfl.json"
    fresh = dest.exists() and (time.time() - dest.stat().st_mtime) < 86400
    if fresh and not refresh:
        return
    data = get("players/nfl")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", required=True,
                    help="your Sleeper username (the handle, not an email)")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cache and re-download everything")
    args = ap.parse_args()

    user = get(f"user/{args.user}")
    if not user:
        sys.exit(f"No Sleeper user named '{args.user}'.")
    user_id = user["user_id"]
    season = int(get("state/nfl")["season"])
    print(f"{args.user} -> user_id {user_id}, current season {season}")

    chains = league_chain(user_id, season)
    if not chains:
        sys.exit(f"'{args.user}' is not in any NFL league for {season}.")

    index = {"username": args.user, "user_id": user_id, "seasons": []}
    for chain in chains:
        for league in chain:
            print(f"  {league['season']}  {league['name']}")
            pull_league(league, args.refresh)
            index["seasons"].append({
                "season": league["season"],
                "league_id": league["league_id"],
                "name": league["name"],
                "status": league.get("status"),
            })

    print("  players/nfl ...")
    pull_players(args.refresh)

    index["seasons"].sort(key=lambda s: s["season"])
    (RAW / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    size = sum(f.stat().st_size for f in RAW.rglob("*.json"))
    print(f"\nDone. {_calls} API calls, {size / 1e6:.1f} MB cached in data/raw/")


if __name__ == "__main__":
    main()
