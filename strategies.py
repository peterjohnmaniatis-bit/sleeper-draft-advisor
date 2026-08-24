#!/usr/bin/env python3
"""The draft strategies, and how they become a rule the advisor can enforce.

One definition, two consumers. mock_page.py renders these as cards and enforces
them in JavaScript; draft.py enforces them in Python on the live board. Keeping
two copies in step by hand is exactly the kind of drift that ends with the mock
teaching one thing and draft night doing another, so the list lives here.

A grade is about FIT WITH THIS LEAGUE, not about whether a strategy is any good
in the abstract.
"""

# A grade is about fit here, not about whether the strategy is any good.
STRATEGIES = [
    {"key": "best", "label": "Best available", "grade": "A-",
     "one": "No positional rules. Always take the most valuable player left.",
     "detail": "Also called Best Player Available or Value-Based Drafting. You "
               "rank everyone by value over replacement and take the top of the "
               "board every time, letting roster shape sort itself out.",
     "verdict": "Hard to beat as a default. It cannot be wrong about a player, "
                "only about shape, and this league's two flex spots forgive "
                "shape. It will not stop you taking a quarterback in round 3, "
                "which is the one mistake worth ruling out here.",
     "rules": {"earliest": {"K": 13, "DEF": 13},
               "caps": {"QB": 2, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7}}},

    {"key": "hero_rb", "label": "Hero RB", "grade": "A",
     "one": "Exactly one elite back early, then receivers until round 6.",
     "detail": "One big-name running back inside the first two rounds, then no "
               "RB again for several rounds while you take three or four "
               "receivers, then RB2 from round 6 onward and late darts. The "
               "defining feature is exactly one early back, not the specific "
               "round he comes in.",
     "verdict": "Close to purpose-built for this league. Two flex spots in full "
                "PPR reward the receiver run in rounds 2-5, the one early back "
                "covers the fact that rolling waivers make in-season RB repair "
                "unreliable, and it only needs two or three speculative backs "
                "late, which a five-man bench can actually hold.",
     "rules": {"earliest": {"QB": 8, "TE": 5, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7},
               "max": {"RB": [4, 1]}}},

    {"key": "late_qb", "label": "Late-Round QB", "grade": "A",
     "one": "No quarterback before round 8. Everything else is best available.",
     "detail": "JJ Zachariason's approach, and the canonical name. In a "
               "one-quarterback league only twelve start, so the gap between "
               "the best QB and the twelfth is small while the gap between "
               "the best back and the thirtieth is enormous. Spend early "
               "capital where the gaps are.",
     "verdict": "The single sharpest edge available to you, because a quarter "
                "of round three in this league goes to quarterbacks every "
                "year. Three rivals hand you the backs and receivers they pass "
                "on. One adjustment: the standard version says carry two late "
                "QBs and play matchups, but that is 40% of a five-man bench "
                "here, so take one around rounds 8-11 you intend to start.",
     "rules": {"earliest": {"QB": 8, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7}}},

    {"key": "mod_zero_rb", "label": "Modified Zero RB", "grade": "B+",
     "one": "No back before round 4. Receivers first, then backs from the middle.",
     "detail": "A relaxed Zero RB that pulls the first back forward and shrinks "
               "the late stockpile: fade RB for the first three rounds, take "
               "three receivers in the first four, and have your first real "
               "back by rounds 4-6.",
     "verdict": "The only build in the Zero RB family that survives this "
                "league. Getting a back by round 4-6 means two or three late "
                "darts rather than five or six, which is the difference "
                "between fitting on a five-man bench and not. It also does not "
                "stake the season on winning rolling-priority waiver claims.",
     "rules": {"earliest": {"RB": 4, "QB": 8, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7},
               "max": {"RB": [6, 2]}}},

    {"key": "deadzone", "label": "RB Dead Zone", "grade": "B+",
     "one": "Backs early or late, never in rounds 3 to 6.",
     "detail": "The dead zone is the band where committee backs with no "
               "guaranteed volume go at prices that assume they have it. This "
               "build takes running backs at the top of the draft or at the "
               "bottom and refuses to pay in the middle.",
     "verdict": "A rule rather than a shape, and a good one here. It is "
                "compatible with almost everything else on this list and it "
                "targets the exact band where your league's worst picks have "
                "historically been made.",
     "rules": {"earliest": {"QB": 8, "TE": 5, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7},
               "banned": {"RB": [3, 6]}}},

    {"key": "barbell", "label": "Barbell RB", "grade": "B",
     "one": "Two elite backs early, nothing at RB until round 9, then darts.",
     "detail": "Adam Levitan's build. Load both ends and skip the middle: two "
               "backs inside the first three rounds taken off the top of the "
               "board, receivers and a tight end through rounds 4-8, then late "
               "picks sprayed at ambiguous backfields.",
     "verdict": "The early half fits well, since two elite backs is real "
                "insurance where rolling waivers make repair unreliable. The "
                "late half strains a five-man bench, which cannot hold the "
                "spread of lottery tickets the build wants.",
     "rules": {"earliest": {"QB": 8, "TE": 5, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7},
               "max": {"RB": [8, 2]}}},

    {"key": "late_te", "label": "Late-Round TE", "grade": "B",
     "one": "No tight end before round 8. Take the position last.",
     "detail": "Treat tight end the way late-round QB treats quarterback: the "
               "gap between the sixth-best and the fifteenth is small, so pay "
               "nothing and stream if it goes wrong.",
     "verdict": "Correct on the numbers here. An elite tight end is worth "
                "about 32 points over replacement in this scoring, against 103 "
                "for a back. The risk is that tight end is only the fourth-most "
                "replaceable position on your waiver wire, so a miss lingers.",
     "rules": {"earliest": {"TE": 8, "QB": 8, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7}}},

    {"key": "hero_wr", "label": "Hero WR", "grade": "B-",
     "one": "One elite receiver early, then backs until round 5.",
     "detail": "The mirror of Hero RB. Anchor with a top receiver, then take "
               "running backs while everyone else is chasing pass catchers.",
     "verdict": "Workable and genuinely contrarian in a PPR league, but it "
                "fights the scoring. Two flex spots mean you want receiver "
                "volume, and this build spends the rounds where that volume is "
                "cheapest on the position that is hardest to replace anyway.",
     "rules": {"earliest": {"QB": 8, "TE": 5, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7},
               "max": {"WR": [4, 1]}}},

    {"key": "robust_rb", "label": "Robust RB", "grade": "B-",
     "one": "Backs with your first two or three picks, receivers after.",
     "detail": "Corner the top running back tiers. Two backs in the first two "
               "rounds at minimum, often three of the first five, then fill "
               "receiver through the middle.",
     "verdict": "Defensible, and the two flex spots inflate RB demand enough to "
                "justify it. But full PPR with two starting receivers plus two "
                "flexes means opening RB-RB-RB leaves you starting WR3-quality "
                "receivers all year, and the ones you passed do not come back "
                "in a twelve-team league. Also concentrates injury risk in the "
                "position that suffers most of it.",
     "rules": {"earliest": {"QB": 7, "TE": 6, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 7, "WR": 6},
               "max": {"WR": [3, 1]}}},

    {"key": "elite_te", "label": "Elite TE", "grade": "C+",
     "one": "Take a top tight end in the first three rounds.",
     "detail": "Buy the one position where a single player can be a weekly "
               "advantage over every other roster, and accept a weaker start "
               "elsewhere to get him.",
     "verdict": "The premise is real but the price is wrong here. Elite tight "
                "end is worth about a third of an elite back over replacement "
                "in this scoring, and your league has shown no relationship "
                "between when a tight end is drafted and how the season goes.",
     "rules": {"earliest": {"QB": 8, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7}}},

    {"key": "elite_qb", "label": "Elite QB", "grade": "C-",
     "one": "Take one of the top quarterbacks in rounds 2 to 4.",
     "detail": "The named foil to Late-Round QB. Pay up for a quarterback who "
               "wins you weeks outright, and skip a backup entirely to get the "
               "bench spot back.",
     "verdict": "Playable but the format argues against it. One starting "
                "quarterback and no superflex means there is no demand "
                "inflating the position, and the round 2-3 cost lands directly "
                "on the RB and WR bodies this lineup needs most. This is the "
                "thing you have done in four of five seasons.",
     "rules": {"earliest": {"K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7}}},

    {"key": "zero_rb", "label": "Zero RB", "grade": "D",
     "one": "No running back before round 5. Backs come from waivers.",
     "detail": "Shawn Siegele's original. Fade running back entirely early, "
               "load receivers and a tight end, then take many late lottery "
               "tickets and win the waiver wire when a backfield opens up.",
     "verdict": "Ruled out here, and not because the strategy is bad. It needs "
                "bench space to stash lottery tickets and you have five spots "
                "that also cover byes. It needs to win the waiver race when a "
                "backfield opens, and rolling priority means you cannot outbid "
                "anyone. Running back is also the least replaceable position "
                "on your wire, at a 15% hit rate.",
     "rules": {"earliest": {"RB": 5, "QB": 8, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 3, "K": 1, "DEF": 1, "RB": 7, "WR": 7}}},

    {"key": "zero_wr", "label": "Zero WR", "grade": "F",
     "one": "No receiver before round 5. Backs and a tight end first.",
     "detail": "The inverse of Zero RB, and much rarer. Load the positions "
               "with guaranteed volume and treat receiver as replaceable.",
     "verdict": "The worst fit on this list. Full PPR with two starting "
                "receivers and two flex spots means receiver volume is most of "
                "your scoring, and receiver is the least replaceable position "
                "on your waiver wire at a 13% hit rate. Included so you can "
                "see what it costs.",
     "rules": {"earliest": {"WR": 5, "QB": 8, "K": 14, "DEF": 14},
               "caps": {"QB": 1, "TE": 2, "K": 1, "DEF": 1, "RB": 7, "WR": 7}}},
]


# draft.py speaks a slightly different dialect: it keys "max" on a (pos, round)
# tuple and calls the buckets earliest_round / roster_caps / max_by_round. It
# also had no notion of a dead zone at all, which is the whole point of the
# RB Dead Zone strategy -- directive_check() grew a `banned` branch for it.
def to_directive(key):
    """One strategy as the directive dict draft.py's directive_check() reads."""
    st = BY_KEY.get(key) or BY_KEY["best"]
    r = st["rules"]
    return {
        "key": st["key"],
        "label": st["label"],
        "earliest_round": dict(r.get("earliest") or {}),
        "roster_caps": dict(r.get("caps") or {}),
        # {"RB": [4, 1]} means at most 1 RB through round 4.
        "max_by_round": {(pos, through): limit
                         for pos, (through, limit) in (r.get("max") or {}).items()},
        # {"RB": [3, 6]} means no RB at all in rounds 3 through 6.
        "banned_rounds": {pos: tuple(rng)
                          for pos, rng in (r.get("banned") or {}).items()},
        "want_by_round": {},
    }


BY_KEY = {s["key"]: s for s in STRATEGIES}
DEFAULT_KEY = "hero_rb"
