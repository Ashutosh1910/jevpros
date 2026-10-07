"""E01 - Numbers, dates and negation.

Part A (no API calls): slice the main 600-scenario run by what the deciding conditions contained -
exact-threshold values, negated conditions, condition kind.
Part B (targeted micro-tests, one question per call):
  B1 numeric comparators (8 phrasings x 4 magnitudes x 5 value relations)
  B2 date comparisons   (2 operators x 4 formats x 5 relations)
  B3 negation stacking  (0-3 negations wrapped around a simple fact, both base truths)
"""

import datetime as dt
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ROOT, ci, log_event, mean, run_jev, save_results, table  # noqa: E402

EXP = "e01_numbers_negation"


# ---------- Part A ----------

def part_a():
    rows = {r["id"]: r for r in map(json.loads, open(ROOT / "data/dataset.jsonl"))}
    resp = {r["id"]: r["response"] for r in map(json.loads, open(ROOT / "data/responses.jsonl"))}
    groups = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # tag -> depth -> [right, n]
    for sid, row in rows.items():
        ans = resp[sid]["answers"]
        for i, it in enumerate(row["items"]):
            ok = (ans[f"A{i}"]["noul"] > 0.5) == it["truth"]
            ev = [c for c in it["chain"] if c["evaluated"]]
            decider = ev[-1]
            tags = {
                "boundary value in an evaluated condition": any(c["boundary"] for c in ev),
                "negated wording in an evaluated condition": any(c["negated"] for c in ev),
                "deciding condition is numeric": decider["kind"] == "num",
                "deciding condition is categorical": decider["kind"] == "cat",
                "deciding condition is yes/no": decider["kind"] == "bool",
                "deciding condition is numeric AND at the exact boundary": decider["kind"] == "num" and decider["boundary"],
            }
            for tag, present in tags.items():
                g = groups[(tag, present)][row["depth"]]
                g[0] += ok
                g[1] += 1
    out_rows, summary = [], {}
    for tag in dict.fromkeys(t for t, _ in groups):
        cells = []
        for present in (True, False):
            per_depth = groups[(tag, present)]
            k = sum(v[0] for v in per_depth.values())
            n = sum(v[1] for v in per_depth.values())
            # depth-standardised accuracy: mean over depths of per-depth accuracy (removes depth mix)
            std = mean(v[0] / v[1] for v in per_depth.values() if v[1])
            cells.append((k, n, std))
            summary[f"{tag} | {'yes' if present else 'no'}"] = {"right": k, "n": n, "depth_standardised": std}
        (k1, n1, s1), (k0, n0, s0) = cells
        out_rows.append([tag, ci(k1, n1), f"{s1:.1%}", ci(k0, n0), f"{s0:.1%}"])
    md = ("### Part A — slicing the main run (no new calls)\n\n"
          "Atom accuracy (A_i questions) split by what the item's *evaluated* conditions contained. "
          "'Depth-std' averages per-depth accuracies so differences in depth mix don't drive the comparison.\n\n"
          + table(["tag", "present: acc [95% CI]", "present: depth-std", "absent: acc [95% CI]", "absent: depth-std"],
                  out_rows))
    return summary, md


# ---------- Part B ----------

COMPARATORS = [  # phrase, fn(value, threshold)
    ("over", lambda v, t: v > t), ("more than", lambda v, t: v > t), ("at least", lambda v, t: v >= t),
    ("exceeding", lambda v, t: v > t), ("under", lambda v, t: v < t), ("less than", lambda v, t: v < t),
    ("at most", lambda v, t: v <= t), ("not exceeding", lambda v, t: v <= t),
]
MAGNITUDES = {  # name: (threshold sampler, unit step, formatter)
    "small int": (lambda r: r.randint(5, 30), 1, lambda x: f"{x} kg"),
    "money": (lambda r: r.randint(20, 900), 1, lambda x: f"${x}"),
    "large": (lambda r: r.randint(10_000, 99_000), 1, lambda x: f"{x:,} units"),
    "decimal": (lambda r: round(r.uniform(1, 9), 2), 0.01, lambda x: f"{x:.2f} mm"),
}
RELATIONS = {"far below": -0.4, "just below": "-1", "equal": 0, "just above": "+1", "far above": 0.4}


