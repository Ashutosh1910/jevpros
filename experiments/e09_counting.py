"""E09 - Is Jev's notion of "how many" internally consistent?

200 cases (K=4, depth 1-3). Questions: atoms A0-A3, CNT score (0..4), GE_n nouls "at least n of the 4
are <yes>" (n=1..4), EQ_n nouls "exactly n of the 4 are <yes>" (n=0..4).
Coherence checks:
  monotone      P(GE_n) must not increase with n            (violation if P(GE_n+1) > P(GE_n) + 0.1)
  exact_sum     sum_n P(EQ_n) should be ~1                   (violation if |sum-1| > 0.2)
  ge_vs_eq      P(GE_n) ~ sum_{m>=n} P(EQ_m)                  (violation if > 0.2 apart)
  ge_vs_score   P(GE_n) ~ score-distribution tail             (violation if > 0.2 apart)
  hard          thresholded GE/EQ/CNT answers vs the count implied by Jev's own atoms
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ci, log_event, mean, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, atom_q, build_case, render  # noqa: E402

EXP = "e09_counting"
DOMS = list(DOMAINS)
K = 4


def main():
    rng = random.Random(909)
    calls = []
    for n in range(200):
        case = build_case(rng, DOMS[n % 4], K, 1 + n % 3)
        yes = DOMAINS[case["domain"]]["yes"]
        q = {f"A{i}": atom_q(case, i) for i in range(K)}
        q["CNT"] = {"type": "score", "instructions": f"How many of the {K} items in the case are {yes}?",
                    "criteria": [f"{m} of {K}" for m in range(K + 1)]}
        for m in range(1, K + 1):
            q[f"GE{m}"] = {"type": "noul", "instructions": f"At least {m} of the {K} items in the case are {yes}."}
        for m in range(K + 1):
            q[f"EQ{m}"] = {"type": "noul", "instructions": f"Exactly {m} of the {K} items in the case are {yes}."}
        calls.append({"call_id": str(n), "state": render(case), "questions": q,
                      "meta": {"truth_count": sum(it["truth"] for it in case["items"]),
                               "atoms": [it["truth"] for it in case["items"]], "depth": case["depth"]}})
    log_event(EXP, f"starting: {len(calls)} calls")
    resp = run_jev(EXP, [dict(c) for c in calls])

    s = defaultdict(list)
    for c in calls:
        m, a = c["meta"], resp[c["call_id"]]["answers"]
        tc = m["truth_count"]
        atoms = [a[f"A{i}"]["noul"] for i in range(K)]
        own = sum(p > 0.5 for p in atoms)
        ge = {n: a[f"GE{n}"]["noul"] for n in range(1, K + 1)}
        eq = {n: a[f"EQ{n}"]["noul"] for n in range(K + 1)}
        cnt = {int(k): float(v) for k, v in a["CNT"]["probabilities"].items()}
        cnt_pick = max(cnt, key=cnt.get)
        s["acc_atoms"] += [(p > 0.5) == t for p, t in zip(atoms, m["atoms"])]
        s["acc_cnt"].append(cnt_pick == tc)
        s["acc_ge"] += [(ge[n] > 0.5) == (tc >= n) for n in ge]
        s["acc_eq"] += [(eq[n] > 0.5) == (tc == n) for n in eq]
        s["acc_atoms_count"].append(own == tc)
        s["v_monotone"] += [ge[n + 1] > ge[n] + 0.1 for n in range(1, K)]
        s["v_exact_sum"].append(abs(sum(eq.values()) - 1) > 0.2)
        s["exact_sum"].append(sum(eq.values()))
        s["v_ge_vs_eq"] += [abs(ge[n] - sum(eq[k] for k in eq if k >= n)) > 0.2 for n in ge]
        s["v_ge_vs_score"] += [abs(ge[n] - sum(cnt.get(k, 0) for k in range(n, K + 1))) > 0.2 for n in ge]
        s["h_cnt_vs_atoms"].append(cnt_pick != own)
        s["h_ge_vs_atoms"] += [(ge[n] > 0.5) != (own >= n) for n in ge]
        s["h_eq_vs_atoms"] += [(eq[n] > 0.5) != (own == n) for n in eq]
        s["h_eq_multiple_yes"].append(sum(p > 0.5 for p in eq.values()) != 1)
    summary = {k: mean(v) for k, v in s.items()}
    acc_rows = [["atoms (per item)", f"{mean(s['acc_atoms']):.1%}"],
                ["count implied by own atoms", f"{mean(s['acc_atoms_count']):.1%}"],
                ["CNT score argmax", ci(sum(s["acc_cnt"]), len(s["acc_cnt"]))],
                ["'at least n' nouls", f"{mean(s['acc_ge']):.1%}"], ["'exactly n' nouls", f"{mean(s['acc_eq']):.1%}"]]
    coh_rows = [["P(at least n) increases with n", f"{mean(s['v_monotone']):.1%}"],
                ["Σ P(exactly n) far from 1", f"{mean(s['v_exact_sum']):.1%} (mean Σ = {mean(s['exact_sum']):.2f})"],
                ["P(at least n) vs Σ P(exactly m≥n)", f"{mean(s['v_ge_vs_eq']):.1%}"],
                ["P(at least n) vs score tail", f"{mean(s['v_ge_vs_score']):.1%}"],
                ["CNT pick ≠ count of own atoms (hard)", f"{mean(s['h_cnt_vs_atoms']):.1%}"],
                ["'at least n' ≠ own atoms (hard)", f"{mean(s['h_ge_vs_atoms']):.1%}"],
                ["'exactly n' ≠ own atoms (hard)", f"{mean(s['h_eq_vs_atoms']):.1%}"],
                ["not exactly one 'exactly n' said yes", f"{mean(s['h_eq_multiple_yes']):.1%}"]]
    md = (f"# E09 — Counting consistency\n\n{__doc__.strip()}\n\n### Accuracy\n\n"
          + table(["question", "accuracy"], acc_rows) + "\n\n### Coherence (violation rates)\n\n"
          + table(["check", "violation rate"], coh_rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
