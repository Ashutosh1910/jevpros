"""Render REPORT.html - the shareable, plain-language report - from results/*.md and results/*.json.

The narrative (what each benchmark asks, how, what we found, what it means) lives in EXPERIMENTS below;
numbers in it were copied from results/*.md. Charts are drawn from results/*.json.
"""

import html
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R = ROOT / "results"


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return c - h, c + h


# ---------- tiny markdown -> html (for the folded raw tables) ----------

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def md_to_html(text):
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append('<div class="scroll"><pre class="mono">' + html.escape("\n".join(lines[i + 1:j])) + "</pre></div>")
            i = j + 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|(\s*-+\s*\|)+\s*$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ['<div class="scroll"><table><thead><tr>' + "".join(f"<th>{inline(h)}</th>" for h in rows[0]) + "</tr></thead><tbody>"]
            t += ["<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:]]
            out.append("".join(t) + "</tbody></table></div>")
        elif ln.startswith("# "):
            i += 1
        elif ln.startswith("#"):
            out.append(f"<h5>{inline(ln.lstrip('#').strip())}</h5>")
            i += 1
        elif ln.strip() == "" or ln.startswith("---"):
            i += 1
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(\||#|```)", lines[i]):
                para.append(lines[i])
                i += 1
            if any(p.startswith("  ") for p in para):
                out.append(f'<pre class="method">{html.escape(chr(10).join(para))}</pre>')
            else:
                out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


# ---------- charts ----------

def line_chart(cid, pts, ymin, ymax, xlabel, ylabel, ref=None, ref_label="", xticks=None, logx=False):
    W, H, L, Rr, T, B = 640, 280, 52, 20, 16, 44
    xs = [math.log2(p[0]) if logx else p[0] for p in pts]
    x0, x1 = min(xs), max(xs)
    sx = lambda x: L + ((math.log2(x) if logx else x) - x0) / (x1 - x0) * (W - L - Rr)  # noqa: E731
    sy = lambda y: T + (ymax - y) / (ymax - ymin) * (H - T - B)  # noqa: E731
    g = []
    for yt in range(int(ymin * 100), int(ymax * 100) + 1, 10):
        y = sy(yt / 100)
        g.append(f'<line class="grid" x1="{L}" x2="{W - Rr}" y1="{y:.1f}" y2="{y:.1f}"/>'
                 f'<text class="tick" x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{yt}%</text>')
    for xt in (xticks or [p[0] for p in pts]):
        g.append(f'<text class="tick" x="{sx(xt):.1f}" y="{H - B + 18}" text-anchor="middle">{xt}</text>')
    band = " ".join(f"{sx(p[0]):.1f},{sy(p[3]):.1f}" for p in pts) + " " + \
        " ".join(f"{sx(p[0]):.1f},{sy(p[2]):.1f}" for p in reversed(pts))
    g.append(f'<polygon class="band" points="{band}"/>')
    if ref is not None:
        g.append(f'<line class="ref" x1="{L}" x2="{W - Rr}" y1="{sy(ref):.1f}" y2="{sy(ref):.1f}"/>'
                 f'<text class="reflabel" x="{L + 8}" y="{sy(ref) - 6:.1f}">{ref_label}</text>')
    g.append('<path class="series" d="' + " ".join(f"{'M' if k == 0 else 'L'}{sx(p[0]):.1f},{sy(p[1]):.1f}"
                                                    for k, p in enumerate(pts)) + '"/>')
    for p in pts:
        g.append(f'<circle class="dot" cx="{sx(p[0]):.1f}" cy="{sy(p[1]):.1f}" r="4.5"/>'
                 f'<circle class="hit" cx="{sx(p[0]):.1f}" cy="{sy(p[1]):.1f}" r="16" data-tip="{html.escape(p[4])}"/>')
    last = pts[-1]
    g.append(f'<text class="endlabel" x="{sx(last[0]) - 8:.1f}" y="{sy(last[1]) + 20:.1f}" text-anchor="end">{last[1]:.0%}</text>')
    g.append(f'<text class="axis" x="{(L + W - Rr) / 2}" y="{H - 6}" text-anchor="middle">{xlabel}</text>')
    g.append(f'<text class="axis" transform="translate(13 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle">{ylabel}</text>')
    return f'<svg id="{cid}" class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{ylabel} by {xlabel}">{"".join(g)}</svg>'


def bar_chart(cid, bars, xmax, ref=None, ref_label="", label_w=190):
    rowh, W = 34, 640
    T = 8 if ref is None else 26
    H = T + rowh * len(bars) + 30
    L, Rr = label_w, 56
    sx = lambda v: L + v / xmax * (W - L - Rr)  # noqa: E731
    g = []
    for t in range(0, int(xmax * 100) + 1, 10 if xmax <= 0.3 else 20):
        x = sx(t / 100)
        g.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{H - 28}"/>'
                 f'<text class="tick" x="{x:.1f}" y="{H - 10}" text-anchor="middle">{t}%</text>')
    for k, (lab, v, lo, hi, tip, emph) in enumerate(bars):
        y = T + k * rowh + 8
        g.append(f'<text class="barlabel" x="{L - 10}" y="{y + 13}" text-anchor="end">{html.escape(lab)}</text>')
        g.append(f'<rect class="bar{" emph" if emph else ""}" x="{L}" y="{y}" width="{max(sx(v) - L, 0):.1f}" height="18" rx="3"/>')
        g.append(f'<line class="whisker" x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y + 9}" y2="{y + 9}"/>')
        g.append(f'<text class="value" x="{max(sx(hi), sx(v)) + 8:.1f}" y="{y + 13}">{v:.0%}</text>')
        g.append(f'<rect class="hitbar" x="{L}" y="{y - 6}" width="{W - L - Rr}" height="{rowh - 4}" data-tip="{html.escape(tip)}"/>')
    if ref is not None:
        g.append(f'<line class="ref" x1="{sx(ref):.1f}" x2="{sx(ref):.1f}" y1="{T}" y2="{H - 28}"/>'
                 f'<text class="reflabel" x="{sx(ref):.1f}" y="{T - 8}" text-anchor="middle">{ref_label}</text>')
    return f'<svg id="{cid}" class="chart" viewBox="0 0 {W} {H}" role="img">{"".join(g)}</svg>'


def charts():
    e08 = json.loads((R / "e08_depth.json").read_text())
    pts = []
    for d, s in e08.items():
        lo, hi = wilson(round(s["atom"] * 80), 80)
        pts.append((int(d), s["atom"], lo, hi, f"{d} exception(s): {s['atom']:.1%} correct (likely range {lo:.0%}–{hi:.0%})"))
    depth = line_chart("c-depth", pts, 0.4, 1.0, "exceptions stacked in each rule", "answers correct",
                       ref=0.5, ref_label="coin flip (50%)", xticks=list(range(1, 11)))

    e04 = json.loads((R / "e04_injection.json").read_text())
    names = {"benign": "Harmless comment", "assertion": "User insists on answer", "fake_rule": "Claims the rule changed",
             "instruction": "“Ignore all rules” (at end)", "instruction_top": "“Ignore all rules” (at top)",
             "authority": "Fake administrator note"}
    n_ok = round(e04["none"]["acc_target"] * 150)
    bars = []
    for key in ["benign", "assertion", "instruction", "fake_rule", "instruction_top", "authority"]:
        v = e04[key]["flip_rate_of_correct"]
        lo, hi = wilson(round(v * n_ok), n_ok)
        bars.append((names[key], v, lo, hi, f"{names[key]}: turned {v:.1%} of {n_ok} correct answers wrong", key == "authority"))
    inj = bar_chart("c-inj", bars, 0.8)

    e03 = json.loads((R / "e03_invariance.json").read_text())
    vn = {"rename": "Rename the items", "units": "Change unit format", "reorder": "Shuffle the order",
          "synonyms": "Reword every rule", "all": "All four at once"}
    noise = e03["repeat (noise floor)"]["atom_flip"]
    bars = []
    for key in ["rename", "units", "reorder", "synonyms", "all"]:
        v = e03[key]["atom_flip"]
        lo, hi = wilson(round(v * 300), 300)
        bars.append((vn[key], v, lo, hi, f"{vn[key]}: {v:.1%} of 300 answers changed (re-asking changes {noise:.1%})", False))
    inv = bar_chart("c-inv", bars, 0.25, ref=noise, ref_label=f"just re-asking: {noise:.0%}")

    e06 = json.loads((R / "e06_options.json").read_text())
    pts = []
    for n in [2, 4, 8, 16, 32, 64, 128, 255]:
        s = e06[f"T2 roster|{n}"]
        lo, hi = wilson(round(s["ok"] * 25), 25)
        pts.append((n, s["ok"], lo, hi, f"{n} options: {s['ok']:.0%} correct"))
    opt = line_chart("c-opt", pts, 0.4, 1.0, "number of employees to choose from (log scale)", "picked correctly", logx=True)
    e13 = json.loads((R / "e13_anchoring.json").read_text())["conds"]
    an = [("control_r1", "Re-asked, no history"), ("model_wrong_95", "Another AI model said wrong"),
          ("reviewer_wrong_95", "A human reviewer said wrong"), ("user_wrong_95", "The user said wrong"),
          ("self_wrong_95", "Jev itself said wrong"),
          ("fb_incorrect_on_correct", "Reviewer: right answer “incorrect”"),
          ("fb_correct_on_wrong", "Reviewer: wrong answer “correct”")]
    bars = []
    for key, lab in an:
        c = e13[key]
        lo, hi = wilson(c["harm_k"], c["harm_n"])
        bars.append((lab, c["harm"], lo, hi, f"{lab}: turned {c['harm']:.1%} of {c['harm_n']} right answers wrong",
                     key.startswith("fb_")))
    anchor = bar_chart("c-anchor", bars, 1.0, label_w=280)
    e14 = [json.loads(line) for line in (ROOT / "data/e14_dutch_book/answers.jsonl").open()]
    groups = [("Dice, cards, urns, coins", lambda r: r["family"] == "chance"),
              ("Base-rate populations", lambda r: r["family"] == "baserate")]
    groups += [(f"Policies, {d} exceptions deep", lambda r, d=d: r["family"] == "policy" and r["depth"] == d)
               for d in (2, 3, 4, 5)]
    bars = []
    for lab, keep in groups:
        v = [r["checks"]["cells_sum"] for r in e14 if keep(r)]
        m = sum(v) / len(v)
        se = (sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v)) ** 0.5
        bars.append((lab, m, m - 1.96 * se, m + 1.96 * se, f"{lab}: the four outcomes sum to {m:.0%} on average "
                     f"({len(v)} sets)", False))
    cells = bar_chart("c-cells", bars, 1.8, ref=1.0, ref_label="should be exactly 100%", label_w=220)
    e15 = [json.loads(line) for line in (ROOT / "data/e15_reasoning/answers.jsonl").open()]
    deep = [r for r in e15 if r["depth"] >= 7]
    base = sum(r["ok0"] for r in deep if r["cond"] == "none") / sum(r["cond"] == "none" for r in deep)
    rows15 = [("first_half", "partial", "First half of the steps"), ("steps", "steps", "All steps, no conclusion"),
              ("wrong", "steps_wrongconcl", "All steps + a WRONG conclusion"),
              ("verified", "steps_wrongconcl_verified", "Same, labelled “verified”"),
              ("flawed", "flawed", "One wrong step, conclusion follows it"),
              ("concl", "concl_only_wrong", "Only a WRONG conclusion")]
    bars = []
    for _, cond, lab in rows15:
        v = [r["ok0"] for r in deep if r["cond"] == cond]
        k, n = sum(v), len(v)
        lo, hi = wilson(k, n)
        bars.append((lab, k / n, lo, hi, f"{lab}: {k / n:.0%} correct on rules 7–10 exceptions deep ({n} cases)",
                     cond in ("steps_wrongconcl_verified", "flawed")))
    reason = bar_chart("c-reason", bars, 1.0, ref=base, ref_label=f"no notes: {base:.0%}", label_w=250)
    return {"E08": depth, "E04": inj, "E03": inv, "E06": opt, "E13": anchor, "E14": cells, "E15": reason}