def b1(rng):
    calls = []
    for ci_, (phrase, fn) in enumerate(COMPARATORS):
        for mag, (samp, step, f) in MAGNITUDES.items():
            for rel, off in RELATIONS.items():
                for rep in range(3):
                    t = samp(rng)
                    if off == "-1":
                        v = t - step
                    elif off == "+1":
                        v = t + step
                    else:
                        v = t + off * t
                    v = round(v, 2) if isinstance(step, float) else int(round(v))
                    truth = fn(v, t)
                    state = (f"Rule: a shipment is flagged if its measured value is {phrase} {f(t)}.\n"
                             f"Shipment 1 measured value: {f(v)}.")
                    calls.append({"call_id": f"b1-{ci_}-{mag}-{rel}-{rep}", "state": state,
                                  "questions": {"q": {"type": "noul", "instructions": "Shipment 1 is flagged."}},
                                  "meta": {"part": "B1", "comparator": phrase, "magnitude": mag, "relation": rel,
                                           "t": t, "v": v, "truth": truth}})
    return calls


DATE_FMTS = {
    "ISO": lambda d: d.isoformat(),
    "US numeric": lambda d: d.strftime("%m/%d/%Y"),
    "long": lambda d: d.strftime("%B %-d, %Y"),
    "day-first": lambda d: d.strftime("%-d %b %Y"),
}
DATE_OPS = [("after", lambda v, t: v > t), ("on or before", lambda v, t: v <= t)]
DATE_REL = {"months before": -75, "1 day before": -1, "same day": 0, "1 day after": 1, "months after": 75}


def b2(rng):
    calls = []
    for oi, (op, fn) in enumerate(DATE_OPS):
        for fname, f in DATE_FMTS.items():
            for rel, off in DATE_REL.items():
                for rep in range(4):
                    t = dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(0, 330))
                    if rep == 3:  # cross a year boundary
                        t = dt.date(2025, 12, 31) if off > 0 else dt.date(2026, 1, 1)
                    v = t + dt.timedelta(days=off)
                    truth = fn(v, t)
                    state = (f"Rule: an application is marked late if it was submitted {op} {f(t)}.\n"
                             f"Application 1 submission date: {f(v)}.")
                    calls.append({"call_id": f"b2-{oi}-{fname}-{rel}-{rep}", "state": state,
                                  "questions": {"q": {"type": "noul", "instructions": "Application 1 is marked late."}},
                                  "meta": {"part": "B2", "op": op, "format": fname, "relation": rel,
                                           "t": str(t), "v": str(v), "truth": truth}})
    return calls


NEG_BASES = [  # (rule, fact_true, fact_false, proposition)
    ("Members get free entry; non-members do not.", "Visitor 1 is a member.", "Visitor 1 is not a member.",
     "Visitor 1 gets free entry"),
    ("Packages over 10 kg require a signature; lighter ones do not.", "Package 1 weighs 14 kg.",
     "Package 1 weighs 6 kg.", "Package 1 requires a signature"),
    ("Accounts with two-factor authentication enabled are marked secure; others are not.",
     "Account 1 has two-factor authentication enabled.", "Account 1 does not have two-factor authentication enabled.",
     "Account 1 is marked secure"),
    ("Orders paid in full are shipped; unpaid orders are held.", "Order 1 is paid in full.", "Order 1 is unpaid.",
     "Order 1 is shipped"),
    ("Students with a GPA of 3.5 or higher make the honor roll; others do not.", "Student 1 has a GPA of 3.8.",
     "Student 1 has a GPA of 3.1.", "Student 1 makes the honor roll"),
    ("Drivers with a valid license may rent a car; others may not.", "Driver 1's license is valid.",
     "Driver 1's license has expired.", "Driver 1 may rent a car"),
    ("Tickets purchased more than 48 hours before departure are refundable; others are not.",
     "Ticket 1 was purchased 5 days before departure.", "Ticket 1 was purchased 3 hours before departure.",
     "Ticket 1 is refundable"),
    ("Servers with an uptime above 99% pass the audit; others fail.", "Server 1 has an uptime of 99.7%.",
     "Server 1 has an uptime of 97.2%.", "Server 1 passes the audit"),
]


