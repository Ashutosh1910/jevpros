"""E16 - Delegating an agent's memory-write decision: Mem0's ADD / UPDATE / DELETE / NONE step.

The Mem0 paper's update step (arXiv:2504.19413; used by mem0ai 1.x, still in the 2.x repo but no longer called by
add()) asks an LLM, for each newly extracted fact and the related existing memories, whether to ADD it, UPDATE an
existing memory, DELETE an existing memory, or do NONE. This benchmark asks whether a single-pass typed decider can
take over that decision.

Gold labels follow Mem0's own rules (experiments/mem0_prompt.py, copied verbatim):
  dup_exact        the new fact repeats a memory word for word                      -> NONE
  dup_paraphrase   the new fact says the same thing in other words                  -> NONE
  weaker           the memory is more detailed than the new fact                    -> NONE
  update_detail    the new fact adds detail to a memory                             -> UPDATE that memory
  update_change    a single-valued attribute changed (city, job, car, favourite)    -> UPDATE that memory
  delete_contra    the new fact contradicts a memory (antonym / explicit "not" / "no longer")  -> DELETE that memory
  add_unrelated    no existing memory is about the new fact's topic                 -> ADD
Each subtype x K (number of existing memories: 1, 5, 10) x 100 items = 2,100 decisions. With K > 1 the other
memories are about other topics; for multi-valued topics (foods, sports, pets, allergies, languages), half of the
items also hold a NEAR distractor: the same topic with a different value ("Loves pizza" next to "Loves sushi").

Deciders (each sees the same existing memories and new fact):
  jev_flat        Jev, one Choice over every (operation, memory) pair: ADD, UPDATE i, DELETE i, NONE
  jev_flat_m0     the same Choice, but the state carries Mem0's own prompt text instead of the short rule summary
  jev_decomp      Jev, one Choice per existing memory: unrelated / same or less / adds or changes / contradicts;
                  code combines (any contradiction -> DELETE, else any adds/changes -> UPDATE, else any same -> NONE,
                  else ADD)
  typed:<model>   an open small LLM given the same options as jev_flat, lettered; the decision and its probability
                  are read from the first token's log-probabilities (max_tokens 1)
  mem0:<model>    the model run exactly as Mem0 runs it: Mem0's prompt verbatim, JSON output, events parsed as Mem0's
                  code reads them (only explicit ADD / UPDATE / DELETE events count)
jev_flat, jev_decomp and typed:* get a short plain-text summary of Mem0's four rules instead of Mem0's JSON prompt.
Scoring: STRICT = the set of (operation, memory) changes equals the gold set exactly. LENIENT also accepts
semantically equivalent changes: DELETE i + ADD for an UPDATE or DELETE gold, and UPDATE i for an exact/paraphrase
duplicate (rewriting the same fact). Outputs: data/e16_memory_ops/{dataset,answers}.jsonl, logs/e16_memory_ops/calls.jsonl.
"""

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench.common import ROOT, ci, log_event, mean, pct, run_jev, save_results, table  # noqa: E402
from bench.llm import content, first_token_logprobs, run_llm  # noqa: E402
from mem0_prompt import DEFAULT_UPDATE_MEMORY_PROMPT, get_update_memory_messages  # noqa: E402

EXP = "e16_memory_ops"
OUT = ROOT / "data" / EXP
PER_CELL = 100
KS = [1, 5, 10]
SUBTYPES = ["dup_exact", "dup_paraphrase", "weaker", "update_detail", "update_change", "delete_contra", "add_unrelated"]
GOLD_OP = {"dup_exact": "NONE", "dup_paraphrase": "NONE", "weaker": "NONE", "update_detail": "UPDATE",
           "update_change": "UPDATE", "delete_contra": "DELETE", "add_unrelated": "ADD"}
