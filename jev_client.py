"""Minimal client for Jev (TypeSafe) via OpenRouter's alpha Decisions API. Stdlib only."""

import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "~typesafe/jev-latest"
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 520, 522, 524}  # 52x: transient Cloudflare errors


class JevError(RuntimeError):
    pass


def _load_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    env_file = Path(__file__).with_name(".env")
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY (env var or .env file next to this script).")
    return key


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def noul(instructions: str) -> dict:
    return {"type": "noul", "instructions": instructions}


def score(instructions: str, levels: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": levels}


def decide(state: str, questions: dict[str, dict], model: str = JEV_MODEL, retries: int = 4) -> dict:
    """POST one decisions request. Returns the parsed JSON plus `latency_ms`."""
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    headers = {"Authorization": f"Bearer {_load_key()}", "Content-Type": "application/json"}
    for attempt in range(retries + 1):
        req = urllib.request.Request(DECISIONS_URL, data=body, headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            data["latency_ms"] = round((time.perf_counter() - started) * 1000)
            return data
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code not in RETRY_STATUS or attempt == retries:
                raise JevError(f"HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise JevError(str(e)) from e
        time.sleep(2**attempt + random.random())
    raise AssertionError("unreachable")
