"""OpenRouter chat-completions client for LLM baselines, logged through the same resumable runner as Jev calls.

Each call dict: {call_id, request: {model, messages, max_tokens, ...}, meta}. The full request and response
(content, logprobs, usage incl. OpenRouter's reported cost) go to logs/<exp>/calls.jsonl.
"""

import json
import random
import time
import urllib.error
import urllib.request

from bench.common import _run_logged
from jev_client import _load_key

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 520, 522, 524}


class LLMError(RuntimeError):
    pass


def chat(request: dict, retries: int = 4) -> dict:
    body = dict(request)
    body.setdefault("temperature", 0)
    body["usage"] = {"include": True}  # OpenRouter reports the cost of the call
    if body.get("logprobs") or body.get("response_format"):
        body["provider"] = {"require_parameters": True}  # only route to providers that honour them
    data = json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {_load_key()}", "Content-Type": "application/json"}
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(CHAT_URL, data=data, headers=headers), timeout=120) as r:
                out = json.loads(r.read())
            if "error" in out:
                raise LLMError(json.dumps(out["error"])[:500])
            out["latency_ms"] = round((time.perf_counter() - started) * 1000)
            return out
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code not in RETRY_STATUS or attempt == retries:
                raise LLMError(f"HTTP {e.code}: {detail[:500]}") from e
        except (urllib.error.URLError, TimeoutError, LLMError) as e:
            if attempt == retries:
                raise LLMError(str(e)) from e
        time.sleep(2 ** attempt + random.random())
    raise AssertionError("unreachable")


def run_llm(exp, calls, workers=8):
    """calls: [{call_id, request, meta}] -> {call_id: response}"""
    def fn(c):
        r = chat(c["request"])
        return r, (r.get("usage") or {}).get("cost") or 0.0
    return _run_logged(exp, calls, fn, workers)


def content(resp):
    return ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def first_token_logprobs(resp):
    """{token_text: logprob} for the first generated token's top alternatives (empty if not returned)."""
    lp = ((resp.get("choices") or [{}])[0].get("logprobs") or {}).get("content") or []
    if not lp:
        return {}
    out = {lp[0]["token"]: lp[0]["logprob"]}
    for alt in lp[0].get("top_logprobs") or []:
        out.setdefault(alt["token"], alt["logprob"])
    return out
