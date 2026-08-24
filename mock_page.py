#!/usr/bin/env python3
"""Build a self-contained mock-draft page that needs no install and no network.

    python mock_page.py        # -> out/mock-draft.html

Everything a mock draft needs is historical: the player board and each
manager's drafting tendencies. Both are baked into the page at build time, so
the simulation runs entirely in the browser. That is what makes this shareable
as a link, where the live draft advisor cannot be -- following a real draft
means polling Sleeper, and a hosted page is not allowed to.

Whoever opens it picks which manager they are and drafts from that seat against
models of the other eleven.
"""

import json
import sys
from pathlib import Path

from draft import DRAFT_REPLACEMENT, build_board, opponent_tendencies, setup
from model import RAW, Players, _load

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "mock-draft.html"

# Deep enough to draft 15 rounds and still show a real waiver-tier board
# underneath, without bloating the page.
BOARD_DEPTH = 420

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def collect():
    import types
    args = types.SimpleNamespace(slot=None, season=None, mock=True)
    state = setup(args)

    # Projected carries, for the Konami filter. Already in the cached
    # projections -- no extra source needed.
    rush = {}
    cache = RAW / f"projections_{state.season}_season.json"
    if cache.exists():
        for row in json.loads(cache.read_text(encoding="utf-8")):
            pid = str(row.get("player_id") or "")
            ra = ((row.get("stats") or {}).get("rush_att")) or 0
            if pid and ra:
                rush[pid] = round(float(ra))

    board = [{"i": p["player_id"], "n": p["name"], "p": p["pos"],
              "j": round(p["proj"], 1), "v": round(p["vor"], 1), "r": p["rank"],
              "a": p.get("adp"), "ru": rush.get(p["player_id"], 0)}
             for p in state.board[:BOARD_DEPTH]]

    tend, league = opponent_tendencies()
    rounds = state.rounds

    index = _load("index.json")
    league_id = next(s["league_id"] for s in index["seasons"]
                     if s["season"] == state.season)
    from model import Season, SLOT_ELIGIBILITY
    slots = Season(state.season, league_id).starting_slots

    def trim(d):
        return {str(r): {k: round(v, 3) for k, v in (d.get(r) or {}).items() if v > 0}
                for r in range(1, rounds + 1)}

    return {
        "season": state.season,
        "teams": state.teams,
        "rounds": rounds,
        "managers": list(state.order),
        "board": board,
        "tendencies": {m: trim(t) for m, t in tend.items()},
        "league": trim(league),
        "replacement": DRAFT_REPLACEMENT,
        "slots": slots,
        "eligible": {s: sorted(SLOT_ELIGIBILITY.get(s, [])) for s in set(slots)},
    }


# Every strategy the survey confirmed as a genuinely named approach, with the
# rules it implies and a grade against THIS league specifically: 12-team full
# PPR, one QB, two flex spots, five bench spots, rolling waiver priority.
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


# Manager -> skin. Drop an image at assets/skin-<manager>.<png|jpg|gif|webp>
# and it is inlined here automatically. Nothing is fetched over the network,
# at build time or at view time.
SKIN_CONFIG = {
    "wburnett7": {"cls": "skin-wburnett7", "title": "Jalen Hurts RB2"},
}
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp"}


def skins():
    """Build the skin table, inlining any image found in assets/."""
    import base64
    out = {}
    assets = ROOT / "assets"
    for name, cfg in SKIN_CONFIG.items():
        art = ""
        for ext, mime in MIME.items():
            f = assets / f"skin-{name}{ext}"
            if f.exists():
                blob = base64.b64encode(f.read_bytes()).decode("ascii")
                art = f"data:{mime};base64,{blob}"
                print(f"  skin {name}: embedded {f.name} "
                      f"({f.stat().st_size/1024:.0f} KB)")
                break
        else:
            print(f"  skin {name}: no image at assets/skin-{name}.png "
                  f"-- header only")
        out[name] = {**cfg, "art": art}
    return out


