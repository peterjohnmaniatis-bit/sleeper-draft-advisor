#!/usr/bin/env python3
"""In-season state: where the league stands right now.

Standings, rosters, who is actually free, the remaining schedule, and each
manager's scoring distribution -- the shared foundation the in-season tools
all read from. No network calls beyond what pull.py already cached.
"""

import sys
from collections import defaultdict

from model import Season, _load

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class LeagueState:
    """Everything the in-season tools need about one season, at one point."""

    def __init__(self, season_id, league_id, through=None):
        self.s = Season(season_id, league_id)
        self.season = season_id
        played = self.s.scored_weeks()
        self.through = through if through is not None else (max(played) if played else 0)
        self.weeks = [w for w in played if w <= self.through]
        self.scored = set(self.weeks)          # weeks with real results
        self.playoff_start = self.s.playoff_week_start
        self.teams = len(self.s.managers)
        self.names = {rid: self.s.display(rid) for rid in self.s.managers}

        self.scores = defaultdict(list)      # roster_id -> weekly points
        self.results = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0})
        self.schedule = defaultdict(dict)    # week -> roster_id -> opponent
        for wk in sorted(self.s.weeks):
            entries = self.s.weeks[wk]
            pairs = defaultdict(list)
            for rid, e in entries.items():
                if e.get("matchup_id") is not None:
                    pairs[e["matchup_id"]].append(rid)
            for sides in pairs.values():
                if len(sides) != 2:
                    continue
                a, b = sides
                self.schedule[wk][a] = b
                self.schedule[wk][b] = a
                # Gate on whether the week ACTUALLY has results, not on a
                # numeric bound. A week inside `through` that was never played
                # scores 0-0 and was being counted as a tie for both teams,
                # which poisoned every record, mean and spread downstream.
                if wk not in self.scored or wk >= self.playoff_start:
                    continue
                pa = entries[a].get("points") or 0.0
                pb = entries[b].get("points") or 0.0
                self.scores[a].append(pa)
                self.scores[b].append(pb)
                self.results[a]["pf"] += pa; self.results[a]["pa"] += pb
                self.results[b]["pf"] += pb; self.results[b]["pa"] += pa
                if pa > pb:
                    self.results[a]["w"] += 1; self.results[b]["l"] += 1
                elif pb > pa:
                    self.results[b]["w"] += 1; self.results[a]["l"] += 1
                else:
                    self.results[a]["t"] += 1; self.results[b]["t"] += 1

        # Rosters as of the most recent scored week, which is the only view
        # Sleeper's matchup data gives us historically.
        self.rosters = {}
        live = (self.s.status or "").lower() != "complete"
        cached = {r["roster_id"]: list(r.get("players") or [])
                  for r in (_load(f"{self.season}/rosters.json") or [])}
        last = max(self.weeks) if self.weeks else None
        if live and cached:
            # Mid-season the matchup snapshot is a week stale, so a player
            # already claimed shows up as a free agent. rosters.json is current.
            self.rosters = cached
        elif last is not None:
            for rid, e in self.s.weeks[last].items():
                self.rosters[rid] = list(e.get("players") or [])
        else:
            for r in (_load(f"{self.season}/rosters.json") or []):
                self.rosters[r["roster_id"]] = list(r.get("players") or [])

        self.rostered = {p for ps in self.rosters.values() for p in ps}

    # -- helpers ---------------------------------------------------------
    def remaining_weeks(self):
        """Only weeks that actually have a cached pairing. Returning weeks with
        no schedule made the simulator announce 'N weeks left' and then play
        none of them."""
        return [w for w in range(self.through + 1, self.playoff_start)
                if self.schedule.get(w)]

    def free_agents(self, players, positions=("QB", "RB", "WR", "TE")):
        """Everyone not on a roster in this league. The pool a waiver claim
        actually draws from -- not the whole NFL."""
        out = []
        for pid, info in players.by_id.items():
            if pid in self.rostered:
                continue
            if info.get("position") in positions:
                out.append(pid)
        return out

    PRIOR_GAMES = 5      # weight of the league prior, in games

    def mean_sd(self, rid):
        """Scoring mean and spread for simulating the rest of the season.

        The mean is shrunk toward the league average with a prior worth about
        five games, and the spread is widened by the uncertainty in that mean.
        Using the raw point estimate after three games treats a hot start as
        settled fact and produces far more confident odds than the data earns.
        """
        vals = self.scores.get(rid) or []
        if not vals:
            return 0.0, 1.0
        n = len(vals)
        m = sum(vals) / n
        allv = [v for vs in self.scores.values() for v in vs]
        league = sum(allv) / len(allv) if allv else m
        k = self.PRIOR_GAMES
        m_hat = (n * m + k * league) / (n + k)
        if n < 2:
            return m_hat, max(m_hat * 0.22, 1.0)
        var = sum((v - m) ** 2 for v in vals) / (n - 1)
        sd = max(var ** 0.5, 1.0)
        return m_hat, sd * (1.0 + 1.0 / n) ** 0.5

    def standings(self):
        rows = []
        for rid in self.s.managers:
            r = self.results[rid]
            rows.append({"roster_id": rid, "name": self.names[rid],
                         "w": r["w"], "l": r["l"], "t": r["t"],
                         "pf": round(r["pf"], 1), "pa": round(r["pa"], 1)})
        rows.sort(key=lambda x: (-x["w"], -x["pf"]))
        for i, row in enumerate(rows, 1):
            row["seed"] = i
        return rows

    def roster_slots(self):
        return self.s.starting_slots


def load(through=None, season=None):
    """The CURRENT season, unless one is named.

    Deliberately not "the newest season with played weeks". In week zero that
    rule silently handed every in-season tool last year's league -- correct
    standings, correct rosters, entirely the wrong season -- and nothing on
    screen said so.
    """
    index = _load("index.json")
    if not index:
        raise SystemExit("No data. Run: python pull.py --user <name>")
    seasons = sorted(index["seasons"], key=lambda x: x["season"])
    if season:
        pick = next((s for s in seasons if s["season"] == season), None)
        if not pick:
            raise SystemExit(f"No cached season {season}")
    else:
        pick = seasons[-1]        # the current season, played or not
    return LeagueState(pick["season"], pick["league_id"], through)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season")
    ap.add_argument("--through", type=int)
    a = ap.parse_args()
    st = load(a.through, a.season)
    print(f"{st.season}  through week {st.through}  "
          f"({len(st.weeks)} scored, playoffs start week {st.playoff_start})")
    print(f"remaining regular-season weeks: {st.remaining_weeks() or 'none'}\n")
    print(f"  {'#':<3}{'manager':<20}{'rec':>8}{'PF':>9}{'mean':>8}{'sd':>7}")
    for row in st.standings():
        m, sd = st.mean_sd(row["roster_id"])
        rec = f"{row['w']}-{row['l']}" + (f"-{row['t']}" if row["t"] else "")
        print(f"  {row['seed']:<3}{row['name'][:18]:<20}{rec:>8}"
              f"{row['pf']:>9.1f}{m:>8.1f}{sd:>7.1f}")