MEM0_MODELS = ["meta-llama/llama-3.1-8b-instruct", "qwen/qwen-2.5-7b-instruct", "openai/gpt-4o-mini"]
TYPED_MODELS = ["meta-llama/llama-3.1-8b-instruct", "meta-llama/llama-3.3-70b-instruct", "openai/gpt-4o-mini"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def an(w):
    return "an" if w[0].lower() in "aeiou" else "a"


# ---------- topics: each returns texts for one value; `alt` gives a second value for changes / near distractors ----------

CITIES = [("Pune", "Kothrud"), ("Bangalore", "Indiranagar"), ("Lyon", "Croix-Rousse"), ("Osaka", "Namba"),
          ("Toronto", "Leslieville"), ("Austin", "Hyde Park"), ("Leeds", "Headingley"), ("Melbourne", "Fitzroy")]
JOBS = ["software engineer", "nurse", "high-school teacher", "data analyst", "architect", "pharmacist",
        "graphic designer", "civil engineer"]
FOODS = [("sushi", "salmon nigiri"), ("pizza", "thin-crust margherita"), ("biryani", "Hyderabadi biryani"),
         ("ramen", "tonkotsu ramen"), ("dosa", "masala dosa"), ("tacos", "fish tacos"), ("pasta", "carbonara"),
         ("dark chocolate", "70% dark chocolate")]
SPORTS = ["cricket", "badminton", "football", "tennis", "basketball", "table tennis"]
DAYS = ["Saturday", "Sunday", "Wednesday", "Friday"]
PEOPLE = ["colleagues", "friends from college", "their cousins", "neighbours"]
PETS = [("dog", "Max"), ("cat", "Luna"), ("parrot", "Kiwi"), ("rabbit", "Coco"), ("tortoise", "Shelly")]
ALLERGIES = [("peanuts", "peanut"), ("shellfish", "shellfish"), ("pollen", "pollen"), ("penicillin", "penicillin"),
             ("dust mites", "dust-mite")]
LANGS = ["Spanish", "Japanese", "Tamil", "German", "Marathi", "French"]
MOVIES = ["Inception", "Spirited Away", "3 Idiots", "The Godfather", "Interstellar", "Lagaan"]
CARS = ["Honda City", "Tesla Model 3", "Maruti Swift", "Toyota Corolla", "Hyundai Creta"]
COLORS = ["red", "white", "grey", "blue"]


def topic_city(rng, v, alt):
    c, area = v
    return {"mem": f"Lives in {c}", "para": [f"Is based in {c}", f"Resides in {c}"],
            "detail": f"Lives in the {area} area of {c}",
            "change": [f"Moved to {alt[0]}", f"Now lives in {alt[0]}"],
            "contra": [("explicit_not", f"Does not live in {c}"), ("no_longer", f"No longer lives in {c}")]}


def topic_job(rng, v, alt):
    return {"mem": f"Works as {an(v)} {v}", "para": [f"Is {an(v)} {v} by profession", f"Has a job as {an(v)} {v}"],
            "detail": f"Works as {an(v)} {v} and has done so for {rng.randint(3, 15)} years",
            "change": [f"Now works as {an(alt)} {alt}", f"Changed careers and is now {an(alt)} {alt}"],
            "contra": [("no_longer", f"Is no longer {an(v)} {v}"), ("explicit_not", f"Does not work as {an(v)} {v}")]}


def topic_food(rng, v, alt):
    f, variant = v
    return {"mem": f"Loves {f}", "para": [f"Really enjoys {f}", f"Is a big fan of {f}"],
            "detail": f"Loves {f}, especially {variant}", "change": None,
            "contra": [("antonym", f"Dislikes {f}"), ("antonym", f"Hates {f}"), ("explicit_not", f"Does not like {f}")]}


def topic_sport(rng, v, alt):
    return {"mem": f"Plays {v}", "para": [f"Is {an(v)} {v} player"],
            "detail": f"Plays {v} every {rng.choice(DAYS)} with {rng.choice(PEOPLE)}", "change": None,
            "contra": [("no_longer", f"Has stopped playing {v}"), ("explicit_not", f"Does not play {v}")]}


def topic_pet(rng, v, alt):
    p, name = v
    age = rng.randint(2, 9)
    return {"mem": f"Has {an(p)} {p} named {name}", "para": [f"Owns {an(p)} {p} called {name}", f"Has a pet {p} named {name}"],
            "detail": f"Has {'an' if age == 8 else 'a'} {age}-year-old {p} named {name}",
            "change": None,
            "contra": [("no_longer", f"No longer has {an(p)} {p}"), ("explicit_not", f"Does not have {an(p)} {p}")]}


def topic_allergy(rng, v, alt):
    a, adj = v
    return {"mem": f"Is allergic to {a}", "para": [f"Has {an(adj)} {adj} allergy"],
            "detail": f"Is severely allergic to {a} and carries an adrenaline pen", "change": None,
            "contra": [("explicit_not", f"Is not allergic to {a}"), ("no_longer", f"Has outgrown their {adj} allergy")]}


def topic_lang(rng, v, alt):
    return {"mem": f"Speaks {v}", "para": [f"Can speak {v}", f"Is able to speak {v}"],
            "detail": f"Speaks {v} fluently", "change": None,
            "contra": [("explicit_not", f"Does not speak {v}"), ("explicit_not", f"Cannot speak {v}")]}


def topic_movie(rng, v, alt):
    return {"mem": f"Favourite movie is {v}", "para": [f"Likes {v} more than any other film"],
            "detail": f"Favourite movie is {v}, which they have watched {rng.randint(4, 20)} times",
            "change": [f"Favourite movie is now {alt}"], "contra": [("antonym", f"Dislikes {v}")]}


def topic_car(rng, v, alt):
    return {"mem": f"Drives {an(v)} {v}", "para": [f"Gets around in {an(v)} {v}"],
            "detail": f"Drives a {rng.choice(COLORS)} {v}",
            "change": [f"Now drives {an(alt)} {alt}", f"Sold their {v} and bought {an(alt)} {alt}"],
            "contra": [("no_longer", f"Sold their {v} and no longer has a car"), ("explicit_not", "Does not drive")]}


def topic_diet(rng, v, alt):
    if v == "vegetarian":
        return {"mem": "Is vegetarian", "para": ["Does not eat meat"], "detail": "Is vegetarian and also avoids eggs",
                "change": None, "contra": [("antonym", "Eats meat"), ("explicit_not", "Is not vegetarian")]}
    return {"mem": "Is vegan", "para": ["Avoids all animal products"], "detail": "Is vegan and avoids honey too",
            "change": None, "contra": [("antonym", "Eats dairy and eggs"), ("explicit_not", "Is not vegan")]}


def topic_siblings(rng, v, alt):
    return {"mem": f"Has {v} siblings", "para": [f"Has {v} brothers and sisters"],
            "detail": f"Has {v} siblings, all of them older", "change": None,
            "contra": [("antonym", "Is an only child")]}


TOPICS = {  # name: (builder, values, multi-valued?)
    "city": (topic_city, CITIES, False), "job": (topic_job, JOBS, False), "food": (topic_food, FOODS, True),
    "sport": (topic_sport, SPORTS, True), "pet": (topic_pet, PETS, True), "allergy": (topic_allergy, ALLERGIES, True),
    "lang": (topic_lang, LANGS, True), "movie": (topic_movie, MOVIES, False), "car": (topic_car, CARS, False),
    "diet": (topic_diet, ["vegetarian", "vegan"], False), "siblings": (topic_siblings, [2, 3, 4], False),
}


def texts_for(rng, topic):
    build, values, _ = TOPICS[topic]
    v, alt = rng.sample(values, 2)
    return build(rng, v, alt), v, alt


def make_item(rng, n, subtype, k):
    eligible = [t for t in TOPICS if subtype != "update_change" or TOPICS[t][0](rng, TOPICS[t][1][0], TOPICS[t][1][1])["change"]]
    topic = rng.choice(eligible)
    tx, v, alt = texts_for(rng, topic)
    meta = {"topic": topic}
    if subtype == "add_unrelated":
        target_text, new = None, tx["mem"]
    elif subtype == "dup_exact":
        target_text, new = tx["mem"], tx["mem"]
    elif subtype == "dup_paraphrase":
        target_text, new = tx["mem"], rng.choice(tx["para"])
        meta["para_has_negation"] = " not " in f" {new.lower()} "
    elif subtype == "weaker":
        target_text, new = tx["detail"], tx["mem"]
    elif subtype == "update_detail":
        target_text, new = tx["mem"], tx["detail"]
    elif subtype == "update_change":
        target_text, new = tx["mem"], rng.choice(tx["change"])
    else:  # delete_contra
        style, new = rng.choice(tx["contra"])
        target_text = tx["mem"]
        meta["contra_style"] = style
    mems = []
    if target_text:
        mems.append(target_text)
    near = False
    if k > len(mems) and TOPICS[topic][2] and rng.random() < 0.5:  # same-topic look-alike, different value
        build, values, _ = TOPICS[topic]
        others = [x for x in values if x not in (v,)]
        mems.append(build(rng, rng.choice(others), alt)["mem"])
        near = True
    pool = [t for t in TOPICS if t != topic]
    for t in rng.sample(pool, max(0, k - len(mems))):
        mems.append(texts_for(rng, t)[0]["mem"])
    mems = mems[:k]
    rng.shuffle(mems)
    memories = [{"id": str(i), "text": m} for i, m in enumerate(mems)]
    target = str(mems.index(target_text)) if target_text else None
    op = GOLD_OP[subtype]
    gold = [] if op == "NONE" else ([("ADD", None)] if op == "ADD" else [(op, target)])
    return {"id": n, "subtype": subtype, "k": k, "memories": memories, "new_fact": new, "gold_op": op,
            "target": target, "gold": gold, "near": near, **meta}


# ---------- prompts ----------

RULES = """MEMORY MANAGER RULES (Mem0)
A memory store holds short facts about a user. A new fact has just been extracted from the conversation. Compare it
with the existing memories and choose exactly one operation:
- ADD: the new fact is new information that none of the existing memories covers.
- UPDATE memory N: memory N is about the same thing, and the new fact has more information, or the information is
  totally different (for example it has changed). Memory N is replaced by the more informative or newer version.
- DELETE memory N: the new fact contradicts memory N.
- NONE: the new fact conveys the same information as an existing memory, or less, so nothing changes.
Examples: memory "User likes to play cricket" + new fact "Loves to play cricket with friends" -> UPDATE that memory.
Memory "Loves cheese pizza" + new fact "Dislikes cheese pizza" -> DELETE that memory. Memory "Likes cheese pizza" +
new fact "Loves cheese pizza" -> NONE. Memory "User is a software engineer" + new fact "Name is John" -> ADD."""


def state_text(it):
    mem_lines = "\n".join(f"Memory {m['id']}: {m['text']}" for m in it["memories"])
    return f"{RULES}\n\nEXISTING MEMORIES\n{mem_lines}\n\nNEW FACT\n{it['new_fact']}"


def flat_options(it):
    opts = {"add": "ADD the new fact as a new memory"}
    for m in it["memories"]:
        opts[f"update_{m['id']}"] = f"UPDATE memory {m['id']} (“{m['text']}”)"
        opts[f"delete_{m['id']}"] = f"DELETE memory {m['id']} (“{m['text']}”)"
    opts["none"] = "NONE: make no change"
    return opts


def opt_to_changes(key):
    if key == "add":
        return [("ADD", None)]
    if key == "none":
        return []
    op, i = key.split("_")
    return [(op.upper(), i)]


REL = {"unrelated": "It is about something else", "same": "It says the same thing as the memory, or less",
       "more": "It is about the same thing and adds information or changes it",
       "contradicts": "It contradicts the memory"}


def build_calls(items):
    jev, llm = [], []
    for it in items:
        meta = {"item": it["id"], "subtype": it["subtype"], "k": it["k"]}
        jev.append({"call_id": f"{it['id']}-jev_flat", "state": state_text(it),
                    "questions": {"OP": {"type": "choice", "instructions": "Which memory operation should be applied for the new fact?",
                                         "criteria": flat_options(it)}},
                    "meta": {**meta, "system": "jev_flat"}})
        mem_lines = "\n".join(f"Memory {m['id']}: {m['text']}" for m in it["memories"])
        jev.append({"call_id": f"{it['id']}-jev_flat_m0",
                    "state": f"{DEFAULT_UPDATE_MEMORY_PROMPT}\n\nEXISTING MEMORIES\n{mem_lines}\n\nNEW FACT\n{it['new_fact']}",
                    "questions": {"OP": {"type": "choice", "instructions": "Which memory operation should be applied for the new fact?",
                                         "criteria": flat_options(it)}},
                    "meta": {**meta, "system": "jev_flat_m0"}})
        jev.append({"call_id": f"{it['id']}-jev_decomp", "state": state_text(it),
                    "questions": {f"R{m['id']}": {"type": "choice", "criteria": REL,
                                                  "instructions": f"How does the new fact relate to memory {m['id']} (“{m['text']}”)?"}
                                  for m in it["memories"]},
                    "meta": {**meta, "system": "jev_decomp"}})
        for model in MEM0_MODELS:
            prompt = get_update_memory_messages(it["memories"], [it["new_fact"]])
            llm.append({"call_id": f"{it['id']}-mem0:{model}", "meta": {**meta, "system": f"mem0:{model}"},
                        "request": {"model": model, "messages": [{"role": "user", "content": prompt}],
                                    "response_format": {"type": "json_object"}, "max_tokens": 1500}})
        for model in TYPED_MODELS:
            keys = list(flat_options(it))
            lines = "\n".join(f"{LETTERS[i]}. {flat_options(it)[k_]}" for i, k_ in enumerate(keys))
            prompt = (f"{state_text(it)}\n\nWhich memory operation should be applied for the new fact?\nOptions:\n{lines}\n\n"
                      f"Reply with the letter of the correct option only.")
            llm.append({"call_id": f"{it['id']}-typed:{model}", "meta": {**meta, "system": f"typed:{model}", "keys": keys},
                        "request": {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1,
                                    "logprobs": True, "top_logprobs": 20}})
    return jev, llm


# ---------- parsing ----------

def parse_mem0(text, ids):
    """Changes as Mem0's code reads them: explicit ADD/UPDATE/DELETE events; NONE ignored."""
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict) or not isinstance(data.get("memory"), list):
        return None
    out = set()
    for e in data["memory"]:
        if not isinstance(e, dict):
            continue
        ev = str(e.get("event", "")).upper()
        if ev == "ADD":
            out.add(("ADD", None))
        elif ev in ("UPDATE", "DELETE"):
            i = str(e.get("id"))
            out.add((ev, i) if i in ids else (ev, "invalid"))
    return out


