"""E14 - Can you Dutch-book Jev? (coherence of its probabilities as prices)

Treat every Jev probability as the price of a $1 ticket that pays if the statement is true. A set of prices is
COHERENT if no combination of bets (buy or sell each ticket, at most $1 of each) wins money in every possible
world. The Dutch-book value g = the largest guaranteed profit a bettor can lock in against Jev's prices; g = 0
exactly when the prices are consistent with some probability distribution (de Finetti). Conditional prices
("B, given that A") are called-off bets: refunded if A turns out false.

Each set is two statements A and B about one situation, so there are 4 worlds (AB, A¬B, ¬AB, ¬A¬B).
Families (200 sets each):
  chance    dice / cards / urn without replacement / biased coin; exact true probabilities by enumeration
  baserate  a population with counts or percentages (patients, employees, emails, parcels, students);
            exact true probabilities; includes the classic "P(condition | positive test)" setup
  policy    nested-exception policy cases (depth 2-5), A = item 1 is <yes>, B = item 2 is <yes>; truth is 0/1
Calls per set (every question in its own call unless noted):
  A, ¬A, B, ¬B, A∧B, A∨B, A∧¬B, ¬A∧B, ¬A∧¬B       9 unconditional prices
  B|A, A|B                                        conditioning: "It is known that the following is true: ..."
                                                  added to the state (chance and baserate only)
  A again                                         noise floor: arbitrage from re-asking the same price
  bundled                                         the 9 unconditional questions in ONE call
  choice                                          one Choice over the 4 worlds (coherent by construction)
Dutch book solved exactly: g = min over distributions λ on the 4 worlds of Σ_i |E_λ[payoff of bet i]| (LP dual),
minimised by enumerating the vertices of the arrangement. Baselines: uniformly random prices on the same events.
Outputs: data/e14_dutch_book/dataset.jsonl (every set: state, statements, true probabilities, the requests),
data/e14_dutch_book/answers.jsonl (prices, Dutch-book values and checks per set), logs/e14_dutch_book/calls.jsonl.
"""

import itertools
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.common import ROOT, log_event, mean, run_jev, save_results, table  # noqa: E402
from bench.scenarios import DOMAINS, atom_q, build_case, render  # noqa: E402

EXP = "e14_dutch_book"
OUT = ROOT / "data" / EXP
N_PER_FAMILY = 200
WORLDS = [(1, 1), (1, 0), (0, 1), (0, 0)]  # (A, B)
# event name -> indicator over worlds (a, b)
EVENTS = {"A": lambda a, b: a, "nA": lambda a, b: 1 - a, "B": lambda a, b: b, "nB": lambda a, b: 1 - b,
          "AB": lambda a, b: a * b, "AoB": lambda a, b: max(a, b), "AnB": lambda a, b: a * (1 - b),
          "nAB": lambda a, b: (1 - a) * b, "nAnB": lambda a, b: (1 - a) * (1 - b)}
UNCOND = list(EVENTS)
COND = {"BgA": ("B", "A"), "AgB": ("A", "B")}  # name -> (target, condition)
CELLS = {"both": "AB", "only_1": "AnB", "only_2": "nAB", "neither": "nAnB"}


# ---------- statement texts ----------

def cap(s):
    return s[0].upper() + s[1:]


def texts(a, b):
    """Question text per event, from two lower-case statements without a final period."""
    both = "Both of the following are true: (1) {}; (2) {}."
    return {"A": cap(a) + ".", "nA": f"It is not the case that {a}.", "B": cap(b) + ".",
            "nB": f"It is not the case that {b}.", "AB": both.format(a, b),
            "AoB": f"At least one of the following is true: (1) {a}; (2) {b}.",
            "AnB": both.format(a, f"it is not the case that {b}"),
            "nAB": both.format(f"it is not the case that {a}", b),
            "nAnB": both.format(f"it is not the case that {a}", f"it is not the case that {b}")}


# ---------- family 1: chance setups (exact enumeration) ----------