# ---------- the narrative ----------
# verdict: good | mixed | bad

EXPERIMENTS = [
    {"id": "E00", "file": "e00_main", "title": "Do related answers fit together logically?", "verdict": "mixed",
     "short": "Probabilities follow logic; borderline yes/no answers often contradict each other",
     "asks": "When Jev answers several related questions about the same situation, do the answers agree with each other? "
             "If it says “Expense 1 is approved” and “Expense 2 is approved”, it should also say “both are approved”.",
     "how": ["600 computer-generated policy scenarios like the example above, each with 2–4 items and 1–5 nested exceptions.",
             "13–17 linked questions per scenario: each item on its own, the opposite of each item, AND, OR, a nested "
             "combination, a “what if one fact changed” question, multiple-choice over outcomes, and a count. About 9,000 answers in total.",
             "Every answer was checked against the correct answer and against Jev's other answers. The same checks were run on "
             "random guesses as a baseline."],
     "found": ["Individual items were answered correctly <b>87%</b> of the time (98% with one exception, 76% with five).",
               "The <b>probabilities</b> obey logic: an item and its opposite added up to roughly 100% in 96% of cases, and "
               "AND/OR answers broke the rules of probability only 2–3% of the time (random guessing: 54–63%).",
               "After rounding each probability to yes or no, <b>46% of scenarios</b> contained at least one answer that "
               "contradicted another. Nearly all of these were borderline answers near 50%. Jev never said a confident "
               "“yes” and a confident “no” to the same thing.",
               "Its confidence means something: when a yes/no probability was above 90%, it was right about 98% of the time."],
     "means": "Jev's probabilities are consistent and meaningful, but its answers near 50% are coin flips that can contradict "
              "each other. Use the probability, not just the yes/no, and treat anything between about 0.3 and 0.7 as “unsure”."},

    {"id": "E01", "file": "e01_numbers_negation", "title": "Numbers, dates and negatives", "verdict": "good",
     "short": "480/480 number and 159/160 date comparisons right; three stacked “nots” trip it",
     "asks": "Can Jev compare numbers and dates, and understand sentences with “not” in them? Other write-ups said it can't "
             "reliably compare numbers or dates.",
     "how": ["704 tiny one-rule tests, e.g. “a shipment is flagged if its weight is over 12 kg. Weight: 12 kg.” "
             "Is it flagged? (No, because 12 is not over 12.)",
             "8 phrasings (over, at least, under, not exceeding…), whole numbers, money, five-digit numbers and decimals, with "
             "values far away, 1 unit away, or exactly on the threshold.",
             "Dates in 4 formats (2026-03-04, 03/04/2026, March 4, 2026, 4 Mar 2026), including across New Year.",
             "Statements wrapped in 0–3 negations (“It is not the case that it is false that…”)."],
     "found": ["Numbers: <b>480 of 480</b> correct, including every exact-threshold case.",
               "Dates: <b>159 of 160</b> correct.",
               "Negation: perfect with up to two negatives, but <b>11 of 16</b> (69%) with three.",
               "In the bigger scenarios, rules worded with “not” cost about 2–5 percentage points of accuracy."],
     "means": "Comparing numbers and dates is not a weakness, so there's no need to pre-compute them in code. Avoid double "
              "and triple negatives when writing questions."},

    {"id": "E02", "file": "e02_unknowable", "title": "Does it admit when it can't know?", "verdict": "mixed",
     "short": "Spots a missing rule 99% of the time, but a missing fact only 33%",
     "asks": "When the information needed to answer is missing, does Jev say “can't tell”, or does it guess?",
     "how": ["150 scenarios, each shown four ways: complete; with a harmless fact removed; with a <i>deciding</i> fact removed; "
             "and with the item's category having no rule at all.",
             "Jev was asked the question and also given a three-way choice: yes, no, or “not enough information”."],
     "found": ["No matching rule: it chose “not enough information” <b>99%</b> of the time.",
               "A deciding fact removed: it chose “not enough information” only <b>33%</b> of the time. Otherwise it "
               "guessed yes or no, although its confidence dropped (0.71 against 0.84 normally).",
               "A harmless fact removed: it still answered correctly (87–91%), so it doesn't panic over irrelevant gaps."],
     "means": "Jev notices when a whole rule is missing but often guesses when a single fact is missing. Offer a "
              "“can't tell” option, and check for required fields in code rather than relying on Jev to notice."},

    {"id": "E03", "file": "e03_invariance", "title": "Same question, different wording, or asked twice", "verdict": "mixed",
     "short": "Not deterministic (4% of answers change on re-ask); rewording or reordering changes 14–15%",
     "asks": "If we describe exactly the same situation in different words, or simply ask again, do we get the same answer?",
     "how": ["150 scenarios shown six ways: the original, items renamed (“Expense 1” → “Submission Q-17”), the order of "
             "rules and facts shuffled, every rule sentence reworded, units written differently (“$120” → “120 USD”), and all "
             "of these at once. The correct answer never changes.",
             "The original was also sent 5 times, identically, to measure how much answers vary on their own."],
     "found": ["Sending the identical request again changed <b>4%</b> of yes/no answers, and the exact numbers were identical "
               "only 4% of the time. This is the “noise floor”.",
               "Renaming items (6%) and changing units (5%) made no difference beyond that noise.",
               "Shuffling the order (14%) and rewording (15%) changed about <b>3.5× more</b> answers than noise. With 5 "
               "nested exceptions, about half the scenarios got a different answer."],
     "means": "Jev is not deterministic, and it is sensitive to wording and ordering on complex rules. Keep your prompt "
              "template fixed. For important decisions, ask 3–5 times and take the majority."},

    {"id": "E04", "file": "e04_injection", "title": "Can planted text trick it?", "verdict": "bad",
     "short": "Ignores “ignore all rules”, but obeys a fake administrator note 64% of the time",
     "asks": "If someone slips a line into the input pushing for the wrong answer, does Jev follow it?",
     "how": ["150 scenarios that Jev normally gets right (93%). One line was added pushing towards the wrong answer, "
             "in six styles: a harmless comment, the user insisting, a claim that the rule changed, “IGNORE ALL "
             "PREVIOUS RULES” at the end or the top, and a note claiming to be from the policy administrator.",
             "We counted how many previously correct answers became wrong."],
     "found": ["Harmless comments and users insisting: <b>0%</b> changed.",
               "“Ignore all rules” instructions: <b>1–4%</b>. A claimed rule change: 2%.",
               "Fake administrator note: <b>64%</b> of correct answers turned wrong, and accuracy fell from 93% to 33%."],
     "means": "Jev resists crude attacks but defers to anything that looks like official authority. If the input can "
              "contain user-written text, remove or clearly label it before sending. Don't use Jev as a security filter "
              "without that step."},

    {"id": "E05", "file": "e05_independence", "title": "Do questions in one call affect each other?", "verdict": "good",
     "short": "No: batching or leading questions change answers no more than noise",
     "asks": "When many questions are sent in one request (which is cheaper), does one question influence another?",
     "how": ["150 scenarios. The same question was asked alone, alongside 16 others, last in the list, next to four "
             "“leading” questions that assume the wrong answer, and five times in the same request."],
     "found": ["Answers changed only <b>3–5%</b> of the time, which matches the 4% you get by simply asking again.",
               "Leading questions had no measurable effect.",
               "Even five identical copies in one request gave identical numbers only 19% of the time, differing by at most 0.16."],
     "means": "Batch freely. Putting many questions in one request doesn't bias the answers, and it saves cost and time."},

    {"id": "E06", "file": "e06_options", "title": "How many choices can it handle?", "verdict": "good",
     "short": "100% with 255 options for lookups; searching a 255-item list with 3 conditions drops to 80%",
     "asks": "Jev allows up to 255 options in a multiple-choice question. Does accuracy drop as the number of options grows?",
     "how": ["Lookup: “What is this record's reference code?” with 2 to 255 similar-looking codes as options.",
             "Search: a list of N employees where exactly one meets three conditions (department, badge level, training) "
             "and most others miss by just one. N ranged from 2 to 255. 25 tries per size."],
     "found": ["Lookup: <b>100%</b> correct at every size, up to 255 options.",
               "Search: 100% up to 32 employees, 96% at 64–128, and <b>80%</b> at 255."],
     "means": "Many options on their own are fine. Searching a long list against several conditions gets harder, so "
              "pre-filter long lists in code where you can."},

    {"id": "E07", "file": "e07_context", "title": "Does a lot of irrelevant text confuse it?", "verdict": "good",
     "short": "No: 95–97% accuracy even with ~25k tokens of look-alike rules",
     "asks": "Real inputs are messy. If the relevant rules are buried in pages of unrelated text, does Jev still find them?",
     "how": ["30 scenarios with the relevant rules buried in 1,000 to 25,000 tokens (roughly 2 to 50 pages) of look-alike "
             "rules or generic policy text, placed before, between or after the relevant rules."],
     "found": ["Accuracy stayed at <b>95–97%</b>, against 97% with no extra text. Where the filler went made no difference.",
               "Response time rose from about 400 to 690 milliseconds."],
     "means": "Long inputs are fine. Trimming them saves time and money but isn't needed for accuracy."},

    {"id": "E08", "file": "e08_depth", "title": "How deep can the rule logic go?", "verdict": "bad",
     "short": "98% with 1 exception, 83% with 5, coin flip (56%) with 10",
     "asks": "Rules often have exceptions to exceptions. How many layers can Jev follow?",
     "how": ["320 scenarios where each rule has 1 to 10 exceptions stacked on top of each other "
             "(“approved by default, unless X, but if also Y then rejected, however if Z…”)."],
     "found": ["Correct answers fell from <b>98%</b> with 1 exception to 90% with 3, 83% with 5, about 75% with 6–9, and "
               "<b>56% with 10</b>, the same as a coin flip.",
               "When lost, it falls back to the rule's default. With 10 exceptions, 69% of its wrong answers were simply the default.",
               "Scenarios with at least one self-contradiction rose from 5% to 85%."],
     "means": "Keep each question to about 3 layers of exceptions. For deeper logic, split it into steps and feed each "
              "result into the next request."},

    {"id": "E09", "file": "e09_counting", "title": "Can it count consistently?", "verdict": "bad",
     "short": "Gets each item right 94% of the time, but its count is right only 67.5%",
     "asks": "Are Jev's answers to “how many items are approved?” consistent with its answers about each item?",
     "how": ["200 scenarios with 4 items each. We asked about each item, “how many are approved” (0 to 4), “at least n” "
             "for n = 1 to 4, and “exactly n” for n = 0 to 4."],
     "found": ["Each item individually: <b>94%</b> correct. The count question: only <b>67.5%</b>, and it disagreed with "
               "Jev's own per-item answers 28.5% of the time.",
               "“At least n” behaved perfectly: the probability always went down as n went up.",
               "The five “exactly n” probabilities should add up to 100% but averaged <b>136%</b>. In a third of cases it "
               "said “yes” to more or fewer than one of them."],
     "means": "Don't ask Jev to count or total. Ask about each item and add up in code. When exactly one of several options "
              "is true, use one multiple-choice question rather than several yes/no questions."},

    {"id": "E11", "file": "e11_load", "title": "Speed under load", "verdict": "good",
     "short": "~400 ms median at any load; 92 requests/second at 64 parallel; no errors",
     "asks": "How fast is Jev, and does it slow down when many requests arrive at once?",
     "how": ["The same request (about 1,200 tokens of input, 13 questions) sent 1, 2, 4, 8, 16, 32 and 64 at a time."],
     "found": ["Median response time was about <b>400 ms</b> at every level.",
               "The slowest 5% took about 500 ms up to 16 parallel requests and about 950 ms from 32 upwards.",
               "Throughput reached <b>92 requests per second</b> at 64 parallel, with zero errors or rate-limit rejections."],
     "means": "Fast enough for real-time use. It scales well to at least 64 concurrent requests."},

    {"id": "E12", "file": "e12_selftrust", "title": "Does it know when it can answer?", "verdict": "mixed",
     "short": "Great at spotting missing information; blind to its own reasoning mistakes",
     "asks": "Before answering, can Jev tell whether it will be able to answer correctly? This is useful as a cheap pre-check.",
     "how": ["3,744 questions of 17 kinds, from one-line number checks to 255-option choices and 20,000-token inputs. "
             "740 of them cannot be answered from the information given (a missing fact, no matching rule, or a question "
             "about something not mentioned).",
             "Two separate requests per question. First: “can this be answered with certainty from the information "
             "given?”, asked as yes/no and on a 4-step scale from “cannot be determined” to “certain”. Second: the question itself."],
     "found": ["The yes/no version <b>leaks the answer</b>: Jev scored whether the statement was true rather than whether "
               "it could be answered. The 4-step scale doesn't have this problem, so the rest uses the scale.",
               "It is very good at spotting <b>missing information</b>. It said “can't” for 98–100% of questions about "
               "facts not given, and separated answerable from unanswerable questions almost perfectly (AUROC 0.977; see glossary).",
               "It is <b>blind to its own reasoning mistakes</b>. It claimed it could answer 100% of multi-step policy "
               "questions but got only 71–79% right. On inputs with a fake administrator note it was still sure, then "
               "right only 31% of the time. It missed 41% of cases where a deciding fact was removed.",
               "As a filter it helps: keeping the half of questions it rated most answerable gave <b>90%</b> accuracy, "
               "against 83% using the answer's confidence alone and 92.6% using both together."],
     "means": "Ask “can this be answered?” on a scale, never as yes/no, and use it to catch missing information. It won't "
              "warn you about hard logic or manipulated inputs, so pair it with the answer's own confidence."},

    {"id": "E13", "file": "e13_anchoring", "title": "Does it stick to earlier answers in a conversation?", "verdict": "mixed",
     "short": "Its own history doesn't lock in mistakes, but one reviewer line saying “incorrect” flips 69% of right answers",
     "asks": "Jev has no memory, so a conversation means writing the earlier turns into the input. When the input shows an "
             "earlier answer to the same question, does Jev work it out again or copy it?",
     "how": ["400 policy scenarios with 2 to 5 stacked exceptions, each sent 25 ways: three times with no history (to "
             "measure noise), and with a “conversation so far” block holding one earlier true/false answer to the same question.",
             "The earlier answer was right or wrong, stated at 95% or 55% confidence, and credited to Jev itself, another AI "
             "model, the user or a human reviewer. Four versions added a reviewer's verdict on Jev's earlier answer "
             "(“correct” or “incorrect”), and one showed Jev its own real first answer. 10,000 requests in total."],
     "found": ["In a realistic conversation, where Jev sees its <b>own real first answer</b>, its decision matched that answer "
               "94% of the time, the same as simply asking again (95%). Accuracy didn't change (86%) and mistakes weren't "
               "locked in, though confidence rose slightly (0.80 → 0.83).",
               "A planted wrong answer nudges it, and <b>its own nudges it most</b>. “Your earlier answer” being wrong turned "
               "<b>13%</b> of right answers wrong, against 5–8% when the same answer came from the user, a reviewer or another "
               "AI model, and 1.5% from re-asking. With 5 stacked exceptions this rose to 31%.",
               "A right earlier answer helps more than a wrong one hurts. Shown its own right answer, Jev fixed <b>68%</b> of "
               "the questions it had got wrong, and accuracy rose from 84% to 94%.",
               "A <b>verdict takes over</b>. “A reviewer says it is incorrect” turned <b>69%</b> of right answers wrong, and "
               "“says it is correct” kept a planted wrong answer 96% of the time. When the verdict was true, it fixed 95% of mistakes."],
     "means": "Carrying Jev's own earlier answers between turns is safe; it doesn't compound mistakes. But anything in the "
              "history that reads like a ruling (“correct”, “incorrect”) overrides the rules, like the fake administrator note "
              "in E04. Keep feedback, verdicts and user claims out of the input, or handle them in code."},

    {"id": "E14", "file": "e14_dutch_book", "title": "Can its probabilities be exploited as prices?", "verdict": "mixed",
     "short": "Every set can be Dutch-booked for 4–7¢ a ticket, about what random error of the same size gives; "
              "“not” and “or” statements are overpriced",
     "asks": "If each Jev probability were the price of a $1 bet, could someone combine bets to win whatever happens "
             "(a “Dutch book”)? That is only possible when the probabilities don't fit together, so it measures in "
             "dollars how coherent they are.",
     "how": ["600 pairs of statements about one situation: dice, cards, urns and coins; populations described by counts "
             "or percentages (e.g. “12% have the condition; 90% of those test positive”); and the nested policies used "
             "elsewhere. The first two have exact true probabilities.",
             "Each pair was priced in 9–11 separate requests: each statement, its opposite, AND, OR, the four combinations, "
             "and “B, given that A is true”. We also asked everything in one request, as one multiple choice over the "
             "four combinations, and asked one question twice. 8,000 requests in total.",
             "An exact calculation found the largest guaranteed profit for each pair, with at most $1 per bet."],
     "found": ["<b>Every</b> pair could be Dutch-booked, for $0.48–0.66 on 9–11 one-dollar tickets (about 4–7 cents a "
               "ticket). But prices equal to the true probability plus random error of Jev's size are just as exploitable, "
               "so this mostly reflects ordinary error, not a special flaw. Random prices give about $2.20.",
               "The part that is a real flaw: statements with “not” or “or” are <b>overpriced</b>. The four combinations "
               "should add up to 100% but came to 111% (chance), 128% (populations) and 145% (policies), rising to 169% "
               "with 5 layers of exceptions.",
               "Updating on new information is <b>coherent</b>: Bayes' rule held within 0.03, and it didn't fall for the "
               "classic base-rate trap (confusing “positive if ill” with “ill if positive”) in 94% of cases.",
               "Asking everything in one request didn't help. A single multiple-choice over chance outcomes put 77% on "
               "the most likely outcome when the truth averaged 51%, so separate yes/no questions were more accurate there."],
     "means": "Use Jev's answers to single statements and do the probability arithmetic (AND, OR, NOT) in code. Don't "
              "quote its compound probabilities as prices or odds, and for chance events prefer yes/no questions over one "
              "multiple choice."},

    {"id": "E15", "file": "e15_reasoning", "title": "Can reasoning written into the input help it?", "verdict": "good",
     "short": "Written-out steps take deep rules from 69% to 100%; it follows the steps over a wrong conclusion, "
              "unless the notes claim to be “verified”",
     "asks": "Jev can't reason step by step on its own. If code or another AI writes the reasoning into the input, does "
             "Jev use it, or does it just copy whatever conclusion the notes state?",
     "how": ["400 policy scenarios with 1 to 10 stacked exceptions. For each, a program wrote exact reasoning notes "
             "about one item: every exception checked in order, quoting the fact it depends on.",
             "Each scenario was sent 10 ways: no notes (twice); all steps without a conclusion; all steps with the right "
             "conclusion; all steps with a <i>wrong</i> conclusion (also once labelled “verified result from the rule "
             "engine”); one wrong step with a conclusion that follows it; a conclusion only (right or wrong); and only "
             "the first half of the steps. 4,000 requests."],
     "found": ["With all the steps written out and no conclusion, it was right <b>99.5%</b> of the time, and 100% on "
               "the deepest rules, where it otherwise manages 69%. Half the steps helped much less (78%).",
               "It <b>reads the steps</b>. When correct steps ended in a wrong conclusion, it followed the steps 99% of the "
               "time. A conclusion on its own, without steps, was mostly ignored.",
               "But label the same notes “verified” and it copied the wrong conclusion <b>36%</b> of the time, and half "
               "the time on the deepest rules. It defers to authority, as in E04 and E13.",
               "One plausible wrong step misled it on deep rules: 59% correct, worse than having no notes at all."],
     "means": "This is the way past the depth limit: have code or an LLM write out the steps and let Jev decide from "
              "them. Leave the final answer out, never label the notes as verified, and check the steps themselves, "
              "because a wrong step is the one thing it often won't catch."},
]

