"""Map ibm_fez heavy-hex topology to hexagonal Eisenstein cells."""

import json, warnings
warnings.filterwarnings('ignore')
import networkx as nx
from collections import Counter

with open('outputs/ibm_fez_coupling_map.json') as f:
    edges = json.load(f)

G = nx.Graph()
G.add_edges_from(edges)

deg = dict(G.degree())
d3 = [n for n, d in deg.items() if d == 3]
d2 = [n for n, d in deg.items() if d == 2]
print(f'Degree-3 (lattice vertices): {len(d3)}')
print(f'Degree-2 (edge qubits):      {len(d2)}')

# Build vertex graph: degree-3 nodes connected if linked via a degree-2 node
Gv = nx.Graph()
Gv.add_nodes_from(d3)
for v in d3:
    for nb in G.neighbors(v):
        if deg[nb] == 2:
            for nb2 in G.neighbors(nb):
                if nb2 != v and deg[nb2] == 3:
                    Gv.add_edge(v, nb2)

vdeg = Counter(dict(Gv.degree()).values())
print(f'\nVertex graph: {Gv.number_of_nodes()} nodes, {Gv.number_of_edges()} edges')
print(f'Vertex degree distribution: {dict(sorted(vdeg.items()))}')

# Find hexagonal 6-cycles in vertex graph
hex6v = [c for c in nx.simple_cycles(Gv) if len(c) == 6]
print(f'Hexagonal 6-cycles in vertex graph: {len(hex6v)}')

if hex6v:
    h = hex6v[0]
    print(f'\nFirst hexagon (degree-3 qubits): {h}')

    # Find the degree-2 mediator qubit for each edge
    edge_qubits = []
    for i in range(len(h)):
        a, b = h[i], h[(i+1) % 6]
        for nb in G.neighbors(a):
            if deg[nb] == 2 and b in G.neighbors(nb):
                edge_qubits.append(nb)
                break

    print(f'Edge (degree-2) qubits:  {edge_qubits}')
    plaquette = sorted(set(h) | set(edge_qubits))
    print(f'Full 12-qubit plaquette: {plaquette}')

    # Find a central degree-3 qubit for a 7-vertex Eisenstein cell
    # Central = degree-3 node adjacent to 3+ nodes of the hexagon in Gv
    candidates = {}
    for v in d3:
        if v in h:
            continue
        count = sum(1 for nb in Gv.neighbors(v) if nb in h)
        if count >= 2:
            candidates[v] = count

    print(f'\nDegree-3 nodes adjacent to 2+ hexagon vertices: {candidates}')
    if candidates:
        center = max(candidates, key=candidates.get)
        seven = sorted(set(h) | {center})
        print(f'Best 7-vertex cell: {seven}')

    # Also: find all 12-cycles in the original graph (full plaquettes)
    # These are the physical hexagonal loops
    print('\nSearching for 12-cycles in physical coupling graph...')
    c12 = [c for c in nx.simple_cycles(G) if len(c) == 12]
    print(f'12-cycles found: {len(c12)}')
    if c12:
        print(f'First 12-cycle: {sorted(c12[0])}')

    # Save the best cell for circuit construction
    cell_info = {
        'hexagon_vertices': h,
        'edge_qubits': edge_qubits,
        'plaquette_12': plaquette,
        'all_hexagons': hex6v[:5],
    }
    with open('outputs/ibm_fez_cells.json', 'w') as f:
        json.dump(cell_info, f, indent=2)
    print('\nSaved cell info → outputs/ibm_fez_cells.json')
