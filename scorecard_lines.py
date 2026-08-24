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
        "{over} picks early. Not a crime, {mgr}, just fucking annoying.",
        "{player} had ADP {adp} tattooed on his forehead and you still went at {pick}. You bid against nobody and lost. Fucking impressive.",
        "Reaching {over} spots for a {pos} in round {rnd} is sprinting for a bus that hasn't fucking left yet.",
        "{over} early. Sure. Fine. Whatever gets you through the fucking night.",
        "That's {sd} standard deviations of pure impatience and not one goddamn reason for it.",
        "You paid {over} picks of tax on a {pos} who was falling to you anyway. Goddamn waste of a perfectly good slot.",
        "Bullshit process, survivable outcome. {player} at {pick}, market said {adp}, you said now.",
        "Mild reach, genuinely mild, delivered with such total confidence that it somehow ends up fucking worse.",
        "You could have made a sandwich, eaten it, come back, and still had {player}. Instead you jumped {over} picks early like the clock was on fire.",
        "{mgr} reaches {over}. Career mean {mean_over}. This is him showing restraint, which is the genuinely depressing part.",
        "ADP {adp}. Pick {pick}. Somewhere a spreadsheet just sighed.",
        "It's only {over} picks. It's also completely fucking unnecessary. Both things are true.",
        "A {pos} in round {rnd}, {over} ahead of the market. Not wrong, not right, just a bit shit.",
        "League average reach is {league}. Yours today was {over}. You're not a lunatic, {mgr}, you're just impatient and slightly worse at this than you fucking think.",
        "I'd call it a clusterfuck, but a clusterfuck takes effort. This was just lazy.",
        "Nobody else in this room wanted {player} at {pick}. Nobody. You reached {over} picks into an empty fucking room and shook hands with yourself.",
        "{over} picks early, {sd} standard deviations out, zero excuses offered. Noted.",
        "Fine player. Shit price. {over} picks of shit price, to be precise.",
        "The number was {adp}, {mgr}. It was printed right there. You had one job and it was to sit on your arse and wait.",
        "Round {rnd} and you're already bidding against ghosts. Prick move, honestly.",
        "You pulled this in {bust_yr} with {bust} and he finished {bust_fin}. That was a shitshow. This is only {over} early, so treat it as a warning shot.",
        "{over} picks early is the reach of a man who doesn't trust his own queue. Fix the fucking queue.",
        "Not angry. Mildly fucking irritated. {player}, pick {pick}, ADP {adp}.",
        "{sd} standard deviations above the market. You've turned mild impatience into a personality trait.",
        "Two things can be true: {player} is good, and taking him {over} picks early was a dickhead decision.",
        "{over} picks early. Christ. That's panic-buying with extra steps.",
        "That's reach number {n} today, {mgr}. Each one small. All of them fucking unnecessary.",
        "{pos} off the board {over} early. Eleven other managers just quietly thanked you and moved the fuck on.",
        "Reached {over} on a guy the market had at {adp}. Not a fireable offence. Still a shit look.",
        "{over} picks early on a {pos} in round {rnd} won't lose you the season. It'll just sit there being fucking stupid until January.",
        "Honest scale: this is a stubbed toe, not a car crash. Still fucking hurts.",
        "{player}, {over} picks early, no competition, no clock pressure, no reason. Baffling fucking work.",
        "The bad news is {over} picks early. The good news is it's only {over} picks early.",
        "You wanted that pick to look like conviction. It looks like anxiety with a draft board.",
        "A {pos} at {pick} against an ADP of {adp}. That's not a steal, that's a self-inflicted fucking premium.",
        "Every draft, {mgr}. {over} here, {over} there. It's never one disaster, it's a thousand small stupid ones, and the shit adds up.",
        "{over} early. The pick isn't the problem. The reflex is the fucking problem.",
        "You went {pos} {over} picks early. You did the same in {qb_yrs}. At some point 'my guy' becomes 'my fucking problem'.",
        "Round {rnd}, {over} picks early, and the man had ADP {adp}. You didn't draft him, you rescued him from a threat that didn't exist.",
        "{over} picks early on {player}. Not fatal, just needless — the fantasy equivalent of tipping forty percent at a fucking drive-thru.",
        "Eleven other managers watched {mgr} take {player} {over} ahead of {adp} and not one of them said a word. That silence is them smiling, you absolute prick.",
        "{player} at {pick}, ADP {adp}. {mgr} beat the market by {over} picks and the market wasn't even fucking playing.",
        "Round {rnd} and {mgr} is already bidding against himself. {over} early. Nobody was fucking coming for him.",
        "A {over}-pick reach on a {pos}. Mild on its own. But this shit compounds, and {mgr} is carrying a career {mean_over} against a league mean of {league}.",
        "{mgr} takes {player} {over} early. Somewhere in this room a guy who wanted him at {adp} quietly pivoted to someone better and said fuck all about it.",
        "{over} ahead of ADP. It's not a clusterfuck. It's just persistently, quietly dumb, which across fourteen rounds is worse.",
        "{sd} standard deviations early. {mgr} has never once in his life let a {pos} sit on the board and be available to somebody else.",
        "Round {rnd}, {over} early. This is the draft equivalent of turning up an hour early to a party and helping set the fucking chairs out.",
        "You did not need to do that, {mgr}. {over} picks of pure unforced bullshit.",
        "{player} was going at {adp}. {mgr} went at {pick}. That {over}-pick gap is the tax he pays for not being able to sit the fuck still.",
        "{over} over market for a {pos} in round {rnd}. Nobody else at this table is panicking about the position. That should have been your first goddamn clue.",
        "{over} early. Career mean {mean_over}. At some point this stops being a reach and starts being a goddamn personality trait.",
        "Taking {player} {over} ahead of {adp} in round {rnd} feels decisive in the moment. On the tape it reads as twitchy as hell.",
        "{mgr} reached {over} for {bust} back in {bust_yr} and watched him finish {bust_fin}. Same itch, same round, same fucking result loading.",
        "The board said {adp}. {mgr} said {pick}. One of those numbers came out of thousands of drafts and the other came out of a bloke who couldn't wait {over} more picks.",
        "{over} picks early on a {pos}. Not enough to lose a season. Exactly enough to lose a round.",
        "Eleven managers just got gifted {over} picks of extra room, free of charge. Generous of you, {mgr}. Fucking stupid, but generous.",
        "{mgr} sits at {mean_over} for his career while the league sits at {league}. Today's {over} isn't variance, it's a habit he point-blank refuses to fix.",
        "A {over}-pick reach nobody will remember — unless {player} does sod all, in which case it gets dragged up at every draft for the next decade.",
        "Not a shitshow. Just a small, avoidable, {over}-pick shrug.",
        "{mgr} took {player} at {pick} because he got worried. {over} picks of worry. That's all that fucking number measures.",
        "A {pos} in round {rnd}, {over} ahead of the market. Bold. Also completely fucking unnecessary.",
        "ADP {adp}. Actual {pick}. Difference {over}. No further comment required, and yet somehow the whole chat is already typing.",
        "{mgr} has taken a quarterback early in {qb_yrs}, and here he is again, {over} ahead of the market, chasing the same shit up the same hill.",
        "That's {n} reaches from {mgr} today and this one's {over} early. Individually forgivable. Collectively a fucking pattern.",
        "{player} at {pick}, {over} early. Someone else at this table had him ranked lower than you did and just got handed a better player for free. Cheers for that, dickhead.",
        "Round {rnd}, {over} over ADP, and the entire room leaned back at exactly the same moment. Read the fucking room, {mgr}.",
        "It's only {over} picks. It's only {sd} standard deviations. It's only every single goddamn year.",
        "A {pos} taken {over} early is the draft equivalent of clearing your throat when nobody asked you to speak. Mildly embarrassing. Largely harmless.",
        "{mgr} burns {over} picks of value on {player} and calls it conviction. Everyone else calls it an inability to sit through a bit of fucking silence.",
        "{over} early in round {rnd}. Not the worst pick of the draft. Give it time though — {mgr} is only warming his arse up.",
        "You reached {over} for {player}, {mgr}. The market had him at {adp}. The market has never once had to explain itself in a group chat.",
        "{over} early on a {pos} and eleven managers just quietly recalculated their boards in their own favour. Enjoy it — you've paid well over the odds for the privilege of going first, you daft prick.",
        "Mild reach: {over}. Mild consequences: probably. Mild irritation from the other eleven: absolutely fucking zero, they're delighted.",
        "{mgr} at {pick} for {player}, ADP {adp}. That's {over} picks of impatience dressed up as a fucking plan.",
        "{sd} standard deviations, {over} picks, round {rnd}. Small numbers, same old bullshit.",
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
        "{over} picks early. {over} fucking picks early. {mgr} stared at an entire board of available humans and decided {player} was the emergency.",
        "Nobody else was touching {player}. Not one soul. {mgr} still paid a {over}-pick tax that did not fucking exist.",
        "{sd} standard deviations above the mean. That's not a reach, that's a fucking crime scene.",
        "ADP said {adp}. {mgr} said {pick}. {over} picks of daylight between them and not one fucking shred of reasoning.",
        "Round {rnd}, and {mgr} sets {over} picks of value on fire for a {pos}. Absolute shitshow.",
        "{mgr} could have sat there, done nothing, drunk a beer, and still had {player} {over} picks later. Instead we got this bullshit.",
        "{player} at {pick}. ADP {adp}. No further questions.",
        "League average reach is {league}. {mgr}'s career average is {mean_over}. Tonight: {over}. Apparently that shitty record needed defending.",
        "{over} picks early on a {pos} in round {rnd}. Goddamn. Somebody take the mouse off them.",
        "Reaching {over} picks for {player} is a 2am decision made at 8pm in front of eleven witnesses.",
        "{sd} standard deviations. {over} picks. One extremely fucked draft board.",
        "Remember {bust}? {mgr} reached in {bust_yr}, he finished {bust_fin}, and here we go again — {over} early on {player}. Same shit, new season.",
        "That's {over} picks early for a guy who'd still be sitting there two rounds from now. Not aggressive. Just bad fucking arithmetic.",
        "Bold. Stupid. Mostly stupid. {over} picks early at {pick}.",
        "There's a timeline where {mgr} takes any other {pos} here and doesn't torch {over} picks of capital on someone nobody else fucking wanted. We are not in it.",
        "Complete clusterfuck. {player} at {pick} against an ADP of {adp} — {over} picks of unforced, self-inflicted damage.",
        "{over} picks early, {sd} above the mean. A random number generator would have done better and it wouldn't have talked half as much shit beforehand.",
        "Round {rnd}. {over} early. {mgr} is drafting like the board is on fire. It isn't. There is no fucking fire.",
        "Christ almighty. {over} picks. For {player}. In round {rnd}.",
        "You didn't have to beat the market by {over} picks, {mgr}. The market wasn't even fucking bidding.",
        "{mgr} reached {over} spots for {pos} help, and the only people helped are the other eleven managers quietly losing their shit in the chat.",
        "{sd} standard deviations of pure, undiluted bullshit at pick {pick}.",
        "Somewhere an ADP sheet just got torn in half. {over} picks early, {mgr}. {over}.",
        "In {bust_yr} this exact instinct produced {bust}, who finished {bust_fin}. Tonight it cost {over} picks. The instinct is not your fucking friend.",
        "A {pos} taken {over} picks early in round {rnd}. Genuinely — what in the actual fuck was the plan here?",
        "{player} was going at {adp}. {mgr} grabbed him at {pick} like someone was closing in. Nobody was closing in. Nobody fucking wanted him.",
        "Eleven managers just had {over} picks of free value dropped in their laps. Say thanks to {mgr} on the way past.",
        "{over} picks early. Screenshot this one. It'll be funny in November and fucking hilarious in December.",
        "That pick was fucking stupid and the numbers beside it agree: {over} spots, {sd} deviations, round {rnd}.",
        "{mgr} has pulled this {n} times now — reach {over}-plus, blame the board, learn absolutely fuck all.",
        "Taking a {pos} {over} picks early at {pick} is a choice. A dogshit one, but a choice.",
        "Squint hard enough and {over} picks early looks like conviction. Stop squinting. It's a reach and it's going to fucking hurt.",
        "{qb_yrs}: the years {mgr} went early and swore blind it was the plan. Tonight adds {over} more picks to the tab.",
        "{over} picks early. {mgr} has now paid a premium into a market of one, and that market was them.",
        "This is the pick that gets brought up every year until the heat death of the universe. {over} fucking picks early, {sd} above the mean.",
        "Ugly. Just fucking ugly. {player}, {over} picks before anyone else in this league would have even blinked.",
        "Reached {over} picks for {player}. The room went dead silent, and not the good kind of silent.",
        "{player} at {pick}. His ADP was {adp}. That is {over} picks of pure, uncut, unforced fucking error.",
        "Somewhere on that board, real value just died. {mgr} killed it in round {rnd} and didn't even have the decency to look sorry.",
        "{over} picks early. {sd} standard deviations out. There is a projection model somewhere quietly closing itself.",
        "You could have had {player} at {adp}. You could have had him after another sandwich. Instead {mgr} panicked {over} picks early like an absolute prick who forgot the draft was tonight.",
        "The entire {pos} tier is untouched. Untouched! And {mgr} sprinted past all of it to reach {over} picks for this.",
        "A {over}-pick reach in round {rnd}. Not aggressive. Not bold. Just bad.",
        "Market says {adp}. {mgr} says {pick}. One of those two has a track record of being wrong and it isn't the market.",
        "{over} picks early for a lad who would have been sat on that board doing fuck all two rounds from now.",
        "Deadpan for a second: {player} was available at {adp}. It is now {pick}. Nothing occurred in the interim to justify a single one of those {over} picks.",
        "Reaching {over} in round {rnd} is exactly how you end up explaining a {bust_fin}th-place finish to people who stopped listening in November.",
        "Remember {bust} in {bust_yr}? {bust_fin}th? {mgr} clearly doesn't, because here we fucking go again, {over} picks early.",
        "The value on this board was flashing like a goddamn hazard light and {mgr} drove straight through it at {pick}.",
        "{over} picks early. In a snake draft. With a timer that hadn't even started blinking. What exactly was the rush?",
        "That is not a pick. That is a shitshow with a name attached to it.",
        "{sd} standard deviations from normal behaviour. Congratulations {mgr}, you are now a statistical outlier, and not in a fun way.",
        "There were {n} better options at {pos} still on the board at {pick}. {mgr} took the one that cost an extra {over} picks.",
        "Complete clusterfuck. {player} at {pick}, ADP {adp}, and eleven people behind {mgr} who just got a free upgrade out of it.",
        "{over} picks early. Call it conviction if it helps you sleep. Everyone else is calling it a reach.",
        "{player} sat at {adp} on every board, every site, all bloody summer. {mgr} went {over} picks early anyway, apparently from memory.",
        "Round {rnd} and the good {pos}s are all still there. Every one of them. {mgr} paid a {over}-pick premium specifically to avoid a bargain.",
        "This is what a {mean_over} career average looks like out in the wild. Unpleasant, isn't it.",
        "That pick was fucking stupid and the {over} printed next to it is the receipt.",
        "Bold. Decisive. Wrong by {over} picks.",
        "You had until {adp}, {mgr}. You had until {adp}. That is a genuinely enormous amount of time in which to not do this.",
        "The board just lost a name it did not need to lose. {over} picks early, round {rnd}, for reasons nobody in this league can articulate.",
        "{mgr} takes {player} at {pick}. Twelve people open the ADP. Twelve people see {adp}. Twelve people say absolutely nothing.",
        "{over} picks of daylight between the market and this decision. Fill that gap with whatever story you like, it is still bullshit.",
        "Reached {over} for a {pos} while the rest of the {pos} tier sat there gathering dust. Beautiful. Genuinely beautiful stuff.",
        "Not a reach. A goddamn expedition.",
        "Total silence, then someone typed 'oh', then silence again. {over} picks early will do that to a room.",
        "{mgr} is now {mean_over} across a career against a league mean of {league}. At this point it isn't a habit, it's a whole personality, and tonight it cost {over} picks.",
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
        "{mgr} reached {over} for {bust} in {bust_yr}. {bust} finished {bust_fin}. Here's {player} at {pick} — same fucking movie, new poster.",
        "Career mean of {mean_over} against a league mean of {league}, and {mgr} still went {over} early like the fucking spreadsheet doesn't exist.",
        "{over} picks early isn't a mistake, it's a personality. {mgr} averages {mean_over} and calls it a fucking process.",
        "{mgr} takes his {pos} {over} picks before the market every single year. The market has not adjusted. Neither has he.",
        "A {pos} in round {rnd}. Again. {qb_yrs}, and now this — {mgr} genuinely cannot fucking help himself.",
        "{n} times {mgr} has taken this exact swing and {n} times it's landed on his own fucking foot. {player}, {over} early, pick {pick}.",
        "{bust} finished {bust_fin} back in {bust_yr} and {mgr} learned absolutely fuck all from it. {over} early, right on schedule.",
        "{sd} standard deviations early. Career mean {mean_over}, league mean {league}. The man is his own goddamn outlier.",
        "Receipts, since we're all here: {mgr}, {mean_over} career, {over} on {player} tonight. The trend line is a fucking cliff.",
        "Remember {bust}? {bust_yr}? Finished {bust_fin}? {mgr} clearly doesn't, because he just torched {over} picks of value doing the same shit again.",
        "{mgr} sits at {mean_over}, the league sits at {league}. That gap isn't variance, it's a goddamn habit, and {player} at {pick} is the newest entry.",
        "Same shit, different August: {mgr} spots a {pos} he likes and burns {over} picks getting there.",
        "{player}, {over} ahead of an ADP of {adp}. Filed in the same shit drawer as {bust}, {bust_yr}, {bust_fin}.",
        "Two things are true. {mgr} reaches {mean_over} on average. And he is absolutely convinced tonight is different.",
        "That's the {n}th time {mgr} has jumped a {pos} by this much. {over} early on {player}, and he'll do it again next year because he learns fuck all.",
        "{mgr}'s draft history is one long fucking apology he never gets round to writing. {over} early tonight. {bust} sends his regards from {bust_fin}.",
        "The league reaches {league} picks. {mgr} reaches {mean_over}. Tonight, {over}. Consistency is a virtue, apparently.",
        "{over} picks early is a bold move from a man whose last bold move finished {bust_fin}.",
        "{mgr} has gone {pos} in round {rnd} in {qb_yrs}. Not one of those years taught him a fucking thing, and here we are again at {over} early.",
        "{mgr} doesn't reach, he pre-orders. {player}, {over} early, ADP {adp} — no receipt, no refund, no fucking chance.",
        "History says {mgr} takes his guy {over} picks early and then spends December wondering what the fuck happened. {bust_yr} said it loudest: {bust_fin}.",
        "The board had {player} at {adp}. {mgr} had him {over} picks ago, which is precisely where he had {bust} in {bust_yr}.",
        "{mgr} is {mean_over} for his career. The league is {league}. Only one of those numbers belongs to a man who reads ADP.",
        "Shitshow sequel, straight to video: {over} early on {player}, following {bust} in {bust_yr}, who finished {bust_fin}.",
        "Round {rnd}, {pos}, {mgr}. We've watched this in {qb_yrs} and it ended the same fucking way every time.",
        "{over} picks early. {mean_over} career. {league} league average. The numbers don't lie, {mgr} just doesn't read the fuckers.",
        "A clusterfuck with provenance: {over} early on {player}, the exact same reach he made on {bust} in {bust_yr}.",
        "If you want to know how a {over}-pick reach ages, ask {bust}. He finished {bust_fin} and {mgr} went and did it again anyway.",
        "{mgr}'s pattern, plainly stated: sees {pos}, panics, clicks. {over} early tonight, {mean_over} for the fucking career.",
        "Nobody in this league reaches like {mgr}. {mean_over} career, {league} for everyone else, and {player} at {pick} is the arse-end of that trend.",
        "Someone pull the archive. Oh wait, it's already open: {mean_over} career, {over} tonight. Bullshit repeats itself.",
        "A prick of a reach at {pick}, {over} ahead of the board, and the archive says {mgr} does this every year at {mean_over}.",
        "The {bust} pick in {bust_yr} finished {bust_fin} and somehow that's still the fucking blueprint. {player}, {over} early.",
        "{mgr} reaching {over} picks early is the most predictable event in this draft, and he's been doing it since before {bust_yr}.",
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
        "{late} picks late on {player}. Fine. Fucking fine. I've got nothing.",
        "Look at {mgr} not being a dickhead for once: {player} at {pick}, a full {late} picks past his {adp} ADP.",
        "{player}, {late} picks after ADP. That's a good pick. Moving on before anyone gets emotional.",
        "Eleven other people fell asleep and {mgr} walked off with {player} {late} picks late. Broken clock, twice a day, still a fucking clock.",
        "{late} picks of free value on a {pos}, and of course it goes to {mgr}. Of fucking course it does.",
        "The board collapsed and {player} slid {late} picks past his ADP. {mgr} did the hard part: clicking the button.",
        "Credit where it's due -- {player} at {pick} is {late} picks of value and I hate every letter I just typed.",
        "{sd} standard deviations in the RIGHT direction. Somebody frame this, it won't fucking happen again.",
        "{pos} in round {rnd} at pick {pick}, {late} picks late. No notes. Genuinely no notes, which is its own insult to me.",
        "{mgr}'s career average is {mean_over} picks early. Today he's {late} picks LATE. What the fuck happened.",
        "This league reaches {league} picks early on average. {mgr} just went {late} picks the other way. Bullshit. Good bullshit, but bullshit.",
        "Same manager who reached for {bust} in {bust_yr} and watched him finish {bust_fin}. Today: {player}, {late} picks late. Growth, apparently. Fucking growth.",
        "That's {late} picks of value. I had a whole paragraph loaded about what a shitshow this was going to be. Wasted.",
        "Nobody wants to hear it, but {player} at {pick} is a steal. There. Said it. Fuck.",
        "{late} picks late. Not a reach, not a clusterfuck, just a pick. Boring. Correct. Boring.",
        "Every other manager looked at {player} and did nothing at all. {mgr} looked at him and typed the name. Genius by default.",
        "ADP said {adp}. {mgr} got him at {pick}. That is {late} picks of somebody else's stupidity, harvested.",
        "Good pick. Now do it {n} more times and we'll call it a draft instead of a happy accident.",
        "{sd} SDs of value on a {pos}. I'd applaud, but I remember the QB picks in {qb_yrs} and I'm not that fucking forgiving.",
        "Genuinely good pick. Genuinely. I'm as pissed off about it as you are confused.",
        "{late} picks late on {player} and {mgr} still looked terrified pressing the button. Take the win, you prick.",
        "This is the bit where I'd swear at you. Can't. {player} at {pick} is {late} picks of value and it's fucking inconvenient for me.",
        "Round {rnd}, pick {pick}, {late} picks past ADP. Fine pick. Don't get comfortable, there are {n} more chances to ruin this.",
        "The rest of you let a {pos} fall {late} picks. That's on you lot, not on {mgr}, who just picked up the free money like a normal fucking person.",
        "Not a shitshow. Say that quietly and don't jinx it.",
        "{mgr} took {player} {late} picks under market and the room went quiet, because nobody had a joke ready. Including me. Especially me.",
        "Correct pick. Full stop. I'll be back to calling you a dickhead in roughly four minutes.",
        "{late} picks of value. Every draft has exactly one non-idiot pick in it, and congratulations, this is yours.",
        "Solid. {player}, pick {pick}, {late} picks late. Enjoy it, because the career mean is {mean_over} and the regression is coming for your arse.",
        "Somebody drafted like they'd actually read something. {player}, {late} picks after his {adp} ADP. Deeply suspicious. Who helped you?",
        "Goddamn it. That's good.",
        "{late} picks of value in round {rnd}. Statistically you were due, and by due I mean {n} drafts of absolute shite preceded this.",
        "That's {late} picks late on a {pos} this roster actually needed. One moment of competence, logged and timestamped.",
        "{mgr} at pick {pick}, {late} picks below ADP, and the worst part is he'll walk away thinking it was skill.",
        "Value of {late} picks, {sd} SDs the good way, and a {pos} the roster needed. Three correct things in one pick. I'm going for a fucking walk.",
    ],
}


