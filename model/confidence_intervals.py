"""
95% Wilson confidence intervals for the headline evaluation numbers.

    python model/confidence_intervals.py

Small test sets give wide intervals. This makes that visible next to every
headline number instead of letting "97.4%" read as more certain than it is.
"""
import math


def wilson(successes, n, z=1.96):
    """Wilson score interval for a proportion; well-behaved near 0% and 100%."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


HEADLINES = [
    ("Rule-based parser alone (103-message set)", 55, 103),
    ("gpt-oss-120b, prompt v1, fresh 39-message holdout", 30, 39),
    ("gpt-oss-120b, prompt v2, fresh 39-message holdout", 37, 39),
    ("gpt-oss-120b, prompt v3, fresh 39-message holdout", 38, 39),
    ("gpt-oss-20b, prompt v3, fresh 39-message holdout", 36, 39),
    ("Recovery agent, correct dispositions (30-case holdout)", 25, 30),
]

if __name__ == "__main__":
    print(f"{'Result':58} {'Point':>7}   95% interval")
    for name, k, n in HEADLINES:
        lo, hi = wilson(k, n)
        print(f"{name:58} {k / n:7.1%}   {lo:.1%} to {hi:.1%}   ({k}/{n})")
    lo, hi = wilson(0, 30)
    print(f"{'Wrong or invented vitals reaching a family (30 notes)':58} {0:7.1%}   {lo:.1%} to {hi:.1%}   (0/30)")
