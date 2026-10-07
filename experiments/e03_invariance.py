"""E03 - Invariance to meaning-preserving changes, and run-to-run determinism.

150 cases (K=2, depth 1-5, 30 per depth). Questions: A0, A1 (nouls) and J (4-way joint choice).
Variants of the same logical case:
  base          original rendering
  rename        items renamed (e.g. "Expense 1" -> "Submission Q-17")
  reorder       rule order and fact order shuffled
  synonyms      title, header and every rule clause reworded
  units         "$120" -> "120 USD", "30 days" -> "30 calendar days", ...
  all           all four at once
Determinism: `base` sent 5 times (base = repeat 0).
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ci, log_event, mean, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, atom_q, build_case, joint_q, joint_truth, render  # noqa: E402

EXP = "e03_invariance"
DOMS = list(DOMAINS)
REPEATS = 5


def main():
    rng = random.Random(303)
    calls, cases = [], {}
    for n in range(150):
        case = build_case(rng, DOMS[n % 4], 2, 1 + n % 5)
        cases[n] = case
        new_names = [f"Submission {rng.choice('QKXZWV')}-{rng.randint(10, 99)}" for _ in range(2)]
        while new_names[0] == new_names[1]:
            new_names[1] = f"Submission {rng.choice('QKXZWV')}-{rng.randint(10, 99)}"
        order = list(range(len(case["rules"])))
        while len(order) > 1 and order == list(range(len(case["rules"]))):
            rng.shuffle(order)
        facts = [rng.sample(fo, len(fo)) for fo in case["fact_order"]]
        opts = {
            "base": {}, "rename": {"names": new_names}, "reorder": {"rule_order": order, "fact_orders": facts},
            "synonyms": {"synonyms": True}, "units": {"alt_units": True},
            "all": {"names": new_names, "rule_order": order, "fact_orders": facts, "synonyms": True, "alt_units": True},
        }
        for var, o in opts.items():
            names = o.get("names")
            q = {"A0": atom_q(case, 0, names), "A1": atom_q(case, 1, names), "J": joint_q(case, names)}
            reps = REPEATS if var == "base" else 1
            for r in range(reps):
                calls.append({"call_id": f"{n}-{var}-r{r}", "state": render(case, **o), "questions": q,
                              "meta": {"case": n, "variant": var, "repeat": r, "depth": case["depth"]}})
    log_event(EXP, f"starting: {len(calls)} calls")
    resp = run_jev(EXP, [dict(c) for c in calls])

    def get(n, var, r=0):
        a = resp[f"{n}-{var}-r{r}"]["answers"]
        return a["A0"]["noul"], a["A1"]["noul"], a["J"]["choice"], a["J"]["probabilities"]

    truth = {n: (c["items"][0]["truth"], c["items"][1]["truth"], joint_truth(c)) for n, c in cases.items()}
    stats = defaultdict(lambda: defaultdict(list))
    for n in cases:
        b0, b1, bj, _ = get(n, "base")
        t0, t1, tj = truth[n]
        for var in ["base", "rename", "reorder", "synonyms", "units", "all"]:
            p0, p1, j, _ = get(n, var)
            s = stats[var]
            s["acc_atom"] += [(p0 > 0.5) == t0, (p1 > 0.5) == t1]
            s["acc_joint"].append(j == tj)
            if var != "base":
                s["atom_flip"] += [(p0 > 0.5) != (b0 > 0.5), (p1 > 0.5) != (b1 > 0.5)]
                s["joint_flip"].append(j != bj)
                s["abs_dp"] += [abs(p0 - b0), abs(p1 - b1)]
                s["by_depth_flip"].append((cases[n]["depth"], (p0 > 0.5) != (b0 > 0.5) or (p1 > 0.5) != (b1 > 0.5)))

    # noise floor: an identical re-send (repeat 1) compared with base exactly like a variant
    for n in cases:
        b0, b1, bj, _ = get(n, "base")
        p0, p1, j, _ = get(n, "base", 1)
        s = stats["repeat (noise floor)"]
        s["acc_atom"] += [(p0 > 0.5) == truth[n][0], (p1 > 0.5) == truth[n][1]]
        s["acc_joint"].append(j == truth[n][2])
        s["atom_flip"] += [(p0 > 0.5) != (b0 > 0.5), (p1 > 0.5) != (b1 > 0.5)]
        s["joint_flip"].append(j != bj)
        s["abs_dp"] += [abs(p0 - b0), abs(p1 - b1)]
        s["by_depth_flip"].append((cases[n]["depth"], (p0 > 0.5) != (b0 > 0.5) or (p1 > 0.5) != (b1 > 0.5)))

    rows, summary = [], {}
    for var in ["repeat (noise floor)", "rename", "reorder", "synonyms", "units", "all"]:
        s = stats[var]
        summary[var] = {k: mean(v) for k, v in s.items() if k != "by_depth_flip"}
        rows.append([var, ci(sum(s["atom_flip"]), len(s["atom_flip"])), ci(sum(s["joint_flip"]), len(s["joint_flip"])),
                     f"{mean(s['abs_dp']):.3f}", f"{mean(s['acc_atom']):.1%}", f"{mean(s['acc_joint']):.1%}"])
    base_acc = [f"{mean(stats['base']['acc_atom']):.1%}", f"{mean(stats['base']['acc_joint']):.1%}"]
    summary["base"] = {"acc_atom": mean(stats["base"]["acc_atom"]), "acc_joint": mean(stats["base"]["acc_joint"])}

    depth_rows = []
    for d in range(1, 6):
        row = [d]
        for var in ["repeat (noise floor)", "rename", "reorder", "synonyms", "units", "all"]:
            xs = [f for dd, f in stats[var]["by_depth_flip"] if dd == d]
            row.append(f"{mean(xs):.0%}")
        depth_rows.append(row)

    # determinism
    spread, flips, identical, jflip = [], [], [], []
    for n in cases:
        reps = [get(n, "base", r) for r in range(REPEATS)]
        for idx in (0, 1):
            ps = [r[idx] for r in reps]
            spread.append(max(ps) - min(ps))
            flips.append(len({p > 0.5 for p in ps}) > 1)
        jflip.append(len({r[2] for r in reps}) > 1)
        identical.append(all(resp[f"{n}-base-r{r}"]["answers"] == resp[f"{n}-base-r0"]["answers"]
                             for r in range(REPEATS)))
    summary["determinism"] = {"mean_prob_spread": mean(spread), "max_prob_spread": max(spread),
                              "atom_decision_flip_rate": mean(flips), "joint_flip_rate": mean(jflip),
                              "fully_identical_rate": mean(identical)}
    md = (f"# E03 — Invariance and determinism\n\n{__doc__.strip()}\n\n"
          f"Base accuracy: atoms {base_acc[0]}, joint choice {base_acc[1]}.\n\n"
          "### Changes vs the base rendering (the correct answer never changes)\n\n"
          + table(["variant", "atom decision flips [95% CI]", "joint choice flips [95% CI]", "mean |Δp| atoms",
                   "atom acc", "joint acc"], rows)
          + "\n\nShare of cases where at least one atom decision flipped, by depth:\n\n"
          + table(["depth", "repeat (noise)", "rename", "reorder", "synonyms", "units", "all"], depth_rows)
          + f"\n\n### Determinism ({REPEATS} identical calls per case, n={len(cases)})\n\n"
          + table(["metric", "value"], [
              ["fully identical answers across repeats", f"{mean(identical):.1%}"],
              ["mean spread (max−min) of an atom probability", f"{mean(spread):.3f}"],
              ["max spread observed", f"{max(spread):.3f}"],
              ["atoms whose decision flipped across repeats", f"{mean(flips):.1%}"],
              ["joint choices that changed across repeats", f"{mean(jflip):.1%}"]]) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
