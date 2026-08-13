#!/usr/bin/env python3
"""Commissioner tool: surface the statistical fingerprints of collusion.

    python collusion.py              # run every check
    python collusion.py --season 2025

Three checks, one per common pattern. Each reports the strongest signals it
finds along with how big the sample was.

READ THIS FIRST. These are QUESTIONS, not verdicts. In a twelve-team league
over five seasons there are 66 manager pairs and thousands of transactions, so
some pair will always look worst on any measure -- that is arithmetic, not
evidence. Every check here has an innocent explanation that is usually the
right one: people trade with friends, drop players other people want, and set
bad lineups when they are busy. Use these to decide where to LOOK, then look at
the actual trade or lineup and ask the person. Never lead with an accusation.
"""

import argparse
import sys
from collections import defaultdict

from analyze import optimal_lineup, ownership
from model import load_all

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MIN_MEETINGS = 4      # below this, a head-to-head efficiency gap means nothing
MIN_HANDOFFS = 2      # a single drop-and-claim is a coincidence


# ------------------------------------------------- 1. one-way trade value

def trade_flow(seasons, players):
    """Did value move one way between the same two managers, repeatedly?

    Scored on what each side's acquisitions actually produced for them AFTER
    the trade -- not on who 'won' by name value, which is unknowable in advance
    and unfair to judge in hindsight.
    """
    pair_net, rows = defaultdict(float), []
    for s in seasons:
        own = ownership(s)
        for t in s.transactions:
            if t.get("type") != "trade" or t.get("status") != "complete":
                continue
            wk = t["_week"]
            got = defaultdict(float)
            for pid, rid in (t.get("adds") or {}).items():
                held = own.get((rid, pid))
                if held:
                    got[rid] += sum(
                        (s.weeks[w][rid].get("players_points") or {}).get(pid, 0.0)
                        for w in held["weeks"] if w >= wk and rid in s.weeks.get(w, {}))
            sides = t.get("roster_ids") or []
            if len(sides) != 2:
                continue
            a, b = sides
            na, nb = round(got[a], 1), round(got[b], 1)
            rows.append({"season": s.season, "week": wk,
                         "a": s.display(a), "b": s.display(b),
                         "a_got": na, "b_got": nb, "gap": round(abs(na - nb), 1)})
            key = tuple(sorted((s.display(a), s.display(b))))
            pair_net[key] += (na - nb) if s.display(a) == key[0] else (nb - na)
    return rows, pair_net


# ------------------------------------------- 2. drop-and-claim handoffs

def handoffs(seasons):
    """Player dropped by one manager, picked up by the same manager every time.

    The signal is not the handoff itself -- that is how waivers work. It is the
    same PAIR repeating it, especially as a free-agent add rather than a waiver
    claim, because a free-agent add is uncontested and instant.
    """
    pairs = defaultdict(list)
    for s in seasons:
        last_drop = {}
        for t in sorted(s.transactions, key=lambda x: (x["_week"], x.get("created") or 0)):
            for pid, rid in (t.get("drops") or {}).items():
                last_drop[pid] = (rid, t["_week"])
            if t.get("status") != "complete":
                continue
            for pid, rid in (t.get("adds") or {}).items():
                prev = last_drop.get(pid)
                if not prev or prev[0] == rid:
                    continue
                gap = t["_week"] - prev[1]
                if gap > 3:
                    continue
                pairs[(s.display(prev[0]), s.display(rid))].append({
                    "season": s.season, "week": t["_week"], "player_id": pid,
                    "type": t.get("type"), "weeks_after": gap})
    return pairs


# --------------------------------------- 3. lineups tanked in one matchup

def matchup_effort(seasons, players):
    """Does a manager set a worse lineup against one specific opponent?

    The most detectable pattern, because it needs no cooperation to spot: a
    thrown matchup shows up as that manager's lineup efficiency collapsing in
    those weeks while staying normal everywhere else.
    """
    overall, versus = defaultdict(list), defaultdict(list)
    for s in seasons:
        slots = s.starting_slots
        for wk in s.scored_weeks():
            entries = s.weeks[wk]
            pairs = defaultdict(list)
            for rid, e in entries.items():
                if e.get("matchup_id") is not None:
                    pairs[e["matchup_id"]].append(rid)
            for sides in pairs.values():
                if len(sides) != 2:
                    continue
                for rid, opp in ((sides[0], sides[1]), (sides[1], sides[0])):
                    e = entries[rid]
                    opt, _ = optimal_lineup(e, players, slots)
                    if opt <= 0:
                        continue
                    eff = (e.get("points") or 0.0) / opt * 100
                    overall[s.display(rid)].append(eff)
                    versus[(s.display(rid), s.display(opp))].append(eff)
    return overall, versus


