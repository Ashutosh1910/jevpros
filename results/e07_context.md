# E07 — Irrelevant context

E07 - Irrelevant context: does accuracy hold as the relevant rules get buried?

30 base cases (K=2, depth 2, no decoy). Filler is inserted among the rules:
  decoy_rules  - many rules in the same format for categories not in the case (hard distractors)
  boilerplate  - generic policy prose (easy distractors)
Sizes ~1k, 4k, 12k, 24k tokens (estimated as chars/4); filler placed at start / middle / end of the
rule list (i.e. relevant rules at the end / split / start). Questions: A0, A1, J.

| filler | target tokens | position | actual input tokens | atom acc | joint acc | mean atom confidence | latency ms |
|---|---|---|---|---|---|---|---|
| none | 0 | - | 691 | 96.7% | 96.7% | 0.93 | 405 |
| decoy_rules | 1000 | all | 1735 | 97.8% | 93.3% | 0.90 | 417 |
| decoy_rules | 4000 | all | 4770 | 93.9% | 90.0% | 0.89 | 446 |
| decoy_rules | 12000 | all | 12990 | 96.7% | 90.0% | 0.88 | 535 |
| decoy_rules | 24000 | all | 25292 | 95.0% | 87.8% | 0.87 | 687 |
| boilerplate | 1000 | all | 1548 | 95.6% | 92.2% | 0.92 | 411 |
| boilerplate | 4000 | all | 4132 | 95.6% | 90.0% | 0.92 | 447 |
| boilerplate | 12000 | all | 11019 | 95.6% | 91.1% | 0.91 | 529 |
| boilerplate | 24000 | all | 21378 | 96.7% | 91.1% | 0.91 | 669 |

Atom accuracy by where the filler was inserted (start = relevant rules come last):

| filler | size | filler at start | filler in middle | filler at end |
|---|---|---|---|---|
| decoy_rules | 1000 | 98% | 97% | 98% |
| decoy_rules | 4000 | 90% | 95% | 97% |
| decoy_rules | 12000 | 97% | 97% | 97% |
| decoy_rules | 24000 | 95% | 93% | 97% |
| boilerplate | 1000 | 95% | 95% | 97% |
| boilerplate | 4000 | 95% | 95% | 97% |
| boilerplate | 12000 | 95% | 95% | 97% |
| boilerplate | 24000 | 95% | 98% | 97% |
