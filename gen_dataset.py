"""Generate nested-exception policy scenarios with exact ground truth.

Each scenario: a policy with one rule per item category. A rule has a default decision and a
chain of `depth` exceptions; exception k is only considered if exception k-1 applied, and
each applying exception flips the decision. K items are then described by attribute values.

For every item we pick a uniform "stop level" s in 0..depth: exceptions 1..s apply, s+1 does
not, so truth = default XOR (s is odd). This keeps deep exceptions relevant instead of rarely
reached. Numeric thresholds include exact-boundary values; conditions include negations;
facts include distractor attributes; half the policies contain a decoy rule.

Questions per scenario (all derived from atoms A_i = "item i gets the positive decision"):
  A{i}   atom                         N{i}  negation (antonym wording)
  P0     paraphrase of A0             AND   A0 and A1          OR  A0 or A1
  NEST   (A0 and A1) or A2  [K>=3]  /  A0 and not A1  [K=2]
  CF     counterfactual: one evaluated fact changed, recomputed truth
  J      4-way joint choice over (A0, A1)      JR   same, options reversed
  SUB    2^K-way choice over all items         CNT  score: how many are positive
"""

import argparse
import itertools
import json
import random
from pathlib import Path

DOMAINS = {
    "expense": {
        "title": "COMPANY EXPENSE REIMBURSEMENT POLICY",
        "noun": "Expense", "yes": "reimbursed", "no": "rejected",
        "categories": ["meals", "lodging", "taxi", "client entertainment", "software",
                       "conference fees", "equipment", "training courses"],
        "attrs": [
            {"key": "approver", "kind": "cat", "label": "pre-approved by",
             "values": ["a VP", "a Director", "a Manager", "a Team Lead"],
             "is": "it was pre-approved by {v}", "not": "it was not pre-approved by {v}"},
            {"key": "claimant", "kind": "cat", "label": "claimant type",
             "values": ["a full-time employee", "a contractor", "an intern", "a part-time employee"],
             "is": "the claimant is {v}", "not": "the claimant is not {v}"},
            {"key": "trip", "kind": "cat", "label": "trip type",
             "values": ["international", "domestic", "local (no travel)"],
             "is": "the trip is {v}", "not": "the trip is not {v}"},
            {"key": "amount", "kind": "num", "label": "amount", "fmt": "${x}",
             "range": (20, 400), "step": 5,
             "over": "the amount is over {t}", "atmost": "the amount is at most {t}"},
            {"key": "days", "kind": "num", "label": "days between purchase and submission",
             "fmt": "{x} days", "range": (5, 90), "step": 1,
             "over": "it was submitted more than {t} after purchase",
             "atmost": "it was submitted within {t} of purchase"},
            {"key": "receipt", "kind": "bool", "label": "receipt attached",
             "true": "a receipt is attached", "false": "no receipt is attached"},
            {"key": "card", "kind": "bool", "label": "paid with corporate card",
             "true": "it was paid with the corporate card", "false": "it was not paid with the corporate card"},
            {"key": "weekend", "kind": "bool", "label": "incurred on a weekend",
             "true": "it was incurred on a weekend", "false": "it was incurred on a weekday"},
            {"key": "vendor", "kind": "bool", "label": "vendor on preferred list",
             "true": "the vendor is on the preferred list", "false": "the vendor is not on the preferred list"},
            {"key": "currency", "kind": "cat", "label": "currency",
             "values": ["USD", "EUR", "GBP", "JPY"],
             "is": "it was paid in {v}", "not": "it was not paid in {v}"},
            {"key": "attendees", "kind": "num", "label": "number of attendees", "fmt": "{x}",
             "range": (1, 20), "step": 1,
             "over": "there were more than {t} attendees", "atmost": "there were at most {t} attendees"},
        ],
    },
    "access": {
        "title": "FACILITY ACCESS CONTROL POLICY",
        "noun": "Request", "yes": "granted", "no": "denied",
        "categories": ["server room", "chemistry lab", "rooftop", "archive vault", "loading dock",
                       "executive floor", "data center cage", "clean room"],
        "attrs": [
            {"key": "badge", "kind": "num", "label": "badge clearance level", "fmt": "level {x}",
             "range": (1, 9), "step": 1,
             "over": "the badge clearance is above {t}", "atmost": "the badge clearance is at most {t}"},
            {"key": "role", "kind": "cat", "label": "person type",
             "values": ["an employee", "a contractor", "a visitor", "an auditor"],
             "is": "the person is {v}", "not": "the person is not {v}"},
            {"key": "escort", "kind": "cat", "label": "escorted by",
             "values": ["a security officer", "a facilities manager", "a colleague", "no one"],
             "is": "the person is escorted by {v}", "not": "the person is not escorted by {v}"},
            {"key": "hour", "kind": "num", "label": "requested entry time", "fmt": "{x}:00",
             "range": (0, 23), "step": 1,
             "over": "entry is requested after {t}", "atmost": "entry is requested at or before {t}"},
            {"key": "training", "kind": "bool", "label": "safety training completed",
             "true": "safety training is completed", "false": "safety training is not completed"},
            {"key": "nda", "kind": "bool", "label": "NDA signed",
             "true": "an NDA is on file", "false": "no NDA is on file"},
            {"key": "tickets", "kind": "num", "label": "open security incidents",
             "fmt": "{x}", "range": (0, 6), "step": 1,
             "over": "the person has more than {t} open security incidents",
             "atmost": "the person has at most {t} open security incidents"},
            {"key": "holiday", "kind": "bool", "label": "on a public holiday",
             "true": "the entry date is a public holiday", "false": "the entry date is not a public holiday"},
            {"key": "biometric", "kind": "bool", "label": "biometric check passed",
             "true": "the biometric check passed", "false": "the biometric check did not pass"},
            {"key": "site", "kind": "cat", "label": "home site",
             "values": ["headquarters", "the east campus", "a remote office", "a partner site"],
             "is": "the person's home site is {v}", "not": "the person's home site is not {v}"},
            {"key": "tenure", "kind": "num", "label": "months with the organization", "fmt": "{x} months",
             "range": (0, 60), "step": 1,
             "over": "the person has been with the organization for more than {t}",
             "atmost": "the person has been with the organization for at most {t}"},
        ],
    },
    "insurance": {
        "title": "HOME INSURANCE CLAIMS POLICY",
        "noun": "Claim", "yes": "covered", "no": "denied",
        "categories": ["water damage", "theft", "fire", "windstorm", "liability", "flood",
                       "mold", "electrical surge"],
        "attrs": [
            {"key": "tier", "kind": "cat", "label": "policy tier",
             "values": ["basic", "standard", "premium", "platinum"],
             "is": "the policy tier is {v}", "not": "the policy tier is not {v}"},
            {"key": "inspector", "kind": "cat", "label": "damage assessed by",
             "values": ["a licensed adjuster", "an independent contractor", "the policyholder", "an agent"],
             "is": "the damage was assessed by {v}", "not": "the damage was not assessed by {v}"},
            {"key": "loss", "kind": "num", "label": "claimed loss", "fmt": "${x}",
             "range": (500, 50000), "step": 500,
             "over": "the claimed loss is over {t}", "atmost": "the claimed loss is at most {t}"},
            {"key": "report_days", "kind": "num", "label": "days before incident was reported",
             "fmt": "{x} days", "range": (1, 60), "step": 1,
             "over": "the incident was reported more than {t} after it happened",
             "atmost": "the incident was reported within {t} of it happening"},
            {"key": "prior", "kind": "num", "label": "prior claims in last 3 years",
             "fmt": "{x}", "range": (0, 5), "step": 1,
             "over": "there are more than {t} prior claims in the last 3 years",
             "atmost": "there are at most {t} prior claims in the last 3 years"},
            {"key": "police", "kind": "bool", "label": "police report filed",
             "true": "a police report was filed", "false": "no police report was filed"},
            {"key": "vacant", "kind": "bool", "label": "home vacant at time of incident",
             "true": "the home was vacant at the time", "false": "the home was occupied at the time"},
            {"key": "maint", "kind": "bool", "label": "maintenance records provided",
             "true": "maintenance records were provided", "false": "maintenance records were not provided"},
            {"key": "alarm", "kind": "bool", "label": "monitored alarm installed",
             "true": "a monitored alarm was installed", "false": "no monitored alarm was installed"},
            {"key": "region", "kind": "cat", "label": "property region",
             "values": ["coastal", "urban", "rural", "mountain"],
             "is": "the property is in a {v} region", "not": "the property is not in a {v} region"},
            {"key": "age_home", "kind": "num", "label": "home age", "fmt": "{x} years",
             "range": (1, 120), "step": 1,
             "over": "the home is older than {t}", "atmost": "the home is at most {t} old"},
        ],
    },
    "library": {
        "title": "UNIVERSITY LIBRARY LOAN POLICY",
        "noun": "Loan", "yes": "approved", "no": "refused",
        "categories": ["rare manuscripts", "reference books", "periodicals", "maps",
                       "audio recordings", "theses", "microfilm", "art prints"],
        "attrs": [
            {"key": "role", "kind": "cat", "label": "borrower",
             "values": ["a faculty member", "a graduate student", "an undergraduate", "a visiting scholar"],
             "is": "the borrower is {v}", "not": "the borrower is not {v}"},
            {"key": "sponsor", "kind": "cat", "label": "request signed by",
             "values": ["the department chair", "a librarian", "an academic advisor", "no one"],
             "is": "the request is signed by {v}", "not": "the request is not signed by {v}"},
            {"key": "length", "kind": "num", "label": "requested loan length", "fmt": "{x} days",
             "range": (1, 60), "step": 1,
             "over": "the loan is longer than {t}", "atmost": "the loan is at most {t}"},
            {"key": "fines", "kind": "num", "label": "unpaid fines", "fmt": "${x}",
             "range": (0, 100), "step": 1,
             "over": "unpaid fines exceed {t}", "atmost": "unpaid fines are at most {t}"},
            {"key": "age", "kind": "num", "label": "item age", "fmt": "{x} years",
             "range": (1, 300), "step": 1,
             "over": "the item is older than {t}", "atmost": "the item is at most {t} old"},
            {"key": "overdue", "kind": "bool", "label": "has overdue items",
             "true": "the borrower has overdue items", "false": "the borrower has no overdue items"},
            {"key": "exam", "kind": "bool", "label": "requested during exam period",
             "true": "it is requested during the exam period", "false": "it is requested outside the exam period"},
            {"key": "digital", "kind": "bool", "label": "digital copy available",
             "true": "a digital copy is available", "false": "no digital copy is available"},
            {"key": "course", "kind": "bool", "label": "on a course reading list",
             "true": "the item is on a course reading list", "false": "the item is not on a course reading list"},
            {"key": "branch", "kind": "cat", "label": "holding branch",
             "values": ["the main library", "the science branch", "the law library", "off-site storage"],
             "is": "the item is held at {v}", "not": "the item is not held at {v}"},
            {"key": "loans", "kind": "num", "label": "items currently on loan", "fmt": "{x}",
             "range": (0, 30), "step": 1,
             "over": "the borrower currently has more than {t} items on loan",
             "atmost": "the borrower currently has at most {t} items on loan"},
        ],
    },
}