# ------------------------------------------ 4. value passed to one partner

def draft_value_flow(seasons, players, data):
    """Whose picks does one manager's passed value keep landing on?

    Everybody passes value on every pick -- nobody drafts perfectly, and this
    is judged in hindsight. So "he passed on a good player" means nothing. The
    signal is CONCENTRATION: with eleven opponents, a manager's passed value
    should scatter at roughly 9% each. One partner collecting 25-30% is the
    shape a funnelling arrangement makes.

    Slot distance is reported alongside because it is the innocent explanation
    for most of it: in a snake, whoever picks right after you collects the most
    of what you skipped, by pure geometry rather than by arrangement.
    """
    flow, totals, dist = defaultdict(float), defaultdict(float), defaultdict(list)
    for s in data["seasons"]:
        picks = sorted(s["draft"], key=lambda p: p["pick_no"] or 0)
        if not picks:
            continue
        teams = len({p["roster_id"] for p in picks}) or 12
        slot_of = {}
        for p in picks:
            rnd = (p["pick_no"] - 1) // teams + 1
            idx = (p["pick_no"] - 1) % teams
            slot_of[p["pick_no"]] = (idx + 1) if rnd % 2 == 1 else (teams - idx)

        for i, mine in enumerate(picks):
            for later in picks[i + 1:]:
                # Still on the board when `mine` picked, and finished better.
                if later["value_rank"] >= mine["value_rank"]:
                    continue
                worth = mine["value_rank"] - later["value_rank"]
                key = (mine["manager"], later["manager"])
                flow[key] += worth
                totals[mine["manager"]] += worth
                gap = abs(slot_of[later["pick_no"]] - slot_of[mine["pick_no"]])
                dist[key].append(min(gap, teams - gap))

    rows = []
    for (a, b), v in flow.items():
        if a == b or totals[a] <= 0:
            continue
        share = v / totals[a] * 100
        rows.append((share, a, b, sum(dist[(a, b)]) / len(dist[(a, b)])))
    return sorted(rows, reverse=True)


