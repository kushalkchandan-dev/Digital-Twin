"""
Network Topology Module
Defines the 10-node network graph with links and initial properties.
"""

import networkx as nx

def create_topology():
    """
    Creates a 10-node network topology representing a mix of:
    - Core routers (nodes 0-2)
    - Edge routers (nodes 3-5)
    - Access switches (nodes 6-9)
    
    Returns a NetworkX DiGraph with node/link attributes.
    """
    G = nx.DiGraph()

    # --- Define Nodes ---
    nodes = [
        {"id": 0, "type": "core",   "label": "Core-R1",   "cpu_capacity": 100, "bandwidth_capacity": 10000},
        {"id": 1, "type": "core",   "label": "Core-R2",   "cpu_capacity": 100, "bandwidth_capacity": 10000},
        {"id": 2, "type": "core",   "label": "Core-R3",   "cpu_capacity": 100, "bandwidth_capacity": 10000},
        {"id": 3, "type": "edge",   "label": "Edge-R1",   "cpu_capacity": 80,  "bandwidth_capacity": 5000},
        {"id": 4, "type": "edge",   "label": "Edge-R2",   "cpu_capacity": 80,  "bandwidth_capacity": 5000},
        {"id": 5, "type": "edge",   "label": "Edge-R3",   "cpu_capacity": 80,  "bandwidth_capacity": 5000},
        {"id": 6, "type": "access", "label": "Access-SW1","cpu_capacity": 50,  "bandwidth_capacity": 1000},
        {"id": 7, "type": "access", "label": "Access-SW2","cpu_capacity": 50,  "bandwidth_capacity": 1000},
        {"id": 8, "type": "access", "label": "Access-SW3","cpu_capacity": 50,  "bandwidth_capacity": 1000},
        {"id": 9, "type": "access", "label": "Access-SW4","cpu_capacity": 50,  "bandwidth_capacity": 1000},
    ]

    for n in nodes:
        G.add_node(n["id"],
                   type=n["type"],
                   label=n["label"],
                   cpu_capacity=n["cpu_capacity"],
                   bandwidth_capacity=n["bandwidth_capacity"],
                   status="up")

    # --- Define Links (bidirectional) ---
    edges = [
        # Core mesh
        (0, 1, 1000, 2),   (1, 0, 1000, 2),
        (1, 2, 1000, 2),   (2, 1, 1000, 2),
        (0, 2, 1000, 2),   (2, 0, 1000, 2),
        # Core → Edge
        (0, 3, 500, 5),    (3, 0, 500, 5),
        (1, 4, 500, 5),    (4, 1, 500, 5),
        (2, 5, 500, 5),    (5, 2, 500, 5),
        # Edge cross-links
        (3, 4, 300, 8),    (4, 3, 300, 8),
        (4, 5, 300, 8),    (5, 4, 300, 8),
        # Edge → Access
        (3, 6, 100, 10),   (6, 3, 100, 10),
        (3, 7, 100, 10),   (7, 3, 100, 10),
        (4, 8, 100, 10),   (8, 4, 100, 10),
        (5, 9, 100, 10),   (9, 5, 100, 10),
    ]

    for src, dst, bw, lat in edges:
        G.add_edge(src, dst,
                   bandwidth=bw,         # Mbps max
                   base_latency=lat,     # ms base
                   status="up",
                   utilization=0.0)

    return G


def get_all_paths(G, src, dst):
    """Returns all simple paths between src and dst."""
    try:
        return list(nx.all_simple_paths(G, src, dst, cutoff=5))
    except nx.NetworkXNoPath:
        return []


def get_node_labels(G):
    return {n: G.nodes[n]["label"] for n in G.nodes}
