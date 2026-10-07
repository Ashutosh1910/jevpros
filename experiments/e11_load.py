"""E11 - Latency and throughput under concurrency.

One fixed request (scenario s00000 from the main dataset: ~1.2k input tokens, 13 questions) sent at
concurrency 1, 2, 4, 8, 16, 32, 64. Calls per level: max(32, 2 x concurrency). Run this alone.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ROOT, log_event, mean, run_jev, save_results, table  # noqa: E402

EXP = "e11_load"
LEVELS = [1, 2, 4, 8, 16, 32, 64]


def pctl(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main():
    row = json.loads(open(ROOT / "data/dataset.jsonl").readline())
    rows, summary = [], {}
    for c in LEVELS:
        n = max(32, 2 * c)
        calls = [{"call_id": f"c{c}-{i}", "state": row["state"], "questions": row["questions"],
                  "meta": {"concurrency": c}} for i in range(n)]
        t0 = time.time()
        resp = run_jev(EXP, calls, workers=c)
        wall = time.time() - t0
        lat = [r["latency_ms"] for r in resp.values()]
        errors = sum(1 for line in open(ROOT / "logs" / EXP / "calls.jsonl")
                     if (e := json.loads(line))["meta"].get("concurrency") == c and e["error"])
        summary[c] = {"n": len(lat), "p50": pctl(lat, .5), "p95": pctl(lat, .95), "p99": pctl(lat, .99),
                      "mean": mean(lat), "wall_s": wall, "throughput_rps": len(lat) / wall, "errors": errors}
        rows.append([c, len(lat), summary[c]["p50"], summary[c]["p95"], summary[c]["p99"], f"{wall:.1f}",
                     f"{len(lat) / wall:.1f}", errors])
        log_event(EXP, f"concurrency {c}: p50 {summary[c]['p50']} ms, {len(lat) / wall:.1f} req/s")
    md = (f"# E11 — Latency under load\n\n{__doc__.strip()}\n\n"
          + table(["concurrency", "calls", "p50 ms", "p95 ms", "p99 ms", "wall s", "throughput req/s", "errors"], rows)
          + "\n\nWall time includes one OpenRouter credits check per level (~0.2–0.5 s), so throughput at low call "
            "counts is slightly understated.\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