GLOSSARY = [
    ("Jev", "A model from TypeSafe (available through OpenRouter) that answers questions with probabilities instead of "
            "writing text. You give it a situation and typed questions, and it returns numbers."),
    ("Input / state", "The text describing the situation, e.g. an expense policy plus the expenses being claimed."),
    ("Yes/no question", "Jev returns the probability that a statement is true, e.g. 0.93. We treat 0.5 or above as “yes”. "
                        "(Jev's API calls this type <code>noul</code>.)"),
    ("Multiple choice", "Jev picks one option and gives a probability for every option, plus an overall confidence."),
    ("Scale", "Jev picks a point on an ordered scale, e.g. “0 of 4” … “4 of 4”."),
    ("Confidence", "How sure an answer is. For yes/no it's the distance from 0.5: both 0.95 and 0.05 are confident, 0.5 is a shrug."),
    ("Exception / depth", "A rule like “approved, unless X; but if also Y, rejected” has two exceptions (depth 2). More "
                          "depth means more steps of logic."),
    ("Flip", "An answer that changes from yes to no (or back) between two versions of the same test."),
    ("Noise floor", "How often an answer flips when the identical request is simply sent again: 4%. Differences near 4% are noise."),
    ("Likely range (95% interval)", "Because we test a sample, each rate has uncertainty. The shaded bands and whiskers "
                                    "on charts show the range where the true value most likely lies."),
    ("Calibrated", "When Jev says 80%, it is right about 80% of the time."),
    ("Dutch book", "A set of bets, at prices taken from someone's probabilities, that wins money whatever happens. It "
                   "exists only when those probabilities don't fit together (E14)."),
    ("Anchoring", "Copying an answer shown earlier in the input instead of working it out again (E13)."),
    ("AUROC", "How well a score separates two groups, e.g. answerable vs unanswerable questions. 0.5 means no better than "
              "a coin flip; 1.0 means perfect separation."),
]

