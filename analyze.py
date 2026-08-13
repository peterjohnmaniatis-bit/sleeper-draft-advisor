#!/usr/bin/env python3
"""Compute the decision-making metrics and write data/analysis.json.

    python analyze.py            # console summary + analysis.json
    python analyze.py --anon     # replace real names with Manager A, B, C...
"""

import argparse
import json
import sys
from collections import defaultdict

from model import RAW, SLOT_ELIGIBILITY, load_all

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- lineups

def optimal_lineup(entry, players, slots):
    """The highest-scoring legal lineup available from this roster that week.

    Slots are filled most-restrictive-first. Because every flex slot accepts a
    superset of some dedicated slot's positions, that ordering yields the true
    optimum rather than an approximation.
    """
    pts = entry.get("players_points") or {}
    roster = entry.get("players") or list(pts.keys())
    pool = {pid: (pts.get(pid) or 0.0) for pid in roster}

    order = sorted(
        range(len(slots)),
        key=lambda i: len(SLOT_ELIGIBILITY.get(slots[i], ())) or 99,
    )

    used, total, chosen = set(), 0.0, []
    for i in order:
        eligible = SLOT_ELIGIBILITY.get(slots[i])
        if not eligible:
            continue
        best, best_pts = None, -1.0
        for pid, score in pool.items():
            if pid in used or not (players.positions(pid) & eligible):
                continue
            if score > best_pts:
                best, best_pts = pid, score
        if best is not None:
            used.add(best)
            total += best_pts
            chosen.append({"slot": slots[i], "player_id": best, "points": best_pts})
    return round(total, 2), chosen


def worst_bench_call(entry, players, slots, chosen):
    """The single biggest points swing available: the best player left on the
    bench versus the worst starter he could have legally replaced."""
    pts = entry.get("players_points") or {}
    starters = entry.get("starters") or []
    started = set(starters)
    bench = [p for p in (entry.get("players") or []) if p not in started]
    if not bench:
        return None

    # Which slot did each starter occupy? Sleeper orders starters to match
    # roster_positions, so index alignment gives the slot.
    slot_of = {}
    for idx, pid in enumerate(starters):
        if idx < len(slots):
            slot_of[pid] = slots[idx]

    best = None
    for bp in bench:
        bpts = pts.get(bp) or 0.0
        bpos = players.positions(bp)
        for sp in starters:
            spts = pts.get(sp) or 0.0
            eligible = SLOT_ELIGIBILITY.get(slot_of.get(sp), set())
            if not (bpos & eligible):
                continue
            swing = bpts - spts
            if swing > 0 and (best is None or swing > best["swing"]):
                best = {
                    "benched": players.name(bp), "benched_points": round(bpts, 2),
                    "started": players.name(sp), "started_points": round(spts, 2),
                    "swing": round(swing, 2), "slot": slot_of.get(sp),
                }
    return best


# ---------------------------------------------------------------- records

def season_records(season):
    """Actual wins from head-to-head, plus all-play wins for luck analysis."""
    weeks = season.scored_weeks()
    n = len(season.managers)
    rec = {rid: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0,
                 "allplay_w": 0.0, "allplay_n": 0}
           for rid in season.managers}

    for wk in weeks:
        entries = season.weeks[wk]
        scores = {rid: (e.get("points") or 0.0) for rid, e in entries.items()}

        # head-to-head, paired by matchup_id
        pairs = defaultdict(list)
        for rid, e in entries.items():
            if e.get("matchup_id") is not None:
                pairs[e["matchup_id"]].append(rid)
        for sides in pairs.values():
            if len(sides) != 2:
                continue
            a, b = sides
            rec[a]["pf"] += scores[a]; rec[a]["pa"] += scores[b]
            rec[b]["pf"] += scores[b]; rec[b]["pa"] += scores[a]
            if scores[a] > scores[b]:
                rec[a]["w"] += 1; rec[b]["l"] += 1
            elif scores[b] > scores[a]:
                rec[b]["w"] += 1; rec[a]["l"] += 1
            else:
                rec[a]["t"] += 1; rec[b]["t"] += 1

        # all-play: what your record would be if you played everyone
        for rid, mine in scores.items():
            beat = sum(1 for other, s in scores.items() if other != rid and mine > s)
            tied = sum(1 for other, s in scores.items() if other != rid and mine == s)
            rec[rid]["allplay_w"] += beat + 0.5 * tied
            rec[rid]["allplay_n"] += n - 1

    for r in rec.values():
        r["expected_w"] = round(r["allplay_w"] / r["allplay_n"] * len(weeks), 2) if r["allplay_n"] else 0.0
        r["luck"] = round(r["w"] - r["expected_w"], 2)
        r["pf"] = round(r["pf"], 2)
        r["pa"] = round(r["pa"], 2)
    return rec, weeks