def traded_picks(seasons):
    """Draft picks changing hands. Concentrating early picks on one roster is
    the bluntest way to rig a draft, and Sleeper records every one."""
    out = []
    for s in seasons:
        from model import _load
        for tp in (_load(f"{s.season}/traded_picks.json") or []):
            out.append({
                "season": s.season, "round": tp.get("round"),
                "from": s.display(tp.get("previous_owner_id")),
                "to": s.display(tp.get("owner_id")),
                "original": s.display(tp.get("roster_id")),
            })
    return out


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", help="limit to one season")
    args = ap.parse_args()

    index, seasons, players = load_all()
    if args.season:
        seasons = [s for s in seasons if s.season == args.season]
    if not seasons:
        raise SystemExit("no seasons matched")

    print("=" * 76)
    print("  COLLUSION INDICATORS -- questions to investigate, not conclusions")
    print("=" * 76)

    # 1 -------------------------------------------------------------------
    rows, net = trade_flow(seasons, players)
    print(f"\n1. ONE-WAY TRADE VALUE   ({len(rows)} trades)")
    print("   Points each side's acquisitions produced after the trade.\n")
    if not rows:
        print("   No completed trades in range.")
    else:
        print(f"   {'season':<8}{'wk':<4}{'managers':<34}{'got':>16}{'gap':>7}")
        for r in sorted(rows, key=lambda x: -x["gap"]):
            print(f"   {r['season']:<8}{r['week']:<4}"
                  f"{(r['a'][:15] + ' / ' + r['b'][:15]):<34}"
                  f"{str(r['a_got']) + ' / ' + str(r['b_got']):>16}{r['gap']:>7.0f}")
        print("\n   Cumulative net flow per pair (positive = first name gained):")
        for (a, b), v in sorted(net.items(), key=lambda kv: -abs(kv[1])):
            print(f"     {a[:16]:<18}{b[:16]:<18}{v:>+8.0f}")
        print("\n   What matters is not one lopsided trade -- hindsight makes")
        print("   plenty of fair trades look terrible. It is the SAME PAIR with")
        print("   value flowing the same direction across several trades.")

    # 2 -------------------------------------------------------------------
    hand = handoffs(seasons)
    repeated = {k: v for k, v in hand.items() if len(v) >= MIN_HANDOFFS}
    print(f"\n\n2. DROP-AND-CLAIM HANDOFFS   ({len(hand)} pairs, "
          f"{len(repeated)} repeated {MIN_HANDOFFS}+ times)")
    print("   One manager drops a player, another picks him up within 3 weeks.\n")
    if not repeated:
        print("   No pair did this more than once.")
    else:
        print(f"   {'dropped by':<18}{'claimed by':<18}{'times':>6}  free-agent adds")
        for (a, b), evs in sorted(repeated.items(), key=lambda kv: -len(kv[1]))[:12]:
            fa = sum(1 for e in evs if e["type"] == "free_agent")
            print(f"   {a[:16]:<18}{b[:16]:<18}{len(evs):>6}  {fa} of {len(evs)}")
        print("\n   Waiver claims are competitive -- everyone bids, so a claim")
        print("   proves nothing. FREE-AGENT adds are instant and uncontested,")
        print("   so a pair doing it repeatedly is the column worth reading.")

    # 3 -------------------------------------------------------------------
    overall, versus = matchup_effort(seasons, players)
    print("\n\n3. EFFORT DROPPING IN ONE MATCHUP")
    print("   Lineup efficiency against a specific opponent vs. that manager's")
    print("   own baseline. Large negative gaps are worth a look.\n")
    flags = []
    for (mgr, opp), effs in versus.items():
        if len(effs) < MIN_MEETINGS:
            continue
        base = sum(overall[mgr]) / len(overall[mgr])
        here = sum(effs) / len(effs)
        flags.append((here - base, mgr, opp, here, base, len(effs)))
    flags.sort()
    print(f"   {'manager':<18}{'vs':<18}{'their eff':>10}{'baseline':>10}"
          f"{'gap':>8}{'games':>7}")
    for gap, mgr, opp, here, base, n in flags[:10]:
        print(f"   {mgr[:16]:<18}{opp[:16]:<18}{here:>10.1f}{base:>10.1f}"
              f"{gap:>+8.1f}{n:>7}")
    print(f"\n   Sample sizes here are {MIN_MEETINGS}-8 games. A gap under about")
    print("   10 points is noise. Even a large one usually means someone was on")
    print("   holiday that week, not that they threw a match.")

    # 4 -------------------------------------------------------------------
    import json
    from model import RAW
    data = json.loads((RAW.parent / "analysis.json").read_text(encoding="utf-8"))
    if args.season:
        data["seasons"] = [x for x in data["seasons"] if x["season"] == args.season]

    rows = draft_value_flow(seasons, players, data)
    n_opp = max(1, len({m.get("display_name") for x in data["seasons"]
                        for m in x["managers"].values()}) - 1)
    expected = 100.0 / n_opp
    print("\n\n4. DRAFT VALUE LANDING WITH ONE PARTNER")
    print(f"   Share of each manager's passed-over value collected by each")
    print(f"   opponent. With {n_opp} opponents, chance alone gives about "
          f"{expected:.0f}%.\n")
    print(f"   {'passed by':<18}{'collected by':<18}{'share':>8}{'vs chance':>11}"
          f"{'slot gap':>10}")
    for share, a, b, gap in rows[:10]:
        print(f"   {a[:16]:<18}{b[:16]:<18}{share:>7.1f}%{share - expected:>+11.1f}"
              f"{gap:>10.1f}")
    print("\n   Slot gap is the innocent explanation: whoever drafts right after")
    print("   you collects most of what you skipped, by snake geometry. A high")
    print("   share at gap 1-2 is arithmetic. A high share at gap 5+ is odd.")

    # 5 -------------------------------------------------------------------
    tp = traded_picks(seasons)
    print(f"\n\n5. TRADED DRAFT PICKS   ({len(tp)} found)")
    if not tp:
        print("   None. Nobody in this league has ever traded a draft pick,")
        print("   which removes the bluntest way to rig a draft entirely.")
    else:
        print(f"   {'season':<8}{'round':<7}{'from':<18}{'to':<18}")
        for t in tp[:15]:
            print(f"   {t['season']:<8}{str(t['round']):<7}{t['from'][:16]:<18}"
                  f"{t['to'][:16]:<18}")
        print("\n   Watch for early-round picks concentrating on one roster,")
        print("   especially from managers who then finish badly.")

    print("\n" + "=" * 76)
    print("  Before acting on any of this: look at the actual trade or lineup,")
    print("  check whether the manager was active elsewhere that week, and ask")
    print("  them directly. A wrong accusation costs more than a rigged season.")
    print("=" * 76)


if __name__ == "__main__":
    main()
