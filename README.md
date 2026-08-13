# Sleeper draft advisor

Analyse any Sleeper fantasy football league, then draft with live advice.

Works on **your** league, not a generic one: the draft board is priced against
your league's own scoring and roster settings, and the simulated opponents in a
mock draft are modelled on how your actual leaguemates have drafted, not on
national ADP.

## No credentials, ever

Sleeper's API is read-only and unauthenticated. From
[their documentation](https://docs.sleeper.com/):

> "We do not perform authentication as our API is read-only and only contains
> league information."
>
> "No API Token is necessary, as you cannot modify contents via this API."

So there is nothing to log into, nothing to leak, and nothing to revoke. All you
supply is your public Sleeper username. **This tool cannot make a pick, submit a
waiver claim, or change your lineup** — the API has no write capability. It
advises; you act in the Sleeper app.

If any fork of this asks for your Sleeper password, it is not doing what this
does.

## Requirements

Python 3.9 or newer. **No third-party packages** — standard library only, on
purpose, so there is almost no dependency surface to trust.

## Getting started

```bash
python pull.py --user YOUR_SLEEPER_USERNAME   # download + cache your history
python analyze.py                             # -> data/analysis.json
python strategy.py                            # -> data/strategy.json
python report.py                              # -> report.html
python draft_report.py                        # -> draft-report.html
```

The first pull walks back through `previous_league_id` and grabs every season
your league has played. It caches everything, so re-running only re-fetches the
current season.

## What each tool does

| Command | What you get |
|---|---|
| `python report.py` | Season report: lineup efficiency against the optimal legal lineup, schedule luck via all-play records, draft surplus, waiver activity, trades |
| `python draft_report.py` | Where the points actually are in *your* scoring, when positions leave *your* board, what your waiver wire can really replace |
| `python trade.py --give "X" --get "Y"` | Prices both sides of a trade on value over replacement |
| `python draft.py --serve --mock --manual` | Mock draft against your real leaguemates, with a live draft board |
| `python draft.py --serve` | Draft night: follows the live draft and advises |
| `python check.py` | Validates the generated HTML before you share it |

Add `--anon` to `analyze.py` to replace everyone's handle with Manager A, B, C.
Worth doing before you share anything outside your league.

## Draft night

```bash
python draft.py --serve
```

Opens a local page that follows your live draft. It reads your slot from
Sleeper, ranks the available players by value over replacement, estimates
whether each will survive until your next pick, and flags when your own strategy
rules are blocking someone clearly better.

`--host 0.0.0.0` makes it reachable from your phone on the same wifi, so you can
draft on a laptop and read advice on a handset. That exposes the page to your
local network — fine at home for an evening, but stop it afterwards.

Rehearse first:

```bash
python draft.py --serve --mock --manual
```

The simulation stops on your pick and waits for you to choose, exactly like the
real thing. Every other seat is filled by a model of that manager's real draft
history.

## Your strategy

`draft.py` has a `DIRECTIVE` block near the top:

```python
DIRECTIVE = {
    "label": "Hero RB, late QB, let TE come to you",
    "earliest_round": {"QB": 8, "TE": 5, "K": 14, "DEF": 14},
    "max_by_round": {("RB", 5): 2},
    "roster_caps": {"QB": 2, "K": 1, "DEF": 1, "TE": 2, "RB": 6, "WR": 7},
}
```

**These defaults are an example, not advice for your league.** They came out of
analysing one specific 12-team PPR league, where a quarter of round three went
to quarterbacks every year and the waiver wire replaced quarterbacks far more
reliably than running backs. Run `draft_report.py` on your own league and set
rules that match what it tells you.

## Examples

`examples/` holds real output from five seasons of one league. Open the HTML
files in a browser.

`python mock_page.py` builds a self-contained mock-draft page you can share as a
file or host anywhere — the player board and each manager's tendencies are baked
in at build time, so it needs no install and makes no network requests. Whoever
opens it picks which manager they are and drafts from that seat.

The findings from that league, as a flavour of what the analysis surfaces:

- Draft output correlated with points scored at **r = 0.67**; waiver activity at
  **0.08**. The top four and bottom four finishers were indistinguishable on
  lineup efficiency, add volume and waiver production.
- Value over replacement: RB 103, WR 90, QB 61, TE 32 — so an elite tight end
  was worth about a third of an elite running back.
- **25% of round three went to quarterbacks**, the third-least-scarce position.

None of that generalises. That is the point — run it on yours.

## Limitations

- Player projections come from a Sleeper endpoint that is **not in their public
  docs**. It works today and could be withdrawn without notice. Only `trade.py`
  and `draft.py` depend on it, and both fail loudly rather than guessing.
- Historical player scoring is reconstructed from weekly league results, since
  Sleeper retired its public stats endpoint. A player only accrues points while
  someone rostered him, so deep replacement ranks read low.
- `data/` is gitignored. It contains other league members' names and activity.
  Think before you publish it.

## Licence

MIT. See [LICENSE](LICENSE).
