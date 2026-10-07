# E00 — Main coherence run (600 nested-policy scenarios)

Output of `python3 analyze.py` on `data/dataset.jsonl` / `data/responses.jsonl` (the original run). See `analyze.py` docstring for check definitions.

```

Scenarios: 600   cost $0.0422   input tokens 1,005,208   latency p50 400 ms, p95 476 ms

ACCURACY by question type
  A      87.2%  (n=1800)
  N      85.9%  (n=1800)
  P      85.7%  (n=600)
  AND    87.2%  (n=600)
  OR     87.2%  (n=600)
  NEST   83.5%  (n=600)
  CF     89.3%  (n=600)
  J      76.0%  (n=600)
  JR     76.0%  (n=600)
  SUB    64.8%  (n=600)
  CNT    68.8%  (n=600)

ATOM ACCURACY by rule depth        and by # exceptions that applied (stop level)
  depth 1:  97.8% (n=360)           stop 0:  93.9% (n=521)
  depth 2:  96.1% (n=360)           stop 1:  88.9% (n=524)
  depth 3:  88.1% (n=360)           stop 2:  94.0% (n=348)
  depth 4:  78.6% (n=360)           stop 3:  67.7% (n=223)
  depth 5:  75.6% (n=360)           stop 4:  80.8% (n=125)
                                    stop 5:  61.0% (n=59)

COUNTERFACTUAL accuracy by level of the changed exception
  level 1:  91.5% (n=366)
  level 2:  86.4% (n=140)
  level 3:  81.7% (n=71)
  level 4:  93.8% (n=16)
  level 5: 100.0% (n=7)

SOFT COHERENCE (probability logic)   violation = deviation > 0.2
  check              jev viol  jev mean dev  random viol
  complement             3.6%         0.050        63.2%
  paraphrase             1.7%         0.038        63.2%
  and_bounds             2.2%         0.030        53.8%
  or_bounds              2.8%         0.026        59.8%
  incl_excl             12.8%         0.095        72.2%
  nested_bounds          5.3%         0.046        58.5%
  joint_vs_atoms         8.8%         0.081        63.1%
  joint_vs_and_or        9.2%         0.082        65.5%
  subset_vs_atoms        7.4%         0.073        60.2%
  subset_vs_joint       17.8%         0.111        87.7%
  option_order           6.5%         0.072        89.8%
  count_vs_atoms         1.3%         0.051        38.5%

HARD COHERENCE (thresholded answers vs Jev's own atoms)
  check              jev contra  random contra
  negation                18.2%          87.3%
  paraphrase               3.8%          52.2%
  and                      6.2%          48.5%
  or                       9.0%          51.5%
  nested                  10.7%          47.5%
  joint_choice            13.5%          75.3%
  subset_choice           20.3%          85.8%
  count_score             25.5%          75.5%
  option_order             9.5%          78.0%
  joint_vs_subset         15.0%          75.5%
  scenarios with >=1 hard contradiction:  46.2%

COHERENCE by depth     soft violation rate   hard contradiction rate
  depth 1                  0.5%                  1.1%
  depth 2                  4.3%                  4.2%
  depth 3                 11.1%                 18.1%
  depth 4                  9.1%                 16.8%
  depth 5                  8.4%                 25.7%

ERRORS vs CONSISTENCY on compound questions (does Jev follow its own beliefs?)
  q      right+consistent  right+inconsist  wrong+consistent  wrong+inconsist
  AND              84.8%             2.3%             9.0%             3.8%
  OR               83.3%             3.8%             7.7%             5.2%
  NEST             80.0%             3.5%             9.3%             7.2%
  J                71.2%             4.8%            15.3%             8.7%
  SUB              61.0%             3.8%            18.7%            16.5%
  CNT              60.7%             8.2%            13.8%            17.3%

CALIBRATION of noul probabilities
  Brier 0.0945   ECE 0.0455   (n=6600)
  bin            n  mean p  freq true
  0.0-0.1    1555   0.040      0.017
  0.1-0.2     458   0.141      0.041
  0.2-0.3     334   0.243      0.156
  0.3-0.4     352   0.344      0.261
  0.4-0.5     371   0.448      0.353
  0.5-0.6     410   0.544      0.459
  0.6-0.7     459   0.644      0.654
  0.7-0.8     443   0.746      0.763
  0.8-0.9     582   0.850      0.895
  0.9-1.0    1636   0.951      0.983

CHOICE confidence vs accuracy
  conf 0.00-0.50: acc  43.8% (n=610)
  conf 0.50-0.80: acc  72.5% (n=397)
  conf 0.80-0.95: acc  89.6% (n=288)
  conf 0.95-1.00: acc  96.6% (n=505)

wrote results/e00_main.json
```