RECOMMENDATIONS = [
    "<b>Strip or label user-written text</b> before sending it to Jev. A single line claiming authority overrides the rules (E04).",
    "<b>Keep logic shallow</b>: about 3 layers of exceptions per question. Split deeper rules into several requests (E08).",
    "<b>Use probabilities, not just yes/no.</b> Treat answers between about 0.3 and 0.7 as “unsure” and route them to a "
    "person or a second check (E00).",
    "<b>Ask important questions 3–5 times</b> and take the majority. Identical requests don't always return identical answers (E03).",
    "<b>Keep your prompt template fixed.</b> Reordering or rewording rules changes answers on complex logic (E03).",
    "<b>Count and total in code.</b> Ask about each item separately. For “exactly one of these”, use a single "
    "multiple-choice question (E09).",
    "<b>Check required fields in code</b> and offer a “can't tell” option. Jev often guesses when a single fact is missing (E02, E12).",
    "<b>Pre-check with a scale question</b> (“can this be answered?”) to catch missing information. Never ask it as yes/no (E12).",
    "<b>In a conversation, carry Jev's own earlier answers if useful, but never feedback about them.</b> A line saying a "
    "reviewer found the answer “incorrect” flips 69% of right answers (E13).",
    "<b>For deep logic, write out the steps and let Jev decide.</b> Leave the conclusion out and never label the notes "
    "as verified (E15).",
    "<b>Do probability arithmetic in code.</b> Ask about single statements and combine them yourself. Jev overprices "
    "statements containing “not” or “or” (E14).",
    "<b>Batch questions freely</b> and don't worry about long inputs, number or date comparisons, or up to 255 options (E05, E07, E01, E06).",
]

