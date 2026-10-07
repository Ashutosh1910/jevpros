# E14 — Dutch-booking Jev (coherence of its probabilities as prices)

E14 - Can you Dutch-book Jev? (coherence of its probabilities as prices)

Treat every Jev probability as the price of a $1 ticket that pays if the statement is true. A set of prices is
COHERENT if no combination of bets (buy or sell each ticket, at most $1 of each) wins money in every possible
world. The Dutch-book value g = the largest guaranteed profit a bettor can lock in against Jev's prices; g = 0
exactly when the prices are consistent with some probability distribution (de Finetti). Conditional prices
("B, given that A") are called-off bets: refunded if A turns out false.

Each set is two statements A and B about one situation, so there are 4 worlds (AB, A¬B, ¬AB, ¬A¬B).
Families (200 sets each):
  chance    dice / cards / urn without replacement / biased coin; exact true probabilities by enumeration
  baserate  a population with counts or percentages (patients, employees, emails, parcels, students);
            exact true probabilities; includes the classic "P(condition | positive test)" setup
  policy    nested-exception policy cases (depth 2-5), A = item 1 is <yes>, B = item 2 is <yes>; truth is 0/1
Calls per set (every question in its own call unless noted):
  A, ¬A, B, ¬B, A∧B, A∨B, A∧¬B, ¬A∧B, ¬A∧¬B       9 unconditional prices
  B|A, A|B                                        conditioning: "It is known that the following is true: ..."
                                                  added to the state (chance and baserate only)
  A again                                         noise floor: arbitrage from re-asking the same price
  bundled                                         the 9 unconditional questions in ONE call
  choice                                          one Choice over the 4 worlds (coherent by construction)
Dutch book solved exactly: g = min over distributions λ on the 4 worlds of Σ_i |E_λ[payoff of bet i]| (LP dual),
minimised by enumerating the vertices of the arrangement. Baselines: uniformly random prices on the same events.
Outputs: data/e14_dutch_book/dataset.jsonl (every set: state, statements, true probabilities, the requests),
data/e14_dutch_book/answers.jsonl (prices, Dutch-book values and checks per set), logs/e14_dutch_book/calls.jsonl.

### Guaranteed profit against Jev's prices (per set; each ticket at most $1)

| family | prices | mean | median | sets > $0.05 | sets > $0.20 | max |
|---|---|---|---|---|---|---|
| chance | separate calls, all prices | $0.479 | $0.445 | 100% | 98% | $1.47 |
| chance | separate calls, 9 unconditional prices | $0.434 | $0.400 | 100% | 96% | $1.46 |
| chance | one bundled call, same 9 prices | $0.439 | $0.400 | 100% | 96% | $1.54 |
| chance | noise floor: same price asked twice | $0.008 | $0.010 | 0% | 0% | $0.03 |
| chance | truth + random noise of Jev's error size (mean error 0.070 vs Jev 0.075) | $0.544 | $0.528 | 100% | 100% | $1.02 |
| chance | random prices (baseline) | $2.241 | $2.207 | 100% | 100% | $3.93 |
| baserate | separate calls, all prices | $0.629 | $0.633 | 100% | 100% | $1.26 |
| baserate | separate calls, 9 unconditional prices | $0.554 | $0.550 | 100% | 99% | $1.09 |
| baserate | one bundled call, same 9 prices | $0.542 | $0.540 | 100% | 99% | $1.12 |
| baserate | noise floor: same price asked twice | $0.005 | $0.000 | 0% | 0% | $0.02 |
| baserate | truth + random noise of Jev's error size (mean error 0.074 vs Jev 0.078) | $0.564 | $0.560 | 100% | 100% | $1.00 |
| baserate | random prices (baseline) | $2.210 | $2.204 | 100% | 100% | $4.17 |
| policy | separate calls, 9 unconditional prices | $0.658 | $0.620 | 99% | 80% | $1.91 |
| policy | one bundled call, same 9 prices | $0.658 | $0.630 | 98% | 79% | $2.00 |
| policy | noise floor: same price asked twice | $0.030 | $0.020 | 19% | 0% | $0.41 |
| policy | truth + random noise of Jev's error size (mean error 0.113 vs Jev 0.231) | $0.858 | $0.832 | 98% | 97% | $1.85 |
| policy | random prices (baseline) | $2.016 | $2.034 | 100% | 100% | $3.75 |

