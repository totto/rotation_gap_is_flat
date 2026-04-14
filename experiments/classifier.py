"""
Regime classifier: identify ternary (T75) syndrome events and abstain
from correcting them, leaving standard decoder to handle B31 (binary) errors.

Based on Paper 3, Table 2: five structural features, threshold θ = 0.3.
"""

import numpy as np


def compute_z3_chirality(ancilla_idx: int, d: int) -> int:
    """
    Z3 sublattice assignment for ancilla i in a distance-d repetition code.

    In a 1D repetition code the 'chirality' maps to position mod 3:
      0 → ω^0 (trivial)
      1 → ω^1
      2 → ω^2

    For a 2D surface code this would be derived from the (row, col)
    position in the heavy-hex lattice. In 1D we approximate.
    """
    return ancilla_idx % 3  # ∈ {0, 1, 2}


def classify_syndromes(
    shots_data: list,
    d: int,
    theta: float = 0.3,
) -> list[list[list[bool]]]:
    """
    For each shot × round × ancilla, return True if classified as ternary
    (should NOT be corrected by the decoder).

    shots_data: list[shots] of list[rounds] of list[ancilla bits]
    Returns same shape, boolean mask.
    """
    n_anc = d - 1
    boundary = {0, n_anc - 1}           # leftmost and rightmost ancillas

    # Global syndrome rate across all shots/rounds per ancilla
    activations = [[] for _ in range(n_anc)]
    for shot in shots_data:
        for round_ in shot:
            for i, b in enumerate(round_):
                activations[i].append(b)
    global_rate = np.array([np.mean(a) for a in activations])
    global_mean = global_rate.mean() if global_rate.mean() > 0 else 1e-9

    # Build classification mask
    masks = []
    for shot in shots_data:
        shot_mask = []
        T = len(shot)
        for t, round_ in enumerate(shot):
            round_mask = []
            # Local density: fraction of ancillas firing this round
            local_density = sum(round_) / n_anc

            for i, b in enumerate(round_):
                if b == 0:
                    round_mask.append(False)
                    continue

                # --- Feature 1: Isolation ---
                # No immediate neighbor also fired this round
                left_fired  = (i > 0)       and round_[i - 1] == 1
                right_fired = (i < n_anc-1) and round_[i + 1] == 1
                isolation = 1.0 if not (left_fired or right_fired) else 0.0

                # --- Feature 2: Boundary status ---
                boundary_score = 1.0 if i in boundary else 0.0

                # --- Feature 3: Density contrast ---
                anc_rate = global_rate[i] if global_rate[i] > 0 else 1e-9
                density_contrast = max(0.0, 1.0 - local_density / global_mean)

                # --- Feature 4: Chirality ---
                chir = compute_z3_chirality(i, d)
                chirality_score = 1.0 if chir != 0 else 0.0  # non-trivial sublattice

                # --- Feature 5: Temporal consistency (sporadic = ternary) ---
                # Look at a ±2 round window; ternary events are sporadic (low persistence)
                window = []
                for dt in range(-2, 3):
                    tt = t + dt
                    if 0 <= tt < T:
                        window.append(shot[tt][i])
                persistence = sum(window) / len(window) if window else 0.0
                sporadic_score = 1.0 - persistence  # high sporadic → high ternary score

                score = np.mean([
                    isolation,
                    boundary_score,
                    density_contrast,
                    chirality_score,
                    sporadic_score,
                ])

                round_mask.append(score > theta)

            shot_mask.append(round_mask)
        masks.append(shot_mask)

    return masks


