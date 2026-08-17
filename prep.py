#!/usr/bin/env python3
"""Per-manager draft prep page, built from their seat and their own history.

    python prep.py pjmaniatis wburnett7 JasonMarano --sims 250

Writes out/prep-<name>.html for each. Every page is computed for that seat
alone -- nothing here coordinates one manager's plan around another's.
"""

import argparse
import json
import random
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path

from draft import bot_pick, setup
from model import RAW
from report import CSS, esc, table
from scout import profile

ROOT = Path(__file__).resolve().parent
POS = ("QB", "RB", "WR", "TE")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def picks_for(slot, teams, rounds):
    out = []
    for r in range(1, rounds + 1):
        offset = slot if r % 2 == 1 else (teams - slot + 1)
        out.append((r, (r - 1) * teams + offset))
    return out


def simulate(state, points, sims, seed):
    """Availability at the given pick numbers, over many simulated drafts."""
    rng = random.Random(seed)
    avail, gone = defaultdict(Counter), defaultdict(list)
    total = state.teams * state.rounds
    for _ in range(sims):
        state.picks, state.taken, state.rosters = [], set(), defaultdict(list)
        taken_at = {}
        while state.current_pick <= total:
            pk = state.current_pick
            slot, rnd = state.slot_on_clock(pk)
            p = bot_pick(state, state.order[slot - 1], rnd, rng)
            if not p:
                break
            state.record(pk, p["player_id"], state.order[slot - 1])
            taken_at[pk] = p["player_id"]
        for pk in points:
            before = {taken_at[k] for k in range(1, pk) if k in taken_at}
            for p in state.board[:100]:
                if p["player_id"] not in before:
                    avail[pk][p["player_id"]] += 1
            gone[pk].append(Counter(state.by_id[x]["pos"] for x in before
                                    if x in state.by_id))
    return avail, gone


def read(prof):
    """The one or two things this manager's own history says to change."""
    out = []
    s = prof["surplus"]
    if s <= -3:
        out.append(("Reaching is your biggest leak",
                    f"You draft at {s:+.1f} slots per pick. Before every "
                    f"selection, check the board rank of who you want against "
                    f"the pick you are spending. If he ranks a round or more "
                    f"below where you are, take the higher-ranked player."))
    elif s >= 3:
        out.append(("Your board reading is a strength",
                    f"You draft at {s:+.1f} slots per pick, well above the "
                    f"league. Nothing about your process needs changing; trust "
                    f"it when a pick feels early."))
    qb = prof["first_round"].get("QB")
    if qb and qb <= 5:
        out.append(("You take a quarterback too early",
                    f"Your first QB comes in round {qb} on average. In a "
                    f"one-quarterback league only twelve start, so the gap "
                    f"between the best and the twelfth is small. Every round "
                    f"you wait buys a better back or receiver."))
    te = prof["first_round"].get("TE")
    if te and te <= 4:
        out.append(("Tight end early has not paid",
                    f"Your first TE averages round {te}. An elite tight end is "
                    f"worth roughly a third of an elite back in this scoring."))
    luck = prof["luck"]
    if luck <= -3:
        out.append(("Your record understates you",
                    f"You are {luck:+.1f} wins against expectation across "
                    f"{prof['n']} seasons -- the schedule, not the roster. "
                    f"Do not overcorrect for results that were not your doing."))
    return out


