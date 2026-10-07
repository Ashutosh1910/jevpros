"""Nested-exception policy cases that can be re-rendered under controlled variations.

build_case() samples the logical content (rules, facts, truth). render() turns a case into the
state text; its options change only the surface form (names, ordering, wording, units), or add
controlled content (omitted facts, injected text, filler), so experiments can compare Jev's
answers on the same logical case under different renderings.
"""

import itertools

from gen_dataset import DOMAINS, FOLLOW, evaluate, make_cond, random_value, run_chain, value_for

FIRST = "Exception: if {c}, it is {v} instead."
# Paraphrases used when render(synonyms=True); FOLLOW_ALT[i] means the same as FOLLOW[i].
FIRST_ALT = "One exception: when {c}, the outcome becomes {v}."
FOLLOW_ALT = [
    "Within that exception, when {c}, the outcome becomes {v}.",
    "Still, when {c} as well, the outcome becomes {v}.",
    "And if on top of that {c}, the outcome becomes {v}.",
    "Overriding the previous clause: when {c}, the outcome becomes {v}.",
]
TITLE_ALT = {"expense": "REIMBURSEMENT RULES FOR BUSINESS EXPENSES",
             "access": "RULES FOR ENTERING RESTRICTED AREAS",
             "insurance": "CLAIM COVERAGE RULES FOR HOME POLICIES",
             "library": "BORROWING RULES OF THE UNIVERSITY LIBRARY"}
UNIT_ALT = {"${x}": "{x} USD", "{x} days": "{x} calendar days", "level {x}": "clearance {x}",
            "{x}:00": "{x}h00", "{x} years": "{x} yrs", "{x} months": "{x} mo"}


def build_case(rng, domain, k, depth, decoy=None):
    d = DOMAINS[domain]
    cats = rng.sample(d["categories"], k + 1)
    items, rules = [], []
    for i in range(k):
        chain = [make_cond(rng, a) for a in rng.sample(d["attrs"], depth)]
        default = rng.random() < 0.5
        stop = rng.randint(0, depth)
        values = {}
        for j, cond in enumerate(chain):
            want = j < stop if j <= stop else rng.random() < 0.5
            values[cond["attr"]["key"]] = value_for(rng, cond, want)
        rest = [a for a in d["attrs"] if a["key"] not in values]
        for a in rng.sample(rest, min(len(rest), rng.randint(1, 2))):
            values[a["key"]] = random_value(rng, a)
        truth, applied = run_chain(chain, default, values)
        assert applied == stop
        items.append({"cat": cats[i], "chain": chain, "default": default, "values": values,
                      "truth": truth, "stop": stop})
        rules.append({"cat": cats[i], "chain": chain, "default": default})
    if decoy if decoy is not None else rng.random() < 0.5:
        rules.append({"cat": cats[k], "chain": [make_cond(rng, a) for a in rng.sample(d["attrs"], depth)],
                      "default": rng.random() < 0.5})
    rng.shuffle(rules)
    for r in rules:
        r["follow_idx"] = [rng.randrange(len(FOLLOW)) for _ in r["chain"][1:]]
    fact_order = [rng.sample(list(it["values"]), len(it["values"])) for it in items]
    return {"domain": domain, "k": k, "depth": depth, "items": items, "rules": rules,
            "fact_order": fact_order, "absent_cat": cats[k]}


def default_names(case):
    return [f"{DOMAINS[case['domain']]['noun']} {i + 1}" for i in range(case["k"])]


def _fmt(attr, x, alt_units):
    if attr["kind"] == "num":
        f = UNIT_ALT.get(attr["fmt"], attr["fmt"]) if alt_units else attr["fmt"]
        return f.format(x=x)
    if attr["kind"] == "bool":
        return "yes" if x else "no"
    return x