FOLLOW = [
    "However, in that case, if {c}, it is {v}.",
    "Even then, if {c}, it is {v}.",
    "But if, in addition, {c}, it is {v} after all.",
    "Further exception to the previous clause: if {c}, it is {v}.",
]


def fmt(attr, x):
    if attr["kind"] == "num":
        return attr["fmt"].format(x=x)
    if attr["kind"] == "bool":
        return "yes" if x else "no"
    return x


def evaluate(cond, value):
    attr, op, t = cond["attr"], cond["op"], cond["t"]
    if attr["kind"] == "cat":
        return (value == t) == (op == "is")
    if attr["kind"] == "bool":
        return value == t
    return value > t if op == "over" else value <= t


def cond_text(cond):
    attr, op, t = cond["attr"], cond["op"], cond["t"]
    if attr["kind"] == "cat":
        return attr[op].format(v=t)
    if attr["kind"] == "bool":
        return attr["true" if t else "false"]
    return attr[op].format(t=attr["fmt"].format(x=t))


def make_cond(rng, attr):
    if attr["kind"] == "cat":
        return {"attr": attr, "op": "not" if rng.random() < 0.25 else "is", "t": rng.choice(attr["values"])}
    if attr["kind"] == "bool":
        return {"attr": attr, "op": "is", "t": rng.random() < 0.5}
    lo, hi = attr["range"]
    step = attr["step"]
    t = rng.randrange(lo + step, hi, step)
    return {"attr": attr, "op": rng.choice(["over", "atmost"]), "t": t}


