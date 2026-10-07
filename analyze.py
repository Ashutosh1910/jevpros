"""Score Jev's answers for accuracy and logical coherence.

Two kinds of coherence:
  soft  - probability-logic checks on the raw probabilities (violation if deviation > TOL)
  hard  - after thresholding every noul at 0.5 / taking every argmax, do the compound answers
          follow from Jev's OWN atomic answers? (independent of whether the atoms are right)

A random baseline (uniform nouls, Dirichlet(1) choices) is scored with the same checks so the
violation rates have a chance-level reference.
"""

import argparse
import json
import random
import statistics
from collections import defaultdict

TOL = 0.2


# ---------- helpers ----------

def argmax(d):
    return max(d, key=d.get)


def tvd(p, q):
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in set(p) | set(q))


def jev_view(ans):
    """Normalise a Jev answers dict into (nouls, choice_probs, score_probs)."""
    nouls = {k: v["noul"] for k, v in ans.items() if v["type"] == "noul"}
    choices = {k: {o: float(p) for o, p in v["probabilities"].items()} for k, v in ans.items()
               if v["type"] == "choice"}
    scores = {k: {int(o): float(p) for o, p in v["probabilities"].items()} for k, v in ans.items()
              if v["type"] == "score"}
    return nouls, choices, scores


def random_view(row, rng):
    nouls, choices, scores = {}, {}, {}
    for k, q in row["questions"].items():
        if q["type"] == "noul":
            nouls[k] = rng.random()
        else:
            opts = list(q["criteria"]) if q["type"] == "choice" else list(range(len(q["criteria"])))
            w = [rng.expovariate(1) for _ in opts]
            dist = {o: x / sum(w) for o, x in zip(opts, w)}
            (choices if q["type"] == "choice" else scores)[k] = dist
    return nouls, choices, scores


# ---------- checks ----------

def soft_checks(row, view):
    """Return {check_name: deviation}; deviation 0 means perfectly coherent."""
    p, c, s = view
    k = row["k"]
    out = {}
    for i in range(k):
        out[f"complement"] = out.get("complement", [])
        out["complement"].append(abs(p[f"A{i}"] + p[f"N{i}"] - 1))
    out["paraphrase"] = [abs(p["A0"] - p["P0"])]
    a0, a1 = p["A0"], p["A1"]
    out["and_bounds"] = [max(0, p["AND"] - min(a0, a1), max(0, a0 + a1 - 1) - p["AND"])]
    out["or_bounds"] = [max(0, max(a0, a1) - p["OR"], p["OR"] - min(1, a0 + a1))]
    out["incl_excl"] = [abs(p["OR"] - (a0 + a1 - p["AND"]))]
    if k >= 3:
        lo, hi = max(p["AND"], p["A2"]), min(1, p["AND"] + p["A2"])
    else:
        lo, hi = max(0, a0 + p["N1"] - 1), min(a0, p["N1"])
    out["nested_bounds"] = [max(0, lo - p["NEST"], p["NEST"] - hi)]
    J, JR, SUB = c["J"], c["JR"], c["SUB"]
    out["joint_vs_atoms"] = [abs(J["both"] + J["only_first"] - a0), abs(J["both"] + J["only_second"] - a1)]
    out["joint_vs_and_or"] = [abs(J["both"] - p["AND"]), abs(1 - J["neither"] - p["OR"])]
    out["subset_vs_atoms"] = [abs(sum(v for key, v in SUB.items() if key[i] == "Y") - p[f"A{i}"])
                              for i in range(k)]
    sub2 = defaultdict(float)
    names = {"YY": "both", "YN": "only_first", "NY": "only_second", "NN": "neither"}
    for key, v in SUB.items():
        sub2[names[key[:2]]] += v
    out["subset_vs_joint"] = [tvd(sub2, J)]
    out["option_order"] = [tvd(J, JR)]
    exp_cnt = sum(n * v for n, v in s["CNT"].items())
    out["count_vs_atoms"] = [abs(exp_cnt - sum(p[f"A{i}"] for i in range(k))) / k]
    return out


def hard_checks(row, view):
    """Return {check: consistent?} comparing thresholded compound answers with Jev's own atoms."""
    p, c, s = view
    k = row["k"]
    b = [p[f"A{i}"] > 0.5 for i in range(k)]
    yes = lambda key: p[key] > 0.5  # noqa: E731
    jkey = {(1, 1): "both", (1, 0): "only_first", (0, 1): "only_second", (0, 0): "neither"}[(b[0], b[1])]
    nest = (b[0] and b[1]) or b[2] if k >= 3 else b[0] and not b[1]
    sub = argmax(c["SUB"])
    out = {
        "negation": all(yes(f"N{i}") == (not b[i]) for i in range(k)),
        "paraphrase": yes("P0") == b[0],
        "and": yes("AND") == (b[0] and b[1]),
        "or": yes("OR") == (b[0] or b[1]),
        "nested": yes("NEST") == nest,
        "joint_choice": argmax(c["J"]) == jkey,
        "subset_choice": sub == "".join("Y" if x else "N" for x in b),
        "count_score": argmax(s["CNT"]) == sum(b),
        "option_order": argmax(c["J"]) == argmax(c["JR"]),
        "joint_vs_subset": {"YY": "both", "YN": "only_first", "NY": "only_second", "NN": "neither"}[sub[:2]]
        == argmax(c["J"]),
    }
    return out