def dice(rng):
    om = [((i, j), 1 / 36) for i in range(1, 7) for j in range(1, 7)]
    k1, k2, m = rng.randint(2, 5), rng.randint(2, 5), rng.randint(5, 11)
    preds = [(f"the first roll is at least {k1}", lambda o: o[0] >= k1),
             (f"the second roll is at most {k2}", lambda o: o[1] <= k2),
             (f"the sum of the two rolls is at least {m}", lambda o: o[0] + o[1] >= m),
             ("the sum of the two rolls is even", lambda o: (o[0] + o[1]) % 2 == 0),
             ("both rolls show the same number", lambda o: o[0] == o[1]),
             ("at least one roll shows a 6", lambda o: 6 in o),
             ("the first roll is higher than the second", lambda o: o[0] > o[1])]
    state = ("A fair six-sided die is rolled twice. The two rolls are independent, and each face (1 to 6) is "
             "equally likely on each roll. Nothing else is known about the outcome.")
    return state, om, preds


def cards(rng):
    suits = ["hearts", "diamonds", "clubs", "spades"]
    om = [((r, s), 1 / 52) for r in range(1, 14) for s in suits]
    preds = [("the card is red", lambda o: o[1] in ("hearts", "diamonds")),
             ("the card is a heart", lambda o: o[1] == "hearts"),
             ("the card is a spade", lambda o: o[1] == "spades"),
             ("the card is a face card (a jack, queen or king)", lambda o: o[0] >= 11),
             ("the card is an ace", lambda o: o[0] == 1),
             ("the card is a number card from 2 to 5", lambda o: 2 <= o[0] <= 5),
             ("the card is a king or a queen", lambda o: o[0] in (12, 13)),
             ("the card is a club or a diamond", lambda o: o[1] in ("clubs", "diamonds"))]
    state = ("One card is drawn at random from a standard, well-shuffled 52-card deck: four suits (hearts and "
             "diamonds are red, clubs and spades are black), each with an ace, the numbers 2 to 10, a jack, a queen "
             "and a king. Nothing else is known about the card.")
    return state, om, preds


def urn(rng):
    r, b, g = rng.randint(1, 6), rng.randint(1, 6), rng.randint(0, 4)
    bag = ["red"] * r + ["blue"] * b + ["green"] * g
    n = len(bag)
    om = [((bag[i], bag[j]), 1 / (n * (n - 1))) for i in range(n) for j in range(n) if i != j]
    preds = [("the first marble drawn is red", lambda o: o[0] == "red"),
             ("the second marble drawn is red", lambda o: o[1] == "red"),
             ("the first marble drawn is blue", lambda o: o[0] == "blue"),
             ("the second marble drawn is blue", lambda o: o[1] == "blue"),
             ("the two marbles drawn are the same colour", lambda o: o[0] == o[1]),
             ("neither marble drawn is red", lambda o: "red" not in o)]
    if g:
        preds.append(("at least one of the two marbles drawn is green", lambda o: "green" in o))
    state = (f"A bag contains {r} red, {b} blue and {g} green marbles, identical except for colour. Two marbles "
             f"are drawn at random, one after the other, without putting the first one back. Nothing else is "
             f"known about which marbles were drawn.")
    return state, om, preds


def coin(rng):
    p = rng.choice([0.5, 0.6, 0.7, 0.8])
    om = []
    for flips in itertools.product("HT", repeat=3):
        w = 1.0
        for f in flips:
            w *= p if f == "H" else 1 - p
        om.append((flips, w))
    preds = [("the first flip lands heads", lambda o: o[0] == "H"),
             ("the second flip lands heads", lambda o: o[1] == "H"),
             ("at least two of the three flips land heads", lambda o: o.count("H") >= 2),
             ("exactly one of the three flips lands heads", lambda o: o.count("H") == 1),
             ("all three flips land the same way", lambda o: len(set(o)) == 1),
             ("the last flip lands tails", lambda o: o[2] == "T")]
    state = (f"A coin that lands heads with probability {p} on each flip is flipped three times. The flips are "
             f"independent. Nothing else is known about the outcome.")
    return state, om, preds


