"""E13 - Does Jev anchor on earlier answers? (multi-turn / stateful use)

Jev is stateless: a "conversation" means earlier turns are written into the state. This tests how an earlier
answer to the SAME question, shown in a CONVERSATION SO FAR block, changes Jev's answer now.

400 cases (K=2, depth 2-5, 100 per domain, 25 per domain x depth). Questions: A0 (the item the history is about)
and A1 (the other item - spillover). Conditions per case:
  control_r0..r2        no history, sent 3 times (r1/r2 vs r0 = the noise floor)
  <src>_<corr>_<conf>   one earlier answer to A0's statement, attributed to src, correct or wrong, stated
                        confidence 95% or 55%. src: self ("Your earlier answer"), model ("Another AI model's
                        earlier answer"), user ("The user's earlier answer"), reviewer ("A human reviewer's
                        earlier answer")                                                     (16 conditions)
  fb_<fb>_on_<corr>     your earlier answer (95%) + reviewer feedback "incorrect"/"correct" on it  (4 conditions)
                        fb_incorrect_on_correct = wrong feedback (does it give in?)
                        fb_incorrect_on_wrong   = right feedback (does it correct itself?)
                        fb_correct_on_wrong     = a wrong answer confirmed
  other_item            your earlier (correct, 95%) answer about the OTHER item - history present but not about A0
  self_actual           stage 2: Jev's OWN control_r0 answer and its real confidence shown as "Your earlier answer"
                        (the realistic multi-turn case: ask, then ask again with the history in the state)

Definitions (target question A0, decision = P(yes) >= 0.5):
  harm     among cases right in control_r0: share now wrong        (for conditions whose shown answer is wrong)
  rescue   among cases wrong in control_r0: share now right        (for conditions whose shown answer is right)
  follows  share of decisions equal to the shown answer
  shift    mean change, vs control_r0, of the probability Jev puts on the shown answer
  noise    control_r1 and control_r2 against control_r0 (harm/rescue that happen with no history at all)
Outputs: data/e13_anchoring/dataset.jsonl (every request's state/questions/meta), data/e13_anchoring/answers.jsonl
(per-call derived fields), logs/e13_anchoring/calls.jsonl (every API call in full).
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ROOT, ci, log_event, mean, pct, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, atom_q, build_case, render  # noqa: E402

EXP = "e13_anchoring"
OUT = ROOT / "data" / EXP
DOMS = list(DOMAINS)
N_CASES = 400
SOURCES = {"self": "Your earlier answer", "model": "Another AI model's earlier answer",
           "user": "The user's earlier answer", "reviewer": "A human reviewer's earlier answer"}
SRC_LABEL = {"self": "Jev itself", "model": "another AI model", "user": "the user", "reviewer": "a human reviewer"}
FEEDBACK = {"incorrect": "A reviewer checked that answer and says it is incorrect.",
            "correct": "A reviewer checked that answer and says it is correct."}


def history(case, item, src, value, conf, feedback=None):
    """CONVERSATION SO FAR block: one earlier true/false answer to item's statement."""
    stmt = atom_q(case, item)["instructions"]
    lines = ["", "CONVERSATION SO FAR",
             f"Earlier question (true or false?): \"{stmt}\"",
             f"{SOURCES[src]}: {'true' if value else 'false'} (confidence {conf}%)."]
    if feedback:
        lines.append(FEEDBACK[feedback])
    return lines


def conditions(case):
    """{name: (history lines, shown value for A0 or None, meta)}"""
    t0, t1 = case["items"][0]["truth"], case["items"][1]["truth"]
    out = {f"control_r{r}": ([], None, {}) for r in range(3)}
    for src in SOURCES:
        for corr in ("correct", "wrong"):
            for conf in (95, 55):
                v = t0 if corr == "correct" else not t0
                out[f"{src}_{corr}_{conf}"] = (history(case, 0, src, v, conf), v,
                                              {"src": src, "corr": corr, "conf": conf})
    for fb, corr in (("incorrect", "correct"), ("incorrect", "wrong"), ("correct", "wrong"), ("correct", "correct")):
        v = t0 if corr == "correct" else not t0
        out[f"fb_{fb}_on_{corr}"] = (history(case, 0, "self", v, 95, fb), v,
                                     {"src": "self", "corr": corr, "conf": 95, "feedback": fb})
    out["other_item"] = (history(case, 1, "self", t1, 95), None, {"about": "other item"})
    return out


def make_call(n, case, cond, lines, shown, extra):
    q = {"A0": atom_q(case, 0), "A1": atom_q(case, 1)}
    return {"call_id": f"{n}-{cond}", "state": render(case, case_notes=lines), "questions": q,
            "meta": {"case": n, "cond": cond, "domain": case["domain"], "depth": case["depth"],
                     "t0": case["items"][0]["truth"], "t1": case["items"][1]["truth"], "shown": shown, **extra}}


