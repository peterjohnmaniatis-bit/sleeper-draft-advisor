#!/usr/bin/env python3
"""Live draft scorecard: every pick graded as it lands, with receipts.

Two signals, both chosen by the owner:

  REACH        how far ahead of the market a pick was, measured in the standard
               deviations that adp.py fitted on this league's own 900 picks --
               so "10 picks early" in round one (sd 1.7) is a very different
               crime from ten picks early in round eleven (sd 15.8), and the
               grade knows the difference.
  REPETITION   whether the manager has done this exact thing before, from
               grudges.py. A reach is funny; a reach by someone whose career
               mean is already +12.5 against a league +4.0 is funnier, and it
               is the difference between an insult and a fact.

Deliberately NOT graded: value left on the board and roster construction. Both
were considered and dropped -- the scorecard is sharper for having two things
to say well than four things to say vaguely.

The copy is blunt by request. It only ever mocks a DECISION: never a username,
never a person. See LINES in scorecard_lines.py.
"""

import json
import statistics
import sys
from pathlib import Path

import adp as adp_mod
from scorecard_lines import LINES, pick_line

ROOT = Path(__file__).resolve().parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# A reach only counts once it clears the noise the market itself carries.
MILD_SD, BAD_SD = 1.0, 2.0
VALUE_SD = 1.0            # taken this far AFTER his ADP is genuine value

# Kickers and defences are not graded. Their ADP is close to noise, and more to
# the point a reach there costs nothing -- the alternative was a different
# kicker. Without this the scorecard crowns a round-14 kicker the worst crime of
# the night, which is both wrong and not funny.
UNGRADED_POS = {"K", "DEF"}

# What a reach COSTS depends on where it happens. Twelve picks early in round
# two burns a starter; twelve picks early in round thirteen burns a bench flier
# nobody will remember. Same standard deviations, wildly different crime, so
# severity is damped as the rounds get cheap.
def round_weight(rnd):
    if not rnd or rnd <= 6:
        return 1.0
    if rnd <= 10:
        return 0.7
    return 0.4


def load_grudges():
    p = ROOT / "data" / "grudges.json"
    if not p.exists():
        return {"league_mean_over": 4.0, "managers": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def grade_for(sd_over):
    """Letter grade from how far ahead of market the pick was.

    Grading the REACH rather than the player is deliberate: whether a player
    turns out good is unknowable tonight, but whether you paid more than you
    had to is knowable the instant the pick lands.
    """
    if sd_over <= -VALUE_SD:
        return "A"
    if sd_over <= 0.35:
        return "B"
    if sd_over <= MILD_SD:
        return "C"
    if sd_over <= BAD_SD:
        return "D"
    return "F"


GPA = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}


def _band_sd(a):
    """The fitted spread at this ADP, from adp.py's measured bands."""
    for hi, _bias, sd in adp_mod.BANDS:
        if a <= hi:
            return sd
    return adp_mod.BANDS[-1][2]


