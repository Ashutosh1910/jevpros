"""Send every scenario in the dataset to Jev (one decisions call each). Resumable.

  python3 run_bench.py --limit 10          # pilot
  python3 run_bench.py --workers 8         # full run; skips ids already in the output file
"""

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from jev_client import JevError, decide


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/dataset.jsonl")
    ap.add_argument("--out", default="data/responses.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--budget", type=float, default=1.0, help="stop once spend (USD) exceeds this")
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(args.data)]
    out = Path(args.out)
    done = set()
    spent = 0.0
    if out.exists():
        for line in out.open():
            r = json.loads(line)
            done.add(r["id"])
            spent += r["response"].get("usage", {}).get("cost") or 0
    todo = [r for r in rows if r["id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(done)} already done (${spent:.5f}); running {len(todo)}")

    lock = threading.Lock()
    stop = threading.Event()
    failures = 0

    def work(row):
        if stop.is_set():
            return None
        return row["id"], decide(row["state"], row["questions"])

    with out.open("a") as f, ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(work, r) for r in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                res = fut.result()
            except JevError as e:
                failures += 1
                print(f"  error: {e}")
                continue
            if res is None:
                continue
            sid, resp = res
            with lock:
                f.write(json.dumps({"id": sid, "response": resp}) + "\n")
                f.flush()
                spent += resp.get("usage", {}).get("cost") or 0
                if spent > args.budget:
                    stop.set()
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}  spent ${spent:.5f}")
    print(f"done. failures={failures} total spent ${spent:.5f}" + ("  (budget hit)" if stop.is_set() else ""))


if __name__ == "__main__":
    main()