def _cond_text(cond, alt_units):
    attr, op, t = cond["attr"], cond["op"], cond["t"]
    if attr["kind"] == "cat":
        return attr[op].format(v=t)
    if attr["kind"] == "bool":
        return attr["true" if t else "false"]
    return attr[op].format(t=_fmt(attr, t, alt_units))


def render(case, names=None, rule_order=None, fact_orders=None, synonyms=False, alt_units=False,
           omit=None, case_notes=None, filler=None, filler_position="end", item_values=None):
    """Return the state text.
    omit: {item_idx: set(attr keys)} facts to leave out.
    case_notes: extra lines appended to the CASE section (e.g. injected comments).
    filler: text inserted among the rules at filler_position ("start" | "middle" | "end").
    item_values: {item_idx: values dict} to override facts (counterfactual renders)."""
    d = DOMAINS[case["domain"]]
    yes, no = d["yes"], d["no"]
    names = names or default_names(case)
    word = lambda b: yes if b else no  # noqa: E731
    title = TITLE_ALT[case["domain"]] if synonyms else d["title"]
    header = (f"Each {d['noun'].lower()} is decided by the rule for its category. Within a rule, every "
              f"exception clause is only considered if the clause immediately before it applied; when an "
              f"exception applies, its decision replaces the previous one.")
    if synonyms:
        header = (f"The rule matching a {d['noun'].lower()}'s category decides it. A clause inside a rule is "
                  f"checked only when the clause right before it was triggered, and a triggered clause "
                  f"overrides the earlier outcome.")
    rules = [case["rules"][i] for i in (rule_order or range(len(case["rules"])))]
    rule_lines = []
    for n, r in enumerate(rules, 1):
        base = (f"Rule {n} ({r['cat']}): the baseline outcome for {r['cat']} items is {word(r['default'])}."
                if synonyms else f"Rule {n} ({r['cat']}): {r['cat']} items are {word(r['default'])} by default.")
        parts, dec = [base], r["default"]
        for j, cond in enumerate(r["chain"]):
            dec = not dec
            if j == 0:
                tmpl = FIRST_ALT if synonyms else FIRST
            else:
                idx = r["follow_idx"][j - 1]
                tmpl = FOLLOW_ALT[idx] if synonyms else FOLLOW[idx]
            parts.append(tmpl.format(c=_cond_text(cond, alt_units), v=word(dec)))
        rule_lines.append(" ".join(parts))
    if filler:
        pos = {"start": 0, "middle": len(rule_lines) // 2, "end": len(rule_lines)}[filler_position]
        rule_lines = rule_lines[:pos] + [filler] + rule_lines[pos:]
    lines = [title, header, ""] + rule_lines + ["", "CASE"]
    attr_by_key = {a["key"]: a for a in d["attrs"]}
    for i, (name, it) in enumerate(zip(names, case["items"])):
        values = (item_values or {}).get(i, it["values"])
        order = (fact_orders or case["fact_order"])[i]
        skip = (omit or {}).get(i, set())
        facts = "; ".join(f"{attr_by_key[k]['label']}: {_fmt(attr_by_key[k], values[k], alt_units)}"
                          for k in order if k not in skip)
        lines.append(f"- {name} (category: {it['cat']}) - {facts}.")
    lines += case_notes or []
    return "\n".join(lines)


# ---------- questions ----------

def atom_q(case, i, names=None, negative=False):
    d = DOMAINS[case["domain"]]
    names = names or default_names(case)
    w = d["no"] if negative else d["yes"]
    return {"type": "noul", "instructions": f"Under the policy, {names[i]} ({case['items'][i]['cat']}) is {w}."}


def joint_q(case, names=None, reverse=False):
    d = DOMAINS[case["domain"]]
    names = names or default_names(case)
    yes, no = d["yes"], d["no"]
    l0, l1 = (f"{names[i]} ({case['items'][i]['cat']})" for i in (0, 1))
    crit = {"both": f"Both {l0} and {l1} are {yes}", "only_first": f"{l0} is {yes}, {l1} is {no}",
            "only_second": f"{l0} is {no}, {l1} is {yes}", "neither": f"Neither {l0} nor {l1} is {yes}"}
    if reverse:
        crit = dict(reversed(list(crit.items())))
    return {"type": "choice", "instructions": f"What are the outcomes for {names[0]} and {names[1]}?",
            "criteria": crit}


def joint_truth(case):
    a, b = case["items"][0]["truth"], case["items"][1]["truth"]
    return {(1, 1): "both", (1, 0): "only_first", (0, 1): "only_second", (0, 0): "neither"}[(a, b)]


def full_questions(case, rng, names=None):
    """The same 13-17 question set used in the main dataset. Returns (questions, truth)."""
    d = DOMAINS[case["domain"]]
    yes, no = d["yes"], d["no"]
    names = names or default_names(case)
    k = case["k"]
    A = [it["truth"] for it in case["items"]]
    label = [f"{n} ({it['cat']})" for n, it in zip(names, case["items"])]
    word = lambda b: yes if b else no  # noqa: E731
    q, t = {}, {}
    for i in range(k):
        q[f"A{i}"], t[f"A{i}"] = atom_q(case, i, names), A[i]
        q[f"N{i}"], t[f"N{i}"] = atom_q(case, i, names, negative=True), not A[i]
    q["P0"] = {"type": "noul", "instructions":
               f"Applying every rule and exception correctly, the final outcome for {names[0]} is that it gets {yes}."}
    t["P0"] = A[0]
    q["AND"] = {"type": "noul", "instructions": f"{label[0]} is {yes} AND {label[1]} is {yes}."}
    t["AND"] = A[0] and A[1]
    q["OR"] = {"type": "noul", "instructions": f"At least one of these holds: {label[0]} is {yes}, or {label[1]} is {yes}."}
    t["OR"] = A[0] or A[1]
    if k >= 3:
        q["NEST"] = {"type": "noul", "instructions":
                     f"Either both {label[0]} and {label[1]} are {yes}, or {label[2]} is {yes} (or both)."}
        t["NEST"] = (A[0] and A[1]) or A[2]
    else:
        q["NEST"] = {"type": "noul", "instructions": f"{label[0]} is {yes} while {label[1]} is {no}."}
        t["NEST"] = A[0] and not A[1]
    q["J"], t["J"] = joint_q(case, names), joint_truth(case)
    q["JR"], t["JR"] = joint_q(case, names, reverse=True), joint_truth(case)
    subsets = {}
    for combo in itertools.product([1, 0], repeat=k):
        subsets["".join("Y" if c else "N" for c in combo)] = "; ".join(
            f"{names[i]} {word(c)}" for i, c in enumerate(combo))
    q["SUB"] = {"type": "choice", "instructions": "What is the full set of outcomes for all items in the case?",
                "criteria": subsets}
    t["SUB"] = "".join("Y" if a else "N" for a in A)
    q["CNT"] = {"type": "score", "instructions": f"How many of the {k} items in the case are {yes}?",
                "criteria": [f"{n} of {k}" for n in range(k + 1)]}
    t["CNT"] = sum(A)
    return q, t


def outcome_if(case, i, key, want):
    """Truth for item i if the condition on attribute `key` were forced to evaluate to `want`."""
    it = case["items"][i]
    cond = next(c for c in it["chain"] if c["attr"]["key"] == key)
    import random as _r
    vals = dict(it["values"])
    vals[key] = value_for(_r.Random(0), cond, want)
    return run_chain(it["chain"], it["default"], vals)[0]


def evaluated_keys(item):
    """Attribute keys whose conditions are actually evaluated for this item."""
    return [c["attr"]["key"] for c in item["chain"][: item["stop"] + 1]]


__all__ = ["build_case", "render", "atom_q", "joint_q", "joint_truth", "full_questions", "outcome_if",
           "evaluated_keys", "default_names", "evaluate"]