def negate(prop, level):
    """Wrap `prop` in `level` negations; returns (sentence, polarity) where polarity=True means same as prop."""
    if level == 0:
        return f"{prop}.", True
    if level == 1:
        return f"It is not the case that {prop[0].lower() + prop[1:]}.", False
    if level == 2:
        return f"It is not the case that it is false that {prop[0].lower() + prop[1:]}.", True
    return f"It is false that it is not the case that it is untrue that {prop[0].lower() + prop[1:]}.", False


def b3():
    calls = []
    for bi, (rule, ft, ff, prop) in enumerate(NEG_BASES):
        for base_truth, fact in [(True, ft), (False, ff)]:
            for level in range(4):
                sentence, pol = negate(prop, level)
                truth = base_truth if pol else not base_truth
                calls.append({"call_id": f"b3-{bi}-{int(base_truth)}-{level}", "state": f"Rule: {rule}\nFact: {fact}",
                              "questions": {"q": {"type": "noul", "instructions": sentence}},
                              "meta": {"part": "B3", "base": bi, "base_truth": base_truth, "negations": level,
                                       "truth": truth}})
    return calls


def summarise(calls, resp, key):
    g = defaultdict(lambda: [0, 0, []])
    for c in calls:
        m = c["meta"]
        p = resp[c["call_id"]]["answers"]["q"]["noul"]
        ok = (p > 0.5) == m["truth"]
        for k in ([key] if isinstance(key, str) else key):
            g[(k, m[k])][0] += ok
            g[(k, m[k])][1] += 1
            g[(k, m[k])][2].append(p if m["truth"] else 1 - p)
    return g


def main():
    rng = random.Random(101)
    summary_a, md_a = part_a()
    calls = b1(rng) + b2(rng) + b3()
    log_event(EXP, f"starting: {len(calls)} targeted calls")
    resp = run_jev(EXP, [dict(c) for c in calls])  # copies: run_jev moves state/questions into `request`

    summary = {"part_a": summary_a}
    md = [f"# E01 — Numbers, dates and negation\n\n{__doc__.strip()}\n", md_a]
    for part, keys in [("B1", ["relation", "comparator", "magnitude"]), ("B2", ["relation", "format", "op"]),
                       ("B3", ["negations", "base_truth"])]:
        pc = [c for c in calls if c["meta"]["part"] == part]
        g = summarise(pc, resp, keys)
        right = sum(1 for c in pc if (resp[c["call_id"]]["answers"]["q"]["noul"] > 0.5) == c["meta"]["truth"])
        md.append(f"\n### Part {part}  — overall accuracy {ci(right, len(pc))} (n={len(pc)})\n")
        summary[part] = {"overall": right / len(pc), "n": len(pc)}
        for k in keys:
            rows = []
            for (kk, val), (r, n, pt) in g.items():
                if kk == k:
                    rows.append([val, ci(r, n), f"{mean(pt):.2f}", n])
                    summary[part][f"{k}={val}"] = {"acc": r / n, "n": n, "mean_p_true": mean(pt)}
            md.append(f"\nBy **{k}**:\n\n" + table([k, "accuracy [95% CI]", "mean P(correct)", "n"], rows))
    # cross table: comparator x relation for B1
    pc = [c for c in calls if c["meta"]["part"] == "B1"]
    cross = defaultdict(lambda: [0, 0])
    for c in pc:
        m = c["meta"]
        cross[(m["comparator"], m["relation"])][0] += (resp[c["call_id"]]["answers"]["q"]["noul"] > 0.5) == m["truth"]
        cross[(m["comparator"], m["relation"])][1] += 1
    rels = list(RELATIONS)
    md.append("\nB1 comparator × relation accuracy:\n\n" + table(
        ["comparator"] + rels,
        [[ph] + [f"{cross[(ph, r)][0]}/{cross[(ph, r)][1]}" for r in rels] for ph, _ in COMPARATORS]))
    save_results(EXP, summary, "\n".join(md) + "\n")


if __name__ == "__main__":
    main()
