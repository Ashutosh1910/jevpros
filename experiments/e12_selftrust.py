"""E12 - Does Jev trust itself correctly? (metacognition / self-assessment)

For every item, two SEPARATE calls on the same state (E05 showed questions don't prime each other
within a call, but separate calls remove any doubt):
  meta call    M_CAN   noul  "Using only the information given, this question can be answered with certainty: <question>"
               M_LEVEL score "How well can this question be answered from the information given?"
                             [cannot be determined | only a guess | probably, with some doubt | with certainty]
  answer call  the question itself (noul / choice / score)

"Answered confidently" means: noul -> max(p, 1-p); choice/score -> the returned `confidence`.
Items span 16 families, from one-line numeric checks to 255-option choices and ~20k-token states, and
include UNDETERMINABLE items (truth = None) where the right self-assessment is "can't answer".

Outputs (for later analysis at any threshold - see e12_analyze.py):
  data/e12_selftrust/dataset.jsonl   one line per item: id, family, size, state, question, meta questions, truth
  data/e12_selftrust/answers.jsonl   one line per item: raw meta + answer responses and derived fields
  logs/e12_selftrust/calls.jsonl     every API call in full
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from bench.common import ROOT, log_event, run_jev  # noqa: E402
from bench.scenarios import (DOMAINS, atom_q, build_case, default_names, full_questions, joint_q,  # noqa: E402
                             joint_truth, outcome_if, render)
from e01_numbers_negation import b1, b2, b3  # noqa: E402
from e04_injection import injections  # noqa: E402
from e06_options import t1, t2  # noqa: E402
from e07_context import decoy_rules  # noqa: E402

EXP = "e12_selftrust"
OUT = ROOT / "data" / EXP
DOMS = list(DOMAINS)
UNDET = None  # truth value for undeterminable items

LEVELS = ["It cannot be determined from the information given",
          "Only a guess is possible from the information given",
          "It can probably be answered, with some doubt remaining",
          "It can be answered with certainty"]

GENERAL_TRUE = [
    "Water boils at 100 degrees Celsius at sea level.", "Paris is the capital of France.",
    "A week has seven days.", "The Pacific is the largest ocean on Earth.", "Humans have 23 pairs of chromosomes.",
    "The chemical symbol for gold is Au.", "Mount Everest is the highest mountain above sea level.",
    "A triangle has three sides.", "The Earth orbits the Sun.", "There are 60 minutes in an hour.",
    "Light travels faster than sound.", "The square root of 81 is 9.", "Japan is an island country.",
    "Spiders have eight legs.", "The Nile flows into the Mediterranean Sea.", "Oxygen is a chemical element.",
    "A leap year has 366 days.", "Shakespeare wrote Hamlet.", "The heart pumps blood.", "Ice is less dense than liquid water.",
    "Canberra is the capital of Australia.", "Seven is a prime number.", "The Moon orbits the Earth.",
    "Penguins are birds.", "Diamond is a form of carbon.", "The Amazon is a rainforest in South America.",
    "One kilometre is 1000 metres.", "Bats are mammals.", "Venus is a planet in the Solar System.",
    "The Sahara is a desert.",
]
GENERAL_FALSE = [
    "Water boils at 50 degrees Celsius at sea level.", "Berlin is the capital of France.", "A week has nine days.",
    "The Atlantic is the largest ocean on Earth.", "Humans have 30 pairs of chromosomes.",
    "The chemical symbol for gold is Gd.", "Mount Kilimanjaro is the highest mountain above sea level.",
    "A triangle has five sides.", "The Sun orbits the Earth.", "There are 100 minutes in an hour.",
    "Sound travels faster than light.", "The square root of 81 is 7.", "Switzerland has a sea coast.",
    "Spiders have six legs.", "The Nile flows into the Pacific Ocean.", "Steel is a chemical element.",
    "A leap year has 364 days.", "Charles Dickens wrote Hamlet.", "The liver pumps blood.",
    "Ice is denser than liquid water.", "Sydney is the capital of Australia.", "Nine is a prime number.",
    "The Earth orbits the Moon.", "Penguins are mammals.", "Diamond is a form of iron.",
    "The Amazon is a desert in Africa.", "One kilometre is 100 metres.", "Bats are birds.",
    "Pluto is the largest planet in the Solar System.", "The Sahara is an ocean.",
]
PERSONAL_UNKNOWABLE = [
    "{n} was born on a Tuesday.", "{n}'s favourite colour is green.", "{n} owns a bicycle.",
    "{n} has visited Canada.", "{n} speaks Portuguese.", "{n} has two siblings.", "{n} prefers tea to coffee.",
    "{n} was late to work last Monday.",
]


def question_text(q):
    """Human-readable rendering of a question for the meta call."""
    if q["type"] == "noul":
        return f"Is this statement true or false? \"{q['instructions']}\""
    if q["type"] == "choice":
        return f"{q['instructions']} Options: " + "; ".join(q["criteria"].values())
    return f"{q['instructions']} Scale: " + " / ".join(q["criteria"])


def meta_questions(q):
    qt = question_text(q)
    return {
        "M_CAN": {"type": "noul", "instructions":
                  f"Using only the information given, the following question can be answered with certainty. "
                  f"Question: {qt}"},
        "M_LEVEL": {"type": "score", "instructions":
                    f"How well can the following question be answered using only the information given? "
                    f"Question: {qt}", "criteria": LEVELS},
    }


def item(iid, family, size, state, q, truth, **meta):
    return {"id": iid, "family": family, "size": size, "qtype": q["type"], "state": state, "question": q,
            "truth": truth, "determinable": truth is not UNDET, "meta_questions": meta_questions(q), "info": meta}


def build(rng):
    items = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"i{n:05d}"

    # F1 policy atoms, depth 1-10, random polarity
    for k in range(800):
        depth = 1 + k % 10
        case = build_case(rng, DOMS[k % 4], 2, depth)
        neg = rng.random() < 0.5
        items.append(item(nid(), "policy_atom", "medium", render(case), atom_q(case, 0, negative=neg),
                          case["items"][0]["truth"] != neg, depth=depth))
    # F2 policy joint 4-way choice
    for k in range(300):
        case = build_case(rng, DOMS[k % 4], 2, 1 + k % 6)
        items.append(item(nid(), "policy_joint_choice", "medium", render(case), joint_q(case), joint_truth(case),
                          depth=case["depth"]))
    # F3 full-outcome subset choice (8 / 16 options) and F4 count score
    for k in range(600):
        case = build_case(rng, DOMS[k % 4], 3 + k % 2, 1 + k % 4)
        q, t = full_questions(case, rng)
        key = "SUB" if k < 300 else "CNT"
        items.append(item(nid(), "policy_subset_choice" if key == "SUB" else "policy_count_score", "medium",
                          render(case), q[key], t[key], depth=case["depth"], k=case["k"]))
    # F5/F6/F7 missing facts and missing rules (determinable and not)
    made = {"decisive_missing": 0, "irrelevant_missing": 0, "no_rule": 0}
    while min(made.values()) < 200 or made["decisive_missing"] < 300:
        case = build_case(rng, DOMS[sum(made.values()) % 4], 2, 2 + rng.randrange(3), decoy=False)
        it = case["items"][0]
        keys = [c["attr"]["key"] for c in it["chain"]]
        dec = [x for x in keys if outcome_if(case, 0, x, True) != outcome_if(case, 0, x, False)]
        irr = [x for x in it["values"] if x not in keys]
        if dec and made["decisive_missing"] < 300:
            items.append(item(nid(), "policy_decisive_fact_missing", "medium", render(case, omit={0: {rng.choice(dec)}}),
                              atom_q(case, 0), UNDET, depth=case["depth"]))
            made["decisive_missing"] += 1
        if irr and made["irrelevant_missing"] < 200:
            items.append(item(nid(), "policy_irrelevant_fact_missing", "medium", render(case, omit={0: {rng.choice(irr)}}),
                              atom_q(case, 0), it["truth"], depth=case["depth"]))
            made["irrelevant_missing"] += 1
        if made["no_rule"] < 200:
            nr = dict(case, items=[dict(it, cat=case["absent_cat"])] + case["items"][1:])
            items.append(item(nid(), "policy_no_rule", "medium", render(nr), atom_q(nr, 0), UNDET, depth=case["depth"]))
            made["no_rule"] += 1
    # F8 question about a fact that is not in the state
    for k in range(200):
        case = build_case(rng, DOMS[k % 4], 2, 1 + k % 4)
        d = DOMAINS[case["domain"]]
        it = case["items"][0]
        attr = rng.choice([a for a in d["attrs"] if a["key"] not in it["values"]])
        from bench.scenarios import _fmt
        from gen_dataset import random_value
        stmt = f"{default_names(case)[0]}'s {attr['label']} is {_fmt(attr, random_value(rng, attr), False)}."
        items.append(item(nid(), "fact_not_in_state", "medium", render(case), {"type": "noul", "instructions": stmt},
                          UNDET, depth=case["depth"]))
    # F9 numeric, F10 dates, F11 negation stacks (small states)
    for c in rng.sample(b1(rng), 300):
        items.append(item(nid(), "numeric_compare", "small", c["state"], c["questions"]["q"], c["meta"]["truth"],
                          relation=c["meta"]["relation"]))
    for c in b2(rng):
        items.append(item(nid(), "date_compare", "small", c["state"], c["questions"]["q"], c["meta"]["truth"],
                          relation=c["meta"]["relation"]))
    for c in b3():
        items.append(item(nid(), "negation_stack", "small", c["state"], c["questions"]["q"], c["meta"]["truth"],
                          negations=c["meta"]["negations"]))
    # F12 roster search with many options, F13 pure lookup
    for nopt in [8, 32, 128, 255]:
        for k in range(40):
            c = t2(rng, nopt, k)
            items.append(item(nid(), "roster_search_choice", "huge" if nopt >= 128 else "large", c["state"],
                              c["questions"]["q"], c["meta"]["truth"], options=nopt))
    for nopt in [16, 255]:
        for k in range(30):
            c = t1(rng, nopt, k)
            items.append(item(nid(), "lookup_choice", "small" if nopt == 16 else "large", c["state"],
                              c["questions"]["q"], c["meta"]["truth"], options=nopt))
    # F14 long context (relevant rules buried in decoy rules)
    for k in range(150):
        case = build_case(rng, DOMS[k % 4], 2, 2, decoy=False)
        size = 8000 if k % 2 else 20000
        state = render(case, filler=decoy_rules(rng, case["domain"], size * 4), filler_position=rng.choice(["start", "end"]))
        items.append(item(nid(), "long_context_atom", "huge", state, atom_q(case, 0), case["items"][0]["truth"],
                          filler_tokens=size))
    # F15 fake-authority injection (known failure mode from E04)
    for k in range(150):
        case = build_case(rng, DOMS[k % 4], 2, 2 + k % 2)
        notes, _ = injections(case)["authority"]
        items.append(item(nid(), "authority_injection", "medium", render(case, case_notes=notes), atom_q(case, 0),
                          case["items"][0]["truth"]))
    # F16 general knowledge (no state) and personal facts nobody could know
    for s in GENERAL_TRUE + GENERAL_FALSE:
        items.append(item(nid(), "general_knowledge", "small", "No additional information is provided.",
                          {"type": "noul", "instructions": s}, s in GENERAL_TRUE))
    for k in range(40):
        who = f"Visitor {rng.randint(1, 99)}"
        state = (f"Visitor log\n{who}: arrived 09:{rng.randint(10, 59)}, badge issued, host: Facilities, "
                 f"purpose: {rng.choice(['meeting', 'delivery', 'interview', 'maintenance'])}.")
        items.append(item(nid(), "personal_unknowable", "small", state,
                          {"type": "noul", "instructions": rng.choice(PERSONAL_UNKNOWABLE).format(n=who)}, UNDET))
    return items


def derive(it, meta_resp, ans_resp):
    m, a = meta_resp["answers"], ans_resp["answers"]["Q"]
    lv = {int(k): float(v) for k, v in m["M_LEVEL"]["probabilities"].items()}
    rec = {"id": it["id"], "family": it["family"], "size": it["size"], "qtype": it["qtype"],
           "determinable": it["determinable"], "truth": it["truth"],
           "p_can": m["M_CAN"]["noul"], "level_score": m["M_LEVEL"]["score"], "level_argmax": max(lv, key=lv.get),
           "level_probs": lv, "level_conf": m["M_LEVEL"]["confidence"]}
    if a["type"] == "noul":
        p = a["noul"]
        rec.update(answer=p > 0.5, p_yes=p, answer_conf=max(p, 1 - p))
        rec["correct"] = None if not it["determinable"] else (p > 0.5) == it["truth"]
    elif a["type"] == "choice":
        probs = {k: float(v) for k, v in a["probabilities"].items()}
        rec.update(answer=a["choice"], answer_conf=a["confidence"], answer_maxprob=max(probs.values()))
        rec["correct"] = None if not it["determinable"] else a["choice"] == it["truth"]
    else:
        probs = {int(k): float(v) for k, v in a["probabilities"].items()}
        pick = max(probs, key=probs.get)
        rec.update(answer=pick, answer_conf=a["confidence"], answer_maxprob=max(probs.values()), score=a["score"])
        rec["correct"] = None if not it["determinable"] else pick == it["truth"]
    rec["meta_latency_ms"], rec["answer_latency_ms"] = meta_resp["latency_ms"], ans_resp["latency_ms"]
    rec["cost_usd"] = (meta_resp["usage"].get("cost") or 0) + (ans_resp["usage"].get("cost") or 0)
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ds_path = OUT / "dataset.jsonl"
    if ds_path.exists():  # keep the stored dataset fixed across re-runs
        items = [json.loads(line) for line in ds_path.open()]
    else:
        items = build(random.Random(1212))
        with ds_path.open("w") as f:
            for it in items:
                f.write(json.dumps(it) + "\n")
    est = sum(len(it["state"]) for it in items) * 2 / 4
    log_event(EXP, f"dataset: {len(items)} items, {2 * len(items)} calls, ~{est / 1e6:.1f}M input tokens (est.)")
    calls = []
    for it in items:
        calls.append({"call_id": f"{it['id']}-meta", "state": it["state"], "questions": it["meta_questions"],
                      "meta": {"id": it["id"], "family": it["family"], "call": "meta"}})
        calls.append({"call_id": f"{it['id']}-ans", "state": it["state"], "questions": {"Q": it["question"]},
                      "meta": {"id": it["id"], "family": it["family"], "call": "answer"}})
    resp = run_jev(EXP, calls, workers=10)
    with (OUT / "answers.jsonl").open("w") as f:
        for it in items:
            mr, ar = resp.get(f"{it['id']}-meta"), resp.get(f"{it['id']}-ans")
            if mr and ar:
                f.write(json.dumps(derive(it, mr, ar)) + "\n")
    log_event(EXP, f"wrote {OUT / 'answers.jsonl'}")


if __name__ == "__main__":
    main()