def score_pick(pick, market, grudges, seen_counts):
    """Grade one completed pick. Returns None when ADP cannot price it.

    A player with no ADP is not a reach -- he is a player the market has no
    opinion about, which is a different thing and must not be graded as though
    it were the same.
    """
    pid = str(pick.get("player_id") or "")
    a = market.get(pid)
    if a is None or a > adp_mod.ADP_HORIZON:
        return None
    if (pick.get("pos") or "") in UNGRADED_POS:
        return None
    over = a - pick["pick_no"]           # positive = taken EARLY
    sd = _band_sd(a)
    raw_sd = over / sd if sd else 0.0
    sd_over = raw_sd * round_weight(pick.get("round"))
    g = grade_for(sd_over)

    uid = pick.get("user_id") or ""
    hist = (grudges.get("managers") or {}).get(str(uid)) or {}
    league_mean = grudges.get("league_mean_over", 4.0)

    ctx = {
        "mgr": pick.get("manager") or "somebody",
        "player": pick.get("player") or "that guy",
        "pos": pick.get("pos") or "?",
        "rnd": pick.get("round") or 0,
        "pick": pick["pick_no"],
        "adp": f"{a:.1f}",
        "over": max(0, round(over)),
        "late": max(0, round(-over)),
        "sd": f"{abs(sd_over):.1f}",
        "mean_over": (f"{hist['mean_over']:+.1f}"
                      if hist.get("mean_over") is not None else "+0.0"),
        "league": f"{league_mean:+.1f}",
    }

    # Which bucket of copy this pick earns. A pick that was EARLY never gets
    # value copy, even when late-round damping spares it a bad grade -- the
    # grade forgives it, the sentence must still describe it honestly.
    if sd_over >= BAD_SD:
        cat = "reach-brutal"
    elif sd_over >= MILD_SD or over >= 3:
        cat = "reach-mild"
    else:
        cat = "value-and-credit"

    # A repeat offence outranks a plain reach: it is the better joke and the
    # more useful observation. Only fires when the receipt actually exists.
    repeat = repeat_context(pick, hist, sd_over, seen_counts)
    if repeat:
        ctx.update(repeat)
        cat = "repeat"

    return {
        "pick_no": pick["pick_no"], "round": pick.get("round"),
        "manager": ctx["mgr"], "player": ctx["player"], "pos": ctx["pos"],
        "adp": round(a, 1), "over": round(over, 1), "sd_over": round(sd_over, 2),
        "grade": g,
        "line": pick_line(cat, ctx, pick["pick_no"], skip_tokens(ctx)),
        "repeat": bool(repeat),
    }


def skip_tokens(ctx):
    """Tokens whose value would read as false for this pick."""
    out = []
    if not ctx.get("late"):
        out.append("late")
    if not ctx.get("over"):
        out.append("over")
    for t in ("bust", "bust_yr", "bust_fin", "qb_yrs", "n"):
        if t not in ctx:
            out.append(t)
    return tuple(out)


def repeat_context(pick, hist, sd_over, seen_counts):
    """Receipts, if this pick repeats something the manager has form for.

    Returns the extra template tokens, or None. Order matters: the most
    specific receipt available wins, because a named past flop lands harder
    than a career average.
    """
    if not hist:
        return None
    pos, rnd = pick.get("pos"), pick.get("round") or 99
    uid = str(pick.get("user_id") or "")

    # Early quarterback, in a league where that is the identified mistake.
    if pos == "QB" and rnd <= 4 and hist.get("early_qb"):
        yrs = [q["season"] for q in hist["early_qb"]]
        if yrs:
            return {"qb_yrs": ", ".join(yrs), "n": len(yrs) + 1}

    # Reaching again, with a named past reach that flopped.
    if sd_over >= MILD_SD and hist.get("damning"):
        d = hist["damning"][0]
        return {"bust": d["player"], "bust_yr": d["season"],
                "bust_fin": d.get("finished") or "nowhere",
                "n": len(hist["damning"])}

    # Reaching again when their career average is already ugly.
    if sd_over >= MILD_SD and (hist.get("mean_over") or 0) >= 8:
        seen_counts[uid] = seen_counts.get(uid, 0) + 1
        return {"n": seen_counts[uid]}
    return None


def scorecard(picks, season, grudges=None):
    """Grade a whole draft so far. Returns (rows, standings)."""
    market = adp_mod.load(season)
    grudges = grudges or load_grudges()
    rows, seen = [], {}
    for p in picks:
        r = score_pick(p, market, grudges, seen)
        if r:
            rows.append(r)

    by_mgr = {}
    for r in rows:
        m = by_mgr.setdefault(r["manager"], {"manager": r["manager"], "n": 0,
                                             "gpa": 0.0, "worst": None,
                                             "overs": []})
        m["n"] += 1
        m["gpa"] += GPA[r["grade"]]
        m["overs"].append(r["over"])
        if m["worst"] is None or r["sd_over"] > m["worst"]["sd_over"]:
            m["worst"] = r
    standings = []
    for m in by_mgr.values():
        standings.append({
            "manager": m["manager"], "picks": m["n"],
            "gpa": round(m["gpa"] / m["n"], 2) if m["n"] else 0.0,
            "mean_over": round(statistics.fmean(m["overs"]), 1) if m["overs"] else 0.0,
            "worst": m["worst"],
        })
    standings.sort(key=lambda x: (x["gpa"], -x["mean_over"]))
    return rows, standings