### Where the arbitrage comes from

Dutch book on subsets of the separate-call prices; signed error = mean (price − true probability), positive = overpriced; last column = the Choice's top-cell probability vs the true top-cell probability.

| family | A and ¬A only | the 4 joint cells only | A, B, A∧B, A∨B only | atoms | negations | AND | OR | cells with ¬ | Choice top cell (Jev vs truth) |
|---|---|---|---|---|---|---|---|---|---|
| chance | $0.073 | $0.154 | $0.145 | -0.026 | -0.032 | +0.030 | +0.026 | +0.027 | 0.77 vs 0.51 |
| baserate | $0.036 | $0.280 | $0.209 | -0.025 | +0.074 | -0.026 | +0.183 | +0.102 | 0.61 vs 0.57 |
| policy | $0.088 | $0.453 | $0.118 | +0.010 | +0.068 | +0.071 | +0.003 | +0.126 | 0.72 vs 1.00 |

### Coherence checks (means; separate calls)

| check | chance | baserate | policy |
|---|---|---|---|
| complement |P(A)+P(¬A)−1| | 0.073 | 0.036 | 0.088 |
| four cells: mean Σ | 1.112 | 1.280 | 1.449 |
| four cells: share with |Σ−1| > 0.1 | 0.570 | 0.955 | 0.780 |
| P(A∧B) > min(P(A),P(B)) + 0.05 | 0.090 | 0.010 | 0.220 |
| P(A∨B) < max(P(A),P(B)) − 0.05 | 0.005 | 0.000 | 0.100 |
| |P(A∨B) − (P(A)+P(B)−P(A∧B))| | 0.145 | 0.209 | 0.113 |
| |P(A) − (P(A∧B)+P(A∧¬B))| | 0.115 | 0.105 | 0.207 |
| |P(B|A)·P(A) − P(A∧B)| | 0.073 | 0.034 | — |
| |P(A|B)·P(B) − P(B|A)·P(A)| (Bayes) | 0.027 | 0.030 | — |

### Error against the true probability (mean |price − truth|; policy truth is 0/1)

| question | chance | baserate | policy |
|---|---|---|---|
| atoms (A, B) | 0.053 | 0.035 | 0.222 |
| negations | 0.061 | 0.076 | 0.229 |
| AND | 0.072 | 0.040 | 0.210 |
| OR | 0.092 | 0.184 | 0.217 |
| joint cells (with ¬) | 0.087 | 0.106 | 0.249 |
| conditional B|A | 0.082 | 0.037 | — |
| conditional A|B | 0.085 | 0.054 | — |
| joint cells via one Choice | 0.206 | 0.066 | 0.176 |
| joint cells via 4 separate Nouls | 0.083 | 0.090 | 0.239 |

### Base rates: counts vs percentages

Inverse confusion = P(A|B) lies closer to the true P(B|A) than to the true P(A|B) (sets where the two differ by more than 0.2).

| format | sets | error P(A|B) | error P(B|A) | inverse confusion | mean Dutch book |
|---|---|---|---|---|---|
| counts | 100 | 0.051 | 0.048 | 6% of 54 | $0.672 |
| percent | 100 | 0.058 | 0.026 | 5% of 44 | $0.587 |

### By setup

