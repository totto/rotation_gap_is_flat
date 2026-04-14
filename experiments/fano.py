"""
Fano factor analysis for syndrome data.

F = Var(n) / Mean(n) where n = total syndrome activations per shot.

F < 1  → sub-Poissonian (anti-bunched) — ternary signal claim
F = 1  → Poisson (independent errors) — standard noise model
F > 1  → super-Poissonian (bunched) — correlated errors (e.g. Willow)
"""

import numpy as np
from scipy import stats


def syndrome_counts_per_shot(shots_data: list) -> np.ndarray:
    """Total number of syndrome activations per shot."""
    return np.array([
        sum(b for round_ in shot for b in round_)
        for shot in shots_data
    ])


def fano_factor(counts: np.ndarray) -> tuple[float, float]:
    """
    Compute Fano factor and its standard error.

    SE(F) via delta method: SE(F) ≈ F * sqrt(1/(2*(n-1)) + 1/n)
    where n = number of shots.
    """
    n = len(counts)
    mean = np.mean(counts)
    var  = np.var(counts, ddof=1)
    F    = var / mean
    se   = F * np.sqrt(1 / (2 * (n - 1)) + 1 / n)
    return F, se


def poisson_ttest(counts: np.ndarray) -> tuple[float, float]:
    """
    One-sample t-test: is Fano factor significantly different from 1?

    Under H0 (Poisson), Var(n) = Mean(n), so we test var/mean = 1.
    Equivalently: test that (counts - mean) has variance = mean.

    Returns (t_statistic, p_value).
    """
    n    = len(counts)
    mean = np.mean(counts)
    var  = np.var(counts, ddof=1)
    # t = (F - 1) / SE(F)
    F, se = fano_factor(counts)
    t = (F - 1.0) / se
    p = 2 * stats.t.sf(abs(t), df=n - 1)
    return t, p


def burst_analysis(shots_data: list, d: int) -> dict:
    """
    Identify multi-ancilla syndrome events (bursts) and check scaling.

    A burst = shot where >=2 ancillas fire simultaneously in the same round.
    Perimeter scaling (paper claim): burst count ∝ d (boundary nodes).
    Area scaling (alternative): burst count ∝ d^2.
    """
    bursts = 0
    total_shots = len(shots_data)

    for shot in shots_data:
        for round_ in shot:
            if sum(round_) >= 2:
                bursts += 1

    return {
        "d": d,
        "total_shots": total_shots,
        "burst_events": bursts,
        "burst_rate": bursts / total_shots,
    }


def spatial_correlation(shots_data: list, d: int) -> float:
    """
    Mean pairwise correlation between neighboring ancilla syndrome rates.
    Positive = bunched (Willow), negative = anti-bunched (IBM claim).
    """
    n_anc = d - 1
    if n_anc < 2:
        return 0.0

    # For each ancilla, collect its activation sequence across all rounds/shots
    sequences = [[] for _ in range(n_anc)]
    for shot in shots_data:
        for round_ in shot:
            for i, b in enumerate(round_):
                sequences[i].append(b)

    correlations = []
    for i in range(n_anc - 1):
        a = np.array(sequences[i])
        b = np.array(sequences[i + 1])
        if a.std() > 0 and b.std() > 0:
            correlations.append(np.corrcoef(a, b)[0, 1])

    return float(np.mean(correlations)) if correlations else 0.0


def full_report(shots_data: list, d: int, label: str = "") -> dict:
    """Run all analyses and return a summary dict."""
    counts = syndrome_counts_per_shot(shots_data)
    F, se  = fano_factor(counts)
    t, p   = poisson_ttest(counts)
    bursts = burst_analysis(shots_data, d)
    corr   = spatial_correlation(shots_data, d)

    report = {
        "label":            label or f"d={d}",
        "d":                d,
        "n_shots":          len(shots_data),
        "mean_syndromes":   float(np.mean(counts)),
        "fano_factor":      round(F, 4),
        "fano_se":          round(se, 4),
        "t_vs_poisson":     round(t, 2),
        "p_value":          float(p),
        "sub_poissonian":   F < 1.0,
        "burst_rate":       round(bursts["burst_rate"], 4),
        "spatial_corr":     round(corr, 4),
        "ternary_fraction": round(max(0.0, 1.0 - F), 4),  # f = 1 - F (paper's formula)
    }
    return report


def print_report(report: dict) -> None:
    tag = "SUB-POISSONIAN ✓" if report["sub_poissonian"] else "Poissonian or super"
    print(f"\n{'='*55}")
    print(f"  {report['label']}  ({report['n_shots']} shots)")
    print(f"{'='*55}")
    print(f"  Fano factor F       = {report['fano_factor']:.4f} ± {report['fano_se']:.4f}")
    print(f"  t vs Poisson        = {report['t_vs_poisson']:.1f}  (p={report['p_value']:.2e})")
    print(f"  Regime              → {tag}")
    print(f"  Ternary fraction f  = {report['ternary_fraction']:.4f}  (paper: ~0.144)")
    print(f"  Burst rate          = {report['burst_rate']:.4f}")
    print(f"  Spatial correlation = {report['spatial_corr']:.4f}  (paper IBM: negative)")
    print(f"{'='*55}")
