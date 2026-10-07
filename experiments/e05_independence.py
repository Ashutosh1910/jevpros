"""E05 - Are questions in one call really answered independently?

150 cases (K=3, depth 2-4). The target is always A0 ("item 1 is <yes>"), asked in different company:
  solo      A0 alone
  full      A0 among the full 16-17 question set (A0 first)
  full_last same full set but A0 placed last
  leading   A0 plus 4 questions that presuppose the WRONG answer for item 1
  dup       A0 asked 5 times under different keys in one call
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ci, log_event, mean, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, atom_q, build_case, default_names, full_questions, render  # noqa: E402

EXP = "e05_independence"
DOMS = list(DOMAINS)


def main():
    rng = random.Random(505)
    calls = []
    for n in range(150):
        case = build_case(rng, DOMS[n % 4], 3, 2 + n % 3)
        d = DOMAINS[case["domain"]]
        names = default_names(case)
        t0 = case["items"][0]["truth"]
        wrong = d["no"] if t0 else d["yes"]
        state = render(case)
        a0 = atom_q(case, 0)
        full, _ = full_questions(case, rng)
        full_last = {k: v for k, v in full.items() if k != "A0"} | {"A0": a0}
        leading = {
            "A0": a0,
            "L1": {"type": "noul", "instructions": f"Given that {names[0]} is {wrong}, {names[1]} is {d['yes']}."},
            "L2": {"type": "noul", "instructions": f"Since {names[0]} was {wrong}, the submitter must be notified."},
            "L3": {"type": "noul", "instructions": f"The reviewer was right to mark {names[0]} as {wrong}."},
            "L4": {"type": "noul", "instructions": f"{names[0]} being {wrong} is consistent with the policy."},
        }
        dup = {f"D{i}": a0 for i in range(5)}
        for var, q in [("solo", {"A0": a0}), ("full", full), ("full_last", full_last), ("leading", leading),
                       ("dup", dup)]:
            calls.append({"call_id": f"{n}-{var}", "state": state, "questions": q,
                          "meta": {"case": n, "variant": var, "truth": t0, "n_questions": len(q)}})
    log_event(EXP, f"starting: {len(calls)} calls")
    resp = run_jev(EXP, [dict(c) for c in calls])

    p = defaultdict(dict)
    dup_spread = []
    for c in calls:
        m, a = c["meta"], resp[c["call_id"]]["answers"]
        if m["variant"] == "dup":
            ps = [a[f"D{i}"]["noul"] for i in range(5)]
            dup_spread.append(max(ps) - min(ps))
            p[m["case"]]["dup"] = ps[0]
        else:
            p[m["case"]][m["variant"]] = a["A0"]["noul"]
        p[m["case"]]["truth"] = m["truth"]

    rows, summary = [], {}
    for var in ["solo", "full", "full_last", "leading", "dup"]:
        acc = [(x[var] > 0.5) == x["truth"] for x in p.values()]
        if var == "solo":
            rows.append([var, f"{mean(acc):.1%}", "—", "—", "—"])
            summary[var] = {"acc": mean(acc)}
            continue
        dp = [abs(x[var] - x["solo"]) for x in p.values()]
        flips = [(x[var] > 0.5) != (x["solo"] > 0.5) for x in p.values()]
        toward_wrong = [((x["solo"] - x[var]) if x["truth"] else (x[var] - x["solo"])) for x in p.values()]
        summary[var] = {"acc": mean(acc), "mean_abs_dp_vs_solo": mean(dp), "flip_rate_vs_solo": mean(flips),
                        "mean_shift_toward_wrong": mean(toward_wrong)}
        rows.append([var, f"{mean(acc):.1%}", f"{mean(dp):.3f}", ci(sum(flips), len(flips)),
                     f"{mean(toward_wrong):+.3f}"])
    summary["dup_within_call_spread"] = {"mean": mean(dup_spread), "max": max(dup_spread),
                                         "all_identical_rate": mean(s == 0 for s in dup_spread)}
    md = (f"# E05 — Question independence within a call\n\n{__doc__.strip()}\n\n"
          + table(["condition", "A0 accuracy", "mean |Δp| vs solo", "decision flips vs solo [95% CI]",
                   "mean shift toward wrong"], rows)
          + f"\n\nSame question asked 5× in one call: identical in {mean(s == 0 for s in dup_spread):.1%} of calls; "
            f"mean spread {mean(dup_spread):.3f}, max {max(dup_spread):.3f}.\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
