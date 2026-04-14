"""
Run the Fano factor experiment on real IBM Quantum hardware.

Requires:
  - IBM Quantum account: https://quantum.ibm.com
  - API token saved via:
      from qiskit_ibm_runtime import QiskitRuntimeService
      QiskitRuntimeService.save_account(channel="ibm_quantum", token="<YOUR_TOKEN>")
  - Or set env var: IBM_QUANTUM_TOKEN=<token>

Usage:
  export IBM_QUANTUM_TOKEN=<your_token>
  ../.venv/bin/python experiments/run_hardware.py [--backend ibm_torino] [--shots 2000]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from repetition_code import build_repetition_code, parse_counts
from fano import full_report, print_report
from classifier import classifier_report, print_classifier_report


RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "hardware"


def get_service(token: str | None = None) -> QiskitRuntimeService:
    token = token or os.environ.get("IBM_QUANTUM_TOKEN")
    if token:
        return QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
    # Try saved credentials
    try:
        return QiskitRuntimeService(channel="ibm_quantum_platform")
    except Exception:
        print("ERROR: No IBM Quantum token found.")
        print("  Set IBM_QUANTUM_TOKEN env var, or save credentials with:")
        print("  QiskitRuntimeService.save_account(channel='ibm_quantum_platform', token='<TOKEN>')")
        sys.exit(1)


def get_backend(service: QiskitRuntimeService, name: str | None):
    if name:
        return service.backend(name)
    # Pick least-busy heavy-hex backend (127+ qubits)
    backend = service.least_busy(min_num_qubits=127, simulator=False)
    print(f"Selected backend: {backend.name}")
    return backend


def run_on_hardware(backend, d: int, T: int, shots: int) -> list:
    qc = build_repetition_code(d, T)
    print(f"  Circuit: d={d}, T={T}, depth={qc.depth()}, qubits={qc.num_qubits}")

    # Transpile to backend
    pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
    transpiled = pm.run(qc)
    print(f"  Transpiled depth: {transpiled.depth()}")

    # Submit
    sampler = Sampler(backend)
    job = sampler.run([transpiled], shots=shots)
    print(f"  Job ID: {job.job_id()} — waiting for results …")
    result = job.result()

    # SamplerV2 returns DataBin with BitArrays per register
    pub_result = result[0]
    data = pub_result.data
    syn_strings = data.s.get_bitstrings()  # list[str], each len = T*(d-1)
    fin_strings = data.f.get_bitstrings()  # list[str], each len = d

    # Build counts dict: "fin_bits syn_bits"
    counts = {}
    for syn, fin in zip(syn_strings, fin_strings):
        key = f"{fin} {syn}"
        counts[key] = counts.get(key, 0) + 1

    shots_data = parse_counts(counts, d, T)
    return shots_data, job.job_id()


def save_results(results: list[dict], backend_name: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"fano_{backend_name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved → {path}")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=None, help="IBM backend name")
    parser.add_argument("--token",   default=None, help="IBM Quantum API token")
    parser.add_argument("--shots",   type=int, default=2000)
    parser.add_argument("--T",       type=int, default=20, help="Syndrome rounds")
    parser.add_argument("--distances", nargs="+", type=int, default=[3, 5, 7])
    args = parser.parse_args()

    print("\n" + "="*55)
    print("  Merkabit Hardware Experiment")
    print("  Paper 3: The Rotation Gap Is Not An Error")
    print("="*55)

    service = get_service(args.token)
    backend = get_backend(service, args.backend)
    print(f"Backend: {backend.name}  (qubits: {backend.num_qubits})")

    all_results = []

    for d in args.distances:
        print(f"\n── d={d} repetition code ──────────────────────────")
        shots_data, job_id = run_on_hardware(backend, d=d, T=args.T, shots=args.shots)

        fano = full_report(shots_data, d=d, label=f"d={d} | {backend.name}")
        fano["job_id"]      = job_id
        fano["backend"]     = backend.name
        fano["T_rounds"]    = args.T
        print_report(fano)

        clf = classifier_report(shots_data, d=d)
        print_classifier_report(clf)

        all_results.append({"fano": fano, "classifier": clf})

    save_results(all_results, backend.name)

    # Print summary comparison vs paper
    print("\n── Comparison with Paper 3 claims ─────────────────")
    print(f"  Paper reports F = 0.856 ± 0.03  (t = −131)")
    for r in all_results:
        f = r["fano"]
        direction = "✓ sub-Poissonian" if f["sub_poissonian"] else "✗ not sub-Poissonian"
        print(f"  d={f['d']}: F = {f['fano_factor']:.4f} ± {f['fano_se']:.4f}  → {direction}")
    print(f"\n  Paper reports 7–19% LER improvement from classifier.")
    for r in all_results:
        c = r["classifier"]
        tag = "✓" if c["classifier_helps"] else "✗"
        print(f"  d={c['d']}: {c['improvement_pct']:+.1f}%  {tag}")


if __name__ == "__main__":
    main()
