"""E07 - Irrelevant context: does accuracy hold as the relevant rules get buried?

30 base cases (K=2, depth 2, no decoy). Filler is inserted among the rules:
  decoy_rules  - many rules in the same format for categories not in the case (hard distractors)
  boilerplate  - generic policy prose (easy distractors)
Sizes ~1k, 4k, 12k, 24k tokens (estimated as chars/4); filler placed at start / middle / end of the
rule list (i.e. relevant rules at the end / split / start). Questions: A0, A1, J.
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import log_event, mean, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, atom_q, build_case, joint_q, joint_truth, render  # noqa: E402
from gen_dataset import FOLLOW, cond_text, make_cond  # noqa: E402

EXP = "e07_context"
DOMS = list(DOMAINS)
SIZES = [1000, 4000, 12000, 24000]
POSITIONS = ["start", "middle", "end"]
ADJ = ["imported", "refurbished", "bulk", "seasonal", "custom", "leased", "donated", "archived", "regional",
       "temporary", "shared", "outsourced"]
NOUN = ["furniture", "printing", "signage", "catering", "postage", "courier services", "licenses", "uniforms",
        "parking", "storage", "translation", "consulting", "maintenance", "subscriptions", "vehicles", "hardware"]
DEPTS = ["Finance", "Legal", "Research", "Operations", "Sales", "Security", "Facilities", "Human Resources"]
VERBS = ["file", "review", "archive", "countersign", "reconcile", "report", "audit", "escalate"]
OBJS = ["all supporting documents", "the quarterly summary", "vendor contracts", "incident reports",
        "access logs", "inventory records", "budget variances", "training attendance sheets"]
EVENTS = ["the end of each quarter", "a system upgrade", "an external audit", "the annual review",
          "a change of supplier", "any reorganisation", "a data migration", "the fiscal year close"]


def decoy_rules(rng, domain, target_chars):
    d = DOMAINS[domain]
    out, n = [], 1
    word = lambda b: d["yes"] if b else d["no"]  # noqa: E731
    while sum(len(x) for x in out) < target_chars:
        cat = f"{rng.choice(ADJ)} {rng.choice(NOUN)} (region {rng.randint(1, 40)})"
        default = rng.random() < 0.5
        parts, dec = [f"Rule D{n} ({cat}): {cat} items are {word(default)} by default."], default
        for j, a in enumerate(rng.sample(d["attrs"], rng.randint(1, 3))):
            dec = not dec
            tmpl = "Exception: if {c}, it is {v} instead." if j == 0 else rng.choice(FOLLOW)
            parts.append(tmpl.format(c=cond_text(make_cond(rng, a)), v=word(dec)))
        out.append(" ".join(parts))
        n += 1
    return "\n".join(out)


def boilerplate(rng, target_chars):
    out, n = [], 1
    while sum(len(x) for x in out) < target_chars:
        out.append(f"Section {n // 5 + 1}.{n % 5 + 1}: {rng.choice(DEPTS)} staff must {rng.choice(VERBS)} "
                   f"{rng.choice(OBJS)} within {rng.randint(2, 30)} business days of {rng.choice(EVENTS)}, and "
                   f"retain copies for at least {rng.randint(1, 10)} years unless {rng.choice(DEPTS)} approves otherwise.")
        n += 1
    return "\n".join(out)


def main():
    rng = random.Random(707)
    calls = []
    for n in range(30):
        case = build_case(rng, DOMS[n % 4], 2, 2, decoy=False)
        q = {"A0": atom_q(case, 0), "A1": atom_q(case, 1), "J": joint_q(case)}
        meta = {"case": n, "t0": case["items"][0]["truth"], "t1": case["items"][1]["truth"], "tj": joint_truth(case)}
        calls.append({"call_id": f"{n}-none", "state": render(case), "questions": q,
                      "meta": dict(meta, filler="none", size=0, position="-")})
        for ftype in ["decoy_rules", "boilerplate"]:
            for size in SIZES:
                text = decoy_rules(rng, case["domain"], size * 4) if ftype == "decoy_rules" else boilerplate(rng, size * 4)
                for pos in POSITIONS:
                    calls.append({"call_id": f"{n}-{ftype}-{size}-{pos}", "questions": q,
                                  "state": render(case, filler=text, filler_position=pos),
                                  "meta": dict(meta, filler=ftype, size=size, position=pos)})
    log_event(EXP, f"starting: {len(calls)} calls")
    resp = run_jev(EXP, [dict(c) for c in calls], workers=6)

    g = defaultdict(lambda: defaultdict(list))
    for c in calls:
        m, r = c["meta"], resp[c["call_id"]]
        a = r["answers"]
        keys = [(m["filler"], m["size"], "all"), (m["filler"], m["size"], m["position"])]
        for k in keys:
            s = g[k]
            s["atom"] += [(a["A0"]["noul"] > 0.5) == m["t0"], (a["A1"]["noul"] > 0.5) == m["t1"]]
            s["joint"].append(a["J"]["choice"] == m["tj"])
            s["conf"] += [max(a["A0"]["noul"], 1 - a["A0"]["noul"]), max(a["A1"]["noul"], 1 - a["A1"]["noul"])]
            s["tok"].append(r["usage"]["input_tokens"])
            s["lat"].append(r["latency_ms"])
    rows, summary = [], {}
    base = g[("none", 0, "all")]
    rows.append(["none", 0, "-", f"{mean(base['tok']):.0f}", f"{mean(base['atom']):.1%}", f"{mean(base['joint']):.1%}",
                 f"{mean(base['conf']):.2f}", f"{mean(base['lat']):.0f}"])
    summary["none"] = {k: mean(v) for k, v in base.items()}
    pos_rows = []
    for ftype in ["decoy_rules", "boilerplate"]:
        for size in SIZES:
            s = g[(ftype, size, "all")]
            summary[f"{ftype}|{size}"] = {k: mean(v) for k, v in s.items()}
            rows.append([ftype, size, "all", f"{mean(s['tok']):.0f}", f"{mean(s['atom']):.1%}", f"{mean(s['joint']):.1%}",
                         f"{mean(s['conf']):.2f}", f"{mean(s['lat']):.0f}"])
            pos_rows.append([ftype, size] + [f"{mean(g[(ftype, size, p)]['atom']):.0%}" for p in POSITIONS])
    md = (f"# E07 — Irrelevant context\n\n{__doc__.strip()}\n\n"
          + table(["filler", "target tokens", "position", "actual input tokens", "atom acc", "joint acc",
                   "mean atom confidence", "latency ms"], rows)
          + "\n\nAtom accuracy by where the filler was inserted (start = relevant rules come last):\n\n"
          + table(["filler", "size", "filler at start", "filler in middle", "filler at end"], pos_rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