# ------------------------------------------------------- roster ownership

def ownership(season):
    """(roster_id, player_id) -> weeks held, points while held, points started.

    Derived from weekly matchup rosters, so it survives drops and re-adds
    without needing to replay the transaction log.
    """
    own = defaultdict(lambda: {"weeks": [], "points": 0.0, "started": 0.0})
    for wk in sorted(season.weeks):
        for rid, e in season.weeks[wk].items():
            pts = e.get("players_points") or {}
            starters = set(e.get("starters") or [])
            for pid in (e.get("players") or []):
                slot = own[(rid, pid)]
                slot["weeks"].append(wk)
                score = pts.get(pid) or 0.0
                slot["points"] += score
                if pid in starters:
                    slot["started"] += score
    return own


def player_season_points(season):
    """Regular-season points per player, in this league's scoring, summed over
    the weeks anyone rostered them.

    Sleeper retired its public stats endpoint, so this is the honest ceiling on
    what we can reconstruct: a player is only counted while on some roster. In
    a 12-team league with 15 spots that covers everyone who mattered, but a
    player who went unrostered for stretches will read low.
    """
    totals = defaultdict(float)
    for wk in season.scored_weeks():
        for e in season.weeks[wk].values():
            for pid, score in (e.get("players_points") or {}).items():
                totals[pid] += score or 0.0
    return totals


# ---------------------------------------------------------------- drafts

def draft_analysis(season, players):
    """Grade each pick by comparing where it was taken to where it finished."""
    if not season.draft_picks:
        return []
    totals = player_season_points(season)
    picks = sorted(season.draft_picks, key=lambda p: p.get("pick_no") or 0)

    ranked = sorted(picks, key=lambda p: -totals.get(p.get("player_id"), 0.0))
    value_rank = {p["player_id"]: i + 1 for i, p in enumerate(ranked)}

    out = []
    for p in picks:
        pid = p.get("player_id")
        rid = p.get("roster_id")
        pts = round(totals.get(pid, 0.0), 2)
        rank = value_rank.get(pid, len(picks))
        out.append({
            "pick_no": p.get("pick_no"), "round": p.get("round"),
            "roster_id": rid, "manager": season.display(rid),
            "user_id": season.managers.get(rid, {}).get("user_id"),
            "player": players.name(pid), "position": players.position(pid),
            "points": pts, "value_rank": rank,
            "surplus": (p.get("pick_no") or 0) - rank,
        })
    return out


# --------------------------------------------------------------- waivers