def value_for(rng, cond, want: bool):
    """Pick an attribute value that makes `cond` evaluate to `want`, preferring near-misses."""
    attr = cond["attr"]
    if attr["kind"] == "bool":
        return cond["t"] if want else not cond["t"]
    if attr["kind"] == "cat":
        opts = [v for v in attr["values"] if evaluate(cond, v) == want]
        return rng.choice(opts)
    lo, hi = attr["range"]
    step, t = attr["step"], cond["t"]
    span = max(step, round((hi - lo) * 0.15 / step) * step)
    cands = [v for v in range(max(lo, t - span), min(hi, t + span) + 1, step) if evaluate(cond, v) == want]
    if t in cands and rng.random() < 0.3:  # exact-boundary case
        return t
    return rng.choice(cands)


def run_chain(chain, default, values):
    decision, applied = default, 0
    for cond in chain:
        if not evaluate(cond, values[cond["attr"]["key"]]):
            break
        decision, applied = not decision, applied + 1
    return decision, applied


def chain_meta(chain, values, stop):
    """JSON-safe description of each condition, for slicing results by condition type."""
    out = []
    for j, c in enumerate(chain):
        a, v = c["attr"], values[c["attr"]["key"]]
        out.append({"key": a["key"], "kind": a["kind"], "op": c["op"], "t": c["t"], "value": v,
                    "sat": evaluate(c, v), "evaluated": j <= stop,
                    "boundary": a["kind"] == "num" and v == c["t"],
                    "negated": (a["kind"] == "cat" and c["op"] == "not") or (a["kind"] == "bool" and not c["t"])})
    return out


