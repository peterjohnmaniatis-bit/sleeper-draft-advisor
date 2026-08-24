#!/usr/bin/env python3
"""Draft advising -- mock simulation and live draft night.

    python draft.py --mock              # simulate a full draft in the console
    python draft.py --serve --mock      # same, in a browser, advancing live
    python draft.py --serve             # draft night: follow the real draft

The API is read-only, so this never makes a pick. It watches the board and
tells you what it would do; you pick in the Sleeper app.
"""

import argparse
import http.client
import json
import math
import random
import sys
import atexit
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from model import RAW, Players, Season, _load, replacement_ranks
from tunnel import Tunnel
import adp as adp_mod
import scorecard as scorecard_mod
import strategies as strat_mod
from trade import REPLACEMENT_RANK, replacement_levels, season_projections

ROOT = Path(__file__).resolve().parent
API = "https://api.sleeper.app/v1"

# Filled in from the league's own roster settings at startup. The advisor needs
# kicker and defence on the board -- they are mandatory starters, and without
# them the last two rounds produce no advice and the roster is never legal.
DRAFT_REPLACEMENT = {**REPLACEMENT_RANK, "K": 12, "DEF": 12}
SKILL = tuple(DRAFT_REPLACEMENT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- directive
# Edit this to change what the advisor is trying to do. Defaults encode the
# plan the league analysis pointed to: RB is the scarcest thing here (103 VOR),
# QB the most replaceable off waivers (24% hit rate), TE barely worth reaching
# for (32 VOR), and a quarter of round 3 league-wide goes to QBs -- so waiting
# means the RB/WR those three teams pass on falls to you.
# The advisor's own plan, and the fallback for anyone who has not chosen. Every
# strategy on the landing page comes from strategies.py, so the mock and the
# live board can never drift apart on what a strategy means.
DIRECTIVE = strat_mod.to_directive(strat_mod.DEFAULT_KEY)


def get(path, timeout=15):
    """One read-only GET. Returns parsed JSON, or None on any failure.

    The except list is deliberately wide. urllib only converts errors raised by
    h.request() into URLError -- getresponse() and read() sit outside that
    conversion, so a dropped connection surfaces as a raw ConnectionResetError,
    RemoteDisconnected or IncompleteRead. Over ~1800 requests on draft night a
    narrow except would eventually let one escape and kill the polling thread.
    """
    req = urllib.request.Request(f"{API}/{path}",
                                 headers={"User-Agent": "fantasy-analyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return json.loads(body) if body else None
    except (OSError, urllib.error.URLError, http.client.HTTPException,
            TimeoutError, ValueError):
        return None


# ------------------------------------------------------------- value board

def build_board(season, players):
    """Every projected player, ranked by value over replacement."""
    proj = season_projections(season)
    levels = replacement_levels(proj, players, DRAFT_REPLACEMENT)
    # What the market charges, alongside what he is worth. Same cached file,
    # no extra network call. Missing for deep bench players, which is why every
    # consumer treats None as "unknown" rather than as a number.
    market = adp_mod.load(season)
    board = []
    for pid, pts in proj.items():
        pos = players.position(pid)
        if pos not in DRAFT_REPLACEMENT:
            continue
        board.append({
            "player_id": pid, "name": players.name(pid), "pos": pos,
            "proj": round(pts, 1), "vor": round(pts - levels[pos], 1),
            "adp": market.get(pid),
        })
    board.sort(key=lambda p: -p["vor"])
    for i, p in enumerate(board, 1):
        p["rank"] = i
        # Positive: the market rates him lower than we do, so he can be had
        # later than his value suggests. Negative: he goes before we rank him.
        p["adp_gap"] = adp_mod.gap(p["adp"], i)
    return board, levels


# --------------------------------------------------------- opponent model

def opponent_tendencies():
    """P(position | round) for each manager, from their real drafts.

    Falls back to the league average where a manager has thin history. This is
    what a generic mock draft bot cannot do: these are the actual eleven people.
    """
    data = _load("../analysis.json") or json.loads(
        (RAW.parent / "analysis.json").read_text(encoding="utf-8"))
    per, league = defaultdict(lambda: defaultdict(lambda: defaultdict(int))), \
        defaultdict(lambda: defaultdict(int))
    for s in data["seasons"]:
        for p in s["draft"]:
            pos = p["position"]
            if pos:
                per[p["manager"]][p["round"]][pos] += 1
                league[p["round"]][pos] += 1

    def norm(counts):
        total = sum(counts.values()) or 1
        return {k: v / total for k, v in counts.items()}

    league_norm = {r: norm(c) for r, c in league.items()}
    out = {}
    for mgr, rounds in per.items():
        out[mgr] = {r: (norm(c) if sum(c.values()) >= 3 else league_norm.get(r, {}))
                    for r, c in rounds.items()}
    return out, league_norm


# ------------------------------------------------------------ recommending

def roster_counts(roster, board_by_id):
    counts = defaultdict(int)
    for pid in roster:
        pos = board_by_id.get(pid, {}).get("pos")
        if pos:
            counts[pos] += 1
    return counts


# A seat that is not mine gets no directive at all: plain best-available.
# Two reasons. It is more honest advice for them -- my plan is built around my
# roster and this league's read on me -- and it keeps a shared link from
# broadcasting my strategy and my positional blocks to eleven opponents.
OPEN_DIRECTIVE = strat_mod.to_directive("best")


def directive_check(pos, rnd, counts, directive=None):
    """Why the directive would or would not allow this pick.

    Returns (allowed, note, kind). `kind` separates a timing rule you might
    reasonably override ("no QB before round 8") from a roster fact you cannot
    ("already have 2 TE") -- only the former is worth arguing with.
    """
    d = directive or DIRECTIVE
    earliest = d["earliest_round"].get(pos)
    if earliest and rnd < earliest:
        return False, f"directive: no {pos} before round {earliest}", "timing"
    # Dead zone: a band of rounds the strategy skips entirely. Not expressible
    # as "earliest", because the position is fine before it and after it -- it
    # is the middle that the strategy is avoiding.
    lo_hi = (d.get("banned_rounds") or {}).get(pos)
    if lo_hi and lo_hi[0] <= rnd <= lo_hi[1]:
        return False, f"dead zone: no {pos} in rounds {lo_hi[0]}-{lo_hi[1]}", "timing"
    cap = d["roster_caps"].get(pos)
    if cap is not None and counts.get(pos, 0) >= cap:
        return False, f"already have {counts[pos]} {pos}", "cap"
    for (p, through), limit in d["max_by_round"].items():
        if p == pos and rnd <= through and counts.get(pos, 0) >= limit:
            return False, f"directive: max {limit} {pos} through round {through}", "timing"
    return True, "", ""


def _poisson_below(k, lam):
    """P(X < k) for X ~ Poisson(lam), computed iteratively to avoid factorials."""
    if lam <= 0:
        return 1.0
    term, total = math.exp(-lam), 0.0
    for i in range(max(0, k)):
        if i:
            term *= lam / i
        total += term
    return min(1.0, total)


def survival(queue_rank, picks_until_next, league_norm, rnd, pos):
    """Chance THIS player is still on the board at your next pick.

    Not "will anyone take this position" -- that is near-certain and useless.
    A player who is the k-th best available at his position only disappears if
    at least k players at that position come off the board first. Treating
    those departures as Poisson with rate = (this league's share of picks spent
    on the position in this round) x (picks until you are back up) gives the
    probability he survives. Uses the current round's rate throughout, so it is
    approximate when your next pick lands in a later round.
    """
    rate = league_norm.get(rnd, {}).get(pos, 0.25)
    lam = max(0, picks_until_next) * rate
    return _poisson_below(queue_rank, lam)


def survival_for(p, queue_rank, picks_until_next, league_norm, rnd, next_pick):
    """Chance he lasts to your next pick, preferring the market model.

    The queue model asks "how many players at this position must come off the
    board first", counting from OUR ranking. That is exactly wrong for a player
    the rest of the world rates very differently: we may have him third at his
    position while the market has him thirtieth, and he is then in no danger at
    all. ADP measures the market directly, so it is used whenever it exists and
    the queue model stays as the fallback for players it does not cover.
    """
    if picks_until_next > 0:
        s = adp_mod.survival(p.get("adp"), next_pick)
        if s is not None:
            return s, "adp"
    return survival(queue_rank, picks_until_next, league_norm, rnd, p["pos"]), "queue"


# Six deep at every position, which is what the page draws. Not the top six
# overall: a cross-position list collapses onto whichever position happens to
# be deepest and hides the choice you are actually making.
PER_POS = 6

# Only these fields reach the browser. The scan also carries score, surv_src,
# proj and adp_gap, and six positions x six players of those would pad every
# poll for no pixel on screen.
COL_FIELDS = ("player_id", "name", "pos", "vor", "rank", "adp",
              "survives", "cost", "allowed", "note", "block_kind")


def recommend(board, taken, roster, rnd, pick_no, picks_until_next, league_norm,
              limit=6, directive=None, per_pos=PER_POS):
    """Rank the available players for this pick."""
    by_id = {p["player_id"]: p for p in board}
    counts = roster_counts(roster, by_id)
    out = []
    cols = defaultdict(list)
    queue = defaultdict(int)   # how many better players remain at each position
    for p in board:
        if p["player_id"] in taken:
            continue
        queue[p["pos"]] += 1
        ok, note, kind = directive_check(p["pos"], rnd, counts, directive)
        surv, surv_src = survival_for(p, queue[p["pos"]], picks_until_next,
                                      league_norm, rnd, pick_no + picks_until_next)
        # Value you would lose by waiting. Clamped at zero because the term is
        # multiplicative in VOR: left unclamped, scarcity makes a NEGATIVE-value
        # player score worse, so late in the draft it ranks the scarce player
        # below the abundant one -- exactly backwards.
        urgency = max(0.0, p["vor"]) * (1.0 - surv)
        score = p["vor"] + urgency * 0.5 - (0 if ok else 10_000)
        row = {**p, "allowed": ok, "note": note, "block_kind": kind,
               "survives": round(surv * 100), "surv_src": surv_src,
               "score": round(score, 1)}
        out.append(row)
        # The SAME dict object goes into the column, so one cost pass in
        # advice() reaches both lists. Filled in board order, not score order:
        # a column means "the best six left here", and re-sorting it by a
        # score that already folds in scarcity would shuffle the column for a
        # reason the column does not show.
        if len(cols[p["pos"]]) < per_pos:
            cols[p["pos"]].append(row)
        if len(out) > 260:
            break
    out.sort(key=lambda p: -p["score"])
    allowed = [p for p in out if p["allowed"]][:limit]
    blocked = [p for p in out if not p["allowed"]][:2]
    return allowed, blocked, dict(cols)


def wait_advice(allowed, next_pick, safe=60, gone=25):
    """The whole point of knowing the market: do not spend this pick on a
    player the market will leave sitting there.

    Fires only when the top recommendation is likely to survive to your next
    pick AND something else on the list is likely not to. Both halves matter --
    "you can wait" is useless advice unless there is something worth taking
    instead. Silent when ADP does not cover the player, because the fallback
    queue model is not accurate enough to tell someone to pass on a pick.
    """
    if not allowed or not next_pick:
        return None
    top = allowed[0]
    if top.get("surv_src") != "adp" or top["survives"] < safe:
        return None
    alt = next((r for r in allowed[1:]
                if r.get("surv_src") == "adp" and r["survives"] <= gone), None)
    if not alt:
        return None
    return (f"{top['name']} is {top['survives']}% to last to pick {next_pick}; "
            f"{alt['name']} is {alt['survives']}%. Consider taking {alt['name']} "
            f"now and {top['name']} later.")


def directive_cost(allowed, blocked):
    """The honest tension to surface: when the directive is blocking someone
    clearly better than anything it permits, say so and let the user decide.

    Deliberately NOT a warning about the tool's own top recommendation --
    late in a draft the best player left is always worse than the pick number,
    so a rank-versus-pick check fires constantly and means nothing. What stops
    a reach is seeing the cost of each option, which every row carries.
    """
    # Only timing rules are worth arguing with. "Already have 2 TE" is a roster
    # fact, not a decision -- flagging it as expensive would be noise.
    timing = [b for b in blocked if b.get("block_kind") == "timing"]
    if not allowed or not timing:
        return ""
    best_ok = max(allowed, key=lambda r: r["vor"])
    best_blocked = max(timing, key=lambda r: r["vor"])
    gap = best_blocked["vor"] - best_ok["vor"]
    if gap >= 25:
        return (f"Your directive is expensive here: {best_blocked['name']} "
                f"({best_blocked['pos']}) is worth {gap:.0f} more points than "
                f"{best_ok['name']} -- {best_blocked['note']}")
    return ""


# ---------------------------------------------------------------- draft state

class DraftState:
    """Board, picks made, and whose turn it is. Shared by mock and live."""

    def __init__(self, season, league_id, draft_id, my_name, players, teams=12,
                 rounds=15, slot=None):
        self.season, self.league_id, self.draft_id = season, league_id, draft_id
        self.players = players
        self.teams, self.rounds = teams, rounds
        self.my_name = my_name
        self.board, self.levels = build_board(season, players)
        self.by_id = {p["player_id"]: p for p in self.board}
        self.tendencies, self.league_norm = opponent_tendencies()
        self.order = []          # draft slot -> manager display name
        self.slot = slot
        self.picks = []          # [{pick_no, round, slot, manager, player_id}]
        self.taken = set()
        self.rosters = defaultdict(list)
        self.order_known = False
        self.users = {}
        self.my_user_id = None
        self.last_ok = time.time()
        self.lock = threading.Lock()

        # Manual rehearsal: the simulation stops on your pick and waits for you
        # to choose, the way the real draft will.
        # Guests get FACTS -- the value board, the market price, the odds a
        # player lasts. The owner additionally gets COACHING: the directive and
        # the "take him now, take the other one later" tip. That line is drawn
        # deliberately: the facts are all derivable from public data anyway, and
        # the coaching layer is the part built from this league's own history.
        # --share-all hands guests everything.
        self.share_all = True
        self.manual = False
        self.awaiting = False
        self.pending = None
        self.picked = threading.Event()

    def grid(self):
        """The draft board as Sleeper shows it: one column per slot, one row
        per round, snaking left-to-right then right-to-left."""
        by_pick = {p["pick_no"]: p for p in self.picks}
        rows = []
        for rnd in range(1, self.rounds + 1):
            row = []
            for slot in range(1, self.teams + 1):
                offset = slot if rnd % 2 == 1 else (self.teams - slot + 1)
                pk = (rnd - 1) * self.teams + offset
                p = by_pick.get(pk)
                row.append({"pick": pk, "mine": slot == self.slot,
                            "name": p["name"] if p else "",
                            "pos": p["pos"] if p else ""})
            rows.append({"round": rnd, "cells": row})
        return rows

    def available(self, per_pos=12):
        """Best remaining at each position, so you can take someone the
        recommendation list did not surface."""
        out = defaultdict(list)
        for p in self.board:
            if p["player_id"] in self.taken:
                continue
            if len(out[p["pos"]]) < per_pos:
                out[p["pos"]].append(
                    {k: p[k] for k in ("player_id", "name", "pos", "vor", "rank")})
        return dict(out)

    def apply_order(self, draft_order, users, my_user_id):
        """Seat the draft from Sleeper's published order.

        Never invent an order. Sleeper leaves draft_order null until shortly
        before the draft, and a guessed seating silently misfiles every pick,
        mistimes every turn alert, and computes picks-until-next -- which drives
        the whole ranking -- for the wrong seat, for the entire night.
        """
        self.users, self.my_user_id = users, my_user_id
        if not draft_order:
            self.order = [n for n in users.values() if n][:self.teams]
            self.order += [f"slot {i+1}" for i in range(len(self.order), self.teams)]
            self.order_known = False
            return False
        seats = [None] * self.teams
        for uid, slot in draft_order.items():
            if isinstance(slot, int) and 1 <= slot <= self.teams:
                seats[slot - 1] = users.get(uid) or f"slot {slot}"
        self.order = [s or f"slot {i+1}" for i, s in enumerate(seats)]
        mine = draft_order.get(my_user_id)
        if isinstance(mine, int) and 1 <= mine <= self.teams:
            self.slot = mine
        self.order_known = True
        return True

    def force_slot(self, slot):
        """Put yourself in a specific seat. Your slot and your seat in the
        order have to be the same seat or picks land under a stranger."""
        want = min(max(slot, 1), self.teams) - 1
        if self.my_name in self.order:
            here = self.order.index(self.my_name)
            self.order[here], self.order[want] = self.order[want], self.order[here]
        else:
            self.order[want] = self.my_name
        self.slot = want + 1

    # -- geometry -------------------------------------------------------
    def slot_on_clock(self, pick_no):
        """Snake order: odd rounds left to right, even rounds reversed."""
        rnd = (pick_no - 1) // self.teams + 1
        idx = (pick_no - 1) % self.teams
        return (idx + 1) if rnd % 2 == 1 else (self.teams - idx), rnd

    def my_next_pick(self, after, seat=None):
        seat = seat or self.slot
        for pk in range(after, self.teams * self.rounds + 1):
            s, _ = self.slot_on_clock(pk)
            if s == seat:
                return pk
        return None

    def roast(self):
        """The live scorecard. Isolated from advice() on purpose: this is a
        separate page and a bug in the comedy must not be able to take the
        draft board down with it."""
        uid_by_name = {n: u for u, n in (self.users or {}).items()}
        picks = [{"pick_no": p["pick_no"], "round": p["round"],
                  "manager": p["manager"], "player_id": p["player_id"],
                  "player": p.get("name"), "pos": p.get("pos"),
                  "user_id": uid_by_name.get(p["manager"], "")}
                 for p in self.picks]
        rows, standings = scorecard_mod.scorecard(picks, self.season)
        return {"season": self.season, "picks": len(self.picks),
                "rows": rows, "standings": standings,
                "order_known": self.order_known}

    def seat_of(self, name):
        """Slot number for a manager, or None. Used to give each viewer of a
        shared link the recommendations for THEIR seat rather than mine."""
        if not name:
            return None
        for i, n in enumerate(self.order, 1):
            if n == name:
                return i
        return None

    @property
    def current_pick(self):
        # Highest pick seen, not how many we hold: a gap or an out-of-order
        # arrival would otherwise put the clock on the wrong selection.
        return max((p["pick_no"] for p in self.picks), default=0) + 1

    def record(self, pick_no, player_id, manager):
        rnd = (pick_no - 1) // self.teams + 1
        self.picks.append({"pick_no": pick_no, "round": rnd,
                           "manager": manager, "player_id": player_id,
                           "name": self.players.name(player_id),
                           "pos": self.by_id.get(player_id, {}).get("pos", "?")})
        self.taken.add(player_id)
        self.rosters[manager].append(player_id)

    # -- advice ---------------------------------------------------------
    def advice(self, seat=None, strategy=None):
        """Advice from ONE seat's point of view.

        Defaults to my own seat. A shared link passes ?me=<manager> so each
        league member watching sees their own turn timer, their own roster and
        their own picks-until-next -- which drives the whole ranking, so
        serving everyone my seat would give eleven people confidently wrong
        numbers.
        """
        seat = seat or self.slot
        pk = self.current_pick
        if pk > self.teams * self.rounds:
            return {"done": True}
        slot, rnd = self.slot_on_clock(pk)
        on_clock = self.order[slot - 1] if len(self.order) >= slot else f"slot {slot}"
        nxt = self.my_next_pick(pk + 1, seat)
        gap = (nxt - pk) if nxt else 0
        seat_name = (self.order[seat - 1] if len(self.order) >= seat
                     else self.my_name)
        mine = self.rosters[seat_name]
        # The viewer's own choice wins. Falling back to my directive for my
        # seat, and to plain best-available for anyone who has not chosen,
        # keeps every existing caller working unchanged.
        if strategy and strategy in strat_mod.BY_KEY:
            d = strat_mod.to_directive(strategy)
        elif seat == self.slot or self.share_all:
            d = DIRECTIVE
        else:
            d = OPEN_DIRECTIVE
        allowed, blocked, cols = recommend(self.board, self.taken, mine, rnd, pk,
                                           gap, self.league_norm, directive=d)
        counts = roster_counts(mine, self.by_id)
        # What each option costs against the best thing on the board. This is
        # the number that curbs reaching: take row 4 and you see the price.
        # Priced against the highest VOR on offer, not against row one. Rows
        # are ordered by score (which folds in scarcity), so row one is not
        # always the most valuable player and a naive difference goes negative.
        # Priced against the highest VOR the directive allows ANYWHERE, so the
        # figure is comparable across all six columns. Never against row one:
        # rows are ordered by score, which folds in scarcity, so row one is not
        # always the most valuable player and a naive difference goes negative.
        # Blocked tiles get a price too -- showing what the rule costs is the
        # entire reason they stay on screen.
        rows = allowed + [r for col in cols.values() for r in col]
        best = max((r["vor"] for r in rows if r["allowed"]), default=None)
        for r in rows:
            r["cost"] = (round(max(0.0, best - r["vor"]), 1)
                         if best is not None else 0.0)
        # One blue ring on the whole board, on the highest-scoring player the
        # directive allows. Taken from the COLUMNS, never from allowed[0], so
        # the ring can never land on a player who is not on screen.
        # Shipped so a blocked tile can say how much BETTER it is than anything
        # the strategy allows. Clamping that to zero and printing "-0" on the
        # two best players on the board -- which is what Zero RB does to Gibbs
        # and Robinson -- throws away the one number that makes the rule's
        # price legible on the tile itself.
        best_vor = best
        col_ok = [r for col in cols.values() for r in col if r["allowed"]]
        top_id = (max(col_ok, key=lambda r: r["score"])["player_id"]
                  if col_ok else None)
        mine_seat = seat == self.slot
        wait = wait_advice(allowed, nxt) if (mine_seat or self.share_all) else None
        return {
            "done": False, "pick_no": pk, "round": rnd, "slot": slot,
            "on_clock": on_clock, "my_turn": slot == seat,
            "seat": seat, "seat_name": seat_name,
            "managers": list(self.order),
            "picks_until_next": gap,
            "recommend": allowed, "blocked": blocked,
            # One column per position, board order, fully decorated -- this is
            # what the page renders. `recommend` stays as it is because the
            # console renderer, wait_advice and directive_cost all read it as a
            # flat score-ordered list.
            "by_pos": {pos: [{k: r[k] for k in COL_FIELDS} for r in col]
                       for pos, col in cols.items()},
            "top_id": top_id,
            "best_vor": best_vor,
            "per_pos": PER_POS,
            "warn": directive_cost(allowed, blocked),
            "wait": wait,
            "roster": [self.by_id.get(p, {"name": self.players.name(p), "pos": "?",
                                          "vor": 0}) for p in mine],
            "counts": dict(counts),
            "recent": list(reversed(self.picks[-8:])),
            "directive": d["label"],
            "strategy": d.get("key"),
            "order_known": self.order_known,
            "stale": round(time.time() - self.last_ok),
            "manual": self.manual,
            "awaiting": self.awaiting,
            "grid": self.grid(),
            "available": self.available(),
            "teams": self.teams,
            "order": self.order,
            "my_slot": self.slot,
        }


# ------------------------------------------------------------------- mock

def run_mock(state, rng, verbose=True):
    """Simulate the whole draft. Opponents pick from their own tendencies."""
    total = state.teams * state.rounds
    while state.current_pick <= total:
        pk = state.current_pick
        slot, rnd = state.slot_on_clock(pk)
        mgr = state.order[slot - 1]

        if slot == state.slot:
            adv = state.advice()
            choice = adv["recommend"][0] if adv["recommend"] else None
            if verbose and choice:
                print(f"\n  --- YOUR PICK  (round {rnd}, pick {pk}) ---")
                print(f"      next pick in {adv['picks_until_next']} selections")
                for i, r in enumerate(adv["recommend"][:4], 1):
                    a = r.get("adp")
                    adp_s = "  -  " if a is None else f"{a:>5.1f}"
                    back = ("?" if r.get("surv_src") == "queue" and a is None
                            else f"{r['survives']}%")
                    print(f"      {i}. {r['name']:<24}{r['pos']:<4}"
                          f"VOR {r['vor']:>6.0f}  costs {r['cost']:>5.0f}  "
                          f"board #{r['rank']:<5}adp {adp_s}  back {back:>4}")
                for b in adv["blocked"]:
                    print(f"      x  {b['name']:<24}{b['pos']:<4}{b['note']}")
                if adv["warn"]:
                    print(f"      !! {adv['warn']}")
                if adv.get("wait"):
                    print(f"      >> {adv['wait']}")
                print(f"      -> taking {choice['name']} ({choice['pos']})")
            if not choice:
                break
            state.record(pk, choice["player_id"], mgr)
            continue

        pick = bot_pick(state, mgr, rnd, rng)
        if pick is None:
            break
        state.record(pk, pick["player_id"], mgr)
    return state


# Nobody rosters nine receivers. Without these the simulated opponents draft
# absurd shapes, which distorts what is left on the board for you.
BOT_CAPS = {"QB": 2, "TE": 2, "RB": 6, "WR": 6, "K": 1, "DEF": 1}


def market_order(state, pos=None):
    """Available players in the order the MARKET would take them.

    Bots used to take the top of our own value board at the chosen position,
    which quietly made rehearsal a lie: any player we rate above the market
    vanished immediately, so practising against it taught the opposite of who
    really falls. Real drafters take roughly the consensus next man, so the
    simulation should too. No ADP means the market has no opinion -- sort him
    to the back rather than to the front.
    """
    free = [p for p in state.board
            if p["player_id"] not in state.taken
            and (pos is None or p["pos"] == pos)]
    free.sort(key=lambda p: p["adp"] if p.get("adp") is not None else 9999)
    return free


def bot_pick(state, mgr, rnd, rng):
    """One opponent's selection: sample a position from that manager's own
    draft history, respect roster sanity, then take near the top of the
    market at that position."""
    counts = roster_counts(state.rosters[mgr], state.by_id)
    dist = state.tendencies.get(mgr, {}).get(rnd) or state.league_norm.get(rnd, {})
    dist = {p: w for p, w in dist.items()
            if p in SKILL and counts.get(p, 0) < BOT_CAPS.get(p, 99)}
    pos = weighted_pick(dist, rng) if dist else None
    pool = market_order(state, pos) or market_order(state)
    if not pool:
        return None
    # Not strictly the top of the market: real drafts scatter around ADP, and a
    # perfectly obedient bot would make the survival numbers look sharper than
    # they are. Weighted toward the consensus pick, with a tail.
    weights = [0.55, 0.25, 0.12, 0.08][:len(pool)]
    r = rng.random() * sum(weights)
    for i, w in enumerate(weights):
        r -= w
        if r <= 0:
            return pool[i]
    return pool[0]


def weighted_pick(dist, rng):
    items = [(k, v) for k, v in dist.items() if k in SKILL and v > 0]
    if not items:
        return None
    total = sum(v for _, v in items)
    r = rng.random() * total
    for k, v in items:
        r -= v
        if r <= 0:
            return k
    return items[-1][0]


# ------------------------------------------------------------------- live

def poll_live(state, interval=3.0):
    """Follow the real draft. Read-only -- it never makes a pick.

    Picks are tracked by their own pick_no rather than by list length, so one
    arriving out of order or being removed cannot desynchronise the board. The
    whole cycle is wrapped because this thread must not die: if it does, the
    server keeps answering with a frozen board and the page shows confident,
    stale advice with nothing to indicate anything is wrong.
    """
    seen = set()
    while True:
        try:
            if not state.order_known:
                d = get(f"draft/{state.draft_id}")
                if d and d.get("draft_order"):
                    with state.lock:
                        state.apply_order(d["draft_order"], state.users,
                                          state.my_user_id)
                    print(f"  draft order published -- you are slot {state.slot}")

            picks = get(f"draft/{state.draft_id}/picks")
            if picks is None:
                time.sleep(interval)
                continue
            state.last_ok = time.time()

            fresh = [p for p in picks
                     if p.get("pick_no") and p["pick_no"] not in seen
                     and p.get("player_id")]
            if fresh:
                with state.lock:
                    for p in sorted(fresh, key=lambda x: x["pick_no"]):
                        pk = p["pick_no"]
                        # Sleeper stamps each pick with its own slot and owner.
                        # Trust those over anything derived from pick_no.
                        slot = p.get("draft_slot") or state.slot_on_clock(pk)[0]
                        mgr = (state.users.get(p.get("picked_by"))
                               or (state.order[slot - 1]
                                   if 1 <= slot <= len(state.order) else "?"))
                        state.record(pk, str(p["player_id"]), mgr)
                        seen.add(pk)
                print(f"  {len(seen)} picks recorded")

            if len(seen) >= state.teams * state.rounds:
                print("  draft complete")
                return
        except Exception as err:                      # never let the thread die
            print(f"  poll error ({type(err).__name__}: {err}); retrying")
        time.sleep(interval)


# ------------------------------------------------------------------ server

# Interpolated with str.replace, never with %-formatting: this template holds
# literal percent signs (CSS units, "% back" in the JS) and %-formatting reads
# them as format specifiers and raises TypeError.
ROAST_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Draft scorecard</title><style>/*__CSS__*/
.wrap{max-width:1040px}
.gr{display:inline-flex;align-items:center;justify-content:center;width:30px;
  height:30px;border-radius:8px;font-weight:700;font-size:15px;color:#fff;
  flex:0 0 30px}
.gr.A{background:#0ca30c}.gr.B{background:#2a78d6}.gr.C{background:#c98500}
.gr.D{background:#e07020}.gr.F{background:#b02020}
.feed{display:flex;flex-direction:column;gap:8px;margin-top:12px}
.ev{display:flex;gap:12px;align-items:flex-start;background:var(--surface);
  border:1px solid var(--hairline);border-radius:10px;padding:11px 13px}
.ev.rep{border-color:var(--neg)}
.ev .bd{flex:1;min-width:0}
.ev .hd{font-size:12px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.05em}
.ev .hd b{color:var(--ink-2)}
.ev .ln{margin:3px 0 0;font-size:15px;line-height:1.45}
.ev .rec{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;color:var(--neg);margin-left:6px}
.tbl{width:100%;border-collapse:collapse;font-size:14px;
  font-variant-numeric:tabular-nums;margin-top:10px}
.tbl th{text-align:left;font-size:11px;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ink-2);border-bottom:1px solid var(--axis);
  padding:6px 10px 6px 0}
.tbl td{padding:8px 10px 8px 0;border-bottom:1px solid var(--grid)}
.tbl td.n,.tbl th.n{text-align:right}
.tbl tr:first-child td{font-weight:650}
.empty{color:var(--muted);margin-top:14px}
</style></head><body>
<div class="wrap">
<h1>Draft scorecard</h1><p class="sub" id="sub">waiting for the first pick...</p>
<div id="main"></div>
<p class="note" style="margin-top:34px">Grades measure how far ahead of the
market a pick was, in standard deviations fitted on 900 real picks from this
league's own drafts. Kickers and defences are not graded &mdash; their ADP is
noise and reaching there costs nothing. Late rounds are damped, because twelve
picks early in round two burns a starter and twelve picks early in round
thirteen burns nobody. Receipts come from five seasons of this league.</p>
</div>
<script>
const esc = t => String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function feed(rows){
  if(!rows.length) return '<p class="empty">No graded picks yet. Kickers and '+
    'defences do not count, and neither does anyone the market has no opinion '+
    'about.</p>';
  return '<div class="feed">'+rows.slice().reverse().map(function(r){
    return '<div class="ev'+(r.repeat?' rep':'')+'">'+
      '<span class="gr '+r.grade+'">'+r.grade+'</span>'+
      '<div class="bd"><div class="hd">R'+r.round+' pick '+r.pick_no+' &middot; '+
        '<b>'+esc(r.manager)+'</b> &middot; '+esc(r.player)+' ('+esc(r.pos)+') '+
        '&middot; adp '+r.adp+
        (r.repeat?'<span class="rec">receipts</span>':'')+'</div>'+
      '<p class="ln">'+esc(r.line)+'</p></div></div>';
  }).join('')+'</div>';
}

function table(st){
  if(!st.length) return '';
  return '<h2>Standings, worst first</h2><table class="tbl">'+
    '<tr><th>Manager</th><th class="n">Picks</th><th class="n">GPA</th>'+
    '<th class="n">Avg picks early</th><th>Worst crime</th></tr>'+
    st.map(function(m){
      const w = m.worst;
      return '<tr><td>'+esc(m.manager)+'</td><td class="n">'+m.picks+'</td>'+
        '<td class="n">'+m.gpa.toFixed(2)+'</td>'+
        '<td class="n">'+(m.mean_over>0?'+':'')+m.mean_over.toFixed(1)+'</td>'+
        '<td>'+(w?esc(w.player)+' ('+(w.over>0?'+':'')+w.over.toFixed(0)+')':'&mdash;')+
        '</td></tr>';
    }).join('')+'</table>';
}

async function tick(){
  let s;
  try{ s = await (await fetch('/api/scorecard')).json(); }catch(e){ return; }
  const sub = document.getElementById('sub');
  if(s.error){ sub.textContent = 'scorecard error: '+s.error; return; }
  sub.textContent = s.picks+' picks in, '+s.rows.length+' of them graded';
  document.getElementById('main').innerHTML = table(s.standings)+
    '<h2>Every pick, most recent first</h2>'+feed(s.rows);
}
tick(); setInterval(tick, 3000);
</script></body></html>
"""


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Draft advisor</title><style>/*__CSS__*/
/* Wider than the reports: those are set to a reading measure, this has to fit
   a twelve-column draft board without a sideways scroll. */
.wrap{max-width:1380px}
.grid{display:grid;grid-template-columns:1fr 320px;gap:16px;align-items:start}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
/* One column per position, six deep. Every player on screen is pickable. */
.board6{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:0 0 14px}
@media(max-width:1240px){.board6{grid-template-columns:repeat(3,1fr)}}
@media(max-width:760px){.board6{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){.board6{grid-template-columns:1fr}}
/* report.CSS ships a title-case h3 with a 26px top margin, so a column heading
   restates size, case and margin the way .pool h3 already does. nowrap is
   load-bearing, not tidiness: a directive note long enough to wrap pushes that
   one column ~19px below the other five, and the 1241-1300px band packs six
   columns into ~1200px where exactly that happens. */
.poscol h3{margin:0 0 6px;font-size:12px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-2);font-weight:700;
  border-left:3px solid var(--muted);padding-left:7px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.poscol h3.cQB{border-left-color:var(--cQB)}.poscol h3.cRB{border-left-color:var(--cRB)}
.poscol h3.cWR{border-left-color:var(--cWR)}.poscol h3.cTE{border-left-color:var(--cTE)}
.poscol h3.cK{border-left-color:var(--cK)}.poscol h3.cDEF{border-left-color:var(--cDEF)}
.poscol h3 .blk{text-transform:none;letter-spacing:0;font-weight:400;
  color:var(--neg);font-size:11px}
/* The whole tile carries the position, not just an edge. A low-percentage tint
   of the position hue keeps body text at full contrast in both themes, which a
   saturated fill would not. */
.rec{display:block;padding:8px 10px;border-radius:8px;background:var(--surface);
     border:1px solid var(--hairline);border-left:3px solid var(--muted);margin-bottom:6px}
.rec.cQB{background:color-mix(in srgb,var(--cQB) 15%,var(--surface));border-left-color:var(--cQB)}
.rec.cRB{background:color-mix(in srgb,var(--cRB) 15%,var(--surface));border-left-color:var(--cRB)}
.rec.cWR{background:color-mix(in srgb,var(--cWR) 15%,var(--surface));border-left-color:var(--cWR)}
.rec.cTE{background:color-mix(in srgb,var(--cTE) 15%,var(--surface));border-left-color:var(--cTE)}
.rec.cK{background:color-mix(in srgb,var(--cK) 15%,var(--surface));border-left-color:var(--cK)}
.rec.cDEF{background:color-mix(in srgb,var(--cDEF) 15%,var(--surface));border-left-color:var(--cDEF)}
/* Blue is never a position -- it only ever means "the tool is pointing here". */
.rec.top{box-shadow:inset 0 0 0 2px var(--accent);border-color:var(--accent)}
/* Blocked tiles are desaturated, NOT faded. This directive blocks four of six
   positions early, so a 0.45 opacity would put 30 of 36 tiles' numbers at
   roughly 1.5:1 contrast -- unreadable, on a page being read against a pick
   clock. The red note in the column heading is what actually says "blocked". */
.rec.off{filter:saturate(.25)}
.rec.off .nm{color:var(--ink-2);font-weight:500}
.rec .nm{display:block;font-weight:600;font-size:13.5px;line-height:1.25;
     white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rec .mets{display:grid;grid-template-columns:1fr auto;gap:1px 8px;margin-top:5px;
     font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.rec .mets span:nth-child(even){text-align:right}
.rec .mets b{color:var(--ink);font-weight:600}

.offline{display:none;background:var(--neg);color:#fff;padding:10px 14px;border-radius:8px;margin:10px 0;font-weight:600}
.seatbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:10px 0 4px}
.seatbar .lbl{font-size:12px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);margin-right:4px}
.seatbar button{font:inherit;font-size:13px;padding:4px 10px;border-radius:999px;
  border:1px solid var(--hairline);background:var(--surface);color:var(--ink-2);
  cursor:pointer}
.seatbar button:hover{border-color:var(--accent)}
.seatbar button.sel{background:var(--accent);border-color:var(--accent);
  color:#fff;font-weight:600}
.wait-tip{background:var(--surface);border:1px solid var(--accent);
  color:var(--ink);padding:10px 14px;border-radius:8px;margin-bottom:8px;font-size:14px}
.warn{background:var(--neg);color:#fff;padding:10px 14px;border-radius:8px;
      font-weight:600;margin:10px 0}
.turn{background:var(--accent);color:#fff;padding:14px 16px;border-radius:10px;
      font-size:18px;font-weight:600;margin-bottom:12px}
.wait{background:var(--surface);border:1px solid var(--hairline);padding:14px 16px;
      border-radius:10px;margin-bottom:12px;color:var(--ink-2)}
.blocked{opacity:.55;font-size:13px;padding:4px 12px}
.chip{display:inline-block;background:var(--surface);border:1px solid var(--hairline);
      border-radius:999px;padding:2px 10px;margin:2px 4px 2px 0;font-size:13px}

/* Position hues: reference palette slots 1-6, fixed order, never cycled.
   Every cell also carries the position as text, so colour is never the only
   thing telling you what a player is. Quarterbacks are purple rather than
   blue: blue is reserved for "the tool is pointing here" (the .rec.top ring,
   the turn banner, the selected seat), and the old --cQB was byte-identical
   to --accent, which made a ringed quarterback ambiguous. */
:root{--cQB:#4a3aa7;--cRB:#eb6834;--cWR:#1baf7a;--cTE:#eda100;--cK:#e87ba4;--cDEF:#008300}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --cQB:#9085e9;--cRB:#d95926;--cWR:#199e70;--cTE:#c98500;--cK:#d55181;--cDEF:#008300}}
:root[data-theme="dark"]{
  --cQB:#9085e9;--cRB:#d95926;--cWR:#199e70;--cTE:#c98500;--cK:#d55181;--cDEF:#008300}

/* Landing page: pick a seat, then pick a plan. Card per approach with its
   grade against this league, and the full write-up for whichever is selected. */
.card{background:var(--surface);border:1px solid var(--hairline);
  border-radius:10px;padding:18px;margin-top:12px}
.card h3{margin:0 0 4px;font-size:12px;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ink-2)}
.row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 4px}
.row button{font:inherit;cursor:pointer;border-radius:8px;
  border:1px solid var(--hairline);background:var(--page);color:var(--ink);
  padding:9px 14px}
.row button:hover{border-color:var(--accent)}
.row button.sel{background:var(--accent);color:#fff;border-color:var(--accent);
  font-weight:600}
button.primary{font:inherit;background:var(--accent);color:#fff;
  border:1px solid var(--accent);border-radius:8px;font-weight:600;
  padding:11px 22px;font-size:16px;cursor:pointer}
button.primary:disabled{opacity:.45;cursor:not-allowed}
.strats{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:9px}
.strat{border:1px solid var(--hairline);border-radius:9px;padding:10px 12px;
  background:var(--page);cursor:pointer}
.strat:hover{border-color:var(--accent)}
.strat.sel{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);
  background:var(--surface)}
.strat .sh{display:flex;align-items:center;gap:8px}
.strat .sn{font-weight:600;font-size:14px}
.strat .so{margin:6px 0 0;font-size:12px;color:var(--ink-2);line-height:1.4}
.grade{font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;
  letter-spacing:.02em;color:#fff;background:var(--muted)}
.grade.gA{background:#0ca30c}.grade.gB{background:#2a78d6}
.grade.gC{background:#c98500}.grade.gD{background:#e34948}
.grade.gF{background:#b02020}
.sdetail{margin-top:12px;padding-top:12px;border-top:1px solid var(--grid)}
.sdetail h4{margin:0 0 6px;font-size:15px;display:flex;align-items:center;gap:8px}
.sdetail p{margin:0 0 8px;font-size:13.5px;color:var(--ink-2);max-width:70ch}
.dens{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.dens .d{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--surface);
  border:1px solid var(--hairline);border-left-width:3px;color:var(--ink-2)}
.dens .d b{color:var(--ink);font-variant-numeric:tabular-nums}
.pick-on .rec{cursor:pointer}
/* Hover must restore a blocked tile to full colour: blocked tiles stay
   clickable, because the directive exists to show a cost, not to stop you. */
.pick-on .rec:hover{filter:brightness(1.06);border-color:var(--accent)}
.pick-on .rec:hover .nm{color:var(--ink);font-weight:600}

.board{overflow-x:auto;padding-bottom:6px}
.board table{border-collapse:separate;border-spacing:3px;width:auto;font-size:11px}
.board th{font-size:10px;font-weight:600;padding:1px 4px;border:none;
          color:var(--muted);text-transform:none;letter-spacing:0;white-space:nowrap}
.board th.me{color:var(--accent)}
.board td{padding:0;border:none}
.rd{color:var(--muted);font-variant-numeric:tabular-nums;padding-right:4px}
.cell{width:104px;height:32px;border-radius:5px;background:var(--surface);
      border:1px solid var(--hairline);border-left:3px solid var(--muted);
      padding:3px 6px;overflow:hidden;line-height:1.2}
.cell.empty{background:transparent;border-style:dashed;border-left-color:var(--hairline)}
.cell.mine{box-shadow:inset 0 0 0 1px var(--accent)}
.cell .n{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
         font-weight:600;color:var(--ink)}
.cell .p{color:var(--muted);font-size:10px}
.cQB{border-left-color:var(--cQB)}.cRB{border-left-color:var(--cRB)}
.cWR{border-left-color:var(--cWR)}.cTE{border-left-color:var(--cTE)}
.cK{border-left-color:var(--cK)}.cDEF{border-left-color:var(--cDEF)}

.pool{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.pool h3{margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.av{padding:3px 8px;border-radius:5px;font-size:13px;display:flex;gap:8px;
    border-left:3px solid var(--muted)}
.pick-on .av{cursor:pointer}
.pick-on .av:hover{background:var(--surface)}
.av .v{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums;font-size:12px}
</style></head><body><div class="wrap">
<h1>Draft advisor</h1><p class="sub" id="sub">connecting...</p>
<p class="note" style="margin:2px 0 0"><a href="/roast" target="_blank"
 style="color:var(--accent)">Open the draft scorecard</a> &mdash; every pick
 graded as it lands. It is not kind.</p><div id="seatbar"></div><div id="offline" class="offline"></div>
<div id="main"></div></div>
<script>
const esc = t => String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function pick(pid){
  try{
    const r = await fetch('/api/pick', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({player_id:String(pid)})});
    if(r.ok) tick();
  }catch(e){}
}

function board(s){
  let head = '<tr><th></th>';
  for(let i=0;i<s.teams;i++){
    const nm = (s.order[i]||('slot '+(i+1)));
    head += '<th class="'+(i+1===s.my_slot?'me':'')+'">'+esc(nm.slice(0,13))+'</th>';
  }
  head += '</tr>';
  const rows = s.grid.map(r =>
    '<tr><td class="rd">'+r.round+'</td>'+ r.cells.map(c =>
      '<td><div class="cell '+(c.pos?'c'+c.pos:'empty')+(c.mine?' mine':'')+'">'+
      (c.name ? '<span class="n">'+esc(c.name)+'</span><span class="p">'+esc(c.pos)+'</span>'
              : '<span class="p">'+c.pick+'</span>')+
      '</div></td>').join('') + '</tr>').join('');
  return '<div class="board"><table>'+head+rows+'</table></div>';
}

/* One column per position, PER_POS deep -- the best six left at EVERY
   position, not the best six overall. A cross-position list collapses onto
   whichever position happens to be deepest and hides the choice you are
   actually making. Fed by s.by_pos, which the server fills in board order. */
const POS = ['QB','RB','WR','TE','K','DEF'];

function costLabel(x, s){
  const bv = s.best_vor;
  if(!x.allowed && bv != null && x.vor > bv + 0.5)
    return '+<b>'+(x.vor - bv).toFixed(0)+'</b>';
  if(x.allowed && x.cost < 0.5) return '<b>best</b>';
  return '-<b>'+x.cost.toFixed(0)+'</b>';
}

function columns(s, live){
  const bp = s.by_pos || {};
  let top = null;
  POS.forEach(function(p){
    (bp[p]||[]).forEach(function(x){ if(x.player_id===s.top_id) top = x; });
  });
  return '<p class="note" style="margin:0 0 10px">The best '+(s.per_pos||6)+
    ' left at every position'+(live?' \\u2014 click any of them to draft him':'')+'. '+
    (top?'Best value on the board right now: <b>'+esc(top.name)+'</b> ('+
      esc(top.pos)+', VOR '+top.vor.toFixed(0)+').':'')+'</p>'+
    '<div class="board6">'+POS.map(function(p){
      const list = bp[p] || [];
      if(!list.length) return '';
      /* A directive rule blocks a whole position at once, so the top player's
         reason stands for the entire column -- which is why the old flat
         blocked list underneath is gone: it only ever repeated these. */
      const blk = list[0].allowed ? '' : list[0].note;
      return '<div class="poscol"><h3 class="c'+p+'">'+p+
        (blk?' <span class="blk" title="'+esc(blk)+'">'+esc(blk)+'</span>':'')+'</h3>'+
        list.map(function(x){
          /* Blocked tiles stay clickable on purpose -- the directive is there
             to show a cost, not to stop you. The server refuses the POST
             outside rehearsal anyway. */
          return '<div class="rec c'+p+(x.allowed?'':' off')+
            (x.player_id===s.top_id?' top':'')+'"'+
            (live?' onclick="pick(\\''+x.player_id+'\\')"':'')+'>'+
            '<span class="nm">'+esc(x.name)+'</span>'+
            '<div class="mets">'+
              '<span>VOR <b>'+x.vor.toFixed(0)+'</b></span>'+
              '<span>#'+x.rank+'</span>'+
              '<span>adp <b>'+(x.adp==null?'-':x.adp.toFixed(1))+'</b></span>'+
              /* "best" only ever on an ALLOWED tile: `best` is the max VOR
                 among allowed rows, so a blocked player above that mark would
                 otherwise print "best" too and two tiles would claim it at
                 once. The 0.5 floor stops a 0.4 cost rendering as "-0". */
              /* "best" only ever on an ALLOWED tile: `cost` is measured
                 against the best VOR the strategy permits, so a blocked player
                 above that mark also prices to zero. Those are the ones worth
                 the most, so show what the rule is costing (+N) rather than a
                 meaningless "-0". */
              '<span>'+costLabel(x, s)+'</span>'+
              '<span><b>'+x.survives+'%</b> back</span><span></span>'+
            '</div></div>';
        }).join('')+'</div>';
    }).join('')+'</div>';
}

/* Position density at a glance. The mock fills this cell with a full starting
   lineup table; this is the cheap half of it, and it answers the question that
   actually matters mid-draft -- how many of each do I already have. */
function density(s){
  const c = s.counts || {};
  return '<div class="dens">'+POS.map(function(p){
    return '<span class="d c'+p+'">'+p+' <b>'+(c[p]||0)+'</b></span>';
  }).join('')+'</div>';
}

function pool(s, live){
  /* Starts where the board stops. available[] is the same VOR-sorted board
     sliced per position, so its first PER_POS entries are byte-identical to
     the columns above -- rendering from 0 would print the whole board twice. */
  const skip = s.per_pos || 6;
  return '<div class="pool">'+POS.map(p=>{
    const list = (s.available[p]||[]).slice(skip, skip+8).map(a =>
      '<div class="av c'+p+'"'+(live?' onclick="pick(\\''+a.player_id+'\\')"':'')+'>'+
      '<span>'+esc(a.name)+'</span><span class="v">'+a.vor.toFixed(0)+'</span></div>').join('');
    return list ? '<div><h3>'+p+'</h3>'+list+'</div>' : '';
  }).join('')+'</div>';
}

/* The strategy catalogue is baked in at server start rather than shipped on
   every poll: it is static, and its long copy would add ~8 KB to a request
   made every 1.5 seconds. */
const STRATEGIES = /*__STRATEGIES__*/;

/* Which seat this browser watches from, and which plan it is drafting to.
   Both live in the URL so a link can be sent pre-aimed, and in localStorage so
   a refresh mid-draft does not dump anyone back onto somebody else's view. */
var Q0 = new URLSearchParams(location.search);
var SEAT = Q0.get('me') || localStorage.getItem('ff_seat') || '';
var STRAT = Q0.get('strategy') || localStorage.getItem('ff_strategy') || '';
/* Chosen but not yet started, so the setup screen can show a selection before
   it is committed. */
var PICK_SEAT = SEAT, PICK_STRAT = STRAT;

function setupDone(){ return !!(SEAT && STRAT); }

function saveChoice(){
  SEAT = PICK_SEAT; STRAT = PICK_STRAT;
  try{
    localStorage.setItem('ff_seat', SEAT);
    localStorage.setItem('ff_strategy', STRAT);
  }catch(e){}
  var u = new URL(location);
  u.searchParams.set('me', SEAT);
  u.searchParams.set('strategy', STRAT);
  history.replaceState(null, '', u);
  tick();
}
function chooseSeat(v){ PICK_SEAT = v; renderSetup(LAST); }
function chooseStrat(v){ PICK_STRAT = v; renderSetup(LAST); }
function reopenSetup(){
  PICK_SEAT = SEAT; PICK_STRAT = STRAT;
  SEAT = ''; STRAT = '';
  renderSetup(LAST);
}

var LAST = null;   /* most recent state, so the setup screen can re-render */

function gradeClass(g){ return 'g' + (g || '').charAt(0); }

function renderSetup(s){
  const mgrs = (s && s.managers) || [];
  const chosen = STRATEGIES.filter(function(x){ return x.key === PICK_STRAT; })[0];
  document.getElementById('seatbar').innerHTML = '';
  document.getElementById('main').innerHTML =
    '<div class="card"><h3>1. Which manager are you?</h3><div class="row">'+
      mgrs.map(function(m){
        return '<button data-v="'+esc(m)+'" onclick="chooseSeat(this.dataset.v)"'+
          (m===PICK_SEAT?' class="sel"':'')+'>'+esc(m)+'</button>';
      }).join('')+
      '</div><p class="note">Your draft slot is filled in from the real order.</p>'+
    '</div>'+
    '<div class="card"><h3>2. Strategy</h3>'+
      '<p class="note" style="margin-top:0">Graded against <b>this</b> league '+
      '&mdash; 12 teams, full PPR, one quarterback, two flex spots. The grade '+
      'is about fit here, not whether the strategy is any good in general.</p>'+
      '<div class="strats">'+STRATEGIES.map(function(x){
        return '<div class="strat'+(x.key===PICK_STRAT?' sel':'')+
          '" data-v="'+esc(x.key)+'" onclick="chooseStrat(this.dataset.v)">'+
          '<div class="sh"><span class="grade '+gradeClass(x.grade)+'">'+
          esc(x.grade)+'</span><span class="sn">'+esc(x.label)+'</span></div>'+
          '<p class="so">'+esc(x.one)+'</p></div>';
      }).join('')+'</div>'+
      (chosen ? '<div class="sdetail"><h4><span class="grade '+
        gradeClass(chosen.grade)+'">'+esc(chosen.grade)+'</span>'+
        esc(chosen.label)+'</h4><p>'+esc(chosen.detail)+'</p>'+
        '<p><b>For this league:</b> '+esc(chosen.verdict)+'</p></div>' : '')+
    '</div>'+
    '<p style="margin-top:18px"><button class="primary" onclick="saveChoice()"'+
      (PICK_SEAT && PICK_STRAT ? '' : ' disabled')+'>'+
      (PICK_SEAT && PICK_STRAT ? 'Start advising for '+esc(PICK_SEAT)
                               : 'Pick a manager and a strategy')+'</button></p>';
}
function setSeat(v){
  SEAT = v; try{ localStorage.setItem('ff_seat', v); }catch(e){}
  var u = new URL(location); u.searchParams.set('me', v);
  history.replaceState(null, '', u); tick();
}
function seatBar(s){
  if(!s.managers || !s.managers.length) return '';
  return '<div class="seatbar"><span class="lbl">Watching as</span>'+
    '<button onclick="reopenSetup()" title="Change seat or strategy">'+
      esc(s.seat_name || SEAT)+' · '+esc(s.directive)+' ⚙</button>'+
    '<span class="lbl" style="margin-left:8px">or jump to</span>'+
    s.managers.map(function(m){
      /* Read the name back off the dataset rather than interpolating it into
         a JS string literal -- a manager display name is user-controlled and
         an apostrophe would break out of the handler. */
      return '<button data-seat="'+esc(m)+'" onclick="setSeat(this.dataset.seat)"'+
        (m===s.seat_name?' class="sel"':'')+'>'+esc(m)+'</button>';
    }).join('')+'</div>';
}

/* A dropped connection used to leave the last render on screen with nothing to
   say it was frozen -- a board that is confidently three rounds out of date is
   worse than an obviously broken one, especially for a guest on a tunnel that
   died. Two misses in a row and the page says so. */
var MISSES = 0;
function offline(on){
  var el = document.getElementById('offline');
  if(!el) return;
  el.style.display = on ? 'block' : 'none';
  el.textContent = on
    ? 'Lost connection to the draft board. These numbers are frozen and may be '
      + 'out of date. Trying to reconnect...'
    : '';
}

async function tick(){
  let s;
  try{
    const resp = await fetch('/api/state?me='+encodeURIComponent(SEAT)+
                             '&strategy='+encodeURIComponent(STRAT));
    if(!resp.ok) throw new Error('http '+resp.status);
    s = await resp.json();
    MISSES = 0; offline(false);
  }catch(e){
    if(++MISSES >= 2) offline(true);
    return;
  }
  LAST = s;
  /* Nothing renders until a seat and a plan are chosen. Guessing either would
     be worse than asking: picks-until-next drives the whole ranking, and a
     strategy silently defaulted to mine would give someone else confident
     advice built around my roster. */
  if(!setupDone()){
    document.getElementById('sub').textContent =
      'Pick your seat and your plan to begin';
    renderSetup(s);
    return;
  }
  const sub = document.getElementById('sub');
  if(s.done){
    sub.textContent = 'Draft complete';
    document.getElementById('main').innerHTML = '<h2>Draft complete</h2>'+board(s);
    return;
  }
  sub.textContent = 'Round '+s.round+' \\u00b7 pick '+s.pick_no+' \\u00b7 '+s.directive;
  var sb = document.getElementById('seatbar');
  if(sb) sb.innerHTML = seatBar(s);
  const live = !!(s.manual && s.awaiting && s.my_turn);
  document.body.className = live ? 'pick-on' : '';

  const roster = s.roster.map(p=>
    '<span class="chip">'+esc(p.pos)+' '+esc(p.name)+'</span>').join('');
  const recent = s.recent.map(p=>
    '<div class="blocked">'+p.pick_no+'. '+esc(p.manager)+' \\u2014 '+
    esc(p.name)+' ('+esc(p.pos)+')</div>').join('');
  const alerts =
    (s.order_known===false
      ? '<div class="warn">Sleeper has not published the draft order yet \\u2014 '+
        'whose turn it is and how long until yours are not reliable until it does.</div>' : '')+
    (s.stale>15
      ? '<div class="warn">No update from Sleeper for '+s.stale+'s \\u2014 this board '+
        'may be stale. Check the Sleeper app.</div>' : '');

  document.getElementById('main').innerHTML = alerts+
    (live ? '<div class="turn">YOUR PICK \\u2014 round '+s.round+', pick '+s.pick_no+
            '. Click a player to draft him.</div>'
     : s.my_turn ? '<div class="turn">YOU ARE ON THE CLOCK \\u2014 pick '+s.pick_no+'</div>'
                 : '<div class="wait">'+esc(s.on_clock)+' is picking. You are up in '+
                   s.picks_until_next+'.</div>')+
    (s.warn ? '<div class="warn">'+esc(s.warn)+'</div>' : '')+
    (s.wait ? '<div class="wait-tip">'+esc(s.wait)+'</div>' : '')+
    /* The board goes full width. Six columns inside a 1fr that is also
       carrying a 320px rail come out ~160px each and the metrics collapse into
       unreadable digits, so roster and recent picks drop below it. Recent
       picks takes the wide cell because it is the taller of the two -- the
       other way round leaves a quarter-screen of dead space. */
    '<h2>Take one of these</h2>'+columns(s, live)+
    '<div class="grid"><div><h2>Recent picks</h2>'+recent+'</div>'+
    '<div><h2>Your roster</h2>'+density(s)+'<div>'+
      (roster||'<span class="sub">empty</span>')+'</div></div></div>'+
    '<h2>Deeper at every position</h2>'+
    '<p class="note" style="margin:0 0 10px">Everyone below the six above, so '+
    'you are never limited to what the board surfaced.</p>'+pool(s, live)+
    '<h2>Draft board</h2>'+board(s);
}
tick(); setInterval(tick, 1500);
</script></body></html>"""


def serve(state, host, port, open_browser=True, share=False,
          aggressive=False):
    from report import CSS
    cards = [{k: st[k] for k in ("key", "label", "grade", "one", "detail",
                                 "verdict")} for st in strat_mod.STRATEGIES]
    roast_page = ROAST_PAGE.replace("/*__CSS__*/", CSS).encode("utf-8")
    page = (PAGE.replace("/*__CSS__*/", CSS)
                .replace("/*__STRATEGIES__*/", json.dumps(cards))
                .encode("utf-8"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/scorecard"):
                try:
                    with state.lock:
                        body = json.dumps(state.roast()).encode("utf-8")
                except Exception as err:            # noqa: BLE001
                    # The scorecard is entertainment; the draft board is not.
                    # It fails to an error payload rather than a 500 so a bad
                    # line can never look like the server going down.
                    body = json.dumps({"error": f"{type(err).__name__}: {err}",
                                       "rows": [], "standings": []}).encode()
                self._send(200, body, "application/json")
                return
            if self.path.startswith("/roast"):
                self._send(200, roast_page, "text/html; charset=utf-8")
                return
            if self.path.startswith("/api/state"):
                q = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                who = (q.get("me") or [""])[0]
                strat = (q.get("strategy") or [""])[0]
                with state.lock:
                    seat = state.seat_of(who)
                    body = json.dumps(state.advice(seat, strat)).encode("utf-8")
                self._send(200, body, "application/json")
            else:
                self._send(200, page, "text/html; charset=utf-8")

        def do_POST(self):
            """Your pick, in rehearsal mode. Rejected unless the simulation is
            actually waiting on you and the player is genuinely available."""
            # Rehearsal only. `awaiting` is never true in a live draft, so this
            # was already inert -- but the link is now shareable, and a public
            # endpoint that mutates draft state should be refused outright
            # rather than left to a state flag several call frames away.
            if not state.manual or not self.path.startswith("/api/pick"):
                self._send(404, b'{"ok":false}', "application/json")
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                pid = str(json.loads(self.rfile.read(n) or b"{}").get("player_id") or "")
            except (ValueError, json.JSONDecodeError):
                pid = ""
            with state.lock:
                ok = bool(state.awaiting and pid in state.by_id
                          and pid not in state.taken)
                if ok:
                    state.pending = pid
            if ok:
                state.picked.set()
            self._send(200 if ok else 409,
                       json.dumps({"ok": ok}).encode("utf-8"), "application/json")

    # Threaded: twelve people polling twice a second against a single-threaded
    # server serialises every request behind the slowest one.
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    tun = None
    if share:
        tun = Tunnel(port, aggressive)
        tun.start()
        atexit.register(tun.stop)
    url = f"http://localhost:{port}"
    print(f"  advisor running at {url}")
    if host == "0.0.0.0":
        print(f"  on your phone (same wifi): http://<this-machine-ip>:{port}")
        print("  reachable by anything on your network -- stop it after the draft")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")


# -------------------------------------------------------------------- main

def setup(args):
    index = _load("index.json")
    if not index:
        raise SystemExit("No data. Run: python pull.py")
    me = index["username"]
    season = args.season or max(s["season"] for s in index["seasons"])
    league_id = next(s["league_id"] for s in index["seasons"] if s["season"] == season)

    global DRAFT_REPLACEMENT, SKILL
    players = Players()
    league = get(f"league/{league_id}") or {}
    teams = league.get("total_rosters", 12)

    # Board depth comes from this league's roster settings, not an assumed
    # format. A 10-team or superflex league needs different numbers entirely.
    cached = Season(season, league_id)
    derived = replacement_ranks(cached)
    if derived:
        DRAFT_REPLACEMENT = derived
        SKILL = tuple(derived)

    drafts = get(f"league/{league_id}/drafts") or []
    if not drafts:
        raise SystemExit(f"No draft found for {season}.")
    d = drafts[0]
    rounds = (d.get("settings") or {}).get("rounds", 15)

    state = DraftState(season, league_id, d["draft_id"], me, players,
                       teams=teams, rounds=rounds)

    users = {u["user_id"]: u.get("display_name") for u in
             (get(f"league/{league_id}/users") or [])}
    if not users:
        raise SystemExit(
            "Could not read the league's members from Sleeper. Check your\n"
            "connection and run it again -- continuing without them would file\n"
            "every pick under the wrong manager.")

    published = state.apply_order(d.get("draft_order"), users, index["user_id"])
    if args.slot:
        state.force_slot(args.slot)
    elif not published:
        state.slot = state.order.index(me) + 1 if me in state.order else 1

    if not published:
        print("  ! Sleeper has not published the draft order yet.")
        if args.mock:
            print("    Mock will seat you at slot "
                  f"{state.slot} -- pass --slot N to try another.")
        else:
            print("    Watching for it; advice is not seat-specific until it lands.")
    print(f"  {season} draft {d['draft_id']} | {teams} teams x {rounds} rounds")
    print(f"  you are {me}, slot {state.slot} | directive: {DIRECTIVE['label']}")
    return state


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true", help="simulate instead of following the real draft")
    ap.add_argument("--serve", action="store_true", help="run the browser UI")
    ap.add_argument("--slot", type=int, help="your draft slot (1-12)")
    ap.add_argument("--season", help="defaults to the newest season")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from your phone")
    ap.add_argument("--share", action="store_true",
                    help="expose a public link via cloudflared (read-only)")
    ap.add_argument("--watchdog", action="store_true",
                    help="auto-restart the tunnel if health checks fail "
                         "(changes the link address)")
    ap.add_argument("--private-coaching", action="store_true",
                    help="keep your directive and wait advice off the shared link")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--seed", type=int, default=None, help="repeat a mock draft exactly")
    ap.add_argument("--no-open", action="store_true", help="do not launch a browser")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="seconds per simulated pick (default 3)")
    ap.add_argument("--manual", action="store_true",
                    help="rehearsal: the mock stops on your pick and waits for you")
    args = ap.parse_args()

    state = setup(args)
    state.manual = bool(args.manual and args.mock and args.serve)
    state.share_all = not args.private_coaching
    if args.manual and not (args.mock and args.serve):
        print("  ! --manual needs --serve --mock; ignoring it")
    if state.manual:
        print("  rehearsal mode: the simulation will wait for you on your picks")
    rng = random.Random(args.seed)

    if args.serve:
        if args.mock:
            threading.Thread(target=lambda: mock_loop(state, rng, args.delay),
                             daemon=True).start()
        else:
            threading.Thread(target=lambda: poll_live(state), daemon=True).start()
        serve(state, args.host, args.port, open_browser=not args.no_open,
              share=args.share, aggressive=args.watchdog)
    elif args.mock:
        run_mock(state, rng)
        summarize(state)
    else:
        print("  following the live draft (ctrl-c to stop)")
        poll_live(state)


def mock_loop(state, rng, delay):
    """Advance a simulated draft one pick at a time so the UI can be watched."""
    total = state.teams * state.rounds
    while state.current_pick <= total:
        pk = state.current_pick
        slot, rnd = state.slot_on_clock(pk)
        mgr = state.order[slot - 1]
        if slot == state.slot:
            if state.manual:
                # Hand the pick to the user and wait. The lock is deliberately
                # not held here -- the server needs it to answer /api/state
                # while we wait, or the page would freeze on your own turn.
                with state.lock:
                    state.awaiting = True
                state.picked.clear()
                while not state.picked.wait(timeout=0.25):
                    pass
                with state.lock:
                    choice = state.by_id.get(state.pending)
                    state.pending, state.awaiting = None, False
                if choice is None:
                    continue
            else:
                time.sleep(delay * 2)   # linger so the recommendation is readable
                adv = state.advice()
                if not adv.get("recommend"):
                    return
                choice = adv["recommend"][0]
        else:
            time.sleep(delay)
            choice = bot_pick(state, mgr, rnd, rng)
            if choice is None:
                return
        with state.lock:
            state.record(pk, choice["player_id"], mgr)
            state.last_ok = time.time()   # a mock pick is fresh information too


def summarize(state):
    mine = state.rosters[state.my_name]
    print("\n" + "=" * 62)
    print(f"  YOUR TEAM  ({DIRECTIVE['label']})")
    print("=" * 62)
    counts = defaultdict(int)
    total = 0.0
    for i, pid in enumerate(mine, 1):
        p = state.by_id.get(pid, {})
        counts[p.get("pos", "?")] += 1
        total += p.get("proj", 0)
        print(f"    R{i:<3}{p.get('name','?')[:26]:<28}{p.get('pos','?'):<5}"
              f"proj {p.get('proj',0):>6.1f}   VOR {p.get('vor',0):>+6.0f}")
    print(f"\n    shape: " + "  ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"    projected total: {total:.0f}")
    first_qb = next((i for i, pid in enumerate(mine, 1)
                     if state.by_id.get(pid, {}).get("pos") == "QB"), None)
    print(f"    first QB: round {first_qb}" if first_qb else "    no QB drafted")


if __name__ == "__main__":
    main()