def transaction_analysis(season, players, own):
    """Adds, failed claims, and what each acquisition actually produced."""
    per_manager = defaultdict(lambda: {
        "waiver_adds": 0, "free_agent_adds": 0, "failed_claims": 0,
        "drops": 0, "trades": 0, "acquired_started_points": 0.0,
    })
    acquisitions, seen, trades = [], set(), []

    for t in season.transactions:
        ttype, status = t.get("type"), t.get("status")
        rids = t.get("roster_ids") or []

        if ttype == "trade" and status == "complete":
            for rid in rids:
                per_manager[rid]["trades"] += 1
            trades.append({
                "week": t["_week"],
                "rosters": [season.display(r) for r in rids],
                "adds": {players.name(p): season.display(r)
                         for p, r in (t.get("adds") or {}).items()},
                "picks": len(t.get("draft_picks") or []),
            })
            continue

        if status == "failed":
            for rid in rids:
                per_manager[rid]["failed_claims"] += 1
            continue

        if status != "complete":
            continue

        for pid, rid in (t.get("drops") or {}).items():
            per_manager[rid]["drops"] += 1

        for pid, rid in (t.get("adds") or {}).items():
            key = "waiver_adds" if ttype == "waiver" else "free_agent_adds"
            per_manager[rid][key] += 1
            if (rid, pid) in seen:
                continue
            seen.add((rid, pid))
            held = own.get((rid, pid), {"started": 0.0, "weeks": []})
            started = round(held["started"], 2)
            per_manager[rid]["acquired_started_points"] += started
            acquisitions.append({
                "week": t["_week"], "roster_id": rid,
                "manager": season.display(rid),
                "user_id": season.managers.get(rid, {}).get("user_id"),
                "player": players.name(pid),
                "position": players.position(pid),
                "type": ttype,
                "weeks_held": len(held["weeks"]),
                "started_points": started,
            })

    for v in per_manager.values():
        v["acquired_started_points"] = round(v["acquired_started_points"], 2)
    return per_manager, acquisitions, trades


# ------------------------------------------------------------------ main

def analyze_season(season, players):
    rec, weeks = season_records(season)
    own = ownership(season)
    slots = season.starting_slots

    lineups = {rid: {"actual": 0.0, "optimal": 0.0, "misses": []} for rid in season.managers}
    for wk in weeks:
        for rid, e in season.weeks[wk].items():
            if rid not in lineups:
                continue
            opt, chosen = optimal_lineup(e, players, slots)
            actual = e.get("points") or 0.0
            lineups[rid]["actual"] += actual
            lineups[rid]["optimal"] += opt
            miss = worst_bench_call(e, players, slots, chosen)
            if miss and miss["swing"] > 0:
                miss["week"] = wk
                lineups[rid]["misses"].append(miss)

    tx, acquisitions, trades = transaction_analysis(season, players, own)

    managers = {}
    for rid, m in season.managers.items():
        li = lineups[rid]
        actual, optimal = round(li["actual"], 2), round(li["optimal"], 2)
        misses = sorted(li["misses"], key=lambda x: -x["swing"])
        managers[rid] = {
            **m,
            **rec[rid],
            "actual_points": actual,
            "optimal_points": optimal,
            "points_left_on_bench": round(optimal - actual, 2),
            "efficiency": round(actual / optimal * 100, 2) if optimal else 0.0,
            "worst_calls": misses[:3],
            **tx[rid],
        }

    return {
        "season": season.season,
        "league_name": season.name,
        "weeks": weeks,
        "playoff_week_start": season.playoff_week_start,
        "managers": managers,
        "draft": draft_analysis(season, players),
        "acquisitions": acquisitions,
        "trades": trades,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anon", action="store_true",
                    help="replace league members' names with Manager A, B, C...")
    args = ap.parse_args()

    index, seasons, players = load_all()
    me = index["username"]

    result = {"username": me, "user_id": index["user_id"], "seasons": []}
    for s in seasons:
        print(f"analyzing {s.season} {s.name} ...")
        result["seasons"].append(analyze_season(s, players))

    canonicalize(result)
    me = result["username"]

    if args.anon:
        anonymize(result, me)

    out = RAW.parent / "analysis.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    summarize(result, "You" if args.anon else me)
    return result


