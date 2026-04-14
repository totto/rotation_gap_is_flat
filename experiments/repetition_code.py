"""
Build repetition code circuits for Fano factor measurement.

A distance-d repetition code with T syndrome rounds gives us the raw
syndrome data needed to measure sub-Poissonian statistics (F < 1).
"""

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister


def build_repetition_code(d: int, T: int) -> QuantumCircuit:
    """
    Distance-d repetition code protecting logical |0>.
    d data qubits, (d-1) ancilla qubits, T rounds of syndrome extraction.

    Returns a circuit whose classical bits are laid out as:
      [T*(d-1) syndrome bits] [d final data bits]
    """
    data = QuantumRegister(d, "d")
    anc  = QuantumRegister(d - 1, "a")
    # T rounds of (d-1) syndrome bits, then d final readout bits
    syn  = ClassicalRegister(T * (d - 1), "s")
    fin  = ClassicalRegister(d, "f")

    qc = QuantumCircuit(data, anc, syn, fin)

    # Logical |0>: all data qubits start in |0> (default) — nothing needed

    for t in range(T):
        offset = t * (d - 1)
        # Parity checks: ancilla i measures data[i] XOR data[i+1]
        for i in range(d - 1):
            qc.cx(data[i],     anc[i])
            qc.cx(data[i + 1], anc[i])
            qc.measure(anc[i], syn[offset + i])
            qc.reset(anc[i])

    # Final data readout
    qc.measure(data, fin)

    return qc


def parse_counts(counts: dict, d: int, T: int) -> list[list[list[int]]]:
    """
    Parse Qiskit counts dict into structured syndrome arrays.

    Returns list[shots] of list[rounds] of list[ancilla bits].
    Qiskit orders bits right-to-left in bitstrings; we reverse to get
    natural left-to-right ordering (ancilla 0 first).
    """
    shots_data = []
    n_syn = T * (d - 1)

    for bitstring, freq in counts.items():
        # Qiskit bitstring: "fin_bits syn_bits" (space-separated registers)
        # Both are right-to-left; strip spaces and split
        parts = bitstring.split()
        # parts[0] = fin register, parts[1] = syn register (or merged if no space)
        if len(parts) == 2:
            syn_str = parts[1][::-1]   # reverse → ancilla-0 first
        else:
            # single string: last n_syn bits are syndrome
            syn_str = parts[0][::-1]

        syn_str = syn_str[:n_syn]  # trim to syndrome bits

        rounds = []
        for t in range(T):
            start = t * (d - 1)
            round_bits = [int(b) for b in syn_str[start:start + (d - 1)]]
            rounds.append(round_bits)

        for _ in range(freq):
            shots_data.append(rounds)

    return shots_data
