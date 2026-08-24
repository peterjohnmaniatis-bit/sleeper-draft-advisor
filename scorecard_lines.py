#!/usr/bin/env python3
"""The scorecard's copy, and how a line gets chosen.

Blunt by request. Every line mocks a DECISION -- how far ahead of the market a
pick was, or the fact that the manager has done it before. Never a username,
never a person, never anything about anyone's actual life. That is not
squeamishness: a scorecard that punches at people instead of picks stops being
funny the first time it lands wrong, and this one runs in front of the whole
league.

Selection is DETERMINISTIC on the pick number. The page re-polls every 1.5
seconds and re-renders the whole feed; a random choice would reshuffle every
joke on the board twice a second.
"""

LINES = {
    "reach-mild": [
        "{over} picks early on {player}. Nobody was taking him. Nobody was close to taking him.",
        "{mgr} jumps {over} spots for {player} — the market said {adp}, and the market was not moving.",
        "{player} at {pick} when the board said {adp}. You had time. You had so much fucking time.",
        "That's {over} picks of daylight you just set on fire for {player}. Not fatal. Just dumb.",
        "A {sd} standard deviation reach on {player}. That's not a strategy, that's a flinch.",
        "{over} picks early on {player}. It's fine. It's fine. It's a little stupid, but it's fine.",
        "{mgr} takes {player} {over} ahead of {adp}, which is the draft equivalent of paying sticker price on a used Camry.",
        "Nobody in this room wanted {player} for another {over} picks. You could have gotten up, gotten a beer, come back, and he's still sitting there.",
        "ADP {adp}. Pick {pick}. Do the subtraction: {over} picks you did not have to spend.",
        "You reached {over} for {player}. Your career average is {mean_over}. So by your standards, this was restraint.",
        "{over} picks early on {player} in a league that averages {league}. Above the curve, and not the good curve.",
        "It's a {pos}. There are always more of them. {over} picks early on {player} for a guy who'd have been sitting right there at {adp}.",
        "{mgr} could not wait {over} more picks. The wait is eleven minutes. {player} was not going anywhere.",
        "Mild reach on {player} — {over} early, {sd} deviations. The kind of pick you defend in December by pretending you had a read.",
        "{over} picks. That is the entire gap between {player} at {pick} and {player} at {adp}, and the gap is self-inflicted.",
        "Not criminal. Just {over} picks early on {player}, which is the draft version of showing up an hour before the party starts.",
        "That's time number {n} tonight that {mgr} has gone early. {player}, {over} ahead of {adp}. A pattern is forming and it's an ugly one.",
        "{over} early. {sd} sigma. {player}. Somewhere a spreadsheet just sighed.",
        "The room let out one collective shrug as {mgr} took {player} {over} picks before anyone had to think about him.",
        "You're {over} early on {player} and {mean_over} early across your whole career. At some point that's not variance, that's just how you fucking draft.",
        "{player} at {pick}, {adp} on the market, {over} picks of pure impatience. Round {rnd}, same as it ever was.",
        "Fine player, shit timing: {over} picks early on {player}, and every other {pos} in that tier was going to sit there for another full lap.",
        "{over} early on {player}. Not enough to ruin your draft. Just enough to hear about it every single week.",
        "Reached {over} for a guy going at {adp}. That's not aggression, {mgr}, that's tipping the market.",
        "{mgr} pays {over} picks over the ask for {player}. Nobody was bidding. There was no auction. You bid against yourself.",
        "{player}, {over} ahead of {adp}, in round {rnd}. Impatient, and you knew it before the words left your mouth.",
        "A {sd} sigma jump for {player}. Statistically that's a shrug. Emotionally that's {over} picks of panic you'll deny all season.",
    ],
    "reach-brutal": [
        "{over} picks early on {player}. That's not aggressive, that's a fucking donation to the other eleven teams.",
        "{player} had an ADP of {adp}. {mgr} took him at {pick}. The gap is {over} picks and there is no version of this that was necessary.",
        "Holy shit. {player}, {over} ahead of market, in round {rnd}, with the entire board still breathing.",
        "{sd} standard deviations early. In statistics that's an outlier; here it's just {mgr} taking {player} {over} picks before anyone was going to make him.",
        "Nobody else was in on {player}. Nobody was fucking close. {over} picks early on a guy the market had at {adp}.",
        "Round {rnd}, pick {pick}, {over} picks early. Every manager who picked after this had a shot at {player} and not one of them wanted him.",
        "{over} picks. {over} goddamn picks. {player} was sitting at {adp} and was not going anywhere.",
        "The last time a reach this size happened it was {bust} in {bust_yr}, who finished {bust_fin}. Now it's {player}, {over} early. Same movie, same ending.",
        "You could have walked to the fridge, opened a beer, come back, and still had {player}. Instead: {over} picks early, {sd} deviations out.",
        "{mean_over} career mean against a league mean of {league}, and {player} {over} picks early just dragged that number further into the dirt.",
        "That's a {over}-pick reach, and I want it on the record that the {adp} ADP was publicly available, free, on the internet, all summer.",
        "{player} at {over} over. The draft room went quiet, which is the sound of eleven people deciding to be polite.",
        "Two things are true at once: {player} is a real NFL {pos}, and spending pick {pick} on him {over} picks early was a genuinely stupid use of a roster spot.",
        "{sd} deviations. {over} picks. One {pos}. Zero other managers who would have touched him before {adp}.",
        "This is the {n}th time {mgr} has blown past ADP by double digits. {player} went {over} early tonight, so the pattern isn't bad luck, it's a strategy, and it's a bad fucking strategy.",
        "The ADP was {adp}. The pick was {pick}. The difference is {over}, and the technical term is unforced error.",
        "Waiting one full round gets you {player} anyway. Taking him {over} picks early at {pick} gets you {player} and a worse bench. Pick one, and the wrong one was picked.",
        "{over} picks early on {player} and the value left on the board is now somebody else's problem to enjoy.",
        "{bust}, {bust_yr}, {bust_fin} overall, reached for. {player}, tonight, {over} picks early, {sd} SDs out. History doesn't repeat but it sure as shit rhymes.",
        "Reaching {over} for a {pos} in round {rnd} is exactly how {bust} ended up on a roster in {bust_yr} finishing {bust_fin}.",
        "{player} was going at {adp} in every mock, every projection, every site. Took him {over} picks early anyway.",
        "{over} early. {sd} deviations. Round {rnd}. {player}. I have run out of ways to say this was fucking stupid, so I'm just going to leave the numbers there.",
        "{over} picks early on {player} in round {rnd}. Somewhere a guy still on the board next round is quietly the better player and the cheaper one.",
    ],
    "repeat": [
        "{over} picks early on {player}, which pushes {mgr} to a career mean of {mean_over} against a league {league}. Same shit, different August.",
        "Remember {bust}? {bust_yr}, finished {bust_fin}th, drafted with exactly this energy. {mgr} just did it again with {player} at {pick}.",
        "{pos} in round {rnd}. Again. {qb_yrs}, and now tonight. At some point we have to accept this is on purpose.",
        "{sd} standard deviations early. Career mean {mean_over}. League mean {league}. The math has been screaming for years and {mgr} keeps drafting with headphones on.",
        "That's the {n}th time this exact reach has happened, and the last one was {bust} in {bust_yr} finishing {bust_fin}th. Love the consistency.",
        "{player} at {pick}, {over} early, {mgr}'s {n}th offense.",
        "ADP said {adp}. {mgr} said {pick}. {mgr} has said some version of that {n} times now and it gave us {bust}.",
        "{qb_yrs} and here we are. Nobody in this league learns a goddamn thing.",
        "A career mean of {mean_over} against a league {league} means {mgr} personally dragged that average up. {player} {over} picks early is just the monthly payment.",
        "Years of receipts, one identical mistake: {player} at {pick}, {over} ahead of {adp}, from the same drafter who took {bust} in {bust_yr} and watched him finish {bust_fin}th.",
        "{mean_over} career versus a league {league}. That's not variance. That's a fucking method.",
        "Somewhere there's a spreadsheet with {bust}, {bust_yr}, and the number {bust_fin} on it. Tonight it gets another row.",
        "{pos} in round {rnd} for the {n}th time across {qb_yrs}. Hell of a hill to keep re-buying.",
        "{over} picks early, {sd} deviations off {adp}, career mean {mean_over}. This isn't drafting, it's a re-enactment of {bust_yr}.",
        "Last time this exact reach happened, {bust} finished {bust_fin}th and the whole season got blamed on injuries. Now it's {player} at {pick}. Buckle up.",
        "{mgr} took {player} {over} picks before {adp}, sitting on a career {mean_over} against a league {league}. Statistically the reason we re-explain ADP every single year.",
        "{bust}, {bust_yr}, {bust_fin}th. {player}, tonight, {over} early. Print those side by side and you cannot tell which draft you're watching.",
        "{n} data points is not bad luck, it's a trend, and {qb_yrs} is the trend.",
        "{mgr} lets {player} slide to {pick}, a full {late} picks past {adp}. First time across {qb_yrs} that the pattern broke. Frame it.",
        "The {n}th {pos} reach of the {mgr} era. {qb_yrs} said it wouldn't work. Pick {pick} says {mgr} doesn't care.",
        "Everyone in this room watched {bust} finish {bust_fin}th in {bust_yr}. Everyone in this room just watched the identical fucking thing happen to {player}.",
        "Round {rnd}, {pos}, {mgr}. If you had {qb_yrs} on your bingo card, congratulations on having the easiest card at the table.",
        "{sd} SDs early is a rounding error for a drafter living at {mean_over}. {player} was never getting to {adp} once the clock hit {mgr}.",
        "{over} picks early is bad. {over} picks early when the career average is already {mean_over} and the league is {league} is a documented condition.",
        "{mgr} reaches, board groans, {bust_yr} flashes before everyone's eyes. {bust} finished {bust_fin}th, and {player} just got taken {over} picks early by the same hand.",
        "{n}th showing of the same movie: {pos}, round {rnd}, {qb_yrs}, and a straight face.",
    ],
    "value-and-credit": [
        "Fine. {player} at {pick}, {late} picks after his {adp} ADP. That one was actually fucking fine.",
        "{mgr} watched {player} slide {late} picks past {adp} and had the discipline to just sit there. Who taught you that?",
        "Value. Boring, correct, unglamorous value: {player} at pick {pick}, and not one reach involved.",
        "Round {rnd}, pick {pick}, {late} picks of free money off the board. Nothing to roast here.",
        "A career {mean_over} reacher just took a guy {late} picks LATE. Somebody check the windows, hell may be freezing.",
        "{mgr}'s career mean is {mean_over}. The league's is {league}. This pick sits under both, so we'll say it once and never again: good job.",
        "{sd} standard deviations off market. That's noise. That's a normal, functional, adult draft pick, and I hate that it leaves me nothing.",
        "No reach, no panic, no {bust_yr} flashback. {player} at {pick} is just correct.",
        "{mgr} took {player} {late} picks after ADP, which is the precise opposite of what he did to {bust} in {bust_yr}. Growth. Disgusting.",
        "The {pos} run was on, half the room lost their minds, and {mgr} sat still until {player} fell {late} picks. Cold.",
        "{bust} finished {bust_fin} in {bust_yr}. {player} at {pick}, {late} picks below market, is the closest thing to an apology this league accepts.",
        "That's {n} picks in a row without a reach from {mgr}. Enjoy the streak. It never lasts.",
        "A {pos} in round {rnd} that isn't early. Market said {adp}, {mgr} paid {pick}. After {qb_yrs}, this qualifies as a personality transplant.",
        "{player} at {pick}. {late} picks of value. No notes. Fuck off, next pick.",
        "Everybody else reached for a {pos} they didn't need. {mgr} let {player} come to him {late} picks late. Grudging, brief, deeply unwilling respect.",
        "There's no angle here. {pos}, pick {pick}, ADP {adp}. It's just a good fucking pick and the scorecard will recover.",
        "{mgr} has averaged {mean_over} picks early across his entire miserable draft history. Tonight: {late} late. Frame it.",
        "The board broke and {mgr} caught it. {player}, pick {pick}, {late} under market. Savor it.",
        "Correct. {player} at {pick}, right on {adp}, round {rnd}. Moving the hell on.",
        "{n} seasons of reaching and he finally learned that good players fall. {player}, {late} picks late, at {pick}.",
        "{mgr} needed a {pos} and took the {pos} the market prices at {adp}, at pick {pick}. Revolutionary concept: arithmetic.",
        "Somebody clip this and mail it to the {bust_yr} version of this roster: {player}, {late} picks late, zero damage done.",
        "The whole league drafts {league} picks early on average. {mgr} just went {late} picks LATE on {player}. Do that eleven more times and you might win something.",
        "Two hours of garbage and then this: {player} at {pick}, {late} picks of value. Ruined my entire bit.",
        "Last time {mgr} loved a guy this much it was {bust} in {bust_yr}, who finished {bust_fin}. This time he waited {late} extra picks. Learning is possible.",
    ],
}


def pick_line(cat, ctx, seed, skip=()):
    """One line, chosen deterministically so it never flickers on re-render.

    Falls back rather than raising: a template that references a token this
    pick does not have (a repeat line where the receipt turned out to be
    missing) must degrade to a plainer line, not blank the whole feed.
    """
    # Drop templates whose numbers would render as a lie. {late} is zero on a
    # pick that was actually EARLY, and "slid 0 picks past his ADP" on a
    # fourteen-pick reach is worse than saying nothing: the feed stops being
    # believable the moment one line contradicts the number beside it.
    pool = [t for t in (LINES.get(cat) or LINES["value-and-credit"])
            if not any("{" + tok + "}" in t for tok in skip)]
    pool = pool or [t for t in LINES["value-and-credit"]
                    if not any("{" + tok + "}" in t for tok in skip)]
    if not pool:
        return "{mgr} took {player} at {pick}.".format(**ctx)
    n = len(pool)
    for i in range(n):
        try:
            return pool[(seed + i) % n].format(**ctx)
        except (KeyError, IndexError):
            continue
    return "{mgr} took {player} at {pick}.".format(**ctx)
