#!/usr/bin/env python3
"""Draft-slot strategy guide: what the board looks like from one seat.

    python guide.py pjmaniatis
    python guide.py pjmaniatis wburnett7 JasonMarano --sims 300

Simulates the draft many times with every seat played by a model of that
manager's real drafting history, then reports what actually tends to be sitting
there when a given seat is on the clock.

Each guide is computed independently for that seat. Nothing here coordinates
one manager's picks around another's.
"""

import argparse
import random
import sys
import types
from collections import Counter, defaultdict

from draft import bot_pick, setup
from model import _load

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POS = ("QB", "RB", "WR", "TE")


def picks_for(slot, teams, rounds):
    out = []
    for r in range(1, rounds + 1):
        offset = slot if r % 2 == 1 else (teams - slot + 1)
        out.append((r, (r - 1) * teams + offset))
    return out


def simulate(state, rng):
    """One full draft, every seat bot-played. Returns pick_no -> player."""
    state.picks, state.taken, state.rosters = [], set(), defaultdict(list)
    total = state.teams * state.rounds
    while state.current_pick <= total:
        pk = state.current_pick
        slot, rnd = state.slot_on_clock(pk)
        mgr = state.order[slot - 1]
        p = bot_pick(state, mgr, rnd, rng)
        if not p:
            break
        state.record(pk, p["player_id"], mgr)
    return {p["pick_no"]: p["player_id"] for p in state.picks}


def run(state, sims, seed=0):
    """Availability at every pick number, across many simulated drafts."""
    rng = random.Random(seed)
    avail = defaultdict(Counter)      # pick_no -> Counter(player_id)
    gone = defaultdict(list)          # pick_no -> [positions gone by then]
    total = state.teams * state.rounds
    for _ in range(sims):
        taken_order = simulate(state, rng)
        drafted = set()
        for pk in range(1, total + 1):
            for p in state.board:
                pass
            # players still free at pick pk = board minus those taken earlier
            drafted_now = {taken_order[k] for k in range(1, pk) if k in taken_order}
            if pk in PICK_POINTS:
                for p in state.board[:90]:
                    if p["player_id"] not in drafted_now:
                        avail[pk][p["player_id"]] += 1
                c = Counter(state.by_id[x]["pos"] for x in drafted_now
                            if x in state.by_id)
                gone[pk].append(c)
    return avail, gone


PICK_POINTS = set()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("managers", nargs="+")
    ap.add_argument("--sims", type=int, default=200)
    ap.add_argument("--rounds", type=int, default=6,
                    help="how many of their picks to detail")
    args = ap.parse_args()

    state = setup(types.SimpleNamespace(slot=None, season=None, mock=True))
    order = state.order
    teams, rounds = state.teams, state.rounds

    targets = []
    for name in args.managers:
        match = next((m for m in order if m.lower() == name.lower()), None)
        if not match:
            print(f"No manager '{name}'. Order: {', '.join(order)}")
            continue
        targets.append((match, order.index(match) + 1))

    global PICK_POINTS
    PICK_POINTS = {pk for _, slot in targets
                   for r, pk in picks_for(slot, teams, rounds)[:args.rounds]}

    print(f"\nsimulating {args.sims} drafts ...")
    avail, gone = run(state, args.sims)

    for name, slot in targets:
        seq = picks_for(slot, teams, rounds)
        print("\n" + "=" * 74)
        print(f"  {name.upper()}   slot {slot} of {teams}")
        print("=" * 74)
        print("  your picks: " + ", ".join(str(pk) for _, pk in seq))
        gaps = [seq[i + 1][1] - seq[i][1] for i in range(len(seq) - 1)]
        print(f"  gaps between picks: {', '.join(str(g) for g in gaps[:8])}")
        print(f"  longest wait: {max(gaps)} picks   shortest: {min(gaps)}")

        for r, pk in seq[:args.rounds]:
            if pk not in avail:
                continue
            print(f"\n  ROUND {r}, PICK {pk}")
            c = avail[pk]
            rows = [(state.by_id[pid], n / args.sims * 100)
                    for pid, n in c.items() if pid in state.by_id]
            rows.sort(key=lambda x: (-x[0]["vor"]))
            shown = [x for x in rows if x[1] >= 15][:8]
            print(f"    {'player':<24}{'pos':<5}{'VOR':>7}{'there':>8}")
            for p, pct in shown:
                print(f"    {p['name'][:22]:<24}{p['pos']:<5}{p['vor']:>7.0f}{pct:>7.0f}%")
            if gone[pk]:
                avg = Counter()
                for c2 in gone[pk]:
                    avg.update(c2)
                print("    off the board by now: " + "  ".join(
                    f"{k} {avg[k] / len(gone[pk]):.0f}" for k in POS))


if __name__ == "__main__":
    main()