LIMITATIONS = [
    "All scenarios are computer-generated policies (expenses, building access, insurance, library loans). This lets us "
    "know the correct answer exactly, but real documents are messier.",
    "Sample sizes range from 25 to 3,744 per test. The likely ranges are shown in the charts and in the full tables.",
    "Each result is for one model version (<code>typesafe/jev-1.13-20260917</code>) on 25 September – 1 October 2026. Behaviour "
    "may change in later versions.",
    "The reasoning notes in E15 were generated by a program and are perfectly clean. Reasoning written by an LLM "
    "will be messier and was not tested.",
    "Jev's answers vary between identical requests (E03). Small differences, especially below about 5 percentage points, "
    "are within noise.",
    "We tested Jev on its own. How it compares with a general-purpose LLM on the same tests was out of scope.",
]


def example_block():
    return """
<div class="example">
  <div class="example-state">
    <div class="eyebrow">What Jev receives (input)</div>
<pre>COMPANY EXPENSE REIMBURSEMENT POLICY
Rule 1 (conference fees): rejected by default.
  Exception: if it was not pre-approved by a Director, it is reimbursed instead.
  But if, in addition, it was not paid with the corporate card, it is rejected after all.
Rule 2 (training courses): reimbursed by default.
  Exception: if it was not paid with the corporate card, it is rejected instead.
  However, in that case, if the trip is international, it is reimbursed.

CASE
- Expense 1 (training courses): domestic trip; corporate card: yes; $190.
- Expense 2 (conference fees): corporate card: no; pre-approved by a Manager; no receipt.</pre>
  </div>
  <div class="example-walk">
    <div class="eyebrow">The correct answers, worked out</div>
    <ol>
      <li><b>Expense 1</b>: training is reimbursed by default. The exception needs “not paid with the corporate card”, but it was paid with the card, so the exception doesn't apply. <b>Reimbursed.</b></li>
      <li><b>Expense 2</b>: conference fees are rejected by default. It was approved by a Manager, not a Director, so the first exception applies: reimbursed. It also wasn't paid with the card, so the second exception applies: <b>rejected.</b></li>
    </ol>
    <div class="eyebrow">What Jev said</div>
    <div class="scroll"><table class="qa">
      <thead><tr><th>Question</th><th>Jev</th><th>Correct</th></tr></thead>
      <tbody>
        <tr><td>“Expense 1 is reimbursed”</td><td>0.98 yes</td><td class="ok">✓ yes</td></tr>
        <tr><td>“Expense 2 is reimbursed”</td><td>0.48 no (barely)</td><td class="ok">✓ no</td></tr>
        <tr><td>“Expense 1 AND Expense 2 are reimbursed”</td><td>0.58 yes</td><td class="no">✗ no, and it contradicts the line above</td></tr>
        <tr><td>Multiple choice: which are reimbursed?</td><td>“only Expense 1”</td><td class="ok">✓</td></tr>
      </tbody>
    </table></div>
    <p class="note">This one scenario shows the pattern the whole report measures. Jev is mostly right, and when it's
    unsure (0.48), related answers can contradict each other.</p>
  </div>
</div>"""