def decide_decomp(ans, ids):
    rel = {i: ans[f"R{i}"] for i in ids}
    best = lambda lab: max((i for i in ids if rel[i]["choice"] == lab),  # noqa: E731
                           key=lambda i: float(rel[i]["probabilities"].get(lab, 0)), default=None)
    for lab, change in (("contradicts", "DELETE"), ("more", "UPDATE")):
        i = best(lab)
        if i is not None:
            return {(change, i)}, float(rel[i]["probabilities"][lab])
    if best("same") is not None:
        return set(), float(rel[best("same")]["probabilities"]["same"])
    return {("ADD", None)}, min(float(rel[i]["probabilities"]["unrelated"]) for i in ids)


def score(it, pred):
    gold = {tuple(g) for g in it["gold"]}
    if pred is None:
        return False, False
    strict = pred == gold
    lenient = strict
    if not strict and it["gold_op"] in ("UPDATE", "DELETE"):
        lenient = pred == {("DELETE", it["target"]), ("ADD", None)}
    if not strict and it["subtype"] in ("dup_exact", "dup_paraphrase"):
        lenient = pred == {("UPDATE", it["target"])}
    return strict, lenient


def op_label(pred):
    if pred is None:
        return "PARSE_ERROR"
    if not pred:
        return "NONE"
    if len(pred) > 1:
        return "MULTI"
    (op, i), = pred
    return "INVALID_ID" if i == "invalid" else op