def correct(row, view, key):
    p, c, s = view
    t = row["truth"][key]
    if key in p:
        return (p[key] > 0.5) == t
    if key in c:
        return argmax(c[key]) == t
    return argmax(s[key]) == t


# ---------- report ----------

def pct(x):
    return f"{100 * x:5.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/dataset.jsonl")
    ap.add_argument("--responses", default="data/responses.jsonl")
    ap.add_argument("--json", default="data/report.json")
    args = ap.parse_args()

    rows = {r["id"]: r for r in map(json.loads, open(args.data))}
    resps = {r["id"]: r["response"] for r in map(json.loads, open(args.responses))}
    ids = [i for i in rows if i in resps]
    rng = random.Random(0)

    soft = {"jev": defaultdict(list), "random": defaultdict(list)}
    soft_by_depth = defaultdict(list)
    hard = {"jev": defaultdict(list), "random": defaultdict(list)}
    hard_by_depth = defaultdict(list)
    acc = defaultdict(list)
    acc_atom_depth = defaultdict(list)
    acc_atom_stop = defaultdict(list)
    acc_cf_level = defaultdict(list)
    buckets = defaultdict(lambda: defaultdict(int))  # compound q -> (correct, consistent) counts
    calib = []  # (prob, truth) for every noul
    choice_conf = []  # (confidence, correct)
    scen_hard_any = []
    lat, cost, tok = [], 0.0, 0

    for sid in ids:
        row, resp = rows[sid], resps[sid]
        view = jev_view(resp["answers"])
        rview = random_view(row, rng)
        lat.append(resp["latency_ms"])
        cost += resp.get("usage", {}).get("cost") or 0
        tok += resp.get("usage", {}).get("input_tokens") or 0

        for who, v in [("jev", view), ("random", rview)]:
            for name, devs in soft_checks(row, v).items():
                soft[who][name].extend(devs)
                if who == "jev":
                    soft_by_depth[row["depth"]].extend(devs)
            for name, ok in hard_checks(row, v).items():
                hard[who][name].append(ok)
        h = hard_checks(row, view)
        hard_by_depth[row["depth"]].extend(h.values())
        scen_hard_any.append(not all(h.values()))

        for key in row["truth"]:
            qtype = key.rstrip("0123456789")
            ok = correct(row, view, key)
            acc[qtype].append(ok)
            if qtype == "A":
                i = int(key[1:])
                acc_atom_depth[row["depth"]].append(ok)
                acc_atom_stop[row["items"][i]["stop"]].append(ok)
            if qtype == "CF":
                acc_cf_level[row["cf_level"]].append(ok)
            if key in view[0]:
                calib.append((view[0][key], row["truth"][key]))
            elif key in view[1]:
                choice_conf.append((resp["answers"][key]["confidence"], ok))

        for q, check in [("AND", "and"), ("OR", "or"), ("NEST", "nested"), ("J", "joint_choice"),
                         ("SUB", "subset_choice"), ("CNT", "count_score")]:
            buckets[q][(correct(row, view, q), h[check])] += 1

    n = len(ids)
    report = {"n_scenarios": n, "cost_usd": cost, "input_tokens": tok,
              "latency_ms": {"p50": statistics.median(lat), "p95": sorted(lat)[int(0.95 * n) - 1]}}
    print(f"\nScenarios: {n}   cost ${cost:.4f}   input tokens {tok:,}   "
          f"latency p50 {report['latency_ms']['p50']:.0f} ms, p95 {report['latency_ms']['p95']} ms\n")

    print("ACCURACY by question type")
    report["accuracy"] = {}
    for q in ["A", "N", "P", "AND", "OR", "NEST", "CF", "J", "JR", "SUB", "CNT"]:
        v = acc[q]
        report["accuracy"][q] = sum(v) / len(v)
        print(f"  {q:<5} {pct(sum(v) / len(v))}  (n={len(v)})")

    print("\nATOM ACCURACY by rule depth        and by # exceptions that applied (stop level)")
    report["atom_acc_by_depth"] = {d: sum(v) / len(v) for d, v in sorted(acc_atom_depth.items())}
    report["atom_acc_by_stop"] = {d: sum(v) / len(v) for d, v in sorted(acc_atom_stop.items())}
    ds, ss = sorted(acc_atom_depth), sorted(acc_atom_stop)
    for i in range(max(len(ds), len(ss))):
        left = f"  depth {ds[i]}: {pct(report['atom_acc_by_depth'][ds[i]])} (n={len(acc_atom_depth[ds[i]])})" \
            if i < len(ds) else " " * 34
        right = f"stop {ss[i]}: {pct(report['atom_acc_by_stop'][ss[i]])} (n={len(acc_atom_stop[ss[i]])})" \
            if i < len(ss) else ""
        print(f"{left:<36}{right}")

    print("\nCOUNTERFACTUAL accuracy by level of the changed exception")
    report["cf_acc_by_level"] = {lv: sum(v) / len(v) for lv, v in sorted(acc_cf_level.items())}
    for lv, v in sorted(acc_cf_level.items()):
        print(f"  level {lv}: {pct(sum(v) / len(v))} (n={len(v)})")

    print(f"\nSOFT COHERENCE (probability logic)   violation = deviation > {TOL}")
    print(f"  {'check':<17} {'jev viol':>9} {'jev mean dev':>13} {'random viol':>12}")
    report["soft"] = {}
    for name in soft["jev"]:
        jv, rv = soft["jev"][name], soft["random"][name]
        viol = sum(d > TOL for d in jv) / len(jv)
        rviol = sum(d > TOL for d in rv) / len(rv)
        report["soft"][name] = {"violation_rate": viol, "mean_dev": statistics.mean(jv), "random_violation_rate": rviol}
        print(f"  {name:<17} {pct(viol):>9} {statistics.mean(jv):>13.3f} {pct(rviol):>12}")

    print("\nHARD COHERENCE (thresholded answers vs Jev's own atoms)")
    print(f"  {'check':<17} {'jev contra':>11} {'random contra':>14}")
    report["hard"] = {}
    for name in hard["jev"]:
        jc = 1 - sum(hard["jev"][name]) / n
        rc = 1 - sum(hard["random"][name]) / n
        report["hard"][name] = {"contradiction_rate": jc, "random_contradiction_rate": rc}
        print(f"  {name:<17} {pct(jc):>11} {pct(rc):>14}")
    any_rate = sum(scen_hard_any) / n
    report["scenarios_with_any_hard_contradiction"] = any_rate
    print(f"  scenarios with >=1 hard contradiction: {pct(any_rate)}")

    print("\nCOHERENCE by depth     soft violation rate   hard contradiction rate")
    report["by_depth"] = {}
    for d in sorted(soft_by_depth):
        sv = sum(x > TOL for x in soft_by_depth[d]) / len(soft_by_depth[d])
        hc = 1 - sum(hard_by_depth[d]) / len(hard_by_depth[d])
        report["by_depth"][d] = {"soft_violation": sv, "hard_contradiction": hc}
        print(f"  depth {d}              {pct(sv):>8}              {pct(hc):>8}")

    print("\nERRORS vs CONSISTENCY on compound questions (does Jev follow its own beliefs?)")
    print(f"  {'q':<5} {'right+consistent':>17} {'right+inconsist':>16} {'wrong+consistent':>17} {'wrong+inconsist':>16}")
    report["buckets"] = {}
    for q, bk in buckets.items():
        tot = sum(bk.values())
        cells = [bk[(True, True)], bk[(True, False)], bk[(False, True)], bk[(False, False)]]
        report["buckets"][q] = dict(zip(["right_consistent", "right_inconsistent", "wrong_consistent",
                                         "wrong_inconsistent"], [x / tot for x in cells]))
        print(f"  {q:<5} " + " ".join(f"{pct(x / tot):>16}" for x in cells))

    print("\nCALIBRATION of noul probabilities")
    brier = statistics.mean((pr - t) ** 2 for pr, t in calib)
    bins = defaultdict(list)
    for pr, t in calib:
        bins[min(int(pr * 10), 9)].append((pr, t))
    ece = sum(len(v) / len(calib) * abs(statistics.mean(x for x, _ in v) - statistics.mean(y for _, y in v))
              for v in bins.values())
    report["calibration"] = {"brier": brier, "ece": ece, "bins": {}}
    print(f"  Brier {brier:.4f}   ECE {ece:.4f}   (n={len(calib)})")
    print(f"  {'bin':<9} {'n':>6} {'mean p':>7} {'freq true':>10}")
    for b in sorted(bins):
        v = bins[b]
        mp, ft = statistics.mean(x for x, _ in v), statistics.mean(y for _, y in v)
        report["calibration"]["bins"][b] = {"n": len(v), "mean_p": mp, "freq_true": ft}
        print(f"  {b / 10:.1f}-{(b + 1) / 10:.1f}  {len(v):>6} {mp:>7.3f} {ft:>10.3f}")

    print("\nCHOICE confidence vs accuracy")
    report["choice_conf"] = {}
    for lo, hi in [(0, 0.5), (0.5, 0.8), (0.8, 0.95), (0.95, 1.01)]:
        v = [ok for cf, ok in choice_conf if lo <= cf < hi]
        if v:
            report["choice_conf"][f"{lo}-{min(hi, 1)}"] = {"n": len(v), "acc": sum(v) / len(v)}
            print(f"  conf {lo:.2f}-{min(hi, 1):.2f}: acc {pct(sum(v) / len(v))} (n={len(v)})")

    with open(args.json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
