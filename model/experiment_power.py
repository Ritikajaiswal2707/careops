"""Unadjusted two-arm sample-size sensitivity for the proposed CareOps RCT.

Uses a normal approximation for two independent proportions. Counts are
planning estimates only; repeated patients, exclusions, missing outcomes,
and operational capacity can increase recruitment needs.
"""
from __future__ import annotations

import argparse
import math
from statistics import NormalDist

DEFAULT_FLAGGED_BASELINE = 212 / 631
DEFAULT_TOTAL_APPOINTMENTS_PER_MONTH = 3333
DEFAULT_FLAGGED_SHARE = 0.20
DEFAULT_RELATIVE_REDUCTIONS = (0.10, 0.15, 0.20, 0.25)


def sample_size_per_arm(
    control_rate: float,
    relative_reduction: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """Return approximate participants per arm for a two-sided proportion test.

    Parameters use a *relative* risk reduction: treatment_rate = control_rate
    * (1 - relative_reduction). This is an unclustered appointment-level plan.
    """
    if not 0 < control_rate < 1:
        raise ValueError("control_rate must be between 0 and 1")
    if not 0 < relative_reduction < 1:
        raise ValueError("relative_reduction must be between 0 and 1")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")

    treatment_rate = control_rate * (1 - relative_reduction)
    pooled = (control_rate + treatment_rate) / 2
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power = normal.inv_cdf(power)
    numerator = (
        z_alpha * math.sqrt(2 * pooled * (1 - pooled))
        + z_power * math.sqrt(
            control_rate * (1 - control_rate)
            + treatment_rate * (1 - treatment_rate)
        )
    ) ** 2
    return math.ceil(numerator / ((control_rate - treatment_rate) ** 2))


def sensitivity_table(
    *,
    baseline: float = DEFAULT_FLAGGED_BASELINE,
    total_appointments_per_month: int = DEFAULT_TOTAL_APPOINTMENTS_PER_MONTH,
    flagged_share: float = DEFAULT_FLAGGED_SHARE,
    relative_reductions=DEFAULT_RELATIVE_REDUCTIONS,
    alpha: float = 0.05,
    power: float = 0.80,
) -> list[dict]:
    if total_appointments_per_month <= 0:
        raise ValueError("total_appointments_per_month must be positive")
    if not 0 < flagged_share <= 1:
        raise ValueError("flagged_share must be in (0, 1]")
    eligible_per_month = total_appointments_per_month * flagged_share
    rows = []
    for reduction in relative_reductions:
        per_arm = sample_size_per_arm(baseline, reduction, alpha=alpha, power=power)
        total = per_arm * 2
        rows.append({
            "relative_reduction": reduction,
            "control_rate": baseline,
            "treatment_rate": baseline * (1 - reduction),
            "per_arm": per_arm,
            "total": total,
            "eligible_per_month": round(eligible_per_month),
            "months": total / eligible_per_month,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=float, default=DEFAULT_FLAGGED_BASELINE)
    parser.add_argument("--monthly-appointments", type=int, default=DEFAULT_TOTAL_APPOINTMENTS_PER_MONTH)
    parser.add_argument("--flagged-share", type=float, default=DEFAULT_FLAGGED_SHARE)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--power", type=float, default=0.80)
    args = parser.parse_args()

    rows = sensitivity_table(
        baseline=args.baseline,
        total_appointments_per_month=args.monthly_appointments,
        flagged_share=args.flagged_share,
        alpha=args.alpha,
        power=args.power,
    )
    eligible = round(args.monthly_appointments * args.flagged_share)
    print(f"Control baseline: {args.baseline:.1%}")
    print(f"Eligible volume: {eligible} appointments/month (synthetic volume estimate)")
    print(f"Two-sided alpha: {args.alpha}; power: {args.power:.0%}")
    print("Relative reduction | treatment rate | per arm | total | months (unadjusted)")
    for row in rows:
        print(
            f"{row['relative_reduction']:>17.0%} | {row['treatment_rate']:>14.1%} | "
            f"{row['per_arm']:>7,} | {row['total']:>5,} | {row['months']:>5.2f}"
        )
    print("\nPlanning estimates only; no experiment has been run.")
    print("No adjustment for repeat patients, attrition, or unavailable outcomes is included.")


if __name__ == "__main__":
    main()