def random_value(rng, attr):
    if attr["kind"] == "bool":
        return rng.random() < 0.5
    if attr["kind"] == "cat":
        return rng.choice(attr["values"])
    lo, hi = attr["range"]
    return rng.randrange(lo, hi + 1, attr["step"])


def generate(rng, sid, domain_name, k, depth):
    d = DOMAINS[domain_name]
    yes, no = d["yes"], d["no"]
    cats = rng.sample(d["categories"], k + 1)
    items, rules = [], []
    for i in range(k):
        attrs = rng.sample(d["attrs"], depth)
        chain = [make_cond(rng, a) for a in attrs]
        default = rng.random() < 0.5
        stop = rng.randint(0, depth)  # number of exceptions that apply
        values = {}
        for j, cond in enumerate(chain):
            want = j < stop if j <= stop else rng.random() < 0.5
            values[cond["attr"]["key"]] = value_for(rng, cond, want)
        for a in (rest := [a for a in d["attrs"] if a["key"] not in values]) and rng.sample(rest, min(len(rest), rng.randint(1, 2))):
            values[a["key"]] = random_value(rng, a)
        truth, applied = run_chain(chain, default, values)
        assert applied == stop and truth == (default != (stop % 2 == 1))
        items.append({"cat": cats[i], "chain": chain, "default": default, "values": values,
                      "truth": truth, "stop": stop, "chain_meta": chain_meta(chain, values, stop)})
        rules.append((cats[i], chain, default))

    if rng.random() < 0.5:  # decoy rule for a category not present in the claim
        attrs = rng.sample(d["attrs"], depth)
        rules.append((cats[k], [make_cond(rng, a) for a in attrs], rng.random() < 0.5))
    rng.shuffle(rules)

    word = lambda b: yes if b else no  # noqa: E731
    lines = [d["title"],
             f"Each {d['noun'].lower()} is decided by the rule for its category. Within a rule, every "
             f"exception clause is only considered if the clause immediately before it applied; when an "
             f"exception applies, its decision replaces the previous one.", ""]
    for n, (cat, chain, default) in enumerate(rules, 1):
        parts = [f"Rule {n} ({cat}): {cat} items are {word(default)} by default."]
        dec = default
        for j, cond in enumerate(chain):
            dec = not dec
            tmpl = "Exception: if {c}, it is {v} instead." if j == 0 else rng.choice(FOLLOW)
            parts.append(tmpl.format(c=cond_text(cond), v=word(dec)))
        lines.append(" ".join(parts))
    lines += ["", "CASE"]
    names = [f"{d['noun']} {i + 1}" for i in range(k)]
    for name, it in zip(names, items):
        keys = list(it["values"])
        rng.shuffle(keys)
        attr_by_key = {a["key"]: a for a in d["attrs"]}
        facts = "; ".join(f"{attr_by_key[key]['label']}: {fmt(attr_by_key[key], it['values'][key])}"
                          for key in keys)
        lines.append(f"- {name} (category: {it['cat']}) - {facts}.")
    state = "\n".join(lines)

    A = [it["truth"] for it in items]
    label = [f"{n} ({it['cat']})" for n, it in zip(names, items)]
    q, truth = {}, {}

    def add(key, spec, t):
        q[key], truth[key] = spec, t

    for i in range(k):
        add(f"A{i}", {"type": "noul", "instructions": f"Under the policy, {label[i]} is {yes}."}, A[i])
        add(f"N{i}", {"type": "noul", "instructions": f"Under the policy, {label[i]} is {no}."}, not A[i])
    add("P0", {"type": "noul", "instructions":
               f"Applying every rule and exception correctly, the final outcome for {names[0]} is that it gets {yes}."},
        A[0])
    add("AND", {"type": "noul", "instructions": f"{label[0]} is {yes} AND {label[1]} is {yes}."}, A[0] and A[1])
    add("OR", {"type": "noul", "instructions":
               f"At least one of these holds: {label[0]} is {yes}, or {label[1]} is {yes}."}, A[0] or A[1])
    if k >= 3:
        add("NEST", {"type": "noul", "instructions":
                     f"Either both {label[0]} and {label[1]} are {yes}, or {label[2]} is {yes} (or both)."},
            (A[0] and A[1]) or A[2])
    else:
        add("NEST", {"type": "noul", "instructions":
                     f"{label[0]} is {yes} while {label[1]} is {no}."}, A[0] and not A[1])

    # Counterfactual: flip one condition that was actually evaluated for a random item.
    ci = rng.randrange(k)
    it = items[ci]
    j = rng.randrange(min(it["stop"] + 1, depth))
    cond = it["chain"][j]
    key = cond["attr"]["key"]
    old = it["values"][key]
    new_values = dict(it["values"])
    new_values[key] = value_for(rng, cond, not evaluate(cond, old))
    cf_truth, _ = run_chain(it["chain"], it["default"], new_values)
    ask_yes = rng.random() < 0.5
    add("CF", {"type": "noul", "instructions":
               f"If {names[ci]}'s {cond['attr']['label']} had been {fmt(cond['attr'], new_values[key])} instead of "
               f"{fmt(cond['attr'], old)} (everything else unchanged), {names[ci]} would be {yes if ask_yes else no}."},
        cf_truth == ask_yes)

    joint = {
        "both": f"Both {label[0]} and {label[1]} are {yes}",
        "only_first": f"{label[0]} is {yes}, {label[1]} is {no}",
        "only_second": f"{label[0]} is {no}, {label[1]} is {yes}",
        "neither": f"Neither {label[0]} nor {label[1]} is {yes}",
    }
    jt = {(1, 1): "both", (1, 0): "only_first", (0, 1): "only_second", (0, 0): "neither"}[(A[0], A[1])]
    add("J", {"type": "choice", "instructions": f"What are the outcomes for {names[0]} and {names[1]}?",
              "criteria": joint}, jt)
    add("JR", {"type": "choice", "instructions": f"What are the outcomes for {names[0]} and {names[1]}?",
               "criteria": dict(reversed(list(joint.items())))}, jt)

    subsets = {}
    for combo in itertools.product([1, 0], repeat=k):
        sk = "".join("Y" if c else "N" for c in combo)
        subsets[sk] = "; ".join(f"{names[i]} {word(c)}" for i, c in enumerate(combo))
    add("SUB", {"type": "choice", "instructions": "What is the full set of outcomes for all items in the case?",
                "criteria": subsets}, "".join("Y" if a else "N" for a in A))
    add("CNT", {"type": "score", "instructions": f"How many of the {k} items in the case are {yes}?",
                "criteria": [f"{n} of {k}" for n in range(k + 1)]}, sum(A))

    return {
        "id": sid, "domain": domain_name, "k": k, "depth": depth, "state": state, "questions": q,
        "truth": truth, "items": [{"cat": it["cat"], "truth": it["truth"], "stop": it["stop"],
                                   "default": it["default"], "chain": it["chain_meta"]} for it in items],
        "cf_item": ci, "cf_level": j + 1,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=10, help="scenarios per (domain, K, depth) cell")
    ap.add_argument("--depths", default="1,2,3,4,5")
    ap.add_argument("--ks", default="2,3,4")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/dataset.jsonl")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    depths = [int(x) for x in args.depths.split(",")]
    ks = [int(x) for x in args.ks.split(",")]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w") as f:
        for dom in DOMAINS:
            for k in ks:
                for depth in depths:
                    for _ in range(args.per_cell):
                        f.write(json.dumps(generate(rng, f"s{n:05d}", dom, k, depth)) + "\n")
                        n += 1
    print(f"wrote {n} scenarios to {out}")


if __name__ == "__main__":
    main()
