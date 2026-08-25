"""Loads the cached Sleeper JSON into structures the analysis can work with.

Everything here reads from data/raw/. Nothing here touches the network.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"

# Which roster positions a given slot will accept. Ordered loosely by how
# restrictive each slot is; analysis.optimal_lineup relies on that ordering.
SLOT_ELIGIBILITY = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DEF"},
    "DL": {"DL"}, "LB": {"LB"}, "DB": {"DB"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "IDP_FLEX": {"DL", "LB", "DB"},
}

# Slots that don't start anyone.
NON_STARTING = {"BN", "IR", "TAXI"}


# How a flex slot actually gets filled, across the league. Used to work out how
# deep each position is drafted before you are into freely available players.
FLEX_SPLIT = {"RB": 0.30, "WR": 0.55, "TE": 0.15}


def _load(path):
    f = RAW / path
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def replacement_ranks(season):
    """How many players at each position start somewhere in this league.

    Derived from the league's own roster settings rather than assumed, so the
    tool is correct for any Sleeper league instead of only a 12-team two-flex
    one. A player past this rank is replaceable off the waiver wire, which is
    what makes it the right baseline for value over replacement.
    """
    from collections import Counter
    teams = len(season.managers) or 12
    counts = Counter(season.starting_slots)
    flex = sum(counts.get(s, 0) for s in
               ("FLEX", "WRRB_FLEX", "REC_FLEX", "SUPER_FLEX", "IDP_FLEX"))
    ranks = {}
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        starters = counts.get(pos, 0) * teams
        share = flex * teams * FLEX_SPLIT.get(pos, 0.0)
        if starters or share:
            ranks[pos] = max(1, round(starters + share))
    return ranks


class Players:
    """The NFL player dictionary, trimmed to what the analysis needs."""

    def __init__(self):
        raw = _load("players_nfl.json") or {}
        self.by_id = {}
        for pid, p in raw.items():
            if not isinstance(p, dict):
                continue
            name = p.get("full_name")
            if not name:
                # Team defenses carry no full_name; they key on the abbreviation.
                name = " ".join(filter(None, [p.get("first_name"), p.get("last_name")])) or pid
            self.by_id[pid] = {
                "name": name,
                "position": p.get("position"),
                "fantasy_positions": set(p.get("fantasy_positions") or []),
                "team": p.get("team"),
            }

    def name(self, pid):
        return self.by_id.get(pid, {}).get("name", pid)

    def positions(self, pid):
        """Positions this player can fill. Falls back to the primary position."""
        p = self.by_id.get(pid)
        if not p:
            return set()
        return p["fantasy_positions"] or ({p["position"]} if p["position"] else set())

    def position(self, pid):
        return self.by_id.get(pid, {}).get("position")


class Season:
    """One season of one league."""

    def __init__(self, season, league_id):
        self.season = season
        self.league_id = league_id

        league = _load(f"{season}/league.json") or {}
        self.name = league.get("name", season)
        self.settings = league.get("settings", {})
        self.scoring = league.get("scoring_settings", {})
        self.roster_positions = league.get("roster_positions", [])
        self.status = league.get("status")

        self.playoff_week_start = self.settings.get("playoff_week_start") or 15
        self.starting_slots = [s for s in self.roster_positions if s not in NON_STARTING]

        users = {u["user_id"]: u for u in (_load(f"{season}/users.json") or [])}
        self.managers = {}
        for r in _load(f"{season}/rosters.json") or []:
            u = users.get(r.get("owner_id"), {})
            meta = u.get("metadata") or {}
            self.managers[r["roster_id"]] = {
                "roster_id": r["roster_id"],
                "user_id": r.get("owner_id"),
                "display_name": u.get("display_name") or f"roster {r['roster_id']}",
                "team_name": meta.get("team_name") or "",
            }
        self.user_to_roster = {
            m["user_id"]: rid for rid, m in self.managers.items() if m["user_id"]
        }

        # weeks[week][roster_id] -> matchup record
        self.weeks = {}
        for wk in range(1, 19):
            entries = _load(f"{season}/matchups_{wk:02d}.json") or []
            if not entries:
                continue
            self.weeks[wk] = {e["roster_id"]: e for e in entries if e.get("roster_id")}

        self.transactions = []
        for wk in range(1, 19):
            for t in _load(f"{season}/transactions_{wk:02d}.json") or []:
                t["_week"] = wk
                self.transactions.append(t)

        self.drafts = _load(f"{season}/drafts.json") or []
        self.draft_picks = []
        for d in self.drafts:
            self.draft_picks.extend(_load(f"{season}/draft_{d['draft_id']}_picks.json") or [])

        self.winners_bracket = _load("{}/winners_bracket.json".format(season)) or []

    @property
    def regular_weeks(self):
        """Weeks that count toward the regular-season record."""
        return [w for w in sorted(self.weeks) if w < self.playoff_week_start]

    def display(self, roster_id):
        return self.managers.get(roster_id, {}).get("display_name", f"roster {roster_id}")

    def scored_weeks(self, partial=False):
        """Regular-season weeks that are actually COMPLETE.

        Completion comes from Sleeper's own NFL state, not from whether anyone
        has scored. Points-based inference cannot tell Thursday night from a
        finished Sunday -- between kickoff and Monday night it reported the
        in-progress week as done, advised the wrong week and fabricated a
        record. On screen that is catchable; in a scheduled job it is not.

        `partial=True` includes the week in progress, which is what a live
        view wants. Anything computing a record, a mean or a spread does not.
        """
        cur = nfl_week()          # 0 outside the regular season
        out = []
        for w in self.regular_weeks:
            if not any((e.get("points") or 0) > 0 for e in self.weeks[w].values()):
                continue
            if partial or not cur or w < cur:
                out.append(w)
        return out


def nfl_week():
    """The regular-season week in progress, or 0 if it is not the season yet.

    Read from the cached state file, so this stays a no-network module.
    """
    st = _load("state.json") or {}
    if (st.get("season_type") or "").lower() != "regular":
        return 0
    try:
        return int(st.get("week") or 0)
    except (TypeError, ValueError):
        return 0


def load_all():
    """Every completed season, oldest first, plus the player dictionary."""
    index = _load("index.json")
    if not index:
        raise SystemExit("No data found. Run: python pull.py")
    seasons = []
    for s in sorted(index["seasons"], key=lambda x: x["season"]):
        season = Season(s["season"], s["league_id"])
        if season.weeks:  # skip seasons that haven't been played yet
            seasons.append(season)
    return index, seasons, Players()