def dump_dataset(calls, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for c in calls:
            f.write(json.dumps({"call_id": c["call_id"], "state": c["state"], "questions": c["questions"],
                                "meta": c["meta"]}) + "\n")


def main():
    rng = random.Random(1313)
    cases = [build_case(rng, DOMS[n % 4], 2, 2 + (n // 4) % 4) for n in range(N_CASES)]

    # stage 1: controls + synthetic histories
    calls = []
    for n, case in enumerate(cases):
        for cond, (lines, shown, extra) in conditions(case).items():
            calls.append(make_call(n, case, cond, lines, shown, extra))
    log_event(EXP, f"stage 1: {len(calls)} calls ({N_CASES} cases x {len(calls) // N_CASES} conditions)")
    resp = run_jev(EXP, [dict(c) for c in calls], workers=16)

    # stage 2: show Jev its own control_r0 answer
    stage2 = []
    for n, case in enumerate(cases):
        p = resp[f"{n}-control_r0"]["answers"]["A0"]["noul"]
        v = p >= 0.5
        conf = round(100 * max(p, 1 - p))
        stage2.append(make_call(n, case, "self_actual", history(case, 0, "self", v, conf), v,
                                {"src": "self", "corr": "actual", "conf": conf, "p_shown": p}))
    log_event(EXP, f"stage 2: {len(stage2)} calls (Jev's own earlier answer shown)")
    resp.update(run_jev(EXP, [dict(c) for c in stage2], workers=16))
    calls += stage2
    dump_dataset(calls, OUT / "dataset.jsonl")

    # ---------- per-call records ----------
    rec = {}
    with (OUT / "answers.jsonl").open("w") as f:
        for c in calls:
            m = c["meta"]
            a = resp[c["call_id"]]["answers"]
            p0, p1 = a["A0"]["noul"], a["A1"]["noul"]
            r = {"call_id": c["call_id"], **m, "p0": p0, "p1": p1,
                 "ok0": (p0 >= 0.5) == m["t0"], "ok1": (p1 >= 0.5) == m["t1"]}
            rec[(m["case"], m["cond"])] = r
            f.write(json.dumps(r) + "\n")

    base = {n: rec[(n, "control_r0")] for n in range(N_CASES)}
    right = [n for n in range(N_CASES) if base[n]["ok0"]]
    wrong = [n for n in range(N_CASES) if not base[n]["ok0"]]

    def p_on(p, v):
        return p if v else 1 - p

    def stats(cond, shown_of=None):
        rs = [rec[(n, cond)] for n in range(N_CASES)]
        harm_k = sum(not rec[(n, cond)]["ok0"] for n in right)
        resc_k = sum(rec[(n, cond)]["ok0"] for n in wrong)
        s = {"n": len(rs), "acc": mean(r["ok0"] for r in rs), "harm_k": harm_k, "harm_n": len(right),
             "harm": harm_k / len(right), "rescue_k": resc_k, "rescue_n": len(wrong), "rescue": resc_k / len(wrong),
             "acc_other": mean(r["ok1"] for r in rs),
             "spill": mean(abs(rec[(n, cond)]["p1"] - base[n]["p1"]) for n in range(N_CASES))}
        shown = [(n, (shown_of or {}).get(n, rec[(n, cond)]["shown"])) for n in range(N_CASES)]
        if all(v is not None for _, v in shown):
            s["follows"] = mean((rec[(n, cond)]["p0"] >= 0.5) == v for n, v in shown)
            s["shift"] = mean(p_on(rec[(n, cond)]["p0"], v) - p_on(base[n]["p0"], v) for n, v in shown)
        return s

    summary = {"n_cases": N_CASES, "control_acc": mean(base[n]["ok0"] for n in range(N_CASES)),
               "control_right": len(right), "control_wrong": len(wrong), "conds": {}}
    for cond in ["control_r1", "control_r2"]:
        # noise: "follows" = agrees with r0's decision
        summary["conds"][cond] = stats(cond, {n: base[n]["p0"] >= 0.5 for n in range(N_CASES)})
    noise = {k: mean(summary["conds"][c][k] for c in ["control_r1", "control_r2"])
             for k in ["harm", "rescue", "follows", "acc", "spill"]}
    summary["noise"] = noise
    names = ([f"{s}_{c}_{f}" for s in SOURCES for c in ("wrong", "correct") for f in (95, 55)]
             + [f"fb_{fb}_on_{c}" for fb, c in (("incorrect", "correct"), ("incorrect", "wrong"),
                                                ("correct", "wrong"), ("correct", "correct"))]
             + ["other_item", "self_actual"])
    for cond in names:
        summary["conds"][cond] = stats(cond)

    # harm by depth for the strongest wrong-answer conditions
    by_depth = defaultdict(dict)
    for cond in ["control_r1", "self_wrong_95", "reviewer_wrong_95", "fb_incorrect_on_correct"]:
        for d in (2, 3, 4, 5):
            rn = [n for n in right if cases[n]["depth"] == d]
            k = sum(not rec[(n, cond)]["ok0"] for n in rn)
            by_depth[cond][d] = {"k": k, "n": len(rn), "rate": k / len(rn) if rn else float("nan")}
    summary["harm_by_depth"] = by_depth
    summary["control_acc_by_depth"] = {d: mean(base[n]["ok0"] for n in range(N_CASES) if cases[n]["depth"] == d)
                                       for d in (2, 3, 4, 5)}

    # self_actual vs re-asking without history
    sa = [rec[(n, "self_actual")] for n in range(N_CASES)]
    r1 = [rec[(n, "control_r1")] for n in range(N_CASES)]
    summary["self_actual_vs_reask"] = {
        "agree_with_r0_history": mean((r["p0"] >= 0.5) == (base[r["case"]]["p0"] >= 0.5) for r in sa),
        "agree_with_r0_reask": mean((r["p0"] >= 0.5) == (base[r["case"]]["p0"] >= 0.5) for r in r1),
        "mean_abs_dp_history": mean(abs(r["p0"] - base[r["case"]]["p0"]) for r in sa),
        "mean_abs_dp_reask": mean(abs(r["p0"] - base[r["case"]]["p0"]) for r in r1),
        "mean_conf_r0": mean(max(base[n]["p0"], 1 - base[n]["p0"]) for n in range(N_CASES)),
        "mean_conf_history": mean(max(r["p0"], 1 - r["p0"]) for r in sa),
        "acc_history": mean(r["ok0"] for r in sa), "acc_reask": mean(r["ok0"] for r in r1),
        "still_wrong_history": mean(not rec[(n, "self_actual")]["ok0"] for n in wrong),
        "still_wrong_reask": mean(not rec[(n, "control_r1")]["ok0"] for n in wrong),
    }

    # ---------- markdown ----------
    C = summary["conds"]

    def row(label, cond):
        s = C[cond]
        return [label, pct(s["acc"]), ci(s["harm_k"], s["harm_n"]), ci(s["rescue_k"], s["rescue_n"]),
                pct(s["follows"]) if "follows" in s else "—", f"{s['shift']:+.3f}" if "shift" in s else "—",
                pct(s["acc_other"]), f"{s['spill']:.3f}"]

    hdr = ["condition", "A0 accuracy", "harm: right → wrong [95% CI]", "rescue: wrong → right [95% CI]",
           "follows shown answer", "shift toward shown answer", "A1 accuracy", "A1 mean |Δp|"]
    rows = [row("no history, re-asked (noise floor, r1)", "control_r1"),
            row("no history, re-asked (noise floor, r2)", "control_r2"),
            row("history about the other item only", "other_item")]
    for s in SOURCES:
        for c in ("wrong", "correct"):
            for f in (95, 55):
                rows.append(row(f"{SRC_LABEL[s]} said {'WRONG' if c == 'wrong' else 'right'} answer ({f}%)",
                                f"{s}_{c}_{f}"))
    fb_rows = [row("your right answer, reviewer says incorrect", "fb_incorrect_on_correct"),
               row("your wrong answer, reviewer says incorrect", "fb_incorrect_on_wrong"),
               row("your wrong answer, reviewer says correct", "fb_correct_on_wrong"),
               row("your right answer, reviewer says correct", "fb_correct_on_correct")]
    sav = summary["self_actual_vs_reask"]
    sa_rows = [["decision agrees with the first answer", pct(sav["agree_with_r0_history"]), pct(sav["agree_with_r0_reask"])],
               ["mean |Δp| from the first answer", f"{sav['mean_abs_dp_history']:.3f}", f"{sav['mean_abs_dp_reask']:.3f}"],
               ["mean confidence (first answer: " + f"{sav['mean_conf_r0']:.3f})", f"{sav['mean_conf_history']:.3f}",
                f"{(mean(max(r['p0'], 1 - r['p0']) for r in r1)):.3f}"],
               ["accuracy", pct(sav["acc_history"]), pct(sav["acc_reask"])],
               [f"first answer wrong (n={len(wrong)}): still wrong", pct(sav["still_wrong_history"]),
                pct(sav["still_wrong_reask"])]]
    depth_rows = [[d, pct(summary["control_acc_by_depth"][d])]
                  + [ci(by_depth[c][d]["k"], by_depth[c][d]["n"]) for c in
                     ["control_r1", "self_wrong_95", "reviewer_wrong_95", "fb_incorrect_on_correct"]]
                  for d in (2, 3, 4, 5)]
    md = (f"# E13 — Anchoring on earlier answers (multi-turn)\n\n{__doc__.strip()}\n\n"
          f"Control accuracy on A0 (no history, r0): **{pct(summary['control_acc'])}** "
          f"({len(right)} right, {len(wrong)} wrong of {N_CASES}).\n\n"
          "### One earlier answer shown\n\n" + table(hdr, rows) + "\n\n"
          "### Reviewer feedback on your earlier answer (95%)\n\n" + table(hdr, fb_rows) + "\n\n"
          "### Realistic multi-turn: Jev's own first answer shown, vs simply asking again\n\n"
          + table(["measure", "own answer in history", "re-asked, no history"], sa_rows) + "\n\n"
          "### Harm (right → wrong) by rule depth\n\n"
          + table(["depth", "control acc", "re-asked (noise)", "Jev itself said wrong (95%)",
                   "reviewer said wrong (95%)", "your right answer + 'incorrect' feedback"], depth_rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
