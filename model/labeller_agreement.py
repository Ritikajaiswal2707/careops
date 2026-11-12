"""
Agreement between two people labelling the same messages (Cohen's kappa).

    python model/labeller_agreement.py data/evaluation/intent_holdout_v2.json second_labels.json

The second file is a JSON list of {"id": ..., "intent": ...} written by a second
person who labelled the holdout messages without seeing the first labels. Every
headline accuracy in this project rests on one person's labels; kappa says how
much to trust them. Roughly: above 0.8 strong, 0.6 to 0.8 substantial, below 0.6
the labels themselves need work before model accuracy means much.
"""
import json
import sys
from collections import Counter


def cohens_kappa(a, b):
    """Kappa for two equal-length label lists."""
    n = len(a)
    if n == 0:
        raise ValueError("no overlapping items")
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def load(path):
    data = json.load(open(path, encoding="utf-8"))
    items = data["cases"] if isinstance(data, dict) and "cases" in data else data
    return {str(x["id"]): x.get("intent") or x.get("expected_intent") for x in items}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    first, second = load(sys.argv[1]), load(sys.argv[2])
    ids = sorted(set(first) & set(second))
    a, b = [first[i] for i in ids], [second[i] for i in ids]
    disagree = [(i, x, y) for i, x, y in zip(ids, a, b) if x != y]
    print(f"items labelled by both: {len(ids)}")
    print(f"raw agreement:          {1 - len(disagree) / len(ids):.1%}")
    print(f"Cohen's kappa:          {cohens_kappa(a, b):.2f}")
    for i, x, y in disagree:
        print(f"  {i}: {x} vs {y}")
