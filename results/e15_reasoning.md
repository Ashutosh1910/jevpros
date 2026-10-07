# E15 — Attaching reasoning: does Jev read it or copy the conclusion?

E15 - Attaching reasoning to Jev: does it read the reasoning or copy the conclusion?

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

Re-asking the identical no-notes request flipped 6.5% of A0 decisions (noise floor).

### All depths

| notes in the state | A0 accuracy [95% CI] | mean confidence | decision = stated conclusion [95% CI] | A1 accuracy (no notes about it) |
|---|---|---|---|---|
| no notes | 78.5% [74.2%–82.2%] | 0.73 | — | 81.5% |
| no notes, asked again (noise floor) | 79.5% [75.3%–83.2%] | 0.74 | — | 80.0% |
| correct steps, no conclusion | 99.5% [98.2%–99.9%] | 0.93 | — | 79.5% |
| correct steps + correct conclusion | 99.2% [97.8%–99.7%] | 0.92 | 99.2% [97.8%–99.7%] | 79.0% |
| correct steps + WRONG conclusion | 99.0% [97.5%–99.6%] | 0.89 | 1.0% [0.4%–2.5%] | 78.2% |
| correct steps + WRONG conclusion, labelled “verified” | 64.0% [59.2%–68.6%] | 0.74 | 36.0% [31.4%–40.8%] | 80.2% |
| one wrong step, conclusion follows it | 73.2% [68.7%–77.4%] | 0.78 | 35.8% [31.2%–40.6%] | 77.2% |
| conclusion only, correct | 74.0% [69.5%–78.1%] | 0.73 | 74.0% [69.5%–78.1%] | 79.8% |
| conclusion only, WRONG | 82.0% [77.9%–85.5%] | 0.73 | 18.0% [14.5%–22.1%] | 79.2% |
| first half of the steps only | 82.8% [78.7%–86.1%] | 0.80 | — | 79.0% |

### When the notes state a wrong conclusion

| notes | follows the stated conclusion | A0 accuracy | right without notes → wrong with them |
|---|---|---|---|
| correct steps + WRONG conclusion | 1.0% | 99.0% | 0.3% of 314 |
| correct steps + WRONG conclusion, labelled “verified” | 36.0% | 64.0% | 34.7% of 314 |
| conclusion only, WRONG | 18.0% | 82.0% | 4.5% of 314 |
| one wrong step, conclusion follows it (sets whose conclusion is wrong: 268) | 22.0% | 78.0% | — |

### Accuracy by rule depth

| depth | no notes | correct steps, no conclusion | first half of the steps only | correct steps + correct conclusion | one wrong step, conclusion follows it | correct steps + WRONG conclusion | conclusion only, WRONG |
|---|---|---|---|---|---|---|---|
| 1 | 95.0% | 97.5% | 97.5% | 97.5% | 95.0% | 97.5% | 95.0% |
| 2 | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% | 100.0% | 97.5% |
| 3 | 92.5% | 97.5% | 87.5% | 97.5% | 77.5% | 97.5% | 92.5% |
| 4 | 82.5% | 100.0% | 75.0% | 100.0% | 80.0% | 100.0% | 80.0% |
| 5 | 57.5% | 100.0% | 75.0% | 97.5% | 72.5% | 100.0% | 70.0% |
| 6 | 82.5% | 100.0% | 82.5% | 100.0% | 80.0% | 100.0% | 87.5% |
| 7 | 75.0% | 100.0% | 72.5% | 100.0% | 62.5% | 100.0% | 72.5% |
| 8 | 72.5% | 100.0% | 77.5% | 100.0% | 67.5% | 97.5% | 77.5% |
| 9 | 65.0% | 100.0% | 80.0% | 100.0% | 57.5% | 100.0% | 72.5% |
| 10 | 62.5% | 100.0% | 80.0% | 100.0% | 50.0% | 97.5% | 75.0% |

### Accuracy by depth band [95% CI]

| depths | no notes | correct steps, no conclusion | first half of the steps only | correct steps + correct conclusion | one wrong step, conclusion follows it | correct steps + WRONG conclusion | conclusion only, WRONG |
|---|---|---|---|---|---|---|---|
| depth 1-3 | 95.8% [90.6%–98.2%] | 98.3% [94.1%–99.5%] | 95.0% [89.5%–97.7%] | 98.3% [94.1%–99.5%] | 87.5% [80.4%–92.3%] | 98.3% [94.1%–99.5%] | 95.0% [89.5%–97.7%] |
| depth 4-6 | 74.2% [65.7%–81.2%] | 100.0% [96.9%–100.0%] | 77.5% [69.2%–84.1%] | 99.2% [95.4%–99.9%] | 77.5% [69.2%–84.1%] | 100.0% [96.9%–100.0%] | 79.2% [71.1%–85.5%] |
| depth 7-10 | 68.8% [61.2%–75.4%] | 100.0% [97.7%–100.0%] | 77.5% [70.4%–83.3%] | 100.0% [97.7%–100.0%] | 59.4% [51.6%–66.7%] | 98.8% [95.6%–99.7%] | 74.4% [67.1%–80.5%] |
