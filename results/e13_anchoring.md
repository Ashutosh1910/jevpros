# E13 — Anchoring on earlier answers (multi-turn)

E13 - Does Jev anchor on earlier answers? (multi-turn / stateful use)

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

Control accuracy on A0 (no history, r0): **84.2%** (337 right, 63 wrong of 400).

### One earlier answer shown

| condition | A0 accuracy | harm: right → wrong [95% CI] | rescue: wrong → right [95% CI] | follows shown answer | shift toward shown answer | A1 accuracy | A1 mean |Δp| |
|---|---|---|---|---|---|---|---|
| no history, re-asked (noise floor, r1) | 86.5% | 1.5% [0.6%–3.4%] | 22.2% [13.7%–33.9%] | 95.2% | -0.003 | 88.2% | 0.028 |
| no history, re-asked (noise floor, r2) | 85.8% | 1.2% [0.5%–3.0%] | 15.9% [8.9%–26.8%] | 96.5% | -0.005 | 89.0% | 0.030 |
| history about the other item only | 83.2% | 4.7% [2.9%–7.6%] | 19.0% [11.2%–30.4%] | — | — | 94.2% | 0.077 |
| Jev itself said WRONG answer (95%) | 75.0% | 13.4% [10.1%–17.4%] | 12.7% [6.6%–23.1%] | 25.0% | +0.077 | 88.2% | 0.061 |
| Jev itself said WRONG answer (55%) | 81.5% | 8.0% [5.6%–11.4%] | 25.4% [16.3%–37.3%] | 18.5% | +0.011 | 88.5% | 0.061 |
| Jev itself said right answer (95%) | 93.8% | 1.5% [0.6%–3.4%] | 68.3% [56.0%–78.4%] | 93.8% | +0.068 | 87.2% | 0.059 |
| Jev itself said right answer (55%) | 87.2% | 3.0% [1.6%–5.4%] | 34.9% [24.3%–47.2%] | 87.2% | +0.025 | 88.0% | 0.058 |
| another AI model said WRONG answer (95%) | 84.0% | 5.3% [3.4%–8.3%] | 27.0% [17.6%–39.0%] | 16.0% | +0.003 | 87.5% | 0.060 |
| another AI model said WRONG answer (55%) | 86.2% | 3.0% [1.6%–5.4%] | 28.6% [18.9%–40.7%] | 13.8% | -0.017 | 87.2% | 0.061 |
| another AI model said right answer (95%) | 86.2% | 3.6% [2.0%–6.1%] | 31.7% [21.6%–44.0%] | 86.2% | +0.021 | 86.5% | 0.064 |
| another AI model said right answer (55%) | 85.0% | 3.6% [2.0%–6.1%] | 23.8% [15.0%–35.6%] | 85.0% | +0.010 | 87.2% | 0.061 |
| the user said WRONG answer (95%) | 80.8% | 8.0% [5.6%–11.4%] | 20.6% [12.5%–32.2%] | 19.2% | +0.018 | 86.5% | 0.063 |
| the user said WRONG answer (55%) | 84.2% | 5.3% [3.4%–8.3%] | 28.6% [18.9%–40.7%] | 15.8% | -0.004 | 88.5% | 0.059 |
| the user said right answer (95%) | 90.2% | 1.8% [0.8%–3.8%] | 47.6% [35.8%–59.7%] | 90.2% | +0.042 | 85.2% | 0.062 |
| the user said right answer (55%) | 86.8% | 3.3% [1.8%–5.7%] | 33.3% [22.9%–45.6%] | 86.8% | +0.023 | 87.8% | 0.058 |
| a human reviewer said WRONG answer (95%) | 81.8% | 6.2% [4.1%–9.3%] | 17.5% [10.0%–28.6%] | 18.2% | +0.026 | 87.8% | 0.062 |
| a human reviewer said WRONG answer (55%) | 84.0% | 5.3% [3.4%–8.3%] | 27.0% [17.6%–39.0%] | 16.0% | -0.002 | 86.5% | 0.065 |
| a human reviewer said right answer (95%) | 90.2% | 2.1% [1.0%–4.2%] | 49.2% [37.3%–61.2%] | 90.2% | +0.043 | 85.2% | 0.062 |
| a human reviewer said right answer (55%) | 88.8% | 2.1% [1.0%–4.2%] | 39.7% [28.5%–52.0%] | 88.8% | +0.025 | 88.0% | 0.062 |

### Reviewer feedback on your earlier answer (95%)

| condition | A0 accuracy | harm: right → wrong [95% CI] | rescue: wrong → right [95% CI] | follows shown answer | shift toward shown answer | A1 accuracy | A1 mean |Δp| |
|---|---|---|---|---|---|---|---|
| your right answer, reviewer says incorrect | 26.5% | 68.5% [63.4%–73.3%] | 0.0% [-0.0%–5.7%] | 26.5% | -0.363 | 87.5% | 0.068 |
| your wrong answer, reviewer says incorrect | 99.2% | 0.0% [-0.0%–1.1%] | 95.2% [86.9%–98.4%] | 0.8% | -0.137 | 86.2% | 0.068 |
| your wrong answer, reviewer says correct | 3.8% | 95.5% [92.8%–97.3%] | 0.0% [-0.0%–5.7%] | 96.2% | +0.551 | 85.5% | 0.069 |
| your right answer, reviewer says correct | 99.8% | 0.0% [-0.0%–1.1%] | 98.4% [91.5%–99.7%] | 99.8% | +0.188 | 85.2% | 0.062 |

### Realistic multi-turn: Jev's own first answer shown, vs simply asking again

| measure | own answer in history | re-asked, no history |
|---|---|---|
| decision agrees with the first answer | 94.0% | 95.2% |
| mean |Δp| from the first answer | 0.061 | 0.027 |
| mean confidence (first answer: 0.799) | 0.833 | 0.800 |
| accuracy | 86.2% | 86.5% |
| first answer wrong (n=63): still wrong | 74.6% | 77.8% |

### Harm (right → wrong) by rule depth

| depth | control acc | re-asked (noise) | Jev itself said wrong (95%) | reviewer said wrong (95%) | your right answer + 'incorrect' feedback |
|---|---|---|---|---|---|
| 2 | 96.0% | 0.0% [0.0%–3.8%] | 2.1% [0.6%–7.3%] | 1.0% [0.2%–5.7%] | 51.0% [41.2%–60.8%] |
| 3 | 90.0% | 2.2% [0.6%–7.7%] | 12.2% [7.0%–20.6%] | 6.7% [3.1%–13.8%] | 61.1% [50.8%–70.5%] |
| 4 | 79.0% | 1.3% [0.2%–6.8%] | 12.7% [7.0%–21.8%] | 1.3% [0.2%–6.8%] | 78.5% [68.2%–86.1%] |
| 5 | 72.0% | 2.8% [0.8%–9.6%] | 30.6% [21.1%–42.0%] | 18.1% [10.9%–28.5%] | 90.3% [81.3%–95.2%] |
