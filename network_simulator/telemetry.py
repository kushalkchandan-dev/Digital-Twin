"""
Telemetry Generator Module
Generates realistic real-time metrics for each node and link.
Simulates normal operation with occasional stress patterns.
"""

import random
import time
import math


class TelemetryEngine:
    def __init__(self, graph):
        self.G = graph
        self.tick = 0                  # timestep counter
        self.node_states = {}          # per-node persistent state
        self.link_states = {}          # per-link persistent state
        self._init_states()

    def _init_states(self):
        """Initialize baseline states for all nodes and links."""
        for n in self.G.nodes:
            ntype = self.G.nodes[n]["type"]
            base_cpu = {"core": 30, "edge": 25, "access": 20}[ntype]
            self.node_states[n] = {
                "base_cpu": base_cpu,
                "noise_phase": random.uniform(0, 2 * math.pi),
            }
        for u, v in self.G.edges:
            self.link_states[(u, v)] = {
                "base_util": random.uniform(0.1, 0.4),
                "noise_phase": random.uniform(0, 2 * math.pi),
            }

    def get_node_metrics(self, node_id):
        """Generate telemetry for a single node at current tick."""
        node = self.G.nodes[node_id]
        if node["status"] == "down":
            return {
                "node_id": node_id,
                "label": node["label"],
                "type": node["type"],
                "status": "down",
                "cpu_usage": 0,
                "memory_usage": 0,
                "packet_loss": 100,
                "throughput": 0,
                "energy_consumption": 0,
            }

        state = self.node_states[node_id]
        t = self.tick * 0.1 + state["noise_phase"]

        # Sinusoidal drift + noise = realistic oscillating load
        cpu = state["base_cpu"] + 15 * math.sin(t * 0.7) + random.gauss(0, 3)
        cpu = max(5, min(99, cpu))

        memory = 40 + 20 * math.sin(t * 0.4 + 1.0) + random.gauss(0, 4)
        memory = max(10, min(95, memory))

        pkt_loss = max(0, random.gauss(0.5, 0.8))      # % loss, normally near 0
        throughput = node["bandwidth_capacity"] * (1 - cpu / 100) * random.uniform(0.7, 1.0)
        energy = 20 + (cpu / 100) * 80 + random.gauss(0, 2)   # Watts

        return {
            "node_id": node_id,
            "label": node["label"],
            "type": node["type"],
            "status": "up",
            "cpu_usage": round(cpu, 2),
            "memory_usage": round(memory, 2),
            "packet_loss": round(pkt_loss, 3),
            "throughput": round(throughput, 2),
            "energy_consumption": round(energy, 2),
        }

    def get_link_metrics(self, src, dst):
        """Generate telemetry for a single link at current tick."""
        edge = self.G.edges[src, dst]
        if edge["status"] == "down":
            return {
                "src": src, "dst": dst,
                "status": "down",
                "latency": 9999,
                "utilization": 0,
                "jitter": 0,
                "bandwidth_used": 0,
            }

        state = self.link_states.get((src, dst), {"base_util": 0.3, "noise_phase": 0})
        t = self.tick * 0.1 + state["noise_phase"]

        util = state["base_util"] + 0.2 * math.sin(t * 0.5) + random.gauss(0, 0.05)
        util = max(0, min(1, util))

        latency = edge["base_latency"] * (1 + util * 2) + random.gauss(0, 0.5)
        latency = max(0.1, latency)
        jitter = abs(random.gauss(0, latency * 0.1))
        bw_used = edge["bandwidth"] * util

        return {
            "src": src, "dst": dst,
            "status": "up",
            "latency": round(latency, 3),
            "utilization": round(util, 4),
            "jitter": round(jitter, 3),
            "bandwidth_used": round(bw_used, 2),
        }

    def get_full_snapshot(self):
        """Returns complete telemetry snapshot for all nodes and links."""
        self.tick += 1
        snapshot = {
            "tick": self.tick,
            "timestamp": time.time(),
            "nodes": {},
            "links": [],
        }

        for n in self.G.nodes:
            snapshot["nodes"][n] = self.get_node_metrics(n)

        for u, v in self.G.edges:
            snapshot["links"].append(self.get_link_metrics(u, v))

        return snapshot

    def set_node_status(self, node_id, status):
        self.G.nodes[node_id]["status"] = status

    def set_link_status(self, src, dst, status):
        self.G.edges[src, dst]["status"] = status

    def stress_node(self, node_id, cpu_boost=40, duration_ticks=10):
        """Temporarily spike CPU on a node (simulates overload)."""
        original = self.node_states[node_id]["base_cpu"]
        self.node_states[node_id]["base_cpu"] = min(95, original + cpu_boost)
        # Will be reset by failure injector after duration

    def reset_node_stress(self, node_id):
        ntype = self.G.nodes[node_id]["type"]
        self.node_states[node_id]["base_cpu"] = {"core": 30, "edge": 25, "access": 20}[ntype]
