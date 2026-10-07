# Jev benchmark suite

Benchmarks of TypeSafe's **Jev** (`~typesafe/jev-latest`, a "System One" decision model) through
OpenRouter's `POST /api/alpha/decisions`. Jev returns typed answers with probabilities — no text — so
every test here is built from its three primitives: `noul` (yes/no probability), `choice`, `score`.

**Start with `REPORT.md`** — findings first, then every experiment's method and tables.

## Layout

| path | what |
|---|---|
| `REPORT.md` | assembled report (`python3 make_report.py` rebuilds it) |
| `RUN_LOG.md` | chronological log of every experiment run: calls, time, spend, errors |
| `results/<exp>.md` / `.json` | per-experiment method + tables / machine-readable summary |
| `logs/<exp>/calls.jsonl` | **every API call**: request (state + questions), full response, latency, cost, metadata, error |
| `logs/<exp>.stdout.txt` | console output of each experiment run |
| `data/dataset.jsonl`, `data/responses.jsonl` | the original 600-scenario coherence dataset and Jev's answers |
| `jev_client.py` | stdlib client (retries on 408/429/5xx) |
| `gen_dataset.py` | nested-exception policy generator (4 domains, ground truth computed exactly) |
| `bench/common.py` | logged, resumable, budget-capped runner (`SUITE_BUDGET_USD`, default $4 of OpenRouter usage) |
| `bench/scenarios.py` | re-renders one logical case under controlled variations (names, order, wording, units, omissions, injections, filler) |
| `analyze.py` | coherence/accuracy analysis of the original run (E00) |
| `experiments/eXX_*.py` | one script per experiment; re-running resumes from the log and never re-pays for finished calls |
| `contradiction_probe.py` | the first single-scenario probe |
| `data/e12_selftrust/dataset.jsonl` | E12 dataset: 3,744 items (state, question, meta questions, truth; `truth: null` = undeterminable) |
| `data/e12_selftrust/answers.jsonl` | E12 raw results per item: meta P(can), level probabilities, answer, confidence, correctness |
| `data/e16_memory_ops/dataset.jsonl`, `answers.jsonl` | E16 every decision (memories, new fact, gold) and every decider's parsed answer; `bench/llm.py` = the logged LLM client; `experiments/mem0_prompt.py` = Mem0's prompt, verbatim |
| `data/e15_reasoning/dataset.jsonl`, `answers.jsonl` | E15 every request (state with notes, questions, the notes' stated conclusion) and per-call derived fields |
| `data/e14_dutch_book/dataset.jsonl`, `answers.jsonl` | E14 every statement pair (state, questions, true probabilities) and per-set prices, Dutch-book values and checks |
| `data/e13_anchoring/dataset.jsonl`, `answers.jsonl` | E13 every request (state, questions, meta) and per-call derived fields |
| `results/e12_flagged.jsonl` | every E12 item flagged as a wrong/inconsistent self-assessment at the current thresholds |
| `build_site.py` / `REPORT.html` | the shareable report page |

## Experiments

| id | question |
|---|---|
| E00 | Main run: accuracy + probability-logic coherence on 600 nested-policy scenarios |
| E01 | Numbers, dates, stacked negation (plus slicing E00 by condition type) |
| E02 | Does it admit when the answer can't be determined? |
| E03 | Invariance to renaming / reordering / rewording / units; run-to-run determinism |
| E04 | Prompt injection and persuasion planted in the state |
| E05 | Are questions in one call independent? |
| E06 | Accuracy as the number of choice options grows to 255 |
| E07 | Burying the relevant rules in up to ~24k tokens of irrelevant text |
| E08 | Nesting depth up to 10 exceptions |
| E09 | Internal consistency of counting ("at least n", "exactly n", score) |
| E11 | Latency and throughput under concurrency |
| E12 | Self-trust: asked "can you answer this?" first, then the question (3,744 items, 17 question types) |
| E13 | Multi-turn anchoring: an earlier answer (right/wrong, 4 sources, 2 confidences, reviewer feedback, Jev's own real answer) shown in the state (400 cases, 10,000 calls) |
| E14 | Dutch book: are Jev's probabilities coherent as prices? 600 statement pairs (chance, base rates, policies) priced in separate calls; exact max guaranteed arbitrage (8,000 calls) |
| E15 | Attaching reasoning: exact step-by-step notes written into the state, then edited (no conclusion, wrong conclusion, "verified" label, one wrong step, half the steps) — read or copied? (400 cases, depths 1–10, 4,000 calls) |
| E16 | Agent hook: Mem0's ADD / UPDATE / DELETE / NONE memory decision — Jev vs typed open models (Llama-3.1-8B, Llama-3.3-70B) and GPT-4o-mini, and LLMs run exactly as Mem0 runs them (2,100 decisions × 9 deciders, 18,900 calls) |

(E10, a Jev→LLM cascade, was dropped: this suite only tests Jev itself.)

## Re-running

```
echo 'OPENROUTER_API_KEY=sk-or-...' > .env      # or export it
python3 experiments/e03_invariance.py            # any experiment; resumes if interrupted
python3 make_report.py
python3 build_site.py                            # rebuild REPORT.html
```

E12 at other thresholds (no API calls):

```
python3 experiments/e12_analyze.py --meta 0.8 --conf 0.9          # flag thresholds
python3 experiments/e12_analyze.py --signal p_can                  # use the yes/no meta question instead
python3 experiments/e12_analyze.py --meta-grid 0.5,0.9 --conf-grid 0.7,0.95
```
