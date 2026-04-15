"""
Self-Healing Actions Module
Implements resource optimization actions triggered by the healing engine.

Actions:
  1. reroute_traffic      - find alternate path when link/node fails
  2. reallocate_bandwidth - redistribute bandwidth to reduce congestion
  3. load_balance         - migrate load from overloaded to underloaded node
  4. isolate_node         - mark compromised node down, reroute its traffic
  5. restore_node         - bring a healed node back online
  6. energy_optimization  - reduce power of idle links
"""

import sys
import io
import networkx as nx
import time

# Force UTF-8 stdout on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


class HealingActions:
    def __init__(self, graph, telemetry_engine):
        self.G = graph
        self.telemetry = telemetry_engine
        self.action_log = []         # Full history of all actions taken

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Traffic Rerouting
    # ──────────────────────────────────────────────────────────────────────────

    def reroute_traffic(self, failed_src, failed_dst):
        """
        Find the best alternate path when a link (failed_src→failed_dst) fails.
        Uses Dijkstra on up-links weighted by utilization.
        Returns the alternate path or None.
        """
        # Build subgraph excluding the failed link
        subG = nx.DiGraph()
        for n in self.G.nodes:
            if self.G.nodes[n]["status"] == "up":
                subG.add_node(n)
        for u, v, data in self.G.edges(data=True):
            if (u, v) != (failed_src, failed_dst) and data["status"] == "up":
                util = self.telemetry.link_states.get((u, v), {}).get("base_util", 0.5)
                subG.add_edge(u, v, weight=1 + util * 10)   # prefer less-utilized links

        try:
            path = nx.dijkstra_path(subG, failed_src, failed_dst, weight="weight")
            action = {
                "type": "reroute_traffic",
                "description": f"Traffic rerouted: {failed_src}->{failed_dst} via path {path}",
                "path": path,
                "timestamp": time.time(),
                "severity": "info",
                "resource_saved": "Link failure bypassed",
            }
            self._log(action)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            action = {
                "type": "reroute_traffic",
                "description": f"No alternate path found for {failed_src}->{failed_dst}",
                "path": None,
                "timestamp": time.time(),
                "severity": "critical",
            }
            self._log(action)
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Bandwidth Reallocation
    # ──────────────────────────────────────────────────────────────────────────

    def reallocate_bandwidth(self, congested_src, congested_dst):
        """
        Reduce utilization on a congested link by redistributing traffic
        to parallel paths. Simulates QoS bandwidth reallocation.
        """
        # Find parallel paths
        try:
            paths = list(nx.all_simple_paths(self.G, congested_src, congested_dst, cutoff=4))
        except Exception:
            paths = []

        # Lower congested link utilization
        key = (congested_src, congested_dst)
        if key in self.telemetry.link_states:
            old_util = self.telemetry.link_states[key]["base_util"]
            new_util = max(0.2, old_util * 0.55)    # reduce by ~45%
            self.telemetry.link_states[key]["base_util"] = new_util
            saved_bw = round((old_util - new_util) * self.G.edges[congested_src, congested_dst]["bandwidth"], 2)

            action = {
                "type": "bandwidth_reallocation",
                "description": (
                    f"Bandwidth reallocated on link {congested_src}->{congested_dst}: "
                    f"utilization {old_util:.0%} -> {new_util:.0%}. "
                    f"Freed {saved_bw} Mbps across {len(paths)} alternate paths."
                ),
                "link": (congested_src, congested_dst),
                "old_util": old_util,
                "new_util": new_util,
                "saved_mbps": saved_bw,
                "alternate_paths": len(paths),
                "timestamp": time.time(),
                "severity": "info",
                "resource_saved": f"{saved_bw} Mbps freed",
            }
            self._log(action)
            return action
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # 3. CPU Load Balancing
    # ──────────────────────────────────────────────────────────────────────────

    def load_balance(self, overloaded_node_id, twin_state):
        """
        Find the most underutilized neighbor node and migrate 30% of load.
        Represents VM/service migration for resource optimization.
        """
        neighbors = list(self.G.successors(overloaded_node_id))
        up_neighbors = [n for n in neighbors if self.G.nodes[n]["status"] == "up"]

        if not up_neighbors:
            return None

        # Pick least-loaded neighbor
        def cpu_of(n):
            m = twin_state.get_current_node_metrics(n)
            return m["cpu_usage"] if m else 100

        target = min(up_neighbors, key=cpu_of)
        src_label = self.G.nodes[overloaded_node_id]["label"]
        dst_label = self.G.nodes[target]["label"]

        # Reduce load on overloaded node
        self.telemetry.node_states[overloaded_node_id]["base_cpu"] = max(
            20, self.telemetry.node_states[overloaded_node_id]["base_cpu"] - 30
        )

        action = {
            "type": "load_balancing",
            "description": (
                f"Load balanced: 30% workload migrated from {src_label} -> {dst_label}. "
                f"CPU on {src_label} reduced by ~30%."
            ),
            "from_node": overloaded_node_id,
            "to_node": target,
            "timestamp": time.time(),
            "severity": "info",
            "resource_saved": "30% CPU headroom recovered",
        }
        self._log(action)
        return action

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Node Isolation
    # ──────────────────────────────────────────────────────────────────────────

    def isolate_node(self, node_id):
        """Mark a failed/compromised node as down."""
        self.telemetry.set_node_status(node_id, "down")
        label = self.G.nodes[node_id]["label"]
        action = {
            "type": "node_isolation",
            "description": f"Node {label} isolated. All traffic rerouted away.",
            "node_id": node_id,
            "timestamp": time.time(),
            "severity": "warning",
            "resource_saved": "Compromised node removed from traffic path",
        }
        self._log(action)
        return action

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Node Restoration
    # ──────────────────────────────────────────────────────────────────────────

    def restore_node(self, node_id):
        """Bring a healed node back online."""
        self.telemetry.set_node_status(node_id, "up")
        self.telemetry.reset_node_stress(node_id)
        label = self.G.nodes[node_id]["label"]
        action = {
            "type": "node_restore",
            "description": f"Node {label} restored. Rejoining active network topology.",
            "node_id": node_id,
            "timestamp": time.time(),
            "severity": "info",
            "resource_saved": f"Node {label} capacity restored",
        }
        self._log(action)
        return action

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Energy Optimization
    # ──────────────────────────────────────────────────────────────────────────

    def energy_optimize(self):
        """
        Put idle links (utilization < 5%) into low-power mode.
        Simulates energy-aware resource management.
        """
        optimized = []
        for u, v in self.G.edges:
            if self.G.edges[u, v]["status"] == "up":
                util = self.telemetry.link_states.get((u, v), {}).get("base_util", 0.5)
                if util < 0.05:
                    self.telemetry.link_states[(u, v)]["base_util"] = 0.01
                    optimized.append((u, v))

        if optimized:
            action = {
                "type": "energy_optimization",
                "description": f"Energy optimized: {len(optimized)} idle links set to low-power mode.",
                "links": optimized,
                "timestamp": time.time(),
                "severity": "info",
                "resource_saved": f"{len(optimized) * 5}W estimated savings",
            }
            self._log(action)
            return action
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _log(self, action):
        action["id"] = len(self.action_log)
        self.action_log.append(action)
        print(f"[Heal] {action['type']:25s} | {action['description'][:80]}")

    def get_action_log(self, last_n=50):
        return self.action_log[-last_n:]