PAGE = r"""<title>Mock draft room</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;
 --ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
 --hairline:rgba(11,11,11,0.10);--accent:#2a78d6;--neg:#e34948;--good:#006300;
 --cQB:#4a3aa7;--cRB:#eb6834;--cWR:#1baf7a;--cTE:#eda100;--cK:#e87ba4;--cDEF:#008300}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--hairline:rgba(255,255,255,0.10);
 --accent:#3987e5;--neg:#e66767;--good:#0ca30c;
 --cQB:#9085e9;--cRB:#d95926;--cWR:#199e70;--cTE:#c98500;--cK:#d55181;--cDEF:#008300}}
:root[data-theme="dark"]{color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--hairline:rgba(255,255,255,0.10);
 --accent:#3987e5;--neg:#e66767;--good:#0ca30c;
 --cQB:#9085e9;--cRB:#d95926;--cWR:#199e70;--cTE:#c98500;--cK:#d55181;--cDEF:#008300}
*{box-sizing:border-box}
body{margin:0;padding:28px 18px 70px;background:var(--page);color:var(--ink);
 font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1380px;margin:0 auto}
h1{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:19px;margin:30px 0 8px;letter-spacing:-.01em}
h3{margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-2)}
.sub{color:var(--ink-2);margin:0 0 4px}
.note{color:var(--muted);font-size:13px}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--hairline);
 background:var(--surface);color:var(--ink);padding:9px 14px}
button:hover{border-color:var(--accent)}
button.sel{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent);
 font-weight:600;padding:11px 22px;font-size:16px}
button:disabled{opacity:.45;cursor:not-allowed}
.row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 4px}
.card{background:var(--surface);border:1px solid var(--hairline);border-radius:10px;
 padding:18px;margin-top:12px}
.turn{background:var(--accent);color:#fff;padding:13px 16px;border-radius:10px;
 font-size:17px;font-weight:600;margin-bottom:10px}
.wait{background:var(--surface);border:1px solid var(--hairline);padding:13px 16px;
 border-radius:10px;margin-bottom:10px;color:var(--ink-2)}
.warn{background:var(--neg);color:#fff;padding:10px 14px;border-radius:8px;
 font-weight:600;margin-bottom:10px}
.grid2{display:grid;grid-template-columns:1fr 300px;gap:16px;align-items:start}
@media(max-width:860px){.grid2{grid-template-columns:1fr}}
/* Six recommendations as a 3 x 2 grid of cards. A single flex row per player
   had no room for four metrics without them collapsing into a strip of
   unlabelled digits. */
/* One column per position, six deep. Every player on screen is pickable. */
.board6{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:0 0 14px}
@media(max-width:1240px){.board6{grid-template-columns:repeat(3,1fr)}}
@media(max-width:760px){.board6{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){.board6{grid-template-columns:1fr}}
.poscol h3{margin:0 0 6px;font-size:12px;letter-spacing:.06em;
 border-left:3px solid var(--muted);padding-left:7px}
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
.rec.off{opacity:.45}
.live .rec{cursor:pointer}
.live .rec:hover{opacity:1;filter:brightness(1.06);border-color:var(--accent)}
.rec .nm{display:block;font-weight:600;font-size:13.5px;line-height:1.25;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rec .mets{display:grid;grid-template-columns:1fr auto;gap:1px 8px;margin-top:5px;
 font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.rec .mets span:nth-child(even){text-align:right}
.rec .mets b{color:var(--ink);font-weight:600}
.blocked{opacity:.55;font-size:13px;padding:3px 12px}
.chip{display:inline-block;background:var(--surface);border:1px solid var(--hairline);
 border-radius:999px;padding:2px 10px;margin:2px 4px 2px 0;font-size:13px}
.pool{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:10px}
.pool .col{max-height:340px;overflow-y:auto}
#q{font:inherit;width:100%;max-width:420px;padding:9px 12px;border-radius:8px;
 border:1px solid var(--hairline);background:var(--surface);color:var(--ink)}
#q:focus{outline:2px solid var(--accent);outline-offset:1px}
.hits{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:6px}
/* Strategy chooser: a card per approach with its grade against this league. */
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
.konami{margin-top:12px;padding-top:12px;border-top:1px solid var(--grid);
 display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}
.konami button{white-space:nowrap}
.konami .note{flex:1;min-width:260px;max-width:64ch}
.rec .mets .run{color:var(--ink-2)}
.rec .mets .run.hot b{color:var(--good)}
.shift{background:var(--surface);border:2px solid var(--accent);border-radius:10px;
 padding:12px 15px;margin-bottom:10px;font-size:14px;color:var(--ink)}
.shift .sbtn{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.shift .sbtn button:first-child{background:var(--accent);color:#fff;
 border-color:var(--accent);font-weight:600}

.seat{margin:12px 0 0;padding:9px 14px;border-radius:8px;font-size:14px;
 background:var(--page);border:1px solid var(--accent);color:var(--ink)}
.seat b{color:var(--accent)}

/* Per-manager skin. Applied by adding a class to <body>, so it only has to
   override the accent token and a couple of surfaces. */
body.skin-wburnett7{--accent:#00915c}
body.skin-wburnett7 .turn{background:#00915c}
body.skin-wburnett7 h1{color:#00915c;letter-spacing:-.01em}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]) body.skin-wburnett7{
  --accent:#12b877;--cWR:#12b877}}
:root[data-theme="dark"] body.skin-wburnett7{--accent:#12b877;--cWR:#12b877}
/* Always stacked: image on top, heading beneath, at every width. */
.hero{display:flex;flex-direction:column;align-items:flex-start;gap:14px;
 margin:0 0 8px}
.hero img{max-width:100%;max-height:460px;border-radius:12px;
 border:1px solid var(--hairline);display:block}
.hero .ht{min-width:0;width:100%}
.hero h1{margin:0}
.av{padding:3px 8px;border-radius:5px;font-size:13px;display:flex;gap:8px;
 border-left:3px solid var(--muted)}
.live .av{cursor:pointer}
.live .av:hover{background:var(--surface)}
.av .v{margin-left:auto;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.board{overflow-x:auto;padding-bottom:6px}
.board table{border-collapse:separate;border-spacing:3px;font-size:11px}
.board th{font-size:10px;font-weight:600;padding:1px 4px;color:var(--muted);white-space:nowrap}
.board th.me{color:var(--accent)}
.rd{color:var(--muted);font-variant-numeric:tabular-nums;padding-right:4px;font-size:11px}
.cell{width:104px;height:32px;border-radius:5px;background:var(--surface);
 border:1px solid var(--hairline);border-left:3px solid var(--muted);padding:3px 6px;
 overflow:hidden;line-height:1.2}
.cell.empty{background:transparent;border-style:dashed;border-left-color:var(--hairline)}
.cell.mine{box-shadow:inset 0 0 0 1px var(--accent)}
.cell .n{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.cell .p{color:var(--muted);font-size:10px}
.cQB{border-left-color:var(--cQB)}.cRB{border-left-color:var(--cRB)}
.cWR{border-left-color:var(--cWR)}.cTE{border-left-color:var(--cTE)}
.cK{border-left-color:var(--cK)}.cDEF{border-left-color:var(--cDEF)}
table.sum{border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
table.sum td{padding:5px 14px 5px 0;border-bottom:1px solid var(--grid);
 vertical-align:top;max-width:640px}
table.ros{border-collapse:collapse;width:100%;font-size:13px}
table.ros td{padding:4px 6px 4px 0;border-bottom:1px solid var(--grid)}
table.ros tr.hole td{opacity:.6}
table.ros .sl{color:var(--muted);font-size:11px;width:42px;font-weight:600}
table.ros .num{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:10px;font-weight:600;padding:1px 5px;border-radius:4px;
 border:1px solid var(--hairline);border-left-width:3px;color:var(--ink-2)}
.dens{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.dens .d{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--surface);
 border:1px solid var(--hairline);border-left-width:3px;color:var(--ink-2)}
.dens .d b{color:var(--ink);font-variant-numeric:tabular-nums}
details.key{margin:20px 0 0;background:var(--surface);border:1px solid var(--hairline);
 border-radius:10px;padding:12px 16px}
details.key summary{cursor:pointer;font-weight:600;color:var(--ink-2)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
<div class="wrap" id="app">Loading&hellip;</div>
<script>
(function(){
"use strict";
// Everything is wrapped and wired with addEventListener rather than inline
// onclick attributes: a host page may serve a Content-Security-Policy that
// permits a <script> block but still blocks inline handlers, which would leave
// every button dead with no visible reason.
function fail(e){
  try{
    var a=document.getElementById("app");
    if(a) a.innerHTML='<h1>Something went wrong</h1><p class="sub">'+
      String((e&&e.message)||e)+'</p><pre class="note" style="white-space:pre-wrap">'+
      String((e&&e.stack)||"")+'</pre>';
  }catch(_){}
}
window.addEventListener("error",function(ev){ fail(ev.error||ev.message); });
try{
const DATA = __DATA__;

const STRATS = __STRATS__;
const PRESETS = {};
STRATS.forEach(s=>{
  PRESETS[s.key] = Object.assign({label:s.label, note:s.one,
    earliest:{}, caps:{}, max:{}, banned:{}}, s.rules);
});
const GRADE_RANK = {"A":0,"A-":1,"B+":2,"B":3,"B-":4,"C+":5,"C":6,"C-":7,"D":8,"F":9};
const POS = ["QB","RB","WR","TE","K","DEF"];

// Per-manager skins, assembled at build time. Any image is inlined as a data
// URI, because a published page cannot load one over the network.
const SKINS = __SKINS__;
const BOT_CAPS = {QB:2,TE:2,RB:6,WR:6,K:1,DEF:1};

let S = null;
let query = "";
let konami = false;
const KONAMI_FLOOR = 100;   // carries; the tier where the 93% hit rate lives
const esc = t => String(t).replace(/[&<>"]/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function slotOnClock(pk){
  const r = Math.floor((pk-1)/DATA.teams)+1, i=(pk-1)%DATA.teams;
  return [r%2===1 ? i+1 : DATA.teams-i, r];
}
function nextOwn(after){
  for(let pk=after; pk<=DATA.teams*DATA.rounds; pk++)
    if(slotOnClock(pk)[0]===S.slot) return pk;
  return null;
}
/* Availability from the MARKET, not from our own board -- the same fitted model
   as adp.py, bands measured on 900 real picks from this league's five drafts.
   The queue model below stays as the fallback for players ADP does not cover.
   Counting scarcity from our own ranking said A.J. Brown was 25% to last to
   pick 28 when his ADP of 17.4 means he is usually gone before pick 21. */
var ADP_BANDS=[[12,-0.2,1.7],[24,0.3,4.6],[48,-0.1,5.7],
               [84,0.4,8.1],[120,1.6,12.9],[200,-6.0,15.9]];
var ADP_HORIZON=200;
function erf(x){                       /* Abramowitz & Stegun 7.1.26; no Math.erf */
  var s=x<0?-1:1; x=Math.abs(x);
  var t=1/(1+0.3275911*x);
  var y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t
        +0.254829592)*t*Math.exp(-x*x);
  return s*y;
}
function adpSurvival(adp,pick){
  if(adp==null||adp>ADP_HORIZON) return null;
  var bias=ADP_BANDS[ADP_BANDS.length-1][1], sd=ADP_BANDS[ADP_BANDS.length-1][2];
  for(var i=0;i<ADP_BANDS.length;i++){
    if(adp<=ADP_BANDS[i][0]){ bias=ADP_BANDS[i][1]; sd=ADP_BANDS[i][2]; break; }
  }
  var z=(pick+0.5-(adp+bias))/sd;
  return 1-0.5*(1+erf(z/Math.SQRT2));
}
function poissonBelow(k,lam){
  if(lam<=0) return 1;
  let term=Math.exp(-lam), tot=0;
  for(let i=0;i<k;i++){ if(i) term*=lam/i; tot+=term; }
  return Math.min(1,tot);
}
function counts(roster){
  const c={}; roster.forEach(p=>{c[p.p]=(c[p.p]||0)+1;}); return c;
}
function allowed(pos,rnd,c,key){
  const d=PRESETS[key||S.preset];
  if(d.earliest[pos] && rnd<d.earliest[pos])
    return [false,"not before round "+d.earliest[pos],"timing"];
  const b=d.banned&&d.banned[pos];
  if(b && rnd>=b[0] && rnd<=b[1])
    return [false,"dead zone: no "+pos+" in rounds "+b[0]+"-"+b[1],"timing"];
  if(d.caps[pos]!=null && (c[pos]||0)>=d.caps[pos])
    return [false,"already have "+c[pos]+" "+pos,"cap"];
  const m=d.max[pos];
  if(m && rnd<=m[0] && (c[pos]||0)>=m[1])
    return [false,"max "+m[1]+" "+pos+" through round "+m[0],"timing"];
  return [true,"",""];
}

// Within the opening rounds, check whether a different strategy would let you
// take someone materially better than your current one allows. Suggest it and
// let the user decide -- never switch silently.
// Through round 5, so four picks are on the board and the fifth is still open
// to a pivot.
const SHIFT_THROUGH = 5;
function suggestShift(r){
  if(!S || r.rnd>SHIFT_THROUGH || S.shiftSkip===r.pk) return null;
  // Value gaps compress as the board thins, so a fixed threshold would stop
  // firing after round 2 even when the switch is still worth making.
  const need = r.rnd<=2 ? 20 : 12;
  const c=counts(S.rosters[S.me]||[]);
  const mineBest = r.open.length ? Math.max(...r.open.map(x=>x.v)) : -1e9;
  let best=null;
  for(const s of STRATS){
    if(s.key===S.preset) continue;
    if(GRADE_RANK[s.grade] > GRADE_RANK[curStrat().grade]) continue;  // never downgrade
    let top=-1e9, who=null;
    POS.forEach(p=>(r.byPos[p]||[]).forEach(x=>{
      if(allowed(p,r.rnd,c,s.key)[0] && x.v>top){ top=x.v; who=x; }
    }));
    const gain=top-mineBest;
    if(gain>=need && (!best || gain>best.gain))
      best={strat:s, who:who, gain:gain, kind:"value"};
  }
  if(best) return best;

  // Second trigger, and the one that matters from an unrestricted plan. If you
  // are drafting with no rules, nothing can ever "allow more" than you already
  // have -- so instead, look at what you have actually taken and offer to lock
  // in the graded strategy your own picks already match.
  const mine=S.picks.filter(p=>p.mgr===S.me);
  if(!mine.length || !isLoose(S.preset)) return null;
  const fits=STRATS.filter(s=>s.key!==S.preset &&
      GRADE_RANK[s.grade]<=GRADE_RANK["B"] && !isLoose(s.key) && fitsHistory(s.key));
  fits.sort((a,b)=>GRADE_RANK[a.grade]-GRADE_RANK[b.grade]);
  return fits.length ? {strat:fits[0], who:null, gain:0, kind:"shape",
                        n:mine.length} : null;
}
const SKILL4=["QB","RB","WR","TE"];
// "Loose" means the plan imposes no timing rule on a skill position, so it can
// never be the thing standing between you and a better player.
function isLoose(key){
  const d=PRESETS[key];
  return !SKILL4.some(p=>d.earliest[p]||(d.banned&&d.banned[p])||d.max[p]);
}
// Would every pick you have already made have been legal under this plan?
function fitsHistory(key){
  const c={};
  const mine=S.picks.filter(p=>p.mgr===S.me).sort((a,b)=>a.pick-b.pick);
  for(const p of mine){
    if(!allowed(p.p, slotOnClock(p.pick)[1], c, key)[0]) return false;
    c[p.p]=(c[p.p]||0)+1;
  }
  return true;
}
function ruleText(key){
  const d=PRESETS[key], bits=[];
  SKILL4.forEach(p=>{ if(d.earliest[p]) bits.push("no "+p+" before round "+d.earliest[p]); });
  SKILL4.forEach(p=>{ const b=d.banned&&d.banned[p];
    if(b) bits.push("no "+p+" in rounds "+b[0]+"-"+b[1]); });
  SKILL4.forEach(p=>{ const m=d.max[p];
    if(m) bits.push("at most "+m[1]+" "+p+" through round "+m[0]); });
  return bits.join("; ");
}
function curStrat(){ return STRATS.find(s=>s.key===S.preset) || STRATS[0]; }
const PER_POS = 6;
// The top PER_POS at EVERY position, not the top six overall. A cross-position
// list collapses to whichever position happens to be deepest and hides the
// choice you are actually making.
function recommend(){
  const pk=S.picks.length? Math.max(...S.picks.map(p=>p.pick))+1 : 1;
  const [,rnd]=slotOnClock(pk);
  const nx=nextOwn(pk+1), gap=nx?nx-pk:0;
  const c=counts(S.rosters[S.me]||[]);
  const q={}, byPos={};
  POS.forEach(p=>{ byPos[p]=[]; });
  for(const p of DATA.board){
    if(S.taken.has(p.i)) continue;
    q[p.p]=(q[p.p]||0)+1;                       // queue rank at his position
    if(!byPos[p.p] || byPos[p.p].length>=PER_POS) continue;
    const rate=(DATA.league[String(rnd)]||{})[p.p] || .25;
    const mkt=gap>0? adpSurvival(p.a, pk+gap) : null;
    const surv=mkt!=null? mkt : poissonBelow(q[p.p], gap*rate);
    const [ok,note,kind]=allowed(p.p,rnd,c);
    byPos[p.p].push({...p,ok,note,kind,surv:Math.round(surv*100)});
  }
  // Konami: rank quarterbacks by projected carries rather than by projected
  // points. The claim it rests on is that rushing volume predicts a top-12
  // finish better than passing does -- 26 of 28 QBs with 100+ carries have
  // finished top-12. Applied as a re-ordering of the QB column only; it does
  // not touch any other position or invent a points adjustment.
  if(konami && byPos.QB) byPos.QB.sort((a,b)=>(b.ru||0)-(a.ru||0));

  // Cost is measured against the best player the strategy allows anywhere on
  // the board, so it stays comparable across positions.
  const open=[];
  POS.forEach(p=>byPos[p].forEach(x=>{ if(x.ok) open.push(x); }));
  const best=open.length?Math.max(...open.map(x=>x.v)):0;
  POS.forEach(p=>byPos[p].forEach(x=>{ x.cost=Math.max(0,best-x.v); }));
  const blocked=POS.map(p=>byPos[p][0]).filter(x=>x&&!x.ok);
  return {pk,rnd,gap,byPos,open,blocked,
          top:open.slice().sort((a,b)=>
            (b.v+Math.max(0,b.v)*(1-b.surv/100)*.5)-
            (a.v+Math.max(0,a.v)*(1-a.surv/100)*.5))[0]};
}
function botPick(mgr,rnd){
  const c=counts(S.rosters[mgr]||[]);
  const t=(DATA.tendencies[mgr]||{})[String(rnd)] || DATA.league[String(rnd)] || {};
  const opts=Object.entries(t).filter(([k,v])=>v>0 && (c[k]||0)<(BOT_CAPS[k]||99));
  let pos=null;
  if(opts.length){
    const tot=opts.reduce((s,[,v])=>s+v,0); let r=Math.random()*tot;
    for(const [k,v] of opts){ r-=v; if(r<=0){ pos=k; break; } }
    if(!pos) pos=opts[opts.length-1][0];
  }
  let pick=DATA.board.find(p=>!S.taken.has(p.i) && (!pos || p.p===pos));
  if(!pick) pick=DATA.board.find(p=>!S.taken.has(p.i));
  return pick;
}
function record(pk,player,mgr){
  S.picks.push({pick:pk,mgr,...player});
  S.taken.add(player.i);
  (S.rosters[mgr]=S.rosters[mgr]||[]).push(player);
}
function runBots(){
  const total=DATA.teams*DATA.rounds;
  while(true){
    const pk=S.picks.length? Math.max(...S.picks.map(p=>p.pick))+1 : 1;
    if(pk>total){ S.done=true; break; }
    const [slot,rnd]=slotOnClock(pk);
    if(slot===S.slot) break;
    const mgr=DATA.managers[slot-1];
    const p=botPick(mgr,rnd);
    if(!p){ S.done=true; break; }
    record(pk,p,mgr);
  }
  render();
}
function take(id){
  const p=DATA.board.find(x=>x.i===id);
  if(!p || S.taken.has(id)) return;
  const pk=S.picks.length? Math.max(...S.picks.map(x=>x.pick))+1 : 1;
  record(pk,p,S.me);
  runBots();
}
function autoPick(){ const r=recommend(); if(r.top) take(r.top.i); }

function boardHTML(){
  const byPick={}; S.picks.forEach(p=>byPick[p.pick]=p);
  let h='<div class="board"><table><tr><th></th>';
  for(let i=0;i<DATA.teams;i++)
    h+='<th class="'+(i+1===S.slot?'me':'')+'">'+esc(DATA.managers[i].slice(0,13))+'</th>';
  h+='</tr>';
  for(let r=1;r<=DATA.rounds;r++){
    h+='<tr><td class="rd">'+r+'</td>';
    for(let s=1;s<=DATA.teams;s++){
      const off = r%2===1 ? s : DATA.teams-s+1;
      const pk=(r-1)*DATA.teams+off, p=byPick[pk];
      h+='<td><div class="cell '+(p?'c'+p.p:'empty')+(s===S.slot?' mine':'')+'">'+
        (p? '<span class="n">'+esc(p.n)+'</span><span class="p">'+p.p+'</span>'
          : '<span class="p">'+pk+'</span>')+'</div></td>';
    }
    h+='</tr>';
  }
  return h+'</table></div>';
}
function row(a, live){
  return '<div class="av c'+a.p+'"'+(live?' data-act="take" data-arg="'+esc(a.i)+'"':'')+'>'+
    '<span>'+esc(a.n)+'</span><span class="v">'+a.p+' &middot; '+a.v.toFixed(0)+'</span></div>';
}
// Every undrafted player is reachable: search by name, or scroll a position
// column. Capping the columns at eight was the whole board for most people.
function poolHTML(live){
  const q = query.trim().toLowerCase();
  if(q){
    const hits = DATA.board.filter(p=>!S.taken.has(p.i) && p.n.toLowerCase().indexOf(q)>=0);
    if(!hits.length)
      return '<p class="note">Nobody available matches "'+esc(query)+'".</p>';
    return '<p class="note">'+hits.length+' available'+
      (hits.length>60?' (showing 60)':'')+(live?' &mdash; click to draft':'')+'</p>'+
      '<div class="hits">'+hits.slice(0,60).map(a=>row(a,live)).join('')+'</div>';
  }
  return '<div class="pool">'+POS.map(pos=>{
    const list=DATA.board.filter(p=>p.p===pos && !S.taken.has(p.i));
    if(!list.length) return '';
    return '<div><h3>'+pos+' <span class="note">('+list.length+' left)</span></h3>'+
      '<div class="col">'+list.slice(0,40).map(a=>row(a,live)).join('')+'</div></div>';
  }).join('')+'</div>';
}
function fillSlots(roster){
  // Assign what you have drafted to starting slots, most restrictive first.
  // Every flex accepts a superset of some dedicated slot, so that order gives
  // the true best arrangement rather than an approximation.
  const order=DATA.slots.map((s,i)=>[i,s])
    .sort((a,b)=>(DATA.eligible[a[1]]||[]).length-(DATA.eligible[b[1]]||[]).length);
  const used=new Set(), out=DATA.slots.map(s=>({slot:s,p:null}));
  for(const [i,s] of order){
    const elig=DATA.eligible[s]||[];
    let best=null;
    for(const p of roster){
      if(used.has(p.i) || !elig.includes(p.p)) continue;
      if(!best || p.v>best.v) best=p;
    }
    if(best){ used.add(best.i); out[i].p=best; }
  }
  return {lineup:out, bench:roster.filter(p=>!used.has(p.i))};
}
function rosterPanel(){
  const mine=S.rosters[S.me]||[];
  const {lineup,bench}=fillSlots(mine);
  const c=counts(mine);
  const holes=lineup.filter(x=>!x.p).length;
  return '<h2>Your roster</h2>'+
    '<div class="dens">'+POS.map(p=>'<span class="d c'+p+'">'+p+
      ' <b>'+(c[p]||0)+'</b></span>').join('')+'</div>'+
    '<table class="ros">'+lineup.map(x=>
      '<tr class="'+(x.p?'':'hole')+'"><td class="sl">'+x.slot+'</td><td>'+
      (x.p? '<span class="c'+x.p.p+' pill">'+x.p.p+'</span> '+esc(x.p.n)
          : '<span class="note">empty</span>')+'</td>'+
      '<td class="num">'+(x.p?x.p.j.toFixed(0):'')+'</td></tr>').join('')+'</table>'+
    (holes? '<p class="note">'+holes+' starting spot'+(holes>1?'s':'')+' still open</p>'
          : '<p class="note" style="color:var(--good)">Every starting spot filled</p>')+
    (bench.length? '<h3 style="margin-top:12px">Bench ('+bench.length+')</h3>'+
      '<table class="ros">'+bench.map(p=>'<tr><td class="sl">BN</td><td>'+
      '<span class="c'+p.p+' pill">'+p.p+'</span> '+esc(p.n)+'</td>'+
      '<td class="num">'+p.j.toFixed(0)+'</td></tr>').join('')+'</table>' : '');
}
function legend(){
  // Open by default. Collapsed, it reads as though the page never explained
  // its own numbers.
  return '<details class="key" open><summary>What the numbers mean</summary>'+
    '<table class="sum" style="margin-top:10px">'+
    '<tr><td><b>VOR</b></td><td>Value over replacement: how many more points this '+
      'player is projected to score than a player at his position you could pick up '+
      'off waivers for nothing. It is the honest way to compare a quarterback to a '+
      'running back &mdash; raw projected points are not comparable across positions, '+
      'because quarterbacks score more than everyone.</td></tr>'+
    '<tr><td><b>costs</b></td><td>What you give up by taking this row instead of the '+
      'most valuable player available. <b>costs 0</b> (shown as "best") means nothing '+
      'on the board beats him. This is the number that stops you reaching.</td></tr>'+
    '<tr><td><b>#</b></td><td>His rank on the whole board by VOR. Rank 40 taken at '+
      'pick 20 means you paid a round or two more than he is worth.</td></tr>'+
    '<tr><td><b>adp</b></td><td>Average draft position &mdash; the pick the wider market '+
      'usually takes him at. <b>#</b> is what he is worth; <b>adp</b> is what he costs. '+
      'A player ranked #20 with an adp of 45 can be had two rounds after his value '+
      'says, so taking him now is a reach.</td></tr>'+
    '<tr><td><b>% back</b></td><td>The chance he is still on the board when your next '+
      'turn comes round. <b>5% back</b> means take him now or lose him; <b>60% back</b> '+
      'means you can probably grab someone else first and still get him. This is the '+
      'tiebreak when two players are close in value. Worked out from his adp and from '+
      'how far real drafts in this league have strayed from it &mdash; 900 picks across '+
      'five seasons, where the market proved unbiased for ten rounds and the spread '+
      'widened from under two picks in round one to sixteen by round eleven.</td></tr>'+
    '<tr><td><b>Greyed rows</b></td><td>Players your chosen strategy is blocking, and '+
      'why. They are shown rather than hidden so you can see what the rule is costing.</td></tr>'+
    '<tr><td><b>Red banner</b></td><td>Appears when your strategy is blocking someone '+
      'clearly better than anything it allows. Not an instruction &mdash; just the cost, '+
      'so you can break your own rule knowingly.</td></tr>'+
    '<tr><td><b>Tile colour</b></td><td>Every tile is tinted by the player\'s '+
      'position: '+POS.map(p=>'<span class="c'+p+' pill">'+p+'</span>').join(' ')+
      '. It is only ever a label &mdash; a green tile is not better than an '+
      'orange one. The position is written in the column heading too, so you '+
      'never have to rely on colour.</td></tr>'+
    '<tr><td><b>Blue</b></td><td><b>Blue is never a position.</b> It means the '+
      'tool is pointing at something. A blue ring round a tile marks the '+
      'highest-value player left on the whole board; the blue bar across the '+
      'top means it is your turn; blue text is a live control. Quarterbacks '+
      'are purple, so nothing competes with it.</td></tr>'+
    '<tr><td><b>Faded tiles</b></td><td>A whole column fades when your chosen '+
      'strategy blocks that position, with the reason beside the heading (for '+
      'example "not before round 8"). They stay clickable on purpose &mdash; '+
      'the rule is there to show you a cost, not to stop you.</td></tr>'+
    '<tr><td><b>carries</b></td><td>Shown on quarterbacks only: projected '+
      'rushing attempts. Green means '+KONAMI_FLOOR+' or more, the tier where '+
      '26 of 28 quarterbacks have finished top-12. Turning the Konami filter on '+
      'ranks the quarterback column by this instead of by projected points.</td></tr>'+
    '<tr><td><b>Strategy check</b></td><td>Through round '+SHIFT_THROUGH+', if a '+
      'different strategy of equal or better grade would let you take someone '+
      'materially better than yours allows, you get asked whether to switch. It '+
      'never switches by itself and never suggests a worse-graded approach.</td></tr>'+
    '<tr><td><b>Red</b></td><td>Reserved for warnings: the banner when your '+
      'strategy is blocking someone clearly better, and the reason text on a '+
      'blocked column.</td></tr>'+
    '</table></details>';
}
function summary(){
  const mine=S.rosters[S.me]||[];
  const c=counts(mine);
  const tot=mine.reduce((s,p)=>s+p.j,0);
  const firstQB=mine.findIndex(p=>p.p==="QB")+1;
  return '<h2>Your team</h2><table class="sum">'+mine.map((p,i)=>
    '<tr><td class="rd">R'+(i+1)+'</td><td><strong>'+esc(p.n)+'</strong></td>'+
    '<td>'+p.p+'</td><td>'+p.j.toFixed(1)+'</td>'+
    '<td>'+(p.v>=0?'+':'')+p.v.toFixed(0)+'</td></tr>').join('')+'</table>'+
    '<p class="sub" style="margin-top:10px">'+
    POS.filter(p=>c[p]).map(p=>p+' '+c[p]).join(' &middot; ')+
    ' &middot; projected total '+tot.toFixed(0)+
    (firstQB?' &middot; first QB round '+firstQB:'')+'</p>';
}

function render(){
  const app=document.getElementById("app");
  if(!S){ return renderSetup(); }
  if(S.done){
    app.className="wrap";
    app.innerHTML='<h1>Draft complete</h1><p class="sub">'+esc(S.me)+
      ' &middot; slot '+S.slot+' &middot; '+PRESETS[S.preset].label+'</p>'+
      summary()+'<h2>Draft board</h2>'+boardHTML()+
      '<p style="margin-top:20px"><button class="primary" data-act="reset">Run another</button></p>';
    return;
  }
  const r=recommend();
  const [slot]=slotOnClock(r.pk);
  const live=slot===S.slot;
  app.className="wrap"+(live?" live":"");
  const onClock=DATA.managers[slot-1];
  const warn=(()=>{
    const t=(r.blocked||[]).filter(x=>x.kind==="timing").sort((a,b)=>b.v-a.v);
    if(!r.open.length||!t.length) return "";
    const g=t[0].v-Math.max(...r.open.map(x=>x.v));
    return g>=25 ? "Your strategy is expensive here: "+t[0].n+" ("+t[0].p+") is worth "+
      g.toFixed(0)+" more points, but "+t[0].note : "";
  })();
  const sk = SKINS[S.me];
  const meta = esc(S.me)+' &middot; slot '+S.slot+' &middot; round '+r.rnd+
    ', pick '+r.pk+' &middot; '+PRESETS[S.preset].label;
  app.innerHTML=
    (sk ? '<div class="hero">'+
            (sk.art ? '<img src="'+sk.art+'" alt="">' : '')+
            '<div class="ht"><h1>'+esc(sk.title)+'</h1>'+
            '<p class="sub">'+meta+'</p></div></div>'
        : '<h1>Mock draft room</h1><p class="sub">'+meta+'</p>')+
    (warn?'<div class="warn">'+esc(warn)+'</div>':'')+
    (function(){ const sh=live?suggestShift(r):null; if(!sh) return "";
      const body = sh.kind==="value"
        ? esc(sh.strat.label)+' (grade '+sh.strat.grade+') would let you take '+
          '<b>'+esc(sh.who.n)+'</b> ('+sh.who.p+'), worth <b>'+
          sh.gain.toFixed(0)+' more</b> than anything '+esc(curStrat().label)+
          ' allows right now. '+esc(sh.strat.one)
        : 'Your first '+sh.n+' pick'+(sh.n>1?'s':'')+' already match <b>'+
          esc(sh.strat.label)+'</b> (grade '+sh.strat.grade+'). '+
          esc(sh.strat.one)+' Locking it in holds the line for the rest of the '+
          'draft: '+esc(ruleText(sh.strat.key))+'.';
      return '<div class="shift"><b>Strategy check.</b> '+body+
        '<div class="sbtn"><button data-act="shiftyes" data-arg="'+sh.strat.key+
        '">'+(sh.kind==="shape"?'Lock in ':'Switch to ')+esc(sh.strat.label)+
        '</button><button data-act="shiftno">Stay with '+esc(curStrat().label)+
        '</button></div></div>'; })()+
    (live?'<div class="turn">YOUR PICK &mdash; click a player to draft him</div>'
        :'<div class="wait">'+esc(onClock)+' is picking&hellip;</div>')+
    '<h2>Take one of these</h2>'+
    '<p class="note" style="margin:0 0 10px">The best '+PER_POS+' left at every '+
      'position'+(live?' &mdash; click any of them to draft him':'')+'. '+
      (r.top?'Highest value on the board right now: <b>'+esc(r.top.n)+'</b> ('+
        r.top.p+', VOR '+r.top.v.toFixed(0)+').':'')+'</p>'+
    '<div class="board6">'+POS.map(pos=>{
      const list=r.byPos[pos]||[];
      if(!list.length) return '';
      const blk=list[0].ok?'':list[0].note;
      return '<div class="poscol"><h3 class="c'+pos+'">'+pos+
        (blk?' <span class="blk">'+esc(blk)+'</span>':'')+'</h3>'+
        list.map(x=>'<div class="rec c'+pos+(x.ok?'':' off')+
          (r.top&&x.i===r.top.i?' top':'')+'"'+
          (live?' data-act="take" data-arg="'+esc(x.i)+'"':'')+'>'+
          '<span class="nm">'+esc(x.n)+'</span>'+
          '<div class="mets">'+
            '<span>VOR <b>'+x.v.toFixed(0)+'</b></span>'+
            '<span>#'+x.r+'</span>'+
            '<span>adp <b>'+(x.a==null?'-':x.a.toFixed(1))+'</b></span>'+
            '<span>'+(x.cost>0?'-<b>'+x.cost.toFixed(0)+'</b>':'<b>best</b>')+'</span>'+
            '<span><b>'+x.surv+'%</b> back</span><span></span>'+
            (pos==="QB"&&x.ru ? '<span class="run'+(x.ru>=KONAMI_FLOOR?' hot':'')+
              '"><b>'+x.ru+'</b> carries</span><span></span>' : '')+
          '</div></div>').join('')+'</div>';
    }).join('')+'</div>'+
    '<p style="margin:0 0 6px"><button data-act="auto">Take the best one for me</button> '+
    '<button data-act="reset">Start over</button></p>'+
    '<div class="grid2"><div>'+rosterPanel()+'</div>'+
    '<div><h2>Recent picks</h2>'+
      S.picks.slice(-10).reverse().map(p=>'<div class="blocked">'+p.pick+'. '+
        esc(p.mgr)+' &mdash; '+esc(p.n)+' ('+p.p+')</div>').join('')+
    '</div></div>'+
    '<h2>Every available player</h2>'+
    '<p class="note" style="margin:0 0 8px">Search by name or scroll a position '+
      'column. Anything here can be drafted &mdash; you are never limited to the '+
      'six recommendations above.</p>'+
    '<input id="q" type="search" autocomplete="off" '+
      'placeholder="Type a player name..." value="'+esc(query)+'">'+
    '<div id="pool" style="margin-top:10px">'+poolHTML(live)+'</div>'+
    '<h2>Draft board</h2>'+boardHTML()+
    legend();
}

let pick_me=null, pick_slot=null, pick_preset="best";
function renderSetup(){
  const app=document.getElementById("app");
  app.className="wrap";
  app.innerHTML='<h1>Mock draft room</h1>'+
    '<p class="sub">A practice draft against this league, using '+DATA.season+
    ' projections. The other eleven seats are filled by models of how those '+
    'managers have actually drafted &mdash; not generic bots.</p>'+
    '<div class="card"><h3>1. Which manager are you?</h3><div class="row">'+
      DATA.managers.map(m=>'<button data-m="'+esc(m)+'" data-act="me"'+
        (m===pick_me?' class="sel"':'')+'>'+esc(m)+'</button>').join('')+
    '</div>'+
    // Picking a name seats you. Showing twelve slot buttons as a numbered step
    // made that read as another decision to make, so the seat is now stated as
    // a fact and the override is tucked away.
    (pick_me
      ? '<p class="seat">Seated at <b>slot '+pick_slot+'</b> of '+DATA.teams+
        ', where you were drawn in the real order.</p>'
      : '<p class="note" style="margin-top:10px">Your draft slot is filled in '+
        'automatically from the real order.</p>')+
    '</div>'+
    '<div class="card"><h3>2. Strategy</h3>'+
      '<p class="note" style="margin:0 0 10px">Graded against <b>this</b> league '+
      '&mdash; 12 teams, full PPR, one quarterback, two flex spots, five bench '+
      'spots, rolling waiver priority. The grade is about fit here, not about '+
      'whether the strategy is any good in general.</p>'+
      '<div class="strats">'+STRATS.map(s=>
        '<div class="strat'+(pick_preset===s.key?' sel':'')+'" data-act="preset" '+
        'data-arg="'+s.key+'"><div class="sh">'+
        '<span class="grade g'+s.grade.charAt(0)+'">'+s.grade+'</span>'+
        '<span class="sn">'+esc(s.label)+'</span></div>'+
        '<p class="so">'+esc(s.one)+'</p></div>').join('')+'</div>'+
      '<div class="konami"><button data-act="konami">'+
        (konami?'&#10003; Konami filter ON':'Konami filter OFF')+'</button>'+
        '<span class="note">Ranks quarterbacks by projected <b>carries</b> '+
        'instead of projected points. Rushing volume predicts a top-12 finish '+
        'better than passing does &mdash; 26 of 28 QBs with '+KONAMI_FLOOR+
        '+ carries have finished top-12. Works alongside any strategy above; '+
        'it only re-orders the quarterback column.</span></div>'+
      (function(){ const c=STRATS.find(s=>s.key===pick_preset)||STRATS[0];
        return '<div class="sdetail"><h4>'+esc(c.label)+
          ' <span class="grade g'+c.grade.charAt(0)+'">'+c.grade+'</span></h4>'+
          '<p>'+esc(c.detail)+'</p>'+
          '<p><b>For this league:</b> '+esc(c.verdict)+'</p></div>'; })()+
    '</div>'+
    '<p style="margin-top:18px"><button class="primary" data-act="start"'+
      ((pick_me&&pick_slot)?'':' disabled')+'>'+
      (pick_me?'Start drafting from slot '+pick_slot:'Pick your manager to start')+
      '</button></p>'+
    '<p class="note" style="margin-top:14px">Nothing is sent anywhere. '+
      'The whole draft runs in your browser.</p>';
}
// Picking your name seats you where Sleeper actually put you. You can still
// override it to rehearse a different seat.
function skin(name){
  // Applied to <body> so a skin only has to override tokens, and so it
  // previews on the setup screen rather than appearing after you commit.
  document.body.className = (SKINS[name] && SKINS[name].cls) || "";
}
function setMe(v){
  pick_me=v;
  const i=DATA.managers.indexOf(v);
  if(i>=0) pick_slot=i+1;
  skin(v);
  renderSetup();
}
function setSlot(n){ pick_slot=n; renderSetup(); }
function setPreset(k){ pick_preset=k; renderSetup(); }
function reset(){ S=null; renderSetup(); }
function start(){
  if(!pick_me||!pick_slot) return;
  const order=DATA.managers.slice();
  const here=order.indexOf(pick_me);
  if(here>=0){ const t=order[pick_slot-1]; order[pick_slot-1]=pick_me; order[here]=t; }
  DATA.managers=order;
  S={me:pick_me,slot:pick_slot,preset:pick_preset,picks:[],taken:new Set(),
     rosters:{},done:false};
  runBots();
}
// One delegated listener for the whole app, re-bound to nothing on re-render
// because it lives on the container rather than on the buttons themselves.
document.getElementById("app").addEventListener("click", function(ev){
  var el = ev.target && ev.target.closest ? ev.target.closest("[data-act]") : null;
  if(!el) return;
  var a = el.getAttribute("data-act"), v = el.getAttribute("data-arg");
  try{
    if(a==="me") setMe(el.getAttribute("data-m"));
    else if(a==="slot") setSlot(parseInt(v,10));
    else if(a==="preset") setPreset(v);
    else if(a==="start") start();
    else if(a==="take") take(v);
    else if(a==="auto") autoPick();
    else if(a==="reset") reset();
    else if(a==="shiftyes"){ const pk=S.picks.length?Math.max.apply(null,
        S.picks.map(function(x){return x.pick;}))+1:1;
      S.preset=v; S.shiftSkip=pk; render(); }
    else if(a==="shiftno"){ const pk=S.picks.length?Math.max.apply(null,
        S.picks.map(function(x){return x.pick;}))+1:1;
      S.shiftSkip=pk; render(); }
    else if(a==="konami"){ konami=!konami; S?render():renderSetup(); }
  }catch(err){ fail(err); }
});
// Typing repaints only the results list, so the box keeps its value and focus.
// Re-rendering the whole page on every keystroke would drop the cursor.
document.getElementById("app").addEventListener("input", function(ev){
  if(!ev.target || ev.target.id !== "q" || !S) return;
  query = ev.target.value;
  var pool = document.getElementById("pool");
  if(!pool) return;
  var pk = S.picks.length ? Math.max.apply(null, S.picks.map(function(x){return x.pick;}))+1 : 1;
  try{ pool.innerHTML = poolHTML(slotOnClock(pk)[0] === S.slot); }catch(err){ fail(err); }
});
renderSetup();
}catch(err){ fail(err); }
})();
</script>"""


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--standalone", action="store_true",
                    help="also write a complete .html file that opens by "
                         "double-clicking, with no login and no hosting")
    args = ap.parse_args()

    data = collect()
    blob = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    # ensure_ascii keeps the payload pure ASCII using \uXXXX escapes, which are
    # valid JavaScript. HTML entities would NOT work here -- they are not parsed
    # inside a <script> block.
    doc = PAGE.replace("__DATA__", blob)
    doc = doc.replace("__SKINS__", json.dumps(skins(), ensure_ascii=True))
    doc = doc.replace("__STRATS__", json.dumps(STRATEGIES, ensure_ascii=True))
    if any(ord(c) > 127 for c in doc):
        raise SystemExit("non-ASCII leaked into the page")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(doc, encoding="ascii")
    print(f"wrote {OUT}  ({len(doc)/1024:.0f} KB, {len(data['board'])} players, "
          f"{len(data['managers'])} managers)")

    if args.standalone:
        # The hosted copy is a fragment: the host supplies <head> and <body>.
        # This one carries its own, so it can be emailed or dropped in a chat
        # and opened by anyone with a browser -- no account, no permissions.
        full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,'
                'initial-scale=1">' + doc.replace("<title>", "<title>", 1) +
                "</body></html>").replace("<style>", "</head><body><style>", 1)
        alt = OUT.with_name("mock-draft-standalone.html")
        alt.write_text(full, encoding="ascii")
        print(f"wrote {alt}  ({len(full)/1024:.0f} KB) -- send this file to anyone")


if __name__ == "__main__":
    main()

