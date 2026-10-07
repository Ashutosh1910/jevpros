# E01 — Numbers, dates and negation

E01 - Numbers, dates and negation.

Part A (no API calls): slice the main 600-scenario run by what the deciding conditions contained -
exact-threshold values, negated conditions, condition kind.
Part B (targeted micro-tests, one question per call):
  B1 numeric comparators (8 phrasings x 4 magnitudes x 5 value relations)
  B2 date comparisons   (2 operators x 4 formats x 5 relations)
  B3 negation stacking  (0-3 negations wrapped around a simple fact, both base truths)

### Part A — slicing the main run (no new calls)

Atom accuracy (A_i questions) split by what the item's *evaluated* conditions contained. 'Depth-std' averages per-depth accuracies so differences in depth mix don't drive the comparison.

| tag | present: acc [95% CI] | present: depth-std | absent: acc [95% CI] | absent: depth-std |
|---|---|---|---|---|
| boundary value in an evaluated condition | 84.7% [80.4%–88.2%] | 86.7% | 87.8% [86.0%–89.4%] | 87.3% |
| negated wording in an evaluated condition | 84.1% [81.4%–86.5%] | 86.5% | 89.6% [87.6%–91.4%] | 88.1% |
| deciding condition is numeric | 87.4% [84.6%–89.8%] | 87.8% | 87.1% [85.1%–88.9%] | 87.0% |
| deciding condition is categorical | 83.9% [80.4%–86.8%] | 84.1% | 88.6% [86.7%–90.2%] | 88.5% |
| deciding condition is yes/no | 89.6% [87.1%–91.8%] | 89.3% | 85.8% [83.7%–87.7%] | 86.1% |
| deciding condition is numeric AND at the exact boundary | 89.6% [84.3%–93.2%] | 89.7% | 87.0% [85.2%–88.5%] | 87.0% |

### Part B1  — overall accuracy 100.0% [99.2%–100.0%] (n=480)


By **relation**:

| relation | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| far below | 100.0% [96.2%–100.0%] | 0.98 | 96 |
| just below | 100.0% [96.2%–100.0%] | 0.98 | 96 |
| equal | 100.0% [96.2%–100.0%] | 0.97 | 96 |
| just above | 100.0% [96.2%–100.0%] | 0.98 | 96 |
| far above | 100.0% [96.2%–100.0%] | 0.98 | 96 |

By **comparator**:

| comparator | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| over | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| more than | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| at least | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| exceeding | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| under | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| less than | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| at most | 100.0% [94.0%–100.0%] | 0.98 | 60 |
| not exceeding | 100.0% [94.0%–100.0%] | 0.98 | 60 |

By **magnitude**:

| magnitude | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| small int | 100.0% [96.9%–100.0%] | 0.98 | 120 |
| money | 100.0% [96.9%–100.0%] | 0.98 | 120 |
| large | 100.0% [96.9%–100.0%] | 0.98 | 120 |
| decimal | 100.0% [96.9%–100.0%] | 0.98 | 120 |

### Part B2  — overall accuracy 99.4% [96.5%–99.9%] (n=160)


By **relation**:

| relation | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| months before | 100.0% [89.3%–100.0%] | 0.98 | 32 |
| 1 day before | 100.0% [89.3%–100.0%] | 0.98 | 32 |
| same day | 100.0% [89.3%–100.0%] | 0.98 | 32 |
| 1 day after | 96.9% [84.3%–99.4%] | 0.96 | 32 |
| months after | 100.0% [89.3%–100.0%] | 0.98 | 32 |

By **format**:

| format | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| ISO | 100.0% [91.2%–100.0%] | 0.98 | 40 |
| US numeric | 100.0% [91.2%–100.0%] | 0.98 | 40 |
| long | 100.0% [91.2%–100.0%] | 0.98 | 40 |
| day-first | 97.5% [87.1%–99.6%] | 0.96 | 40 |

By **op**:

| op | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| after | 100.0% [95.4%–100.0%] | 0.98 | 80 |
| on or before | 98.8% [93.3%–99.8%] | 0.97 | 80 |

### Part B3  — overall accuracy 92.2% [83.0%–96.6%] (n=64)


By **negations**:

| negations | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| 0 | 100.0% [80.6%–100.0%] | 0.98 | 16 |
| 1 | 100.0% [80.6%–100.0%] | 0.98 | 16 |
| 2 | 100.0% [80.6%–100.0%] | 0.97 | 16 |
| 3 | 68.8% [44.4%–85.8%] | 0.57 | 16 |

By **base_truth**:

| base_truth | accuracy [95% CI] | mean P(correct) | n |
|---|---|---|---|
| True | 93.8% [79.9%–98.3%] | 0.87 | 32 |
| False | 90.6% [75.8%–96.8%] | 0.88 | 32 |

B1 comparator × relation accuracy:

| comparator | far below | just below | equal | just above | far above |
|---|---|---|---|---|---|
| over | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| more than | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| at least | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| exceeding | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| under | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| less than | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| at most | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| not exceeding | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
