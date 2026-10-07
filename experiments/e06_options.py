"""E06 - Scaling the number of options in a choice (2 -> 255, the documented maximum).

T1 lookup  - fixed-size state (one record); "what is the record's reference code?" with N look-alike
             codes as options. Isolates option count from state size.
T2 roster  - a roster of N employees; exactly one meets 3 conditions (department, badge level above
             a threshold, training done); most others miss by one condition. Options = N employee IDs.
             State grows with N (realistic "pick from a list").
25 trials per (task, N).
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ci, log_event, mean, run_jev, save_results, table  # noqa: E402

EXP = "e06_options"
NS = [2, 4, 8, 16, 32, 64, 128, 255]
TRIALS = 25
DEPTS = ["Finance", "Legal", "Research", "Operations", "Sales", "Security", "Facilities", "HR"]
SITES = ["headquarters", "east campus", "remote office", "partner site"]


def codes(rng, n, prefix):
    out = set()
    while len(out) < n:
        out.add(f"{prefix}-{rng.randint(1000, 9999)}")
    return list(out)


def t1(rng, n, trial):
    prefix = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2))
    opts = codes(rng, n, prefix)
    true = rng.choice(opts)
    state = (f"Record 1\nowner: account team {rng.randint(1, 40)}\nstatus: active\ncreated: 2026-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}\n"
             f"reference code: {true}\nregion: {rng.choice(SITES)}\npriority: {rng.choice(['low', 'medium', 'high'])}")
    rng.shuffle(opts)
    return {"call_id": f"t1-{n}-{trial}", "state": state,
            "questions": {"q": {"type": "choice", "instructions": "What is Record 1's reference code?",
                                "criteria": {o: o for o in opts}}},
            "meta": {"task": "T1 lookup", "n": n, "truth": true}}


def t2(rng, n, trial):
    ids = codes(rng, n, "EMP")
    dept, thr = rng.choice(DEPTS), rng.randint(3, 7)
    target = rng.choice(ids)
    lines = []
    for i in ids:
        if i == target:
            d, b, tr = dept, rng.randint(thr + 1, 9), True
        else:
            fail = {rng.choice(["dept", "badge", "training"])} if rng.random() < 0.7 else \
                set(rng.sample(["dept", "badge", "training"], rng.randint(2, 3)))
            d = rng.choice([x for x in DEPTS if x != dept]) if "dept" in fail else dept
            b = rng.randint(1, thr) if "badge" in fail else rng.randint(thr + 1, 9)
            tr = "training" not in fail
        lines.append(f"{i}: department {d}; badge level {b}; safety training {'completed' if tr else 'not completed'}; "
                     f"site {rng.choice(SITES)}")
    state = "EMPLOYEE ROSTER\n" + "\n".join(lines)
    return {"call_id": f"t2-{n}-{trial}", "state": state,
            "questions": {"q": {"type": "choice", "instructions":
                                f"Which employee meets ALL of these conditions: department is {dept}, badge level is "
                                f"above {thr}, and safety training is completed?",
                                "criteria": {i: i for i in ids}}},
            "meta": {"task": "T2 roster", "n": n, "truth": target}}


def main():
    rng = random.Random(606)
    calls = [f(rng, n, t) for f in (t1, t2) for n in NS for t in range(TRIALS)]
    log_event(EXP, f"starting: {len(calls)} calls")
    resp = run_jev(EXP, [dict(c) for c in calls])

    g = defaultdict(lambda: defaultdict(list))
    for c in calls:
        m = c["meta"]
        r = resp[c["call_id"]]
        a = r["answers"]["q"]
        s = g[(m["task"], m["n"])]
        s["ok"].append(a["choice"] == m["truth"])
        s["conf"].append(a["confidence"])
        s["p_true"].append(float(a["probabilities"].get(m["truth"], 0)))
        s["lat"].append(r["latency_ms"])
        s["tok"].append(r["usage"]["input_tokens"])
    rows, summary = [], {}
    for task in ["T1 lookup", "T2 roster"]:
        for n in NS:
            s = g[(task, n)]
            summary[f"{task}|{n}"] = {k: mean(v) for k, v in s.items()}
            rows.append([task, n, ci(sum(s["ok"]), len(s["ok"])), f"{1 / n:.1%}", f"{mean(s['p_true']):.2f}",
                         f"{mean(s['conf']):.2f}", f"{mean(s['tok']):.0f}", f"{mean(s['lat']):.0f}"])
    md = (f"# E06 — Number of options\n\n{__doc__.strip()}\n\n"
          + table(["task", "N options", "accuracy [95% CI]", "chance", "mean P(true option)", "mean confidence",
                   "input tokens", "latency ms"], rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
