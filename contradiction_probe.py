"""Ask Jev nested, logically linked questions about one scenario and flag self-contradictions.

The scenario is an expense policy with exceptions-inside-exceptions. Every question has an
exact answer, and the questions are built from the same atomic facts combined with
NOT / AND / OR / IF-THEN and counterfactuals. Jev answers each question independently, so
nothing forces the answers to obey probability logic -- that's what we check:
  1. Complements        P(X) + P(not X) ~ 1
  2. Conjunction bound  P(X and Y) <= min(P(X), P(Y))
  3. Disjunction bound  P(X or Y)  >= max(P(X), P(Y))
  4. Inclusion-excl.    P(X or Y) ~ P(X) + P(Y) - P(X and Y)
  5. Nesting            P((X and Y) and Z) <= P(X and Y)
  6. Marginals          a joint 4-way choice over (C, D) must match the separate nouls for C and D
  7. Aggregation        the "how many items" score and "total amount" choice must match the item nouls
  8. Order              reversing choice options must not change the pick
"""

import json
import sys

from jev_client import choice, decide, noul, score

TOL = 0.2  # slack before calling something a contradiction

STATE = """COMPANY TRAVEL EXPENSE POLICY
Rule 1 (Meals): Meals are reimbursable up to $60 per day, unless the trip is international,
in which case the limit is $90 per day. Amounts over the limit are not reimbursed at all
(the whole meal is rejected, not just the excess).
Rule 2 (Alcohol): Alcohol is never reimbursable, except for client entertainment approved in
advance by a Vice President (VP); even then, only if the alcohol cost is at most $40 per person
present. If it exceeds $40 per person, the whole alcohol item is rejected.
Rule 3 (Receipts): A receipt is required for any item over $25, unless the claimant is a
contractor, in which case a receipt is required for every item regardless of amount.
Items missing a required receipt are rejected.
Rule 4 (Deadline): Claims submitted more than 30 days after the trip ends are rejected
entirely, unless the delay was caused by a company system outage confirmed in writing by IT.

CLAIM
Claimant: an external contractor.
Trip: Berlin, Germany (claimant is based in the United States). Trip ended 34 days before
submission. IT confirmed in writing that the expense system was down from day 28 to day 33
after the trip, which caused the delay.
Items:
  (a) Dinner, $85, one day, receipt attached.
  (b) Drinks with a client, $120, for 2 people (claimant + 1 client). Approved in advance by
      a Director (the Director reports to a VP; the VP was not consulted). Receipt attached.
  (c) Taxi, $18, no receipt."""

# Atomic facts and ground truth:
#   A = claim survives the deadline rule        TRUE  (outage exception)
#   B = dinner (a) is reimbursable              TRUE  (international -> $90 cap, receipt)
#   C = drinks (b) are reimbursable             FALSE (Director, not VP)
#   D = taxi (c) is reimbursable                FALSE (contractor -> receipt always needed)
Q = {
    "A": noul("The claim as a whole survives the 30-day deadline rule and is not rejected for lateness."),
    "not_A": noul("The claim as a whole is rejected for being submitted late."),
    "B": noul("Item (a), the $85 dinner, is reimbursable."),
    "C": noul("Item (b), the $120 client drinks, is reimbursable."),
    "not_C": noul("Item (b), the $120 client drinks, is NOT reimbursable."),
    "D": noul("Item (c), the $18 taxi, is reimbursable."),
    "A_and_B": noul("The claim survives the deadline rule AND the $85 dinner is reimbursable."),
    "A_and_C": noul("The claim survives the deadline rule AND the $120 drinks are reimbursable."),
    "A_or_C": noul("Either the claim survives the deadline rule, OR the $120 drinks are reimbursable, or both."),
    "C_or_D": noul("Either the $120 drinks are reimbursable, OR the $18 taxi is reimbursable, or both."),
    "AB_and_CorD": noul(
        "The claim survives the deadline rule AND the dinner is reimbursable, AND in addition "
        "at least one of the drinks or the taxi is reimbursable."),
    "A_implies_B_not_C": noul(
        "IF the claim survives the deadline rule, THEN the dinner is reimbursable but the drinks are not."),
    # Counterfactuals, one level deeper in the exception chain
    "cf_employee_taxi": noul(
        "If the claimant had been a regular employee instead of a contractor (everything else the "
        "same), the $18 taxi would have been reimbursable."),
    "cf_vp_drinks": noul(
        "If a VP (instead of the Director) had approved the drinks in advance (everything else the "
        "same), the $120 drinks would have been reimbursable."),
    "cf_domestic_dinner": noul(
        "If the trip had been domestic instead of international (everything else the same), the "
        "$85 dinner would have been reimbursable."),
    "CD_joint": choice("Which of items (b) drinks and (c) taxi are reimbursable?", {
        "both": "Both the drinks and the taxi are reimbursable",
        "only_drinks": "Only the drinks are reimbursable, the taxi is not",
        "only_taxi": "Only the taxi is reimbursable, the drinks are not",
        "neither": "Neither the drinks nor the taxi is reimbursable",
    }),
    "total": choice("What is the total reimbursed amount for this claim?", {
        "0": "$0", "85": "$85", "103": "$103", "165": "$165", "205": "$205", "223": "$223",
    }),
    "count": score("How many of the three items (a), (b), (c) are reimbursed?",
                   ["None", "One", "Two", "All three"]),
}