def build(state, name, slot, prof, avail, gone, sims, seq, detail):
    teams = state.teams
    gaps = [seq[i + 1][1] - seq[i][1] for i in range(len(seq) - 1)]
    p = ['<div class="wrap">']
    p.append(f"<h1>Draft prep &mdash; {esc(name)}</h1>")
    p.append(f'<p class="sub">Slot {slot} of {teams} &middot; {state.rounds} rounds '
             f'&middot; snake &middot; built from {sims} simulated drafts against '
             f'models of this league</p>')

    p.append('<div class="kpis">')
    for label, val, meta in [
        ("Your slot", str(slot), f"of {teams}"),
        ("First pick", str(seq[0][1]), "overall"),
        ("Longest wait", str(max(gaps)), "picks between turns"),
        ("Draft surplus", f'{prof["surplus"]:+.1f}',
         "slots per pick, 5 seasons"),
    ]:
        p.append(f'<div class="kpi"><div class="label">{label}</div>'
                 f'<div class="value">{val}</div><div class="meta">{esc(meta)}</div></div>')
    p.append("</div>")

    # -- rhythm
    p.append("<h2>Your picks</h2>")
    p.append(f'<p class="sub">Gaps alternate {gaps[0]} and {gaps[1]}. '
             f'Going into a long wait, take the player who will not survive it. '
             f'Coming back in {min(gaps)}, you can afford the one who might.</p>')
    p.append(table(["Round", "#Pick", "#Picks until your next"],
                   [[str(r), str(pk), str(gaps[i]) if i < len(gaps) else "-"]
                    for i, (r, pk) in enumerate(seq)]))

    # -- what is there
    p.append("<h2>What tends to be there</h2>")
    p.append(f'<p class="sub">Share of {sims} simulated drafts in which each '
             f'player was still on the board at that pick. Opponents are modelled '
             f'on how these managers have actually drafted, not on national ADP.</p>')
    for r, pk in seq[:detail]:
        if pk not in avail:
            continue
        rows = [(state.by_id[pid], n / sims * 100)
                for pid, n in avail[pk].items() if pid in state.by_id]
        rows.sort(key=lambda x: -x[0]["vor"])
        shown = [x for x in rows if x[1] >= 15][:8]
        if not shown:
            continue
        p.append(f"<h3>Round {r}, pick {pk}</h3>")
        p.append(table(["Player", "Pos", "#VOR", "#Still there"],
                       [[esc(pl["name"]), pl["pos"], f'{pl["vor"]:.0f}',
                         f'{pct:.0f}%'] for pl, pct in shown]))
        if gone[pk]:
            avg = Counter()
            for c in gone[pk]:
                avg.update(c)
            n = len(gone[pk])
            p.append(f'<p class="note">Off the board by now: ' +
                     " &middot; ".join(f"{k} {avg[k]/n:.0f}" for k in POS) + "</p>")

    # -- their own history
    p.append("<h2>What your own five seasons say</h2>")
    rows = []
    for x in prof["seasons"]:
        rows.append([x["season"], f'{x["w"]}-{x["l"]}', f'{x["exp"]:.1f}',
                     f'{x["luck"]:+.1f}', f'{x["pf"]:.0f}', f'{x["eff"]:.1f}%'])
    p.append(table(["Season", "Record", "#Expected W", "#Luck", "#Points", "#Efficiency"], rows))

    p.append("<h3>Where you take each position, on average</h3>")
    p.append(table(["Position", "#First taken (round)"],
                   [[k, str(v)] for k, v in sorted(prof["first_round"].items())]))

    notes = read(prof)
    if notes:
        p.append("<h3>The things worth changing</h3>")
        p.append(table(["", ""], [[f"<strong>{esc(t)}</strong>", esc(b)]
                                  for t, b in notes]))

    if prof["best_pick"]:
        b, w = prof["best_pick"], prof["worst_pick"]
        p.append("<h3>Your best and worst picks</h3>")
        p.append(table(["", "Player", "#Taken at", "#Finished"],
                       [["Best", esc(b["player"]), str(b["pick_no"]), f'#{b["value_rank"]}'],
                        ["Worst", esc(w["player"]), str(w["pick_no"]), f'#{w["value_rank"]}']]))

    # -- league facts
    p.append("<h2>What is true of this league</h2>")
    p.append(table(
        ["Fact", "What it means for you"],
        [["Value over replacement: RB 103, WR 90, QB 61, TE 32",
          "An elite back is worth about three elite tight ends. Two flex spots "
          "push RB and WR replacement deep, which is what makes their tops so valuable."],
         ["A quarter of round three goes to quarterbacks",
          "Three teams spend a premium pick on the third-least-scarce position "
          "every year. Whoever does not is collecting the backs and receivers they pass."],
         ["Quarterback is the most replaceable position on waivers (24% hit rate)",
          "Running back is the least (15%). If you punt QB and it goes wrong, "
          "this league has historically bailed you out. Punt RB and it has not."],
         ["The draft correlates with points scored at 0.67; waivers at 0.08",
          "Top and bottom finishers here are indistinguishable on in-season "
          "management. The season is decided in August."]]))

    p.append('<p class="note" style="margin-top:32px">Built from cached Sleeper '
             'data and this league\'s own five-season history. Projections come '
             'from an undocumented Sleeper endpoint and are a forecast, not a '
             'fact.</p>')
    p.append("</div>")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("managers", nargs="+")
    ap.add_argument("--sims", type=int, default=250)
    ap.add_argument("--detail", type=int, default=7, help="how many picks to detail")
    args = ap.parse_args()

    state = setup(types.SimpleNamespace(slot=None, season=None, mock=True))
    data = json.loads((RAW.parent / "analysis.json").read_text(encoding="utf-8"))
    me = data["username"]
    _, seasons, players = __import__("model").load_all()

    targets = []
    for name in args.managers:
        match = next((m for m in state.order if m.lower() == name.lower()), None)
        if not match:
            print(f"No manager '{name}'. Order: {', '.join(state.order)}")
            continue
        targets.append((match, state.order.index(match) + 1))

    points = {pk for _, slot in targets
              for _, pk in picks_for(slot, state.teams, state.rounds)[:args.detail]}
    print(f"simulating {args.sims} drafts across {len(points)} pick points ...")
    avail, gone = simulate(state, points, args.sims, seed=11)

    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    for name, slot in targets:
        prof = profile(data, seasons, players, name, me)
        seq = picks_for(slot, state.teams, state.rounds)
        body = build(state, name, slot, prof, avail, gone, args.sims, seq, args.detail)
        doc = (f"<title>Draft prep &mdash; {esc(name)}</title>"
               f"<style>{CSS}</style>{body}")
        doc = doc.encode("ascii", "xmlcharrefreplace").decode("ascii")
        dest = out_dir / f"prep-{name}.html"
        dest.write_text(doc, encoding="ascii")
        print(f"  wrote {dest}  ({len(doc)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