def main():
    rng = random.Random(1616)
    items = []
    for st in SUBTYPES:
        for k in KS:
            for _ in range(PER_CELL):
                items.append(make_item(rng, len(items), st, k))
    pilot = int(__import__("os").environ.get("E16_PILOT", "0"))
    if pilot:  # a few items per subtype; their calls are reused by the full run (same call ids)
        items = [it for st in SUBTYPES for it in [x for x in items if x["subtype"] == st][:pilot]]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "dataset.jsonl").open("w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    jev_calls, llm_calls = build_calls(items)
    log_event(EXP, f"starting: {len(items)} decisions; {len(jev_calls)} Jev calls + {len(llm_calls)} LLM calls")
    resp = run_jev(EXP, [dict(c) for c in jev_calls], workers=16)
    resp.update(run_llm(EXP, [dict(c) for c in llm_calls], workers=12))

    systems = ["jev_flat", "jev_flat_m0", "jev_decomp"] + [f"typed:{m}" for m in TYPED_MODELS] + [f"mem0:{m}" for m in MEM0_MODELS]
    calls_by_id = {c["call_id"]: c for c in jev_calls + llm_calls}
    recs = []
    with (OUT / "answers.jsonl").open("w") as f:
        for it in items:
            ids = [m["id"] for m in it["memories"]]
            for sysname in systems:
                cid = f"{it['id']}-{sysname}"
                r = resp.get(cid)
                rec = {"item": it["id"], "system": sysname, "subtype": it["subtype"], "k": it["k"], "near": it["near"],
                       "contra_style": it.get("contra_style"), "topic": it["topic"], "conf": None}
                if r is None:
                    rec.update(pred=None, missing=True)
                elif sysname in ("jev_flat", "jev_flat_m0"):
                    a = r["answers"]["OP"]
                    rec.update(pred=set(opt_to_changes(a["choice"])), conf=float(a["confidence"]))
                elif sysname == "jev_decomp":
                    pred, conf = decide_decomp(r["answers"], ids)
                    rec.update(pred=pred, conf=conf)
                elif sysname.startswith("typed:"):
                    keys = calls_by_id[cid]["meta"]["keys"]
                    lp = first_token_logprobs(r)
                    probs = defaultdict(float)
                    for tok, l in lp.items():
                        t = tok.strip().upper()
                        if len(t) == 1 and t in LETTERS[:len(keys)]:
                            probs[t] += 2.718281828 ** l
                    if probs:
                        z = sum(probs.values())
                        letter = max(probs, key=probs.get)
                        rec["conf"] = probs[letter] / z
                    else:
                        letter = content(r).strip()[:1].upper()
                    rec["pred"] = set(opt_to_changes(keys[LETTERS.index(letter)])) if letter in LETTERS[:len(keys)] else None
                else:
                    rec["pred"] = parse_mem0(content(r), ids)
                rec["strict"], rec["lenient"] = score(it, rec["pred"])
                rec["op"] = op_label(rec["pred"])
                rec["latency_ms"] = (r or {}).get("latency_ms")
                cost_entry = calls_by_id[cid]
                rec["usage"] = (r or {}).get("usage")
                recs.append(rec)
                f.write(json.dumps({**rec, "pred": sorted(map(list, rec["pred"]), key=str) if rec["pred"] is not None else None},
                                   default=str) + "\n")

    # costs from the call log
    cost = defaultdict(float)
    for line in (ROOT / "logs" / EXP / "calls.jsonl").open():
        e = json.loads(line)
        if e["error"] is None:
            cost[e["call_id"].split("-", 1)[1]] += e.get("cost_usd") or 0

    def pctl(xs, q):
        xs = sorted(x for x in xs if x is not None)
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")

    N = len(items)
    summary = {"n_items": N, "systems": {}}
    rows = []
    for s in systems:
        rs = [r for r in recs if r["system"] == s]
        k_s, k_l = sum(r["strict"] for r in rs), sum(r["lenient"] for r in rs)
        lat = [r["latency_ms"] for r in rs]
        st = {"strict": k_s / N, "lenient": k_l / N, "parse_errors": sum(r["op"] == "PARSE_ERROR" for r in rs),
              "invalid": sum(r["op"] in ("INVALID_ID", "MULTI") for r in rs),
              "p50_ms": pctl(lat, 0.5), "p95_ms": pctl(lat, 0.95), "usd_per_1k": cost[s] / N * 1000, "usd_total": cost[s]}
        summary["systems"][s] = st
        rows.append([s, ci(k_s, N), ci(k_l, N), st["parse_errors"], st["invalid"], f"{st['p50_ms']:.0f}", f"{st['p95_ms']:.0f}",
                     f"${st['usd_per_1k']:.3f}"])

    sub_rows = []
    for st_ in SUBTYPES:
        row = [f"{st_} → {GOLD_OP[st_]}"]
        for s in systems:
            rs = [r for r in recs if r["system"] == s and r["subtype"] == st_]
            v = mean(r["strict"] for r in rs)
            row.append(pct(v))
            summary["systems"][s].setdefault("by_subtype", {})[st_] = v
        sub_rows.append(row)
    k_rows = []
    for k in KS:
        row = [k]
        for s in systems:
            v = mean(r["strict"] for r in recs if r["system"] == s and r["k"] == k)
            row.append(pct(v))
            summary["systems"][s].setdefault("by_k", {})[k] = v
        k_rows.append(row)
    style_rows = []
    for style in ["antonym", "explicit_not", "no_longer"]:
        row = [style]
        for s in systems:
            rs = [r for r in recs if r["system"] == s and r["contra_style"] == style]
            row.append(f"{pct(mean(r['strict'] for r in rs))} (n={len(rs)})")
        style_rows.append(row)
    near_rows = []
    for nv in (False, True):
        row = ["with a same-topic look-alike" if nv else "no look-alike (multi-valued topics, K>1)"]
        for s in systems:
            rs = [r for r in recs if r["system"] == s and r["near"] == nv and TOPICS[r["topic"]][2] and r["k"] > 1
                  and r["subtype"] != "add_unrelated"]
            row.append(f"{pct(mean(r['strict'] for r in rs))} (n={len(rs)})")
        near_rows.append(row)
    conf_rows = []
    for s in systems:
        c = Counter((GOLD_OP[r["subtype"]], r["op"]) for r in recs if r["system"] == s)
        summary["systems"][s]["confusion"] = {f"{g}->{p}": n for (g, p), n in c.items()}
        for g in ["ADD", "UPDATE", "DELETE", "NONE"]:
            tot = sum(n for (gg, _), n in c.items() if gg == g)
            conf_rows.append([s, g] + [pct(c[(g, p)] / tot) if tot else "—" for p in
                                       ["ADD", "UPDATE", "DELETE", "NONE", "MULTI", "INVALID_ID", "PARSE_ERROR"]])

    # cascade: Jev first, low-confidence decisions go to GPT-4o-mini run as Mem0 runs it
    ref = f"mem0:{MEM0_MODELS[-1]}"
    by_item = {(r["item"], r["system"]): r for r in recs}
    casc_rows = []
    for src in ["jev_flat", f"typed:{TYPED_MODELS[0]}", f"typed:{TYPED_MODELS[1]}"]:
        for tau in [0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.01]:
            ok, sent = 0, 0
            for it in items:
                a = by_item[(it["id"], src)]
                if a["conf"] is not None and a["conf"] >= tau:
                    ok += a["strict"]
                else:
                    sent += 1
                    ok += by_item[(it["id"], ref)]["strict"]
            casc_rows.append([src, "never" if tau == 0 else ("always" if tau > 1 else f"conf < {tau}"), pct(sent / N), pct(ok / N)])
            summary.setdefault("cascade", {}).setdefault(src, {})[str(tau)] = {"sent": sent / N, "strict": ok / N}
    cal_rows = []
    for s in ["jev_flat", "jev_flat_m0", "jev_decomp"] + [f"typed:{m}" for m in TYPED_MODELS]:
        for lo, hi in [(0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 0.97), (0.97, 1.01)]:
            rs = [r for r in recs if r["system"] == s and r["conf"] is not None and lo <= r["conf"] < hi]
            if rs:
                cal_rows.append([s, f"{lo:.2f}–{min(hi, 1):.2f}", len(rs), pct(mean(r["strict"] for r in rs))])

    sysnames = [s.replace("meta-llama/", "").replace("qwen/", "").replace("openai/", "") for s in systems]
    md = (f"# E16 — Delegating Mem0's memory-write decision (ADD / UPDATE / DELETE / NONE)\n\n{__doc__.strip()}\n\n"
          "### Overall\n\n" + table(["decider", "strict accuracy [95% CI]", "lenient accuracy [95% CI]", "unparseable",
                                     "invalid / multiple changes", "p50 ms", "p95 ms", "$ per 1,000 decisions"], rows)
          + "\n\n### Strict accuracy by case type\n\n" + table(["case → gold"] + sysnames, sub_rows)
          + "\n\n### Strict accuracy by number of existing memories (K)\n\n" + table(["K"] + sysnames, k_rows)
          + "\n\n### Contradictions (gold DELETE) by wording\n\n" + table(["wording"] + sysnames, style_rows)
          + "\n\n### Same-topic look-alike memories (multi-valued topics, K > 1, excluding ADD cases)\n\n"
          + table(["setting"] + sysnames, near_rows)
          + "\n\n### What each decider did, by gold operation (row shares)\n\n"
          + table(["decider", "gold", "→ ADD", "→ UPDATE", "→ DELETE", "→ NONE", "→ several", "→ bad id", "→ unparseable"], conf_rows)
          + f"\n\n### Cascade: confident decisions kept, the rest sent to {ref.split(':')[1]} (Mem0 prompt)\n\n"
          + table(["first decider", "sent to the LLM when", "share sent", "strict accuracy"], casc_rows)
          + "\n\n### Confidence vs accuracy\n\n" + table(["decider", "confidence", "n", "strict accuracy"], cal_rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