def canonicalize(result):
    """Collapse renamed accounts back into one manager.

    A Sleeper account can change its display name between seasons, which
    splits one person's history into two if you group by name. Identity lives
    on user_id; the most recent name wins everywhere, and earlier names are
    kept as `aka` so the change stays visible rather than silently rewritten.
    """
    latest, seen = {}, defaultdict(set)
    for s in result["seasons"]:  # chronological, so the last write is current
        for m in s["managers"].values():
            uid = m.get("user_id")
            if uid:
                latest[uid] = m["display_name"]
                seen[uid].add(m["display_name"])

    if len(set(latest.values())) != len(latest):
        raise SystemExit("two accounts share a display name -- grouping by "
                         "name downstream would merge different people")

    rename = {old: latest[uid] for uid, names in seen.items()
              for old in names if old != latest[uid]}

    for s in result["seasons"]:
        for m in s["managers"].values():
            uid = m.get("user_id")
            if not uid:
                continue
            m["display_name"] = latest[uid]
            m["aka"] = sorted(seen[uid] - {latest[uid]})
        for row in s["draft"] + s["acquisitions"]:
            if row.get("user_id"):
                row["manager"] = latest[row["user_id"]]
        for t in s["trades"]:
            t["rosters"] = [rename.get(n, n) for n in t["rosters"]]
            t["adds"] = {p: rename.get(n, n) for p, n in t["adds"].items()}

    result["username"] = rename.get(result["username"], result["username"])
    for old, new in sorted(rename.items()):
        print(f"  merged renamed account: {old} -> {new}")
    return result


def anonymize(result, me):
    """Replace every real identity with a stable pseudonym.

    Two rules earned the hard way. Group by user_id, so a manager who renamed
    mid-history gets ONE alias rather than two. And rewrite every string in the
    structure rather than a list of known fields -- prior names in `aka`, both
    sides of a trade, team names and user ids all carry identity, and one
    missed field deanonymises everyone else by elimination.
    """
    by_uid, mine = {}, None
    for s in result["seasons"]:
        for m in s["managers"].values():
            uid = m.get("user_id")
            if not uid:
                continue
            names = by_uid.setdefault(uid, set())
            names.add(m["display_name"])
            names.update(m.get("aka") or [])
            if m["display_name"] == me:
                mine = uid

    alias, letter = {}, 0
    for uid in sorted(by_uid, key=lambda u: sorted(by_uid[u])[0].lower()):
        if uid == mine:
            label = "You"
        else:
            label = f"Manager {chr(65 + letter)}"
            letter += 1
        for name in by_uid[uid]:
            alias[name] = label

    drop = {"user_id", "aka", "team_name", "owner_id"}

    def swap(o):
        if isinstance(o, str):
            return alias.get(o, o)
        if isinstance(o, dict):
            return {k: swap(v) for k, v in o.items() if k not in drop}
        if isinstance(o, list):
            return [swap(x) for x in o]
        return o

    result["seasons"] = swap(result["seasons"])
    result["username"] = "You"
    result.pop("user_id", None)


def summarize(result, me):
    """Console overview so the numbers can be eyeballed before the report."""
    print("\n" + "=" * 78)
    for s in result["seasons"]:
        print(f"\n{s['season']}  {s['league_name']}   ({len(s['weeks'])} regular-season weeks)")
        print(f"{'manager':<20}{'rec':>7}{'luck':>7}{'PF':>9}{'eff%':>7}{'bench':>8}{'adds':>6}{'fail':>6}")
        rows = sorted(s["managers"].values(), key=lambda m: -m["efficiency"])
        for m in rows:
            star = " *" if m["display_name"] == me else "  "
            rec = f"{m['w']}-{m['l']}" + (f"-{m['t']}" if m["t"] else "")
            print(f"{m['display_name'][:18]:<18}{star}{rec:>7}{m['luck']:>7.1f}"
                  f"{m['pf']:>9.1f}{m['efficiency']:>7.1f}"
                  f"{m['points_left_on_bench']:>8.1f}"
                  f"{m['waiver_adds'] + m['free_agent_adds']:>6}{m['failed_claims']:>6}")


if __name__ == "__main__":
    main()
