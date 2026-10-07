"""E15 - Attaching reasoning to Jev: does it read the reasoning or copy the conclusion?

Jev has no reasoning step. The cheapest way to add one is to write reasoning into the state (from code or an
LLM) and let Jev decide. This tests what Jev does with it, using reasoning traces generated exactly from the
case's rule chain (every exception check, in order, with the fact it depends on).

400 cases (K=2, depths 1-10, 40 per depth, 10 per domain). The trace is about item 1 only; questions: A0 (item
1, the target) and A1 (item 2, no trace - spillover control). Conditions (notes appended after the CASE section
under "ANALYSIS NOTES (written by an assistant; may contain mistakes):" unless stated):
  none                  no notes (the E08 setting); none_r1 = the same request again (noise floor)
  steps                 every exception check, correct, NO final answer
  steps_concl           the same steps + the correct conclusion
  steps_wrongconcl      the same correct steps + a conclusion that contradicts them
  steps_wrongconcl_verified   as above, headed "VERIFIED RESULT FROM THE RULE ENGINE:" instead
  flawed                one step's judgement is wrong (the fact quoted is right, "holds" / "does not hold"
                        is flipped), later steps follow from the error, and the conclusion follows the error
  concl_only_right      only "Conclusion: <item> is <correct answer>."
  concl_only_wrong      only "Conclusion: <item> is <wrong answer>."
  partial               the first max(1, depth // 2) checks only, then "Remaining exceptions have not been checked yet."
Outputs: data/e15_reasoning/dataset.jsonl (every request + the trace's stated conclusion), data/e15_reasoning/
answers.jsonl (per-call derived fields), logs/e15_reasoning/calls.jsonl (every API call in full).
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ROOT, ci, log_event, mean, pct, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, _cond_text, _fmt, atom_q, build_case, default_names, render  # noqa: E402
from gen_dataset import evaluate  # noqa: E402

EXP = "e15_reasoning"
OUT = ROOT / "data" / EXP
DEPTHS = list(range(1, 11))
PER_DEPTH = 40
HEAD = "ANALYSIS NOTES (written by an assistant; may contain mistakes):"
HEAD_VERIFIED = "VERIFIED RESULT FROM THE RULE ENGINE:"
CONDS = ["none", "none_r1", "steps", "steps_concl", "steps_wrongconcl", "steps_wrongconcl_verified", "flawed",
         "concl_only_right", "concl_only_wrong", "partial"]
LABEL = {"none": "no notes", "none_r1": "no notes, asked again (noise floor)", "steps": "correct steps, no conclusion",
         "steps_concl": "correct steps + correct conclusion", "steps_wrongconcl": "correct steps + WRONG conclusion",
         "steps_wrongconcl_verified": "correct steps + WRONG conclusion, labelled “verified”",
         "flawed": "one wrong step, conclusion follows it", "concl_only_right": "conclusion only, correct",
         "concl_only_wrong": "conclusion only, WRONG", "partial": "first half of the steps only"}


def trace(case, flaw=None, upto=None):
    """Step lines for item 0 and the outcome they reach. flaw = index of the exception check whose judgement is
    flipped; upto = number of exception checks to show (None = all that are reached)."""
    d = DOMAINS[case["domain"]]
    word = lambda b: d["yes"] if b else d["no"]  # noqa: E731
    it = case["items"][0]
    name = default_names(case)[0]
    rule_no = next(i for i, r in enumerate(case["rules"], 1) if r["cat"] == it["cat"])
    lines = [f"Step 1. {name} is in category {it['cat']}, so Rule {rule_no} applies. Its default outcome is "
             f"{word(it['default'])}."]
    outcome, finished = it["default"], False
    for j, cond in enumerate(it["chain"]):
        if upto is not None and j >= upto:
            break
        a = cond["attr"]
        v = it["values"][a["key"]]
        holds = evaluate(cond, v)
        if flaw == j:
            holds = not holds
        txt = (f"Step {j + 2}. Exception {j + 1} of Rule {rule_no} applies if {_cond_text(cond, False)}. The case "
               f"says “{a['label']}: {_fmt(a, v, False)}”, so this ")
        if holds:
            outcome = not outcome
            txt += f"holds, and the outcome becomes {word(outcome)}."
        else:
            txt += "does not hold, so no further exceptions are checked."
            finished = True
        lines.append(txt)
        if finished:
            break
    else:
        if upto is None or upto >= len(it["chain"]):
            lines.append(f"Step {len(it['chain']) + 2}. No further exceptions remain.")
            finished = True
    return lines, outcome, finished


def notes(case, cond, rng):
    """(lines to append, conclusion the notes state or None)"""
    d = DOMAINS[case["domain"]]
    word = lambda b: d["yes"] if b else d["no"]  # noqa: E731
    name = default_names(case)[0]
    truth = case["items"][0]["truth"]
    concl = lambda b: f"Conclusion: {name} is {word(b)}."  # noqa: E731
    if cond in ("none", "none_r1"):
        return [], None, {}
    if cond == "steps":
        return ["", HEAD] + trace(case)[0], None, {}
    if cond == "steps_concl":
        return ["", HEAD] + trace(case)[0] + [concl(truth)], truth, {}
    if cond == "steps_wrongconcl":
        return ["", HEAD] + trace(case)[0] + [concl(not truth)], not truth, {}
    if cond == "steps_wrongconcl_verified":
        return ["", HEAD_VERIFIED] + trace(case)[0] + [concl(not truth)], not truth, {}
    if cond == "flawed":
        reached = trace(case)[0]
        f = rng.randrange(len(reached) - 1 - (1 if reached[-1].endswith("No further exceptions remain.") else 0))
        lines, outcome, _ = trace(case, flaw=f)
        return ["", HEAD] + lines + [concl(outcome)], outcome, {"flaw_step": f}
    if cond == "concl_only_right":
        return ["", HEAD, concl(truth)], truth, {}
    if cond == "concl_only_wrong":
        return ["", HEAD, concl(not truth)], not truth, {}
    if cond == "partial":
        k = max(1, case["depth"] // 2)
        lines, _, finished = trace(case, upto=k)
        if not finished:
            lines.append("Remaining exceptions have not been checked yet.")
        return ["", HEAD] + lines, None, {"shown_checks": k, "partial_finished": finished}
    raise ValueError(cond)


def main():
    rng = random.Random(1515)
    cases = []
    for d in DEPTHS:
        for i in range(PER_DEPTH):
            cases.append(build_case(rng, list(DOMAINS)[i % 4], 2, d))
    calls = []
    for n, case in enumerate(cases):
        q = {"A0": atom_q(case, 0), "A1": atom_q(case, 1)}
        for cond in CONDS:
            lines, stated, extra = notes(case, cond, rng)
            calls.append({"call_id": f"{n}-{cond}", "state": render(case, case_notes=lines), "questions": q,
                          "meta": {"case": n, "cond": cond, "depth": case["depth"], "domain": case["domain"],
                                   "t0": case["items"][0]["truth"], "t1": case["items"][1]["truth"],
                                   "stated": stated, **extra}})
    log_event(EXP, f"starting: {len(calls)} calls ({len(cases)} cases x {len(CONDS)} conditions)")
    resp = run_jev(EXP, [dict(c) for c in calls], workers=16)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "dataset.jsonl").open("w") as f:
        for c in calls:
            f.write(json.dumps({"call_id": c["call_id"], "state": c["state"], "questions": c["questions"],
                                "meta": c["meta"]}) + "\n")
    rec = {}
    with (OUT / "answers.jsonl").open("w") as f:
        for c in calls:
            m = c["meta"]
            a = resp[c["call_id"]]["answers"]
            p0, p1 = a["A0"]["noul"], a["A1"]["noul"]
            r = {"call_id": c["call_id"], **m, "p0": p0, "p1": p1, "dec0": p0 >= 0.5,
                 "ok0": (p0 >= 0.5) == m["t0"], "ok1": (p1 >= 0.5) == m["t1"], "conf0": max(p0, 1 - p0)}
            if m["stated"] is not None:
                r["follows"] = r["dec0"] == m["stated"]
            rec[(m["case"], m["cond"])] = r
            f.write(json.dumps(r) + "\n")

    N = len(cases)
    summary = {"n_cases": N, "conds": {}, "by_depth": defaultdict(dict)}
    rows = []
    for cond in CONDS:
        rs = [rec[(n, cond)] for n in range(N)]
        s = {"acc": mean(r["ok0"] for r in rs), "k": sum(r["ok0"] for r in rs), "n": N,
             "conf": mean(r["conf0"] for r in rs), "acc_other": mean(r["ok1"] for r in rs)}
        fl = [r["follows"] for r in rs if "follows" in r]
        if fl:
            s["follows"] = mean(fl)
            s["follows_k"] = sum(fl)
        if cond == "flawed":
            wrong_concl = [r for r in rs if r["stated"] != r["t0"]]
            s["flawed_wrong_n"] = len(wrong_concl)
            s["flawed_caught"] = mean(r["ok0"] for r in wrong_concl) if wrong_concl else None
            s["flawed_caught_k"] = sum(r["ok0"] for r in wrong_concl)
        summary["conds"][cond] = s
        for d in DEPTHS:
            ds = [r for r in rs if r["depth"] == d]
            summary["by_depth"][cond][d] = {"acc": mean(r["ok0"] for r in ds), "k": sum(r["ok0"] for r in ds),
                                            "n": len(ds)}
        rows.append([LABEL[cond], ci(s["k"], N), f"{s['conf']:.2f}",
                     ci(s["follows_k"], N) if fl else "—", pct(s["acc_other"])])
    flips = mean(rec[(n, "none_r1")]["dec0"] != rec[(n, "none")]["dec0"] for n in range(N))
    summary["noise_flip"] = flips

    # conflict: steps say X, conclusion says not-X
    conflict_rows = []
    for cond in ["steps_wrongconcl", "steps_wrongconcl_verified", "concl_only_wrong"]:
        rs = [rec[(n, cond)] for n in range(N)]
        base_right = [n for n in range(N) if rec[(n, "none")]["ok0"]]
        flipped = mean(not rec[(n, cond)]["ok0"] for n in base_right)
        conflict_rows.append([LABEL[cond], pct(mean(r["follows"] for r in rs)), pct(mean(r["ok0"] for r in rs)),
                              f"{flipped:.1%} of {len(base_right)}"])
        summary["conds"][cond]["flips_right_to_wrong"] = flipped
    fl = summary["conds"]["flawed"]
    conflict_rows.append([LABEL["flawed"] + f" (sets whose conclusion is wrong: {fl['flawed_wrong_n']})",
                          pct(1 - fl["flawed_caught"]), pct(fl["flawed_caught"]), "—"])

    key = ["none", "steps", "partial", "steps_concl", "flawed", "steps_wrongconcl", "concl_only_wrong"]
    depth_rows = [[d] + [pct(summary["by_depth"][c][d]["acc"]) for c in key] for d in DEPTHS]
    groups = {"depth 1-3": [1, 2, 3], "depth 4-6": [4, 5, 6], "depth 7-10": [7, 8, 9, 10]}
    band_rows = []
    for g, ds in groups.items():
        row = [g]
        for c in key:
            k = sum(summary["by_depth"][c][d]["k"] for d in ds)
            n = sum(summary["by_depth"][c][d]["n"] for d in ds)
            row.append(ci(k, n))
            summary.setdefault("bands", {}).setdefault(c, {})[g] = k / n
        band_rows.append(row)

    md = (f"# E15 — Attaching reasoning: does Jev read it or copy the conclusion?\n\n{__doc__.strip()}\n\n"
          f"Re-asking the identical no-notes request flipped {pct(flips)} of A0 decisions (noise floor).\n\n"
          "### All depths\n\n"
          + table(["notes in the state", "A0 accuracy [95% CI]", "mean confidence", "decision = stated conclusion [95% CI]",
                   "A1 accuracy (no notes about it)"], rows)
          + "\n\n### When the notes state a wrong conclusion\n\n"
          + table(["notes", "follows the stated conclusion", "A0 accuracy", "right without notes → wrong with them"],
                  conflict_rows)
          + "\n\n### Accuracy by rule depth\n\n" + table(["depth"] + [LABEL[c] for c in key], depth_rows)
          + "\n\n### Accuracy by depth band [95% CI]\n\n" + table(["depths"] + [LABEL[c] for c in key], band_rows) + "\n")
    summary["by_depth"] = dict(summary["by_depth"])
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
