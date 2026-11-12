"""
Reliability (calibration) plot for the disruption-risk model on its time-based test set.

    python model/calibration_plot.py

Writes docs/media/calibration.png and prints the Brier score and per-bin numbers.
A well-calibrated model sits on the diagonal: of visits given 30% risk, about 30%
are actually disrupted. This complements ROC-AUC (ranking) with honesty about levels.
"""
import os
import sys

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from disruption_model import y_proba, y_test  # noqa: E402

OUT = os.path.join(BASE_DIR, "..", "docs", "media", "calibration.png")


def reliability(proba, actual, bins=8):
    """Equal-count bins: (mean predicted, observed rate, count) per bin."""
    order = np.argsort(proba)
    rows = []
    for chunk in np.array_split(order, bins):
        rows.append((float(proba[chunk].mean()), float(actual[chunk].mean()), int(len(chunk))))
    return rows


def main():
    proba, actual = np.asarray(y_proba), np.asarray(y_test).astype(float)
    rows = reliability(proba, actual)
    brier = float(np.mean((proba - actual) ** 2))
    base = float(np.mean((actual.mean() - actual) ** 2))
    print(f"Brier score {brier:.4f} (always predicting the base rate: {base:.4f})")
    for p, o, n in rows:
        print(f"  predicted {p:5.1%}   observed {o:5.1%}   n={n}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=150)
    lim = max(max(p for p, _, _ in rows), max(o for _, o, _ in rows)) * 1.15
    ax.plot([0, lim], [0, lim], color="#9aa9a6", linewidth=1, linestyle="--", label="Perfect calibration")
    ax.plot([p for p, _, _ in rows], [o for _, o, _ in rows], marker="o", color="#1e6b63", linewidth=2,
            label="Risk model (8 equal-size groups)")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Predicted disruption risk")
    ax.set_ylabel("Observed disruption rate")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title(f"Disruption-risk model calibration (test set, n={len(actual)})\nBrier {brier:.3f} vs {base:.3f} for the base rate",
                 fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT)
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
