"""Shared plumbing for the experiment suite: logged/resumable Jev calls, budget guard,
results writing and a human-readable run log.

Layout (all relative to the project root):
  logs/<exp>/calls.jsonl   one line per API call: request, response, latency, cost, meta, error
  results/<exp>.json|.md   per-experiment summary written by the experiment
  RUN_LOG.md               chronological log of every experiment run (appended)
"""

import datetime as dt
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jev_client import JEV_MODEL, JevError, _load_key, decide  # noqa: E402

LOGS = ROOT / "logs"
RESULTS = ROOT / "results"
RUN_LOG = ROOT / "RUN_LOG.md"
SUITE_BUDGET_USD = float(os.environ.get("SUITE_BUDGET_USD", "4.0"))  # cap on total OpenRouter usage


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def log_event(exp: str, text: str) -> None:
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# Run log\n\nChronological record of every experiment run.\n\n")
    with RUN_LOG.open("a") as f:
        f.write(f"- `{now()}` **{exp}** — {text}\n")
    print(f"[{exp}] {text}")


def credits_used() -> float:
    req = urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                 headers={"Authorization": f"Bearer {_load_key()}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return float(json.loads(r.read())["data"]["total_usage"])


class BudgetExceeded(RuntimeError):
    pass


def _run_logged(exp, calls, fn, workers):
    """Generic resumable runner. `calls` is a list of dicts with a unique `call_id`.
    `fn(call)` returns (response_dict, cost_usd). Returns {call_id: response}."""
    path = LOGS / exp / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if path.exists():
        for line in path.open():
            r = json.loads(line)
            if r.get("error") is None:
                done[r["call_id"]] = r["response"]
    todo = [c for c in calls if c["call_id"] not in done]
    if not todo:
        return {c["call_id"]: done[c["call_id"]] for c in calls if c["call_id"] in done}

    used0 = credits_used()
    if used0 >= SUITE_BUDGET_USD:
        raise BudgetExceeded(f"OpenRouter usage ${used0:.4f} already >= suite cap ${SUITE_BUDGET_USD}")
    lock, stop = threading.Lock(), threading.Event()
    spent, errors = 0.0, 0
    started = time.time()

    def work(c):
        if stop.is_set():
            return c, None, None, "skipped: budget"
        t0 = time.perf_counter()
        try:
            resp, cost = fn(c)
            return c, resp, cost, None
        except Exception as e:  # noqa: BLE001 - log every failure, keep going
            return c, {"latency_ms": round((time.perf_counter() - t0) * 1000)}, 0.0, repr(e)

    with path.open("a") as f, ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(work, c) for c in todo]
        for n, fut in enumerate(as_completed(futs), 1):
            c, resp, cost, err = fut.result()
            if err == "skipped: budget":
                continue
            entry = {"call_id": c["call_id"], "ts": now(), "exp": exp, "meta": c.get("meta", {}),
                     "request": c["request"], "response": resp, "cost_usd": cost, "error": err}
            with lock:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                spent += cost or 0
                errors += err is not None
                if err is None:
                    done[c["call_id"]] = resp
                if used0 + spent >= SUITE_BUDGET_USD:
                    stop.set()
            if n % 100 == 0:
                print(f"  [{exp}] {n}/{len(todo)} calls, ${spent:.4f}, {errors} errors")
    log_event(exp, f"ran {len(todo)} calls in {time.time() - started:.0f}s, spent ${spent:.4f}, "
                   f"{errors} errors{' — BUDGET CAP HIT' if stop.is_set() else ''} "
                   f"(OpenRouter usage before: ${used0:.4f})")
    if stop.is_set():
        raise BudgetExceeded("suite budget cap reached")
    return {c["call_id"]: done[c["call_id"]] for c in calls if c["call_id"] in done}


def run_jev(exp, calls, workers=8):
    """calls: [{call_id, state, questions, meta}] -> {call_id: jev response}"""
    for c in calls:
        c["request"] = {"model": JEV_MODEL, "state": c.pop("state"), "questions": c.pop("questions")}

    def fn(c):
        r = decide(c["request"]["state"], c["request"]["questions"])
        return r, r.get("usage", {}).get("cost") or 0.0

    return _run_logged(exp, calls, fn, workers)


def save_results(exp: str, summary: dict, markdown: str) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{exp}.json").write_text(json.dumps(summary, indent=2, default=str))
    (RESULTS / f"{exp}.md").write_text(markdown)
    print(markdown)


# ---------- small stats helpers ----------

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def pct(x):
    return f"{100 * x:.1f}%"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def wilson(k, n, z=1.96):
    """95% Wilson interval for a proportion, as (lo, hi)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (c - h, c + h)


def ci(k, n):
    lo, hi = wilson(k, n)
    return f"{pct(k / n)} [{pct(lo)}–{pct(hi)}]" if n else "n/a"
