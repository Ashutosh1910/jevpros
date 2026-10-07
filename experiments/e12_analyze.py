"""Analyse E12 (self-trust) at any thresholds. No API calls - reads the stored dataset and answers.

  python3 experiments/e12_analyze.py                               # defaults
  python3 experiments/e12_analyze.py --meta 0.7 --conf 0.9         # main thresholds for the flag categories
  python3 experiments/e12_analyze.py --meta-grid 0.5,0.8 --conf-grid 0.7,0.9

Definitions
  claims it can      p_can >= META                     (p_can = P(yes) on the M_CAN meta question)
  answers confidently answer_conf >= CONF               (noul: max(p,1-p); choice/score: returned confidence)
  correct            determinable items only; undeterminable items have no correct answer
Flag categories (every flagged item goes to results/e12_flagged.jsonl):
  claimed_can_then_unsure        claims it can, then answers with low confidence
  claimed_cant_then_confident    says it can't, then answers confidently
  claimed_can_confidently_wrong  claims it can, answers confidently, and is wrong
  claimed_can_on_undeterminable  claims it can on an item that has no determinable answer
  confident_on_undeterminable    answers confidently on an item that has no determinable answer
  meta_disagrees_with_itself     M_CAN and M_LEVEL disagree (p_can>=0.5 vs level argmax >= "probably")
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ROOT, ci, mean, save_results, table  # noqa: E402

EXP = "e12_selftrust"
D = ROOT / "data" / EXP


def auroc(scores, labels):
    """P(score of a random positive > score of a random negative), ties count half."""
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return float("nan")
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2
        rank_sum += avg_rank * sum(1 for k in range(i, j) if pairs[k][1])
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j < len(order) and v[order[j]] == v[order[i]]:
                j += 1
            for k in range(i, j):
                r[order[k]] = (i + j - 1) / 2
            i = j
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return cov / (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5


def flags(r, tm, tc):
    claim, conf = r["p_can"] >= tm, r["answer_conf"] >= tc
    out = []
    if claim and not conf:
        out.append("claimed_can_then_unsure")
    if not claim and conf:
        out.append("claimed_cant_then_confident")
    if claim and conf and r["correct"] is False:
        out.append("claimed_can_confidently_wrong")
    if claim and not r["determinable"]:
        out.append("claimed_can_on_undeterminable")
    if conf and not r["determinable"]:
        out.append("confident_on_undeterminable")
    if (r["p_can_raw"] >= 0.5) != (r["level_argmax"] >= 2):
        out.append("meta_disagrees_with_itself")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", type=float, default=0.5)
    ap.add_argument("--conf", type=float, default=0.8)
    ap.add_argument("--meta-grid", default="0.5,0.6,0.7,0.8,0.9")
    ap.add_argument("--conf-grid", default="0.6,0.7,0.8,0.9,0.95")
    ap.add_argument("--signal", choices=["level", "p_can"], default="level",
                    help="meta signal for 'claims it can': level = P(M_LEVEL is 'probably' or 'certain'); "
                         "p_can = P(yes) on M_CAN (leaks the statement's truth - see the leakage section)")
    args = ap.parse_args()
    tm, tc = args.meta, args.conf
    items = {it["id"]: it for it in map(json.loads, open(D / "dataset.jsonl"))}
    recs = [json.loads(line) for line in open(D / "answers.jsonl")]
    for r in recs:
        lp = {int(k): v for k, v in r["level_probs"].items()}
        r["p_level"] = lp.get(2, 0) + lp.get(3, 0)
        r["p_can_raw"] = r["p_can"]
        r["p_can"] = r["p_level"] if args.signal == "level" else r["p_can_raw"]
    det = [r for r in recs if r["determinable"]]
    und = [r for r in recs if not r["determinable"]]
    design = (Path(__file__).parent / "e12_selftrust.py").read_text().split('"""')[1].strip()
    defs = __doc__.split("Definitions", 1)[1].strip()
    md, summary = [f"# E12 — Does Jev trust itself correctly?\n\n{design}\n\nDefinitions:\n  {defs}\n"], {}

    # --- 1. headline signals
    acc = mean(r["correct"] for r in det)
    sig = {
        "P(can) predicts a correct answer (determinable items)": auroc([r["p_can"] for r in det], [r["correct"] for r in det]),
        "answer's own confidence predicts a correct answer": auroc([r["answer_conf"] for r in det], [r["correct"] for r in det]),
        "P(can) predicts the answer will be confident (all items)": auroc([r["p_can"] for r in recs], [r["answer_conf"] >= tc for r in recs]),
        "P(can) separates determinable from undeterminable": auroc([r["p_can"] for r in recs], [r["determinable"] for r in recs]),
        "answer confidence separates determinable from undeterminable": auroc([r["answer_conf"] for r in recs], [r["determinable"] for r in recs]),
        "M_CAN P(yes) predicts a correct answer": auroc([r["p_can_raw"] for r in det], [r["correct"] for r in det]),
        "M_LEVEL P(probably or certain) predicts a correct answer": auroc([r["p_level"] for r in det], [r["correct"] for r in det]),
        "M_CAN P(yes) separates determinable from undeterminable": auroc([r["p_can_raw"] for r in recs], [r["determinable"] for r in recs]),
        "M_LEVEL separates determinable from undeterminable": auroc([r["p_level"] for r in recs], [r["determinable"] for r in recs]),
    }
    rho = spearman([r["p_can"] for r in recs], [r["answer_conf"] for r in recs])
    summary["headline"] = {"n": len(recs), "determinable": len(det), "undeterminable": len(und), "accuracy": acc,
                           "mean_p_can_determinable": mean(r["p_can"] for r in det),
                           "mean_p_can_undeterminable": mean(r["p_can"] for r in und),
                           "spearman_p_can_vs_answer_conf": rho, "auroc": sig}
    md.append(f"### Headline\n\nBelow, **P(can)** means the active meta signal (`{args.signal}`; re-run with "
              f"`--signal p_can` for the yes/no version). Thresholds: P(can) ≥ {tm}, answer confidence ≥ {tc}.\n\n"
              f"{len(recs)} items ({len(det)} determinable, {len(und)} undeterminable). "
              f"Accuracy on determinable items: **{acc:.1%}**. Mean P(can): {summary['headline']['mean_p_can_determinable']:.2f} "
              f"on determinable vs {summary['headline']['mean_p_can_undeterminable']:.2f} on undeterminable items. "
              f"Spearman correlation between P(can) and the later answer's confidence: **{rho:.2f}**.\n\n"
              "AUROC = probability the signal ranks a random positive above a random negative (0.5 = useless, 1 = perfect).\n\n"
              + table(["signal", "AUROC"], [[k, f"{v:.3f}"] for k, v in sig.items()]))

    # --- 1b. leakage: does the meta question answer the embedded statement instead?
    nd = [r for r in det if r["qtype"] == "noul"]
    def pear(x, y):
        mx, my = mean(x), mean(y)
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    leak = {
        "M_CAN": (mean(r["p_can_raw"] for r in nd if r["truth"]), mean(r["p_can_raw"] for r in nd if not r["truth"]),
                  pear([r["p_can_raw"] for r in nd], [r["p_yes"] for r in nd]), pear([r["p_can_raw"] for r in nd], [r["answer_conf"] for r in nd])),
        "M_LEVEL": (mean(r["p_level"] for r in nd if r["truth"]), mean(r["p_level"] for r in nd if not r["truth"]),
                    pear([r["p_level"] for r in nd], [r["p_yes"] for r in nd]), pear([r["p_level"] for r in nd], [r["answer_conf"] for r in nd])),
    }
    summary["leakage"] = {k: dict(zip(["mean_when_true", "mean_when_false", "corr_with_answer_p_yes", "corr_with_answer_conf"], v))
                          for k, v in leak.items()}
    md.append("\n### Leakage: does the meta question secretly answer the question?\n\nFor yes/no items the meta signal "
              "should depend on how answerable the statement is, not on whether it is true. Signal active in this report: "
              f"**{args.signal}**.\n\n"
              + table(["meta signal", "mean when statement true", "mean when false", "corr. with answer's P(yes)",
                       "corr. with answer confidence"], [[k, f"{a:.2f}", f"{b:.2f}", f"{c:.2f}", f"{d:.2f}"] for k, (a, b, c, d) in leak.items()]))
    un = [r for r in und if r["qtype"] == "noul"]
    yes_c, no_c = sum(r["p_yes"] >= tc for r in un), sum(r["p_yes"] <= 1 - tc for r in un)
    summary["undeterminable_noul_direction"] = {"n": len(un), "confident_yes": yes_c, "confident_no": no_c}
    md.append(f"\nOn the {len(un)} undeterminable yes/no items, Jev said a confident **yes** (P ≥ {tc}) {yes_c} times "
              f"({yes_c / len(un):.0%}) and a confident **no** (P ≤ {1 - tc:.1f}) {no_c} times ({no_c / len(un):.0%}). "
              "A confident \"no\" there often means \"not established by the information\" rather than \"false\", so "
              "confident-yes is the real overclaim.\n")

    # --- 2. per family
    fam = defaultdict(list)
    for r in recs:
        fam[r["family"]].append(r)
    rows = []
    summary["families"] = {}
    for f, rs in sorted(fam.items(), key=lambda kv: -mean(x["p_can"] for x in kv[1])):
        d = [r for r in rs if r["determinable"]]
        fl = [flags(r, tm, tc) for r in rs]
        s = {"n": len(rs), "determinable": bool(d), "accuracy": mean(r["correct"] for r in d) if d else None,
             "mean_p_can": mean(r["p_can"] for r in rs), "claim_rate": mean(r["p_can"] >= tm for r in rs),
             "mean_level": mean(r["level_score"] for r in rs), "mean_answer_conf": mean(r["answer_conf"] for r in rs),
             "confident_rate": mean(r["answer_conf"] >= tc for r in rs),
             "any_flag_rate": mean(bool(x) for x in fl), "size": rs[0]["size"]}
        summary["families"][f] = s
        rows.append([f, s["size"], len(rs), "no" if not d else f"{s['accuracy']:.1%}", f"{s['mean_p_can']:.2f}",
                     f"{s['claim_rate']:.0%}", f"{s['mean_level']:.2f}", f"{s['mean_answer_conf']:.2f}",
                     f"{s['confident_rate']:.0%}", f"{s['any_flag_rate']:.0%}"])
    md.append(f"\n### By question family (claims it can = meta signal `{args.signal}` ≥ {tm}; confident = answer confidence ≥ {tc})\n\n"
              + table(["family", "size", "n", "accuracy (determinable)", "mean P(can)", "claims it can",
                       "mean level (0–3)", "mean answer conf", "answered confidently", "any flag"], rows))

    # --- 3. flag categories
    cats = ["claimed_can_then_unsure", "claimed_cant_then_confident", "claimed_can_confidently_wrong",
            "claimed_can_on_undeterminable", "confident_on_undeterminable", "meta_disagrees_with_itself"]
    flagged = defaultdict(list)
    for r in recs:
        for c in flags(r, tm, tc):
            flagged[c].append(r)
    denom = {"claimed_can_on_undeterminable": len(und), "confident_on_undeterminable": len(und),
             "claimed_can_confidently_wrong": sum(1 for r in det if r["p_can"] >= tm and r["answer_conf"] >= tc)}
    rows = []
    summary["flags"] = {}
    for c in cats:
        n = denom.get(c, len(recs))
        top = defaultdict(int)
        for r in flagged[c]:
            top[r["family"]] += 1
        worst = ", ".join(f"{k} ({v})" for k, v in sorted(top.items(), key=lambda kv: -kv[1])[:3])
        summary["flags"][c] = {"count": len(flagged[c]), "denominator": n, "rate": len(flagged[c]) / n if n else None,
                               "by_family": dict(top)}
        rows.append([c, len(flagged[c]), ci(len(flagged[c]), n) if n else "—",
                     {"claimed_can_on_undeterminable": "undeterminable items",
                      "confident_on_undeterminable": "undeterminable items",
                      "claimed_can_confidently_wrong": "items it claimed and answered confidently"}.get(c, "all items"), worst])
    md.append(f"\n### Wrong or inconsistent self-assessments (P(can) ≥ {tm}, confidence ≥ {tc})\n\n"
              + table(["category", "count", "rate [95% CI]", "out of", "most common families"], rows))

    # --- 4. threshold grid
    mg = [float(x) for x in args.meta_grid.split(",")]
    cg = [float(x) for x in args.conf_grid.split(",")]
    grid_rows = []
    summary["grid"] = {}
    for a in mg:
        claimed = [r for r in recs if r["p_can"] >= a]
        for b in cg:
            good = [r["correct"] is True and r["answer_conf"] >= b for r in claimed]
            over = [r for r in claimed if r["correct"] is not True or r["answer_conf"] < b]
            under = [r for r in recs if r["p_can"] < a and r["correct"] is True and r["answer_conf"] >= b]
            key = f"{a}|{b}"
            summary["grid"][key] = {"claim_rate": len(claimed) / len(recs), "trust_precision": mean(good) if good else None,
                                    "overclaim_rate": len(over) / len(recs), "underclaim_rate": len(under) / len(recs)}
            grid_rows.append([a, b, f"{len(claimed) / len(recs):.1%}", f"{mean(good):.1%}" if good else "—",
                              f"{len(over) / len(recs):.1%}", f"{len(under) / len(recs):.1%}"])
    md.append("\n### Threshold grid\n\n*trust precision* = of the items where it claimed it could answer, the share it then "
              "answered correctly AND confidently (undeterminable items count as failures). *overclaim* = claimed but then "
              "wrong, unsure or undeterminable (share of all items). *underclaim* = said it couldn't but then answered "
              "correctly and confidently.\n\n"
              + table(["P(can) ≥", "confidence ≥", "claims it can", "trust precision", "overclaim", "underclaim"], grid_rows))

    # --- 5. selective answering: meta signal vs answer confidence as a filter
    def accept_curve(signal):
        ranked = sorted(recs, key=lambda r: -r[signal])
        out = {}
        for cov in [0.3, 0.5, 0.7, 0.8, 0.9, 1.0]:
            kept = ranked[: max(1, int(cov * len(ranked)))]
            out[cov] = mean(r["correct"] is True for r in kept)
        return out
    for r in recs:
        r["combined"] = r["p_can"] * r["answer_conf"]
    cm, cc, cb = accept_curve("p_can"), accept_curve("answer_conf"), accept_curve("combined")
    summary["selective"] = {"by_p_can": cm, "by_answer_conf": cc, "by_product": cb}
    md.append("\n### Selective answering\n\nKeep only the top X% of items ranked by a signal and count how many kept answers "
              "are correct (an answer to an undeterminable item counts as wrong). Compares asking Jev *beforehand* "
              "(P(can)) with looking at the answer's own confidence.\n\n"
              + table(["keep top", "ranked by P(can)", "ranked by answer confidence", "ranked by P(can) × confidence"],
                      [[f"{int(c * 100)}%", f"{cm[c]:.1%}", f"{cc[c]:.1%}", f"{cb[c]:.1%}"] for c in cm]))

    # --- 6. calibration of P(can)
    bins = defaultdict(list)
    for r in recs:
        bins[min(int(r["p_can"] * 10), 9)].append(r)
    rows = []
    summary["p_can_bins"] = {}
    for b in sorted(bins):
        rs = bins[b]
        good = mean(r["correct"] is True and r["answer_conf"] >= tc for r in rs)
        summary["p_can_bins"][b] = {"n": len(rs), "undeterminable_share": mean(not r["determinable"] for r in rs),
                                    "correct": mean(r["correct"] is True for r in rs), "correct_and_confident": good}
        rows.append([f"{b / 10:.1f}–{(b + 1) / 10:.1f}", len(rs), f"{mean(not r['determinable'] for r in rs):.0%}",
                     f"{mean(r['correct'] is True for r in rs):.0%}", f"{good:.0%}", f"{mean(r['answer_conf'] for r in rs):.2f}"])
    md.append("\n### Is P(can) calibrated?\n\nIf P(can) were a calibrated probability of answering well, the last columns would "
              "rise with it and roughly match the bin.\n\n"
              + table(["P(can) bin", "n", "undeterminable share", "then correct", f"then correct & conf ≥ {tc}",
                       "mean answer conf"], rows))

    # --- 7. flagged examples
    with open(ROOT / "results" / "e12_flagged.jsonl", "w") as f:
        for c in cats:
            for r in flagged[c]:
                it = items[r["id"]]
                f.write(json.dumps({"category": c, **{k: r[k] for k in ["id", "family", "p_can", "level_argmax",
                                                                          "answer", "answer_conf", "truth", "correct"]},
                                    "question": it["question"]["instructions"],
                                    "state_excerpt": it["state"][-400:]}) + "\n")
    ex = []
    for c in cats:
        worst = sorted(flagged[c], key=lambda r: -abs(r["p_can"] - r["answer_conf"]))[:2]
        for r in worst:
            q = items[r["id"]]["question"]["instructions"]
            ex.append([c, r["family"], q[:110] + ("…" if len(q) > 110 else ""), f"{r['p_can']:.2f}",
                       str(r["answer"])[:20], f"{r['answer_conf']:.2f}", "undeterminable" if not r["determinable"] else str(r["truth"])[:20]])
    md.append("\n### Examples (all flagged items are in `results/e12_flagged.jsonl`)\n\n"
              + table(["category", "family", "question", "P(can)", "answer", "answer conf", "truth"], ex) + "\n")
    summary["thresholds"] = {"meta": tm, "conf": tc, "signal": args.signal}
    save_results(EXP, summary, "\n".join(md))


if __name__ == "__main__":
    main()