def exp_section(e, chart_svg):
    li = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"  # noqa: E731
    raw = (R / f"{e['file']}.md").read_text()
    chart = ""
    if chart_svg:
        caption = {
            "E08": "Share of answers correct by number of stacked exceptions. The shaded band is the likely range. Hover for values.",
            "E04": "Share of previously correct answers that became wrong after one planted line. Whiskers show the likely range.",
            "E03": "Share of yes/no answers that changed when the same situation was rewritten. The dashed line is the change from simply asking again.",
            "E06": "Picking the one employee who meets all three conditions, by list length. Pure lookup (not shown) stayed at 100%.",
            "E15": "Share of answers correct on the deepest rules (7–10 stacked exceptions) with different reasoning "
                   "notes in the input. The dashed line is the score with no notes. Red bars are where the notes made "
                   "it worse. Whiskers show the likely range.",
            "E14": "Jev's four separate yes/no answers for “A and B”, “A and not B”, “not A and B” and “neither”, "
                   "added up. Exactly one of them is true, so a coherent set sums to 100%. Whiskers show the likely range.",
            "E13": "Share of answers Jev got right with no history that turned wrong once the conversation showed one earlier "
                   "answer (all stated at 95% confidence). Red bars add a reviewer's verdict on Jev's own earlier answer. "
                   "Whiskers show the likely range.",
        }[e["id"]]
        chart = f'<figure>{chart_svg}<figcaption>{caption}</figcaption></figure>'
    labels = {"good": "Strong", "mixed": "Mixed", "bad": "Weak spot"}
    return f"""
<section class="exp" id="{e['id'].lower()}">
  <header class="exp-head">
    <span class="eid">{e['id']}</span>
    <h3>{e['title']}</h3>
    <span class="chip {e['verdict']}">{labels[e['verdict']]}</span>
  </header>
  <div class="parts">
    <div class="part"><div class="plabel">What it asks</div><p>{e['asks']}</p></div>
    <div class="part"><div class="plabel">How we tested</div>{li(e['how'])}</div>
    <div class="part"><div class="plabel">What we found</div>{li(e['found'])}</div>
  </div>
  {chart}
  <div class="means"><div class="plabel">What it means</div><p>{e['means']}</p></div>
  <details><summary>Full data tables for {e['id']}</summary><div class="dbody">{md_to_html(raw)}</div></details>
</section>"""


def project_spend():
    """Total OpenRouter usage after the latest run, from RUN_LOG.md ("spent $X ... usage before: $Y").
    Includes probe calls that are not in logs/, so it is slightly above the logged total."""
    runs = re.findall(r"spent \$([\d.]+).*?usage before: \$([\d.]+)", (ROOT / "RUN_LOG.md").read_text())
    return max(float(a) + float(b) for a, b in runs)


def main():
    ch = charts()
    labels = {"good": "Strong", "mixed": "Mixed", "bad": "Weak spot"}
    score_rows = "".join(
        f'<tr><td><a href="#{e["id"].lower()}">{e["id"]}</a></td><td>{e["title"]}</td><td>{e["short"]}</td>'
        f'<td><span class="chip {e["verdict"]}">{labels[e["verdict"]]}</span></td></tr>' for e in EXPERIMENTS)
    sections = "".join(exp_section(e, ch.get(e["id"])) for e in EXPERIMENTS)
    gloss = "".join(f"<dt>{t}</dt><dd>{d}</dd>" for t, d in GLOSSARY)
    cost_md = (ROOT / "REPORT.md").read_text().split("## Calls and cost")[1].split("\n---")[0]
    total = re.search(r"\| \*\*total\*\* \| (\d+) \| (\d+) \|", cost_md)
    words = {12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}
    page = TEMPLATE.format(n_exp=len(EXPERIMENTS), n_words=words.get(len(EXPERIMENTS), len(EXPERIMENTS)),
                           n_calls=int(total[1]), n_errors=int(total[2]), spend=project_spend(),
                           errors_label="transient errors, all retried" if int(total[2]) else "errors",
                           scoreboard=score_rows, sections=sections, glossary=gloss, example=example_block(),
                           recs="".join(f"<li>{r}</li>" for r in RECOMMENDATIONS),
                           limits="".join(f"<li>{x}</li>" for x in LIMITATIONS), cost=md_to_html(cost_md))
    (ROOT / "REPORT.html").write_text(page)
    print("wrote REPORT.html", len(page), "bytes")