import re as _re


def _ordinals(text):
    """Fix "3th" and "162th".

    Templates append a literal "th" to a number token, which is right four
    times out of ten and wrong the rest. Correcting the rendered string is far
    safer than editing three hundred templates, and 11/12/13 keep "th".
    """
    def sub(m):
        n = int(m.group(1))
        if n % 100 in (11, 12, 13):
            suf = "th"
        else:
            suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"
    text = _re.sub(r"\b(\d+)th\b", sub, text)
    # Counts arrive as bare numbers, so a manager who did something once was
    # being told he had done it "1 times".
    text = _re.sub(r"\b1 times\b", "once", text)
    text = _re.sub(r"\b1 (picks|rounds|years|seasons|spots|managers)\b",
                   lambda m: "1 " + m.group(1)[:-1], text)
    text = _re.sub(r"\b1 (reaches|offenses|offences)\b",
                   lambda m: "1 " + m.group(1)[:-2], text)
    return text


def pick_line(cat, ctx, seed, skip=(), used=None):
    """One line, chosen deterministically so it never flickers on re-render.

    `used` is a dict of template -> times spent, shared across the whole draft.
    Selection takes the LEAST-used eligible template, tie-broken by an offset
    from the pick number. That is what keeps a 150-pick feed from repeating
    itself: earlier attempts either fell back to a fixed offset (one line fired
    eight times) or cleared the pool on exhaustion (thrashed between categories
    and did worse). Least-used cannot do either -- every template is spent once
    before any is spent twice.

    Templates whose tokens would render as a lie for this pick are filtered out
    first: {late} is zero on a pick that was early, and a sentence contradicting
    the number printed beside it costs more than a repeat would.
    """
    def eligible(pool):
        return [t for t in pool
                if not any("{" + tok + "}" in t for tok in skip)]

    pool = eligible(LINES.get(cat) or [])
    if not pool:
        # Borrow from anywhere rather than print nothing.
        pool = [t for v in LINES.values() for t in eligible(v)]
    if not pool:
        return "{mgr} took {player} at {pick}.".format(**ctx)

    if used is None:
        used = {}
    n = len(pool)
    best, best_key = None, None
    for i in range(n):
        t = pool[(seed + i) % n]
        key = (used.get(t, 0), i)
        if best_key is None or key < best_key:
            best, best_key = t, key
    try:
        line = best.format(**ctx)
    except (KeyError, IndexError):
        for i in range(n):
            t = pool[(seed + i) % n]
            try:
                line = t.format(**ctx)
                best = t
                break
            except (KeyError, IndexError):
                continue
        else:
            return "{mgr} took {player} at {pick}.".format(**ctx)
    used[best] = used.get(best, 0) + 1
    return _ordinals(line)