TRUTH = {
    "A": True, "not_A": False, "B": True, "C": False, "not_C": True, "D": False,
    "A_and_B": True, "A_and_C": False, "A_or_C": True, "C_or_D": False, "AB_and_CorD": False,
    "A_implies_B_not_C": True, "cf_employee_taxi": True, "cf_vp_drinks": False,
    "cf_domestic_dinner": False, "CD_joint": "neither", "total": "85",
}
# Item subsets -> total amount, for checking the "total" choice against the item nouls
AMOUNT = {(1, 0, 0): "85", (1, 0, 1): "103", (1, 1, 0): "205", (1, 1, 1): "223",
          (0, 0, 0): "0", (0, 1, 0): "120", (0, 0, 1): "18", (0, 1, 1): "138"}


def reversed_criteria(q: dict) -> dict:
    return {**q, "criteria": dict(reversed(list(q["criteria"].items())))}


def main() -> None:
    r1 = decide(STATE, Q)
    a = r1["answers"]
    r2 = decide(STATE, {k: reversed_criteria(Q[k]) for k in ("CD_joint", "total")})
    b = r2["answers"]

    if "--raw" in sys.argv:
        print(json.dumps({"call_1": r1, "call_2_reversed": r2}, indent=2))

    p = lambda k: a[k]["noul"]  # noqa: E731
    findings = []

    def check(kind, name, ok, detail):
        findings.append((kind, name, ok, detail))

    for x, nx in [("A", "not_A"), ("C", "not_C")]:
        s = p(x) + p(nx)
        check("complement", f"{x} + {nx}", abs(s - 1) <= TOL, f"{p(x):.2f} + {p(nx):.2f} = {s:.2f} (~1)")

    for conj, parts in [("A_and_B", ["A", "B"]), ("A_and_C", ["A", "C"])]:
        m = min(p(k) for k in parts)
        check("conjunction", f"{conj} <= min({', '.join(parts)})", p(conj) <= m + TOL,
              f"{p(conj):.2f} vs min {m:.2f}")

    for disj, parts in [("A_or_C", ["A", "C"]), ("C_or_D", ["C", "D"])]:
        m = max(p(k) for k in parts)
        check("disjunction", f"{disj} >= max({', '.join(parts)})", p(disj) >= m - TOL,
              f"{p(disj):.2f} vs max {m:.2f}")

    ie = p("A") + p("C") - p("A_and_C")
    check("incl-excl", "A_or_C = A + C - A_and_C", abs(p("A_or_C") - ie) <= TOL,
          f"{p('A_or_C'):.2f} vs {ie:.2f}")

    for outer in ["A_and_B", "C_or_D"]:
        check("nesting", f"AB_and_CorD <= {outer}", p("AB_and_CorD") <= p(outer) + TOL,
              f"{p('AB_and_CorD'):.2f} vs {p(outer):.2f}")

    j = a["CD_joint"]["probabilities"]
    for item, keys in [("C", ["both", "only_drinks"]), ("D", ["both", "only_taxi"])]:
        m = sum(j[k] for k in keys)
        check("marginal", f"joint choice P({item}) vs noul {item}", abs(m - p(item)) <= TOL,
              f"joint {m:.2f} vs noul {p(item):.2f}")

    expected_count = p("B") + p("C") + p("D")
    check("aggregation", "count score vs sum of item nouls",
          abs(a["count"]["score"] - expected_count) <= 0.5,
          f"score {a['count']['score']:.2f} vs {expected_count:.2f}")
    implied = AMOUNT[tuple(int(p(k) > 0.5) for k in "BCD")]
    check("aggregation", "total choice vs item nouls", a["total"]["choice"] == implied,
          f"choice ${a['total']['choice']} vs implied ${implied}")

    for k in ["CD_joint", "total"]:
        check("order", f"reversed options: {k}", a[k]["choice"] == b[k]["choice"],
              f"{a[k]['choice']} vs {b[k]['choice']}")

    cost = sum(r.get("usage", {}).get("cost") or 0 for r in (r1, r2))
    print(f"\nmodel {r1.get('model')}  latency {r1['latency_ms']} ms ({len(Q)} q) / "
          f"{r2['latency_ms']} ms (2 q)  cost ${cost:.7f}\n")

    print("CORRECTNESS")
    right = 0
    for k, truth in TRUTH.items():
        if isinstance(truth, bool):
            got, ok = f"{p(k):.2f}", (p(k) > 0.5) == truth
        else:
            got, ok = f"{a[k]['choice']} ({a[k]['confidence']:.2f})", a[k]["choice"] == truth
        right += ok
        print(f"  [{'ok' if ok else 'WRONG'}] {k:<20} jev={got:<14} truth={truth}")
    print(f"  {right}/{len(TRUTH)} correct\n")

    print("CONSISTENCY")
    bad = 0
    for kind, name, ok, detail in findings:
        bad += not ok
        print(f"  [{'ok' if ok else 'CONTRADICTION'}] {kind:<11} {name}: {detail}")
    print(f"  {bad}/{len(findings)} checks contradicted.")


if __name__ == "__main__":
    main()