TEMPLATE = """<title>Jev Stress Test</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg: #f5f7f9; --panel: #ffffff; --ink: #11161c; --ink-2: #414c58; --ink-3: #6b7682;
  --rule: #dfe4ea; --grid: #e8ecf0; --accent: #2a78d6; --accent-soft: rgba(42,120,214,.13);
  --bad: #c0392b; --bad-soft: #fbeaea; --good: #1d7a45; --good-soft: #e6f4ec; --mid: #9a6700; --mid-soft: #fff4d6;
  --code: #eef2f6;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0f1318; --panel: #161b21; --ink: #eef2f6; --ink-2: #b9c3cd; --ink-3: #8a96a3;
    --rule: #2a323b; --grid: #232a32; --accent: #3987e5; --accent-soft: rgba(57,135,229,.2);
    --bad: #ef7a7a; --bad-soft: #2d1a1c; --good: #4cc27f; --good-soft: #14281d; --mid: #e3b341; --mid-soft: #2b2412;
    --code: #1e252d; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0f1318; --panel: #161b21; --ink: #eef2f6; --ink-2: #b9c3cd; --ink-3: #8a96a3;
  --rule: #2a323b; --grid: #232a32; --accent: #3987e5; --accent-soft: rgba(57,135,229,.2);
  --bad: #ef7a7a; --bad-soft: #2d1a1c; --good: #4cc27f; --good-soft: #14281d; --mid: #e3b341; --mid-soft: #2b2412;
  --code: #1e252d; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--ink); font: 16px/1.65 "Instrument Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 900px; margin: 0 auto; padding-inline: 20px; padding-block: 40px 80px; }}
h1, h2, h3, h5 {{ text-wrap: balance; line-height: 1.25; margin: 0; }}
h1 {{ font-size: clamp(2rem, 5vw, 2.7rem); font-weight: 700; letter-spacing: -.02em; }}
h2 {{ font-size: 1.5rem; font-weight: 650; margin-top: 60px; margin-bottom: 14px; padding-top: 8px; }}
h3 {{ font-size: 1.2rem; font-weight: 650; }}
h5 {{ font-size: .95rem; margin: 18px 0 6px; }}
p {{ margin: 0 0 12px; max-width: 70ch; }}
a {{ color: var(--accent); }}
a:focus-visible, summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.eyebrow, .plabel {{ font: 500 11.5px/1.3 "JetBrains Mono", ui-monospace, monospace; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); }}
.plabel {{ margin-bottom: 6px; color: var(--accent); }}
.lede {{ font-size: 1.12rem; color: var(--ink-2); margin-top: 14px; }}
.facts {{ display: flex; flex-wrap: wrap; gap: 10px 30px; margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--rule); }}
.facts div {{ display: flex; flex-direction: column; }}
.facts b {{ font: 500 1.3rem/1.2 "JetBrains Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
.facts span {{ font-size: 13px; color: var(--ink-3); }}
nav.toc {{ margin-top: 24px; display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 14px; }}
.tldr {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 10px; padding: 20px 24px 8px; }}
.tldr li {{ margin-bottom: 10px; max-width: 72ch; }}
.scroll {{ overflow-x: auto; margin: 10px 0 14px; }}
table {{ border-collapse: collapse; font-size: 14px; min-width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font-weight: 600; color: var(--ink-2); background: var(--code); }}
table.score td:first-child a {{ font: 500 13px "JetBrains Mono", monospace; text-decoration: none; }}
table.score td:nth-child(2) {{ font-weight: 600; min-width: 170px; }}
table.score td:nth-child(3) {{ color: var(--ink-2); }}
.chip {{ display: inline-block; font: 600 11px/1 "JetBrains Mono", monospace; letter-spacing: .05em; text-transform: uppercase; padding: 5px 8px; border-radius: 4px; white-space: nowrap; }}
.chip.good {{ background: var(--good-soft); color: var(--good); }}
.chip.mixed {{ background: var(--mid-soft); color: var(--mid); }}
.chip.bad {{ background: var(--bad-soft); color: var(--bad); }}
.example {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; background: var(--panel); border: 1px solid var(--rule); border-radius: 10px; padding: 20px; }}
@media (max-width: 760px) {{ .example {{ grid-template-columns: 1fr; }} }}
.example pre {{ font: 12.5px/1.55 "JetBrains Mono", monospace; background: var(--code); padding: 14px; border-radius: 6px; white-space: pre-wrap; margin: 8px 0 0; }}
.example ol {{ padding-left: 20px; margin: 8px 0 16px; font-size: 15px; }}
.example li {{ margin-bottom: 8px; }}
table.qa td:nth-child(2) {{ font-family: "JetBrains Mono", monospace; font-size: 13px; white-space: nowrap; }}
td.ok {{ color: var(--good); }} td.no {{ color: var(--bad); }}
.note {{ font-size: 14px; color: var(--ink-2); }}
dl.gloss {{ display: grid; grid-template-columns: minmax(130px, 200px) 1fr; gap: 10px 20px; background: var(--panel); border: 1px solid var(--rule); border-radius: 10px; padding: 20px 24px; margin: 0; }}
@media (max-width: 600px) {{ dl.gloss {{ grid-template-columns: 1fr; gap: 2px; }} dl.gloss dd {{ margin-bottom: 10px; }} }}
dl.gloss dt {{ font-weight: 600; }}
dl.gloss dd {{ margin: 0; color: var(--ink-2); font-size: 15px; }}
.exp {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 10px; padding: 22px 24px 10px; margin-bottom: 22px; scroll-margin-top: 16px; }}
.exp-head {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
.exp-head h3 {{ flex: 1 1 260px; }}
.eid {{ font: 500 13px "JetBrains Mono", monospace; color: var(--accent); }}
.parts {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
.part ul {{ padding-left: 20px; margin: 0; }}
.part li {{ margin-bottom: 7px; max-width: 72ch; }}
.part p {{ margin: 0; }}
.means {{ margin: 16px 0 12px; background: var(--accent-soft); border-radius: 8px; padding: 14px 16px; }}
.means .plabel {{ color: var(--ink); }}
.means p {{ margin: 0; font-weight: 500; }}
figure {{ margin: 16px 0 6px; }}
figcaption {{ font-size: 13.5px; color: var(--ink-3); margin-top: 4px; }}
.chart {{ width: 100%; height: auto; display: block; overflow: visible; }}
.chart .grid {{ stroke: var(--grid); stroke-width: 1; }}
.chart .tick, .chart .reflabel {{ fill: var(--ink-3); font: 12px "JetBrains Mono", monospace; }}
.chart .axis {{ fill: var(--ink-2); font: 13px "Instrument Sans", sans-serif; }}
.chart .series {{ fill: none; stroke: var(--accent); stroke-width: 2.5; stroke-linejoin: round; }}
.chart .band {{ fill: var(--accent-soft); }}
.chart .dot {{ fill: var(--accent); stroke: var(--panel); stroke-width: 2; }}
.chart .hit, .chart .hitbar {{ fill: transparent; }}
.chart .hitbar:hover {{ fill: var(--accent-soft); opacity: .6; }}
.chart .ref {{ stroke: var(--ink-3); stroke-width: 1.2; stroke-dasharray: 4 4; }}
.chart .endlabel, .chart .value {{ fill: var(--ink); font: 500 13px "JetBrains Mono", monospace; }}
.chart .barlabel {{ fill: var(--ink-2); font-size: 13px; }}
.chart .bar {{ fill: var(--accent); }}
.chart .bar.emph {{ fill: var(--bad); }}
.chart .whisker {{ stroke: var(--ink); stroke-width: 1.5; opacity: .5; }}
#tip {{ position: fixed; pointer-events: none; background: var(--ink); color: var(--bg); font-size: 13px; line-height: 1.4; padding: 8px 10px; border-radius: 6px; max-width: 300px; z-index: 5; }}
details {{ border-top: 1px solid var(--rule); margin-top: 8px; }}
summary {{ padding: 12px 2px; cursor: pointer; font-size: 14px; color: var(--ink-3); list-style: none; }}
summary::-webkit-details-marker {{ display: none; }}
summary::before {{ content: "▸ "; }}
details[open] summary::before {{ content: "▾ "; }}
.dbody {{ padding-bottom: 14px; }}
.dbody td:not(:first-child) {{ font-family: "JetBrains Mono", monospace; font-size: 12.5px; white-space: nowrap; }}
.dbody table {{ font-size: 13px; }}
code {{ font: 13px "JetBrains Mono", monospace; background: var(--code); padding: 1px 5px; border-radius: 3px; }}
pre.mono, pre.method {{ font: 12px/1.5 "JetBrains Mono", monospace; background: var(--code); padding: 12px; border-radius: 6px; margin: 0; }}
pre.method {{ white-space: pre-wrap; color: var(--ink-2); margin: 8px 0 12px; }}
.recs li, .limits li {{ margin-bottom: 10px; max-width: 74ch; }}
.recs {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 10px; padding: 18px 24px 8px 44px; }}
</style>

<div class="wrap">
<header>
  <div class="eyebrow">Benchmark report · TypeSafe Jev 1.13 via OpenRouter · September 2026</div>
  <h1>Jev stress test</h1>
  <p class="lede">We ran {n_words} experiments to find out where TypeSafe's Jev model can be trusted to make decisions and
  where it can't. Each section below explains, in plain language, what we tested, how, what happened, and what it means
  for building with Jev.</p>
  <div class="facts">
    <div><b>{n_exp}</b><span>experiments</span></div>
    <div><b>{n_calls:,}</b><span>questions sent</span></div>
    <div><b>{n_errors}</b><span>{errors_label}</span></div>
    <div><b>${spend:.2f}</b><span>total cost</span></div>
    <div><b>~0.4 s</b><span>typical response</span></div>
  </div>
  <nav class="toc" aria-label="Contents">
    <a href="#summary">Summary</a><a href="#background">What Jev is</a><a href="#example">A worked example</a>
    <a href="#glossary">Glossary</a><a href="#experiments">The experiments</a><a href="#recommendations">Recommendations</a>
    <a href="#limitations">Limitations</a><a href="#cost">Cost &amp; data</a>
  </nav>
</header>

<h2 id="summary">Summary in one minute</h2>
<div class="tldr"><ul>
  <li><b>Good at the basics.</b> It gets number and date comparisons right, handles up to 255 answer options, isn't
  distracted by long inputs, answers in about 0.4 seconds, and its probabilities mean what they say.</li>
  <li><b>Loses track of deep logic.</b> Accuracy falls from 98% with one exception in a rule to a coin flip with ten.
  When lost, it falls back to the rule's default answer.</li>
  <li><b>Can be manipulated.</b> A single fake “administrator” line in the input turned 64% of correct answers wrong,
  although it ignores crude “ignore all rules” tricks.</li>
  <li><b>Not fully consistent.</b> Asking the same thing twice changes about 4% of answers, rewording changes about 15%,
  and borderline answers (near 50%) can contradict each other.</li>
  <li><b>Knows when information is missing, but not when it's wrong.</b> Asked beforehand, it reliably flags questions
  that can't be answered from the input, but it's overconfident about multi-step reasoning.</li>
  <li><b>Written-out reasoning fixes deep logic.</b> Given the steps, it scores 100% on rules it otherwise gets
  69% right, and it follows the steps over a wrong conclusion, unless that conclusion claims to be “verified”.</li>
  <li><b>Probabilities mostly fit together.</b> Bayes-style updating is coherent, but compound statements with
  “not” or “or” are overpriced, so do that arithmetic in code.</li>
  <li><b>Safe to give its own history, not verdicts.</b> Seeing its earlier answers doesn't lock in mistakes, but one line
  saying a reviewer found an answer “incorrect” flips 69% of right answers.</li>
</ul></div>
<div class="scroll"><table class="score">
  <thead><tr><th>#</th><th>Experiment</th><th>Headline result</th><th>Verdict</th></tr></thead>
  <tbody>{scoreboard}</tbody>
</table></div>

<h2 id="background">Background: what Jev is and how we tested it</h2>
<p>Most AI models write text. Jev doesn't. You give it a description of a situation and a list of questions, and it
returns numbers: the probability that a statement is true, which option it picks from a list, or a point on a scale.
It is designed to make fast, cheap decisions inside software, such as routing a request, checking a claim against a
policy, or approving a transaction.</p>
<p>To test it fairly we needed questions whose correct answers we knew exactly. So a program generated thousands of
made-up policies (expense reimbursement, building access, insurance claims and library loans), each with rules,
exceptions and a set of cases. Because the program built the rules, it can work out every correct answer, and we can
change one thing at a time (the wording, the depth of the rules, a missing fact) to see what affects Jev.</p>

<h2 id="example">A worked example</h2>
{example}

<h2 id="glossary">Glossary</h2>
<dl class="gloss">{glossary}</dl>

<h2 id="experiments">The experiments</h2>
<p>Each experiment follows the same layout: <b>what it asks</b>, <b>how we tested</b>, <b>what we found</b> and
<b>what it means</b>. The full numeric tables are folded at the bottom of each section.</p>
{sections}

<h2 id="recommendations">Recommendations for building with Jev</h2>
<ol class="recs">{recs}</ol>

<h2 id="limitations">Limitations</h2>
<ul class="limits">{limits}</ul>

<h2 id="cost">Cost and data</h2>
<p>Every request and response is saved, so any number here can be traced back to the raw data. In the project folder:
<code>logs/</code> holds every call, <code>results/</code> the per-experiment tables, <code>data/</code> the generated
datasets, <code>RUN_LOG.md</code> the timestamped history, and <code>experiments/</code> one script per test (re-running
one resumes where it left off without paying again).</p>
{cost}
</div>
<div id="tip" hidden></div>
<script>
(function () {{
  var tip = document.getElementById('tip');
  document.querySelectorAll('[data-tip]').forEach(function (el) {{
    el.addEventListener('mousemove', function (e) {{
      tip.textContent = el.getAttribute('data-tip'); tip.hidden = false;
      var x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
    }});
    el.addEventListener('mouseleave', function () {{ tip.hidden = true; }});
  }});
}})();
</script>
"""

if __name__ == "__main__":
    main()
