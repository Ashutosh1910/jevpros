"""Assemble REPORT.md from results/*.md plus call/cost totals from logs/*/calls.jsonl.

results/00_findings.md (hand-written summary) goes first if present.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS, LOGS = ROOT / "results", ROOT / "logs"


def log_totals():
    rows = []
    main = ROOT / "data/responses.jsonl"
    if main.exists():
        resp = [json.loads(line)["response"] for line in main.open()]
        rows.append(("main run (analyze.py)", len(resp), 0, sum(r["usage"].get("cost") or 0 for r in resp),
                     sum(r["usage"]["input_tokens"] for r in resp)))
    for d in sorted(p for p in LOGS.iterdir() if p.is_dir()):
        f = d / "calls.jsonl"
        if not f.exists():
            continue
        n = err = tok = 0
        cost = 0.0
        for line in f.open():
            e = json.loads(line)
            n += 1
            err += e["error"] is not None
            cost += e.get("cost_usd") or 0
            tok += ((e.get("response") or {}).get("usage") or {}).get("input_tokens") or 0
        rows.append((d.name, n, err, cost, tok))
    return rows


def main():
    parts = ["# Jev benchmark report\n",
             "Model: `~typesafe/jev-latest` (resolved to `typesafe/jev-1.13-20260917`) via OpenRouter's "
             "`/api/alpha/decisions`.\nEvery API call is logged in full (request, response, latency, cost) under "
             "`logs/<experiment>/calls.jsonl`; the run history is in `RUN_LOG.md`.\n"]
    findings = RESULTS / "00_findings.md"
    if findings.exists():
        parts.append(findings.read_text())
    rows = log_totals()
    parts.append("\n## Calls and cost\n\n| experiment | calls logged | errors | cost USD | input tokens |\n|---|---|---|---|---|\n"
                 + "\n".join(f"| {a} | {b} | {c} | ${d:.4f} | {e:,} |" for a, b, c, d, e in rows)
                 + f"\n| **total** | {sum(r[1] for r in rows)} | {sum(r[2] for r in rows)} | "
                   f"${sum(r[3] for r in rows):.4f} | {sum(r[4] for r in rows):,} |\n")
    for f in sorted(RESULTS.glob("e*.md")):
        parts.append("\n---\n\n" + f.read_text())
    (ROOT / "REPORT.md").write_text("\n".join(parts))
    print(f"wrote REPORT.md ({len(rows)} experiments)")


if __name__ == "__main__":
    main()
