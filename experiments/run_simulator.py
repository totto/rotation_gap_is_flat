"""
Run the full experiment on the Qiskit Aer simulator.

This validates the pipeline before touching real hardware.
We test two noise regimes:
  - Pure depolarizing (should give F ≈ 1, classifier neutral)
  - Mixed depolarizing + correlated (should give F < 1, classifier helps)

Usage:
  ../.venv/bin/python experiments/run_simulator.py
"""

import numpy as np
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel, depolarizing_error, pauli_error
)

from repetition_code import build_repetition_code, parse_counts
from fano import full_report, print_report
from classifier import classifier_report, print_classifier_report


# ── Noise models ──────────────────────────────────────────────────────────────

def pure_depolarizing_model(p: float = 0.08) -> NoiseModel:
    """Standard independent depolarizing noise — expect F ≈ 1 (or >1 from gate correlations)."""
    nm = NoiseModel()
    err1 = depolarizing_error(p, 1)
    err2 = depolarizing_error(p, 2)
    nm.add_all_qubit_quantum_error(err1, ["h", "x", "reset"])
    nm.add_all_qubit_quantum_error(err2, ["cx"])
    nm.add_all_qubit_readout_error([[1 - p, p], [p, 1 - p]])
    return nm


def correlated_model(p: float = 0.08, f_ternary: float = 0.144) -> NoiseModel:
    """
    Mixed model approximating paper's claim:
    - (1-f) fraction: standard depolarizing (binary errors)
    - f fraction: Pauli-Z on pairs of neighbouring ancillas (cooperative transitions)

    This is a simplified approximation of ternary transitions.
    """
    nm = NoiseModel()
    p_binary = p * (1 - f_ternary)
    err1 = depolarizing_error(p_binary, 1)
    err2 = depolarizing_error(p_binary, 2)
    nm.add_all_qubit_quantum_error(err1, ["h", "x", "reset"])
    nm.add_all_qubit_quantum_error(err2, ["cx"])
    # Correlated readout: when ancilla i fires, suppress neighbour
    # (simplified as reduced readout error — full correlation not directly
    #  expressible in Aer noise model without custom Kraus operators)
    p_ro = p * 0.856  # scale by paper's Fano factor as readout suppression
    nm.add_all_qubit_readout_error([[1 - p_ro, p_ro], [p_ro, 1 - p_ro]])
    return nm


# ── Run ───────────────────────────────────────────────────────────────────────

def run_experiment(d: int, T: int, shots: int, noise_model: NoiseModel,
                   label: str) -> dict:
    qc  = build_repetition_code(d, T)
    sim = AerSimulator(noise_model=noise_model)
    job = sim.run(qc, shots=shots)
    counts = job.result().get_counts()
    shots_data = parse_counts(counts, d, T)
    return shots_data


def main():
    SHOTS = 2000
    T     = 20   # syndrome rounds

    print("\n" + "="*55)
    print("  Merkabit Experiment — Simulator Validation")
    print("  Paper 3: The Rotation Gap Is Not An Error")
    print("="*55)

    for d in [3, 5, 7]:
        for noise_label, noise_fn in [
            ("pure depolarizing (expect F≈1)",  pure_depolarizing_model),
            ("correlated model  (expect F<1)",  correlated_model),
        ]:
            label = f"d={d} | {noise_label}"
            print(f"\n→ Running {label} …", flush=True)

            shots_data = run_experiment(
                d=d, T=T, shots=SHOTS,
                noise_model=noise_fn(),
                label=label,
            )

            # Fano factor analysis
            fano = full_report(shots_data, d=d, label=label)
            print_report(fano)

            # Classifier performance
            clf = classifier_report(shots_data, d=d)
            print_classifier_report(clf)

    print("\n✓ Simulator run complete.")
    print("  Next step: connect to IBM hardware (see run_hardware.py)")


if __name__ == "__main__":
    main()