def chance_set(rng, kind):
    state, om, preds = {"dice": dice, "cards": cards, "urn": urn, "coin": coin}[kind](rng)
    while True:
        (ta, fa), (tb, fb) = rng.sample(preds, 2)
        joint = {w: 0.0 for w in WORLDS}
        for o, w in om:
            joint[(int(fa(o)), int(fb(o)))] += w
        pa, pb = joint[(1, 1)] + joint[(1, 0)], joint[(1, 1)] + joint[(0, 1)]
        same = all(int(fa(o)) == int(fb(o)) for o, _ in om) or all(int(fa(o)) != int(fb(o)) for o, _ in om)
        if 1e-9 < pa < 1 - 1e-9 and 1e-9 < pb < 1 - 1e-9 and not same:
            return {"family": "chance", "setup": kind, "state": state, "a": ta, "b": tb, "joint": joint}


# ---------- family 2: base-rate populations ----------

POPS = [
    {"setup": "patients", "place": "A clinic has {N} patients.", "unit": "patient", "pl": "patients",
     "A": "has the condition", "Ap": "have the condition", "nAp": "do not have the condition",
     "B": "tests positive", "Bp": "test positive"},
    {"setup": "employees", "place": "A company has {N} employees.", "unit": "employee", "pl": "employees",
     "A": "works in Sales", "Ap": "work in Sales", "nAp": "work in other departments",
     "B": "works remotely", "Bp": "work remotely"},
    {"setup": "emails", "place": "An inbox holds {N} emails.", "unit": "email", "pl": "emails",
     "A": "is spam", "Ap": "are spam", "nAp": "are not spam", "B": "contains a link", "Bp": "contain a link"},
    {"setup": "parcels", "place": "A depot handled {N} parcels.", "unit": "parcel", "pl": "parcels",
     "A": "is fragile", "Ap": "are fragile", "nAp": "are not fragile", "B": "arrived late", "Bp": "arrived late"},
    {"setup": "students", "place": "A school has {N} students.", "unit": "student", "pl": "students",
     "A": "took the evening course", "Ap": "took the evening course", "nAp": "did not take the evening course",
     "B": "passed the exam", "Bp": "passed the exam"},
]


