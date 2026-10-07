# E11 — Latency under load

E11 - Latency and throughput under concurrency.

One fixed request (scenario s00000 from the main dataset: ~1.2k input tokens, 13 questions) sent at
concurrency 1, 2, 4, 8, 16, 32, 64. Calls per level: max(32, 2 x concurrency). Run this alone.

| concurrency | calls | p50 ms | p95 ms | p99 ms | wall s | throughput req/s | errors |
|---|---|---|---|---|---|---|---|
| 1 | 32 | 396 | 489 | 521 | 13.1 | 2.4 | 0 |
| 2 | 32 | 400 | 518 | 527 | 6.7 | 4.8 | 0 |
| 4 | 32 | 397 | 492 | 494 | 3.4 | 9.3 | 0 |
| 8 | 32 | 419 | 542 | 587 | 1.9 | 16.7 | 0 |
| 16 | 32 | 402 | 426 | 433 | 0.9 | 35.1 | 0 |
| 32 | 64 | 406 | 940 | 982 | 1.5 | 42.8 | 0 |
| 64 | 128 | 403 | 958 | 1024 | 1.4 | 92.5 | 0 |

Wall time includes one OpenRouter credits check per level (~0.2–0.5 s), so throughput at low call counts is slightly understated.