| family | setup | sets | mean Dutch book (all prices) | mean error |
|---|---|---|---|---|
| chance | cards | 50 | $0.445 | 0.055 |
| chance | coin | 50 | $0.426 | 0.068 |
| chance | dice | 50 | $0.476 | 0.088 |
| chance | urn | 50 | $0.568 | 0.088 |
| baserate | emails | 40 | $0.450 | 0.058 |
| baserate | employees | 40 | $0.686 | 0.081 |
| baserate | parcels | 40 | $0.654 | 0.088 |
| baserate | patients | 40 | $0.704 | 0.083 |
| baserate | students | 40 | $0.654 | 0.079 |
| policy | access | 50 | $0.682 | 0.222 |
| policy | expense | 50 | $0.700 | 0.252 |
| policy | insurance | 50 | $0.630 | 0.223 |
| policy | library | 50 | $0.619 | 0.225 |

### Policy family by rule depth

| depth | sets | mean Dutch book (9 prices) | sets > $0.05 | error on A |
|---|---|---|---|---|
| 2 | 52 | $0.286 | 96% | 0.106 |
| 3 | 52 | $0.612 | 100% | 0.217 |
| 4 | 48 | $0.798 | 100% | 0.247 |
| 5 | 48 | $0.971 | 100% | 0.338 |

### Most exploitable set (#525, policy/access, guaranteed profit $1.91)

State: FACILITY ACCESS CONTROL POLICY
Each request is decided by the rule for its category. Within a rule, every exception clause is only considered if the clause immediately before it applied; when an exception applies, its decision replaces the previous one.

Rule 1 (loading dock): loading dock items are granted by default. Exception: if no NDA is on file, it is denied instead. But if, in addition, the person has more than 1 open security incidents, it is granted after all. Even then, if the person's home site is a partner site, it is denied. But if, in addition, entry is requested after 12:00, it is granted after all. Even then, if the entry date is not a public holiday, it is denied.
Rule 2 (server room): server room items are denied by default. Exception: if the person has more than 1 open security incidents, it is granted instead. Even then, if no NDA is on file, it is denied. Even then, if the person's home site is not the east campus, it is granted. Further exception to the previous clause: if the badge clearance is at most level 7, it is denied. But if, in addition, the biometric check did not pass, it is granted after all.

CASE
- Request 1 (category: server room) - open security incidents: 2; months with the organization: 51 months; person type: an auditor; home site: headquarters; biometric check passed: no; badge clearance level: level 7; NDA signed: no.
- Request 2 (category: loading dock) - safety training completed: no; requested entry time: 9:00; person type: an auditor; open security incidents: 2; on a public holiday: yes; NDA signed: no; home site: the east campus.

| event | question | Jev price | true probability |
|---|---|---|---|
| A | Under the policy, Request 1 (server room) is granted. | 0.680 | 1.000 |
| nA | It is not the case that under the policy, Request 1 (server room) is granted. | 0.620 | 0.000 |
| B | Under the policy, Request 2 (loading dock) is granted. | 0.770 | 1.000 |
| nB | It is not the case that under the policy, Request 2 (loading dock) is granted. | 0.540 | 0.000 |
| AB | Both of the following are true: (1) under the policy, Request 1 (server room) is granted; (2) under the policy, Request 2 (loading dock) is granted. | 0.640 | 1.000 |
| AoB | At least one of the following is true: (1) under the policy, Request 1 (server room) is granted; (2) under the policy, Request 2 (loading dock) is granted. | 0.790 | 1.000 |
| AnB | Both of the following are true: (1) under the policy, Request 1 (server room) is granted; (2) it is not the case that under the policy, Request 2 (loading dock) is granted. | 0.600 | 0.000 |
| nAB | Both of the following are true: (1) it is not the case that under the policy, Request 1 (server room) is granted; (2) under the policy, Request 2 (loading dock) is granted. | 0.560 | 0.000 |
| nAnB | Both of the following are true: (1) it is not the case that under the policy, Request 1 (server room) is granted; (2) it is not the case that under the policy, Request 2 (loading dock) is granted. | 0.500 | 0.000 |