def baserate_set(rng, n):
    d = POPS[n % len(POPS)]
    fmt = "counts" if (n // len(POPS)) % 2 == 0 else "percent"
    if fmt == "counts":
        N = rng.choice([100, 200, 400, 500, 1000, 2000])
        nA = rng.randint(max(1, N // 50), N * 6 // 10)
        kA = rng.randint(1, nA - 1) if nA > 1 else 1
        kN = rng.randint(1, max(1, (N - nA) * 4 // 10))
        pa, pba, pbn = nA / N, kA / nA, kN / (N - nA)
        state = (d["place"].format(N=N) + f" {nA} of them {d['Ap']}. Of the {d['pl']} who {d['Ap']}, {kA} {d['Bp']}. "
                 f"Of the {N - nA} {d['pl']} who {d['nAp']}, {kN} {d['Bp']}.")
    else:
        pA, pBA, pBN = rng.randint(1, 60), rng.randint(50, 98), rng.randint(2, 40)
        pa, pba, pbn = pA / 100, pBA / 100, pBN / 100
        state = (d["place"].format(N="many") + f" {pA}% of them {d['Ap']}. Of the {d['pl']} who {d['Ap']}, {pBA}% "
                 f"{d['Bp']}. Of the {d['pl']} who {d['nAp']}, {pBN}% {d['Bp']}.")
    state += f" One {d['unit']} is chosen at random; every {d['unit']} is equally likely to be chosen."
    joint = {(1, 1): pa * pba, (1, 0): pa * (1 - pba), (0, 1): (1 - pa) * pbn, (0, 0): (1 - pa) * (1 - pbn)}
    return {"family": "baserate", "setup": d["setup"], "format": fmt, "state": state,
            "a": f"the chosen {d['unit']} {d['A']}", "b": f"the chosen {d['unit']} {d['B']}", "joint": joint}


# ---------- family 3: nested policies ----------

def policy_set(rng, n):
    case = build_case(rng, list(DOMAINS)[n % 4], 2, 2 + (n // 4) % 4)
    low = lambda q: q["instructions"][0].lower() + q["instructions"][1:].rstrip(".")  # noqa: E731
    ta, tb = case["items"][0]["truth"], case["items"][1]["truth"]
    joint = {w: float(w == (int(ta), int(tb))) for w in WORLDS}
    return {"family": "policy", "setup": case["domain"], "depth": case["depth"], "state": render(case),
            "a": low(atom_q(case, 0)), "b": low(atom_q(case, 1)), "joint": joint}


# ---------- truth ----------

def truth_probs(joint):
    p = {e: sum(joint[w] * f(*w) for w in WORLDS) for e, f in EVENTS.items()}
    for name, (t, c) in COND.items():
        pc = p[c]
        p[name] = (sum(joint[w] * EVENTS[t](*w) * EVENTS[c](*w) for w in WORLDS) / pc) if pc > 0 else None
    return p


# ---------- Dutch book (exact) ----------

def coeffs(bets):
    """bets: [(event, condition or None, price)] -> per-bet payoff vector over WORLDS (for a +$1 stake)."""
    out = []
    for e, c, q in bets:
        v = []
        for w in WORLDS:
            if c is not None and not EVENTS[c](*w):
                v.append(0.0)  # called off
            else:
                v.append(EVENTS[e](*w) - q)
        out.append(v)
    return out


def _solve4(M, rhs):
    M = [row[:] + [r] for row, r in zip(M, rhs)]
    n = 4
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col:
                f = M[r][col] / M[col][col]
                M[r] = [x - f * y for x, y in zip(M[r], M[col])]
    return [M[i][n] / M[i][i] for i in range(n)]


def dutch_book(bets):
    """Max guaranteed profit with stakes in [-1, 1] per bet = min over λ in the simplex of Σ_i |a_i·λ|.
    The minimum of this convex piecewise-linear function is at a vertex: 3 of {a_i·λ = 0, λ_w = 0} plus Σλ = 1."""
    A = coeffs(bets)
    planes = A + [[float(i == w) for i in range(4)] for w in range(4)]
    f = lambda lam: sum(abs(sum(a * l for a, l in zip(row, lam))) for row in A)  # noqa: E731
    best = min(f([float(i == w) for i in range(4)]) for w in range(4))
    for trio in itertools.combinations(planes, 3):
        lam = _solve4(list(trio) + [[1.0] * 4], [0.0, 0.0, 0.0, 1.0])
        if lam and min(lam) >= -1e-9:
            best = min(best, f([max(x, 0.0) for x in lam]))
    return max(best, 0.0)


# ---------- requests ----------

def build_calls(sets):
    calls = []
    for s in sets:
        n, fam = s["id"], s["family"]
        tx = texts(s["a"], s["b"])
        s["questions"] = tx
        for e in UNCOND:
            calls.append({"call_id": f"{n}-{e}", "state": s["state"], "questions": {"Q": {"type": "noul", "instructions": tx[e]}},
                          "meta": {"set": n, "family": fam, "kind": "sep", "event": e}})
        calls.append({"call_id": f"{n}-A_rep", "state": s["state"], "questions": {"Q": {"type": "noul", "instructions": tx["A"]}},
                      "meta": {"set": n, "family": fam, "kind": "rep", "event": "A"}})
        calls.append({"call_id": f"{n}-bundled", "state": s["state"],
                      "questions": {e: {"type": "noul", "instructions": tx[e]} for e in UNCOND},
                      "meta": {"set": n, "family": fam, "kind": "bundled"}})
        calls.append({"call_id": f"{n}-choice", "state": s["state"], "questions": {"C": {
            "type": "choice", "instructions": f"Consider two statements. (1) {cap(s['a'])}. (2) {cap(s['b'])}. "
                                              f"Which combination is true?",
            "criteria": {"both": "(1) and (2) are both true", "only_1": "(1) is true and (2) is false",
                         "only_2": "(1) is false and (2) is true", "neither": "(1) and (2) are both false"}}},
            "meta": {"set": n, "family": fam, "kind": "choice"}})
        if fam != "policy":
            for name, (t, c) in COND.items():
                given = s["a"] if c == "A" else s["b"]
                calls.append({"call_id": f"{n}-{name}",
                              "state": s["state"] + f"\n\nIt is known that the following is true: {given}.",
                              "questions": {"Q": {"type": "noul", "instructions": tx[t]}},
                              "meta": {"set": n, "family": fam, "kind": "cond", "event": name}})
    return calls


def fmt3(x):
    return f"{x:.3f}"


def main():
    rng = random.Random(1414)
    sets = []
    kinds = ["dice", "cards", "urn", "coin"]
    for n in range(N_PER_FAMILY):
        sets.append(chance_set(rng, kinds[n % 4]))
    for n in range(N_PER_FAMILY):
        sets.append(baserate_set(rng, n))
    for n in range(N_PER_FAMILY):
        sets.append(policy_set(rng, n))
    for i, s in enumerate(sets):
        s["id"] = i
        s["truth"] = truth_probs(s["joint"])

    calls = build_calls(sets)
    log_event(EXP, f"starting: {len(calls)} calls ({len(sets)} sets)")
    resp = run_jev(EXP, [dict(c) for c in calls], workers=16)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "dataset.jsonl").open("w") as f:
        for s in sets:
            f.write(json.dumps({k: (v if k != "joint" else {f"{w[0]}{w[1]}": p for w, p in v.items()})
                                for k, v in s.items()}) + "\n")

    # ---------- per-set analysis ----------
    rrng = random.Random(7)
    recs = []
    for s in sets:
        n, fam = s["id"], s["family"]
        sep = {e: resp[f"{n}-{e}"]["answers"]["Q"]["noul"] for e in UNCOND}
        bun = {e: resp[f"{n}-bundled"]["answers"][e]["noul"] for e in UNCOND}
        ch = {k: float(v) for k, v in resp[f"{n}-choice"]["answers"]["C"]["probabilities"].items()}
        rep = resp[f"{n}-A_rep"]["answers"]["Q"]["noul"]
        cond = {}
        if fam != "policy":
            cond = {name: resp[f"{n}-{name}"]["answers"]["Q"]["noul"] for name in COND}
        bets_unc = [(e, None, sep[e]) for e in UNCOND]
        bets_all = bets_unc + [(COND[k][0], COND[k][1], q) for k, q in cond.items()]
        r = {"set": n, "family": fam, "setup": s["setup"], "format": s.get("format"), "depth": s.get("depth"),
             "sep": sep, "bundled": bun, "choice": ch, "A_rep": rep, "cond": cond, "truth": s["truth"],
             "g_sep_all": dutch_book(bets_all), "g_sep_unc": dutch_book(bets_unc),
             "g_bundled": dutch_book([(e, None, bun[e]) for e in UNCOND]), "g_noise": abs(sep["A"] - rep),
             "g_random": dutch_book([(e, c, rrng.random()) for e, c, _ in bets_all])}
        t = s["truth"]
        r["checks"] = {
            "complement": abs(sep["A"] + sep["nA"] - 1),
            "cells_sum": sep["AB"] + sep["AnB"] + sep["nAB"] + sep["nAnB"],
            "and_gt_min": sep["AB"] > min(sep["A"], sep["B"]) + 0.05,
            "or_lt_max": sep["AoB"] < max(sep["A"], sep["B"]) - 0.05,
            "incl_excl": abs(sep["AoB"] - (sep["A"] + sep["B"] - sep["AB"])),
            "decomp_A": abs(sep["A"] - (sep["AB"] + sep["AnB"])),
        }
        if cond:
            r["checks"]["product_BgA"] = abs(cond["BgA"] * sep["A"] - sep["AB"])
            r["checks"]["bayes"] = abs(cond["AgB"] * sep["B"] - cond["BgA"] * sep["A"])
        # accuracy vs the true probability (policy: truth is 0/1)
        r["err"] = {e: abs(sep[e] - t[e]) for e in UNCOND}
        r["err"].update({k: abs(q - t[k]) for k, q in cond.items() if t[k] is not None})
        r["err_choice_cells"] = mean(abs(ch[k] - t[v]) for k, v in CELLS.items())
        r["err_noul_cells"] = mean(abs(sep[v] - t[v]) for v in CELLS.values())
        r["err_bundled"] = {e: abs(bun[e] - t[e]) for e in UNCOND}
        recs.append(r)
    with (OUT / "answers.jsonl").open("w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")

    # ---------- summary ----------
    fams = ["chance", "baserate", "policy"]
    by = {fm: [r for r in recs if r["family"] == fm] for fm in fams}

    def gstats(rs, key):
        v = sorted(r[key] for r in rs)
        return {"mean": mean(v), "median": v[len(v) // 2], "gt05": mean(x > 0.05 for x in v),
                "gt20": mean(x > 0.20 for x in v), "max": v[-1]}

    # baseline: the true probabilities plus independent noise sized to match Jev's own mean error in that family
    # (is Jev's incoherence more than its error level alone would produce?)
    nrng = random.Random(11)
    for fm in fams:
        rs = by[fm]
        sd = mean(v for r in rs for v in r["err"].values()) / 0.798  # E|N(0, sd)| = 0.798 sd
        for r in rs:
            t = r["truth"]
            noisy = {k: min(1.0, max(0.0, t[k] + nrng.gauss(0, sd))) for k in UNCOND + list(r["cond"])}
            r["g_matched"] = dutch_book([(k, None, noisy[k]) for k in UNCOND]
                                        + [(COND[k][0], COND[k][1], noisy[k]) for k in r["cond"]])
            r["matched_mae"] = mean(abs(noisy[k] - t[k]) for k in noisy)

    summary = {"n_sets": len(recs), "families": {}}
    g_rows = []
    keys = ["g_sep_all", "g_sep_unc", "g_bundled", "g_noise", "g_matched", "g_random"]
    for fm in fams:
        rs = by[fm]
        fs = {k: gstats(rs, k) for k in keys}
        summary["families"][fm] = {"dutch": fs, "matched_mae": mean(r["matched_mae"] for r in rs),
                                   "jev_mae": mean(v for r in rs for v in r["err"].values()),
                                   "tickets": 11 if fm != "policy" else 9}
        label = {"g_sep_all": "separate calls, all prices",
                 "g_sep_unc": "separate calls, 9 unconditional prices", "g_bundled": "one bundled call, same 9 prices",
                 "g_noise": "noise floor: same price asked twice",
                 "g_matched": f"truth + random noise of Jev's error size (mean error "
                              f"{summary['families'][fm]['matched_mae']:.3f} vs Jev {summary['families'][fm]['jev_mae']:.3f})",
                 "g_random": "random prices (baseline)"}
        for k in keys:
            if fm == "policy" and k == "g_sep_all":
                continue
            s = fs[k]
            g_rows.append([fm, label[k], f"${s['mean']:.3f}", f"${s['median']:.3f}", f"{s['gt05']:.0%}", f"{s['gt20']:.0%}",
                           f"${s['max']:.2f}"])

    # where the arbitrage comes from: Dutch book on subsets of prices, signed errors, Choice concentration
    src_rows = []
    subsets = {"A and ¬A only": ["A", "nA"], "the 4 joint cells only": ["AB", "AnB", "nAB", "nAnB"],
               "A, B, A∧B, A∨B only": ["A", "B", "AB", "AoB"]}
    for fm in fams:
        rs = by[fm]
        sub = {nm: mean(dutch_book([(k, None, r["sep"][k]) for k in ks]) for r in rs) for nm, ks in subsets.items()}
        sgn = {g: mean(r["sep"][k] - r["truth"][k] for r in rs for k in ks)
               for g, ks in {"atoms": ["A", "B"], "negations": ["nA", "nB"], "AND": ["AB"], "OR": ["AoB"],
                             "cells with ¬": ["AnB", "nAB", "nAnB"]}.items()}
        cmax = mean(max(r["choice"].values()) for r in rs)
        tmax = mean(max(r["truth"][v] for v in CELLS.values()) for r in rs)
        summary["families"][fm]["subsets"] = sub
        summary["families"][fm]["signed_error"] = sgn
        summary["families"][fm]["choice_top"] = {"jev": cmax, "truth": tmax}
        src_rows.append([fm] + [f"${sub[nm]:.3f}" for nm in subsets] + [f"{sgn[g]:+.3f}" for g in sgn]
                        + [f"{cmax:.2f} vs {tmax:.2f}"])

    chk_rows = []
    for fm in fams:
        rs = by[fm]
        c = {"complement |P(A)+P(¬A)−1|": mean(r["checks"]["complement"] for r in rs),
             "four cells: mean Σ": mean(r["checks"]["cells_sum"] for r in rs),
             "four cells: share with |Σ−1| > 0.1": mean(abs(r["checks"]["cells_sum"] - 1) > 0.1 for r in rs),
             "P(A∧B) > min(P(A),P(B)) + 0.05": mean(r["checks"]["and_gt_min"] for r in rs),
             "P(A∨B) < max(P(A),P(B)) − 0.05": mean(r["checks"]["or_lt_max"] for r in rs),
             "|P(A∨B) − (P(A)+P(B)−P(A∧B))|": mean(r["checks"]["incl_excl"] for r in rs),
             "|P(A) − (P(A∧B)+P(A∧¬B))|": mean(r["checks"]["decomp_A"] for r in rs)}
        if fm != "policy":
            c["|P(B|A)·P(A) − P(A∧B)|"] = mean(r["checks"]["product_BgA"] for r in rs)
            c["|P(A|B)·P(B) − P(B|A)·P(A)| (Bayes)"] = mean(r["checks"]["bayes"] for r in rs)
        summary["families"][fm]["checks"] = c
    names = list(summary["families"]["chance"]["checks"])
    for nm in names:
        chk_rows.append([nm] + [(f"{summary['families'][fm]['checks'][nm]:.3f}" if nm in summary["families"][fm]["checks"]
                                 else "—") for fm in fams])

    groups = {"atoms (A, B)": ["A", "B"], "negations": ["nA", "nB"], "AND": ["AB"], "OR": ["AoB"],
              "joint cells (with ¬)": ["AnB", "nAB", "nAnB"], "conditional B|A": ["BgA"], "conditional A|B": ["AgB"]}
    err_rows = []
    for gname, evs in groups.items():
        row = [gname]
        for fm in fams:
            vals = [r["err"][e] for r in by[fm] for e in evs if e in r["err"]]
            row.append(fmt3(mean(vals)) if vals else "—")
            summary["families"][fm].setdefault("mae", {})[gname] = mean(vals) if vals else None
        err_rows.append(row)
    err_rows.append(["joint cells via one Choice"] + [fmt3(mean(r["err_choice_cells"] for r in by[fm])) for fm in fams])
    err_rows.append(["joint cells via 4 separate Nouls"] + [fmt3(mean(r["err_noul_cells"] for r in by[fm])) for fm in fams])
    for fm in fams:
        summary["families"][fm]["mae"]["cells_choice"] = mean(r["err_choice_cells"] for r in by[fm])
        summary["families"][fm]["mae"]["cells_noul"] = mean(r["err_noul_cells"] for r in by[fm])

    # base-rate neglect: P(A|B) closer to the inverse P(B|A) than to the truth
    inv = [r for r in by["baserate"] if abs(r["truth"]["AgB"] - r["truth"]["BgA"]) > 0.2]
    neglect = [abs(r["cond"]["AgB"] - r["truth"]["BgA"]) < abs(r["cond"]["AgB"] - r["truth"]["AgB"]) for r in inv]
    summary["baserate_inverse_confusion"] = {"n": len(inv), "rate": mean(neglect) if neglect else None}
    fmt_rows = []
    for fmt_ in ["counts", "percent"]:
        rs = [r for r in by["baserate"] if r["format"] == fmt_]
        rs_inv = [r for r in inv if r["format"] == fmt_]
        conf_ = [abs(r["cond"]["AgB"] - r["truth"]["BgA"]) < abs(r["cond"]["AgB"] - r["truth"]["AgB"]) for r in rs_inv]
        fmt_rows.append([fmt_, len(rs), fmt3(mean(r["err"]["AgB"] for r in rs)), fmt3(mean(r["err"]["BgA"] for r in rs)),
                         f"{mean(conf_):.0%} of {len(rs_inv)}" if conf_ else "—", f"${mean(r['g_sep_all'] for r in rs):.3f}"])
        summary.setdefault("baserate_by_format", {})[fmt_] = {"mae_AgB": mean(r["err"]["AgB"] for r in rs),
                                                             "inverse_confusion": mean(conf_) if conf_ else None,
                                                             "g_mean": mean(r["g_sep_all"] for r in rs)}
    setup_rows = []
    for fm in ["chance", "baserate", "policy"]:
        for st in sorted({r["setup"] for r in by[fm]}):
            rs = [r for r in by[fm] if r["setup"] == st]
            setup_rows.append([fm, st, len(rs), f"${mean(r['g_sep_all'] for r in rs):.3f}",
                               fmt3(mean(mean(r["err"].values()) for r in rs))])
    depth_rows = []
    for d in (2, 3, 4, 5):
        rs = [r for r in by["policy"] if r["depth"] == d]
        depth_rows.append([d, len(rs), f"${mean(r['g_sep_unc'] for r in rs):.3f}",
                           f"{mean(r['g_sep_unc'] > 0.05 for r in rs):.0%}", fmt3(mean(r["err"]["A"] for r in rs))])
    summary["policy_by_depth"] = {r[0]: {"g_mean": r[2], "gt05": r[3]} for r in depth_rows}

    # worst example
    worst = max(recs, key=lambda r: r["g_sep_all"])
    ex = sets[worst["set"]]
    ex_rows = [[e, ex["questions"][e] if e in ex["questions"] else f"{COND[e][0]} given {COND[e][1]}",
                fmt3(worst["sep"][e]) if e in worst["sep"] else fmt3(worst["cond"][e]),
                fmt3(worst["truth"][e]) if worst["truth"].get(e) is not None else "—"]
               for e in UNCOND + (list(COND) if worst["cond"] else [])]
    summary["worst_set"] = {"set": worst["set"], "g": worst["g_sep_all"], "setup": worst["setup"]}

    md = (f"# E14 — Dutch-booking Jev (coherence of its probabilities as prices)\n\n{__doc__.strip()}\n\n"
          "### Guaranteed profit against Jev's prices (per set; each ticket at most $1)\n\n"
          + table(["family", "prices", "mean", "median", "sets > $0.05", "sets > $0.20", "max"], g_rows) + "\n\n"
          "### Where the arbitrage comes from\n\nDutch book on subsets of the separate-call prices; signed error = mean "
          "(price − true probability), positive = overpriced; last column = the Choice's top-cell probability vs the "
          "true top-cell probability.\n\n"
          + table(["family"] + list(subsets) + ["atoms", "negations", "AND", "OR", "cells with ¬",
                                                "Choice top cell (Jev vs truth)"], src_rows) + "\n\n"
          "### Coherence checks (means; separate calls)\n\n" + table(["check", "chance", "baserate", "policy"], chk_rows)
          + "\n\n### Error against the true probability (mean |price − truth|; policy truth is 0/1)\n\n"
          + table(["question", "chance", "baserate", "policy"], err_rows) + "\n\n"
          "### Base rates: counts vs percentages\n\nInverse confusion = P(A|B) lies closer to the true P(B|A) than to "
          "the true P(A|B) (sets where the two differ by more than 0.2).\n\n"
          + table(["format", "sets", "error P(A|B)", "error P(B|A)", "inverse confusion", "mean Dutch book"], fmt_rows)
          + "\n\n### By setup\n\n" + table(["family", "setup", "sets", "mean Dutch book (all prices)", "mean error"], setup_rows)
          + "\n\n### Policy family by rule depth\n\n"
          + table(["depth", "sets", "mean Dutch book (9 prices)", "sets > $0.05", "error on A"], depth_rows)
          + f"\n\n### Most exploitable set (#{worst['set']}, {worst['family']}/{worst['setup']}, "
            f"guaranteed profit ${worst['g_sep_all']:.2f})\n\nState: {ex['state']}\n\n"
          + table(["event", "question", "Jev price", "true probability"], ex_rows) + "\n")
    save_results(EXP, summary, md)


if __name__ == "__main__":
    main()
