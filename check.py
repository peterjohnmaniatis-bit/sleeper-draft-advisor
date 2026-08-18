#!/usr/bin/env python3
"""Validate the generated report before it goes anywhere.

    python check.py

Catches the failure modes that are invisible in the source but obvious on the
page: CSS that breaks under entity encoding, chart elements escaping their
viewBox, colors that only exist in one theme, and missing accessible labels.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGETS = [ROOT / "report.html", ROOT / "out" / "shared.html",
           ROOT / "draft-report.html", ROOT / "out" / "draft-shared.html",
           ROOT / "dashboard.html", ROOT / "out" / "dashboard.html"]
CHAR_W = 6.6  # conservative average advance for 12px system-ui

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

fails = []


def fail(target, msg):
    fails.append(f"{target.name}: {msg}")


def check_css(doc, target):
    """CSS `content` does not parse HTML entities, and neither do CSS
    identifiers. A non-ASCII character anywhere in the stylesheet becomes
    literal '&#NNNN;' text the moment the file is entity-encoded."""
    for css in re.findall(r"<style>(.*?)</style>", doc, re.S):
        for ch in css:
            if ord(ch) > 127:
                fail(target, f"non-ASCII {ch!r} in <style> -- breaks under entity encoding")
                break
        if "&#" in css:
            leaked = re.findall(r"&#\d+;", css)
            fail(target, f"HTML entity inside <style>, renders literally: {leaked[:3]}")


def check_tokens(doc, target):
    """Every color must come from a token defined on bare :root, or the page
    renders one theme's ink on the other theme's ground."""
    for css in re.findall(r"<style>(.*?)</style>", doc, re.S):
        outside = css
        for block in re.findall(r":root[^{]*\{[^}]*\}", css):
            outside = outside.replace(block, "")
        stray = re.findall(r"#[0-9a-fA-F]{6}\b", outside)
        if stray:
            fail(target, f"hex literal outside :root token blocks: {stray[:3]}")

        base = re.search(r":root\s*\{([^}]*)\}", css)
        if not base:
            fail(target, "no bare :root block -- light theme has no definitions")
            continue
        base_tokens = set(re.findall(r"(--[\w-]+):", base.group(1)))
        for block in re.findall(r"(?:@media[^{]*\{\s*)?:root[^{]*\[data-theme[^{]*\{([^}]*)\}", css):
            for tok in set(re.findall(r"(--[\w-]+):", block)):
                if tok not in base_tokens:
                    fail(target, f"{tok} defined only in a themed block, never on bare :root")


def path_bounds(d):
    """Min/max x and y for the path subset the charts emit (M H V Q h v Z)."""
    toks = re.findall(r"([MHVQhvZ])([-\d.,\s]*)", d)
    x = y = 0.0
    xs, ys = [], []
    for cmd, args in toks:
        nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", args)]
        if cmd == "M" and len(nums) >= 2:
            x, y = nums[0], nums[1]
        elif cmd == "H" and nums:
            x = nums[-1]
        elif cmd == "V" and nums:
            y = nums[-1]
        elif cmd == "Q" and len(nums) >= 4:
            xs += [nums[0], nums[2]]
            ys += [nums[1], nums[3]]
            x, y = nums[2], nums[3]
        elif cmd == "h" and nums:
            x += nums[-1]
        elif cmd == "v" and nums:
            y += nums[-1]
        xs.append(x)
        ys.append(y)
    return (min(xs), max(xs), min(ys), max(ys)) if xs else (0, 0, 0, 0)


def check_svgs(doc, target):
    charts = 0
    for block in re.findall(r'(<svg viewBox="0 0 [\d.]+ [\d.]+".*?</svg>)', doc, re.S):
        charts += 1
        W, H = map(float, re.match(r'<svg viewBox="0 0 ([\d.]+) ([\d.]+)"', block).groups())
        tag = f"chart {charts}"

        if 'aria-label="' not in block[:400]:
            fail(target, f"{tag} has no aria-label")
        if "data-tip" not in block:
            fail(target, f"{tag} has no hover layer")

        for m in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"', block):
            x, y, w, h = map(float, m.groups())
            if x < -0.5 or x + w > W + 0.5 or y + h > H + 0.5:
                fail(target, f"{tag} rect escapes viewBox: x..{x+w:.0f} of {W:.0f}")

        for m in re.finditer(r'<path d="([^"]+)"', block):
            x0, x1, y0, y1 = path_bounds(m.group(1))
            if x0 < -0.5 or x1 > W + 0.5 or y1 > H + 0.5:
                fail(target, f"{tag} path escapes viewBox: x {x0:.0f}..{x1:.0f} "
                             f"y {y0:.0f}..{y1:.0f} of {W:.0f}x{H:.0f}")

        texts = []
        for m in re.finditer(r"<text[^>]*x=\"([-\d.]+)\" y=\"([-\d.]+)\"([^>]*)>(.*?)</text>", block):
            x, y, attrs, txt = float(m.group(1)), float(m.group(2)), m.group(3), m.group(4)
            txt = re.sub(r"<[^>]+>", "", txt)
            w = len(txt) * CHAR_W
            anchor = (re.search(r'text-anchor="(\w+)"', attrs) or [None, "start"])[1]
            left = x if anchor == "start" else (x - w if anchor == "end" else x - w / 2)
            if left < -0.5 or left + w > W + 0.5 or y > H + 0.5:
                fail(target, f"{tag} text {txt!r} escapes viewBox: "
                             f"{left:.0f}..{left+w:.0f} of {W:.0f}")
            texts.append((y, left, left + w, txt))

        # Labels that share a baseline must not run into each other. Bounds
        # checks alone miss this: both labels sit inside the viewBox and still
        # overlap, which is exactly how a value ends up printed over a name.
        rows = {}
        for y, left, right, txt in texts:
            rows.setdefault(round(y), []).append((left, right, txt))
        for y, items in sorted(rows.items()):
            items.sort()
            for (l1, r1, t1), (l2, r2, t2) in zip(items, items[1:]):
                if r1 > l2 + 0.5:
                    fail(target, f"{tag} labels collide at y={y}: "
                                 f"{t1!r} ends {r1:.0f}, {t2!r} starts {l2:.0f}")
    return charts


def check_fragment(doc, target):
    if target.parent.name != "out":
        return
    for tag in ("<!doctype", "<html", "<head", "</head>", "<body", "</body>"):
        if tag in doc.lower():
            fail(target, f"fragment contains document wrapper {tag!r}")
    if any(ord(c) > 127 for c in doc):
        fail(target, "fragment contains non-ASCII -- host may not assume UTF-8")


def main():
    checked = 0
    for target in TARGETS:
        if not target.exists():
            continue
        checked += 1
        doc = target.read_text(encoding="utf-8")
        check_css(doc, target)
        check_tokens(doc, target)
        check_fragment(doc, target)
        charts = check_svgs(doc, target)
        print(f"{target.name}: {charts} charts, {len(doc)/1024:.0f} KB")

    if not checked:
        raise SystemExit("nothing to check -- run: python report.py")
    print()
    if fails:
        for f in fails:
            print(f"  FAIL  {f}")
        raise SystemExit(f"\n{len(fails)} problem(s)")
    print("all checks passed")


if __name__ == "__main__":
    main()
