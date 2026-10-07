"""E08 - Deeper nesting (up to 10 exceptions per rule).

40 cases per depth (10 per domain), K=2, depths 1,3,5,6,7,8,9,10, full 13-question set.
Baselines: "always answer the default" and chance (50%).
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analyze import hard_checks, jev_view, soft_checks  # noqa: E402
from bench.common import ci, log_event, mean, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, build_case, full_questions, render  # noqa: E402

EXP = "e08_depth"
DOMS = list(DOMAINS)
DEPTHS = [1, 3, 5, 6, 7, 8, 9, 10]
TOL = 0.2


def main():
    rng = random.Random(808)
    calls, cases = [], {}
    for depth in DEPTHS:
        for n in range(40):
            case = build_case(rng, DOMS[n % 4], 2, depth)
            q, t = full_questions(case, rng)
            cid = f"d{depth}-{n}"
            cases[cid] = (case, t)
            calls.append({"call_id": cid, "state": render(case), "questions": q,
                          "meta": {"depth": depth, "stops": [it["stop"] for it in case["items"]]}})
    log_event(EXP, f"starting: {len(calls)} calls")
    resp = run_jev(EXP, [dict(c) for c in calls])

    g = defaultdict(lambda: defaultdict(list))
    for cid, (case, truth) in cases.items():
        s = g[case["depth"]]
        view = jev_view(resp[cid]["answers"])
        row = {"k": 2, "truth": truth}
        for i, it in enumerate(case["items"]):
            said = view[0][f"A{i}"] > 0.5
            s["atom"].append(said == it["truth"])
            s["always_default"].append(it["default"] == it["truth"])
            if it["truth"] != it["default"]:
                s["fell_back"].append(said == it["default"])
        s["sub"].append(max(view[1]["SUB"], key=view[1]["SUB"].get) == truth["SUB"])
        for devs in soft_checks(row, view).values():
            s["soft"] += [d > TOL for d in devs]
        hc = hard_checks(row, view)
        s["hard"] += [not v for v in hc.values()]
        s["hard_any"].append(not all(hc.values()))
        s["tok"].append(resp[cid]["usage"]["input_tokens"])
    rows, summary = [], {}
    for d in DEPTHS:
        s = g[d]
        summary[d] = {k: mean(v) for k, v in s.items()}
        rows.append([d, ci(sum(s["atom"]), len(s["atom"])), f"{mean(s['always_default']):.1%}",
                     f"{mean(s['fell_back']):.1%}", f"{mean(s['sub']):.1%}", f"{mean(s['soft']):.1%}",
                     f"{mean(s['hard']):.1%}", f"{mean(s['hard_any']):.1%}", f"{mean(s['tok']):.0f}"])
    md = (f"# E08 — Deeper nesting\n\n{__doc__.strip()}\n\n"
          + table(["depth", "atom acc [95% CI]", "'always default' baseline", "answered default when truth≠default",
                   "full-set choice acc", "soft violation rate", "hard contradiction rate",
                   "scenarios w/ ≥1 hard contradiction", "input tokens"], rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
