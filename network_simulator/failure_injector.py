"""
Failure Injector Module
Randomly injects faults into the network to test self-healing.
Fault types: link_failure, node_down, congestion, high_cpu
"""

import random
import time


class FailureInjector:
    FAULT_TYPES = ["link_failure", "node_down", "congestion", "high_cpu"]

    def __init__(self, graph, telemetry_engine, min_interval=15, max_interval=40):
        """
        Args:
            graph: NetworkX DiGraph
            telemetry_engine: TelemetryEngine instance
            min_interval: min seconds between injections
            max_interval: max seconds between injections
        """
        self.G = graph
        self.telemetry = telemetry_engine
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.next_fault_time = time.time() + random.uniform(min_interval, max_interval)
        self.active_faults = []       # list of active fault dicts
        self.fault_history = []       # all past faults (for dashboard log)

    def tick(self):
        """
        Called every second. Returns a new fault dict if one was injected, else None.
        Also auto-recovers faults after their duration.
        """
        now = time.time()
        self._recover_expired(now)

        if now >= self.next_fault_time:
            fault = self._inject_random_fault(now)
            self.next_fault_time = now + random.uniform(self.min_interval, self.max_interval)
            return fault
        return None

    def _inject_random_fault(self, now):
        """Picks a random fault type and applies it."""
        fault_type = random.choice(self.FAULT_TYPES)
        fault = None

        if fault_type == "link_failure":
            # Pick an active link
            active_edges = [(u, v) for u, v in self.G.edges
                            if self.G.edges[u, v]["status"] == "up"]
            if active_edges:
                u, v = random.choice(active_edges)
                self.telemetry.set_link_status(u, v, "down")
                fault = {
                    "type": "link_failure",
                    "target": f"Link {u}→{v}",
                    "detail": f"Link between node {u} and node {v} failed",
                    "src": u, "dst": v,
                    "start_time": now,
                    "duration": random.uniform(20, 45),
                    "severity": "critical",
                }

        elif fault_type == "node_down":
            # Don't take down more than 1 at a time
            up_nodes = [n for n in self.G.nodes if self.G.nodes[n]["status"] == "up"]
            current_down = [f for f in self.active_faults if f["type"] == "node_down"]
            if up_nodes and len(current_down) < 2:
                n = random.choice(up_nodes)
                self.telemetry.set_node_status(n, "down")
                fault = {
                    "type": "node_down",
                    "target": f"Node {self.G.nodes[n]['label']}",
                    "detail": f"Node {self.G.nodes[n]['label']} is unresponsive",
                    "node_id": n,
                    "start_time": now,
                    "duration": random.uniform(15, 35),
                    "severity": "critical",
                }

        elif fault_type == "congestion":
            # Spike utilization on a random link
            active_edges = [(u, v) for u, v in self.G.edges
                            if self.G.edges[u, v]["status"] == "up"]
            if active_edges:
                u, v = random.choice(active_edges)
                old_util = self.telemetry.link_states.get((u, v), {}).get("base_util", 0.3)
                self.telemetry.link_states[(u, v)]["base_util"] = 0.92
                fault = {
                    "type": "congestion",
                    "target": f"Link {u}→{v}",
                    "detail": f"Severe congestion detected on link {u}→{v} (utilization 92%)",
                    "src": u, "dst": v,
                    "old_util": old_util,
                    "start_time": now,
                    "duration": random.uniform(20, 40),
                    "severity": "warning",
                }

        elif fault_type == "high_cpu":
            up_nodes = [n for n in self.G.nodes if self.G.nodes[n]["status"] == "up"]
            if up_nodes:
                n = random.choice(up_nodes)
                self.telemetry.stress_node(n, cpu_boost=50)
                fault = {
                    "type": "high_cpu",
                    "target": f"Node {self.G.nodes[n]['label']}",
                    "detail": f"CPU overload on {self.G.nodes[n]['label']} (>90%)",
                    "node_id": n,
                    "start_time": now,
                    "duration": random.uniform(15, 30),
                    "severity": "warning",
                }

        if fault:
            fault["id"] = len(self.fault_history)
            self.active_faults.append(fault)
            self.fault_history.append(fault)

        return fault

    def _recover_expired(self, now):
        """Auto-remove faults that exceeded their duration (before healing kicks in)."""
        still_active = []
        for fault in self.active_faults:
            if now - fault["start_time"] > fault["duration"] * 1.5:
                self._restore_fault(fault)
            else:
                still_active.append(fault)
        self.active_faults = still_active

    def _restore_fault(self, fault):
        """Restore network state after a fault is healed or expired."""
        if fault["type"] == "link_failure":
            self.telemetry.set_link_status(fault["src"], fault["dst"], "up")
        elif fault["type"] == "node_down":
            self.telemetry.set_node_status(fault["node_id"], "up")
        elif fault["type"] == "congestion":
            if (fault["src"], fault["dst"]) in self.telemetry.link_states:
                self.telemetry.link_states[(fault["src"], fault["dst"])]["base_util"] = fault["old_util"]
        elif fault["type"] == "high_cpu":
            self.telemetry.reset_node_stress(fault["node_id"])

    def heal_fault(self, fault_id):
        """Called by healing engine to mark a fault as healed. Returns True if found."""
        for fault in self.active_faults:
            if fault.get("id") == fault_id:
                self._restore_fault(fault)
                self.active_faults.remove(fault)
                return True
        return False

    def get_active_faults(self):
        return list(self.active_faults)

    def get_fault_history(self):
        return list(self.fault_history)