def majority_vote_decode(shot: list) -> int:
    """
    Simple majority-vote decoder for repetition code.
    Returns 0 or 1 (logical bit).

    Strategy: each ancilla firing marks a domain boundary between data qubits.
    We count how many times each data qubit is implied to be flipped across
    all rounds, then take majority vote.
    """
    T   = len(shot)
    if T == 0:
        return 0
    n_anc = len(shot[0])
    n_data = n_anc + 1

    # flip_count[i] = number of rounds where data qubit i is implied flipped
    flip_count = [0] * n_data

    for round_ in shot:
        # Running parity: a data qubit is flipped if an odd number of
        # syndrome events lie to its left
        running = 0
        for i in range(n_anc):
            running ^= round_[i]
            # data qubit i+1 is between ancilla i and i+1
            flip_count[i + 1] += running

    # Data qubit i is corrected-to-1 if flip_count[i] > T/2
    corrected = [1 if flip_count[i] > T / 2 else 0 for i in range(n_data)]

    # Logical |0> = all data qubits agree on 0; logical error if majority are 1
    return 1 if sum(corrected) > n_data / 2 else 0


def decode_with_classifier(
    shots_data: list,
    d: int,
    theta: float = 0.3,
) -> tuple[list[int], list[int]]:
    """
    Decode all shots with and without the classifier.

    Returns (standard_logicals, classifier_logicals) — logical bit per shot.
    Classifier version: zero out syndrome bits classified as ternary before
    passing to the decoder (abstain from correcting those events).
    """
    masks = classify_syndromes(shots_data, d, theta)

    standard_logicals   = []
    classifier_logicals = []

    for shot, mask in zip(shots_data, masks):
        # Standard: decode all syndromes
        standard_logicals.append(majority_vote_decode(shot))

        # Classifier: mask out ternary events
        filtered = [
            [b if not mask[t][i] else 0 for i, b in enumerate(round_)]
            for t, round_ in enumerate(shot)
        ]
        classifier_logicals.append(majority_vote_decode(filtered))

    return standard_logicals, classifier_logicals


def logical_error_rate(logicals: list[int], true_logical: int = 0) -> float:
    """LER = fraction of shots where decoded logical ≠ true logical."""
    errors = sum(1 for l in logicals if l != true_logical)
    return errors / len(logicals) if logicals else 0.0


def classifier_report(shots_data: list, d: int, theta: float = 0.3) -> dict:
    """Run both decoders and summarise."""
    std, clf = decode_with_classifier(shots_data, d, theta)
    ler_std = logical_error_rate(std)
    ler_clf = logical_error_rate(clf)
    delta   = ler_std - ler_clf
    improvement = (delta / ler_std * 100) if ler_std > 0 else 0.0

    # Count how many ternary classifications were made
    masks = classify_syndromes(shots_data, d, theta)
    total_flags   = sum(b for shot in shots_data for r in shot for b in r)
    ternary_flags = sum(
        1
        for shot_mask in masks
        for round_mask in shot_mask
        for is_ternary in round_mask
        if is_ternary
    )

    return {
        "d":                    d,
        "theta":                theta,
        "ler_standard":         round(ler_std, 5),
        "ler_classifier":       round(ler_clf, 5),
        "ler_delta":            round(delta, 5),
        "improvement_pct":      round(improvement, 2),
        "classifier_helps":     delta > 0,
        "total_syndrome_flags": total_flags,
        "ternary_classified":   ternary_flags,
        "ternary_pct":          round(ternary_flags / total_flags * 100, 1) if total_flags else 0.0,
    }


def print_classifier_report(r: dict) -> None:
    tag = "CLASSIFIER HELPS ✓" if r["classifier_helps"] else "no improvement"
    print(f"\n{'='*55}")
    print(f"  Classifier report  d={r['d']}  θ={r['theta']}")
    print(f"{'='*55}")
    print(f"  LER standard        = {r['ler_standard']:.5f}")
    print(f"  LER + classifier    = {r['ler_classifier']:.5f}")
    print(f"  Improvement         = {r['improvement_pct']:+.1f}%  → {tag}")
    print(f"  Flags classified    = {r['ternary_classified']}/{r['total_syndrome_flags']} "
          f"({r['ternary_pct']}% of syndromes)")
    print(f"{'='*55}")
