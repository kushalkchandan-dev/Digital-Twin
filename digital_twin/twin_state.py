"""
Digital Twin State Module
Maintains the real-time virtual replica of the physical network.
This is the "mirror" — it always reflects current network conditions.
"""

import time
from collections import deque


class DigitalTwinState:
    HISTORY_LENGTH = 100    # keep last 100 ticks per node

    def __init__(self, graph):
        self.G = graph
        self.node_history = {n: deque(maxlen=self.HISTORY_LENGTH) for n in graph.nodes}
        self.link_history = {}
        for u, v in graph.edges:
            self.link_history[(u, v)] = deque(maxlen=self.HISTORY_LENGTH)

        self.current_snapshot = None
        self.last_sync_time = None
        self.sync_count = 0

        # Aggregate KPIs
        self.total_faults_detected = 0
        self.total_healed = 0
        self.uptime_ticks = 0
        self.downtime_ticks = 0

    def update(self, snapshot):
        """
        Called by sync_engine every second with new telemetry.
        Updates history buffers and recomputes KPIs.
        """
        self.current_snapshot = snapshot
        self.last_sync_time = time.time()
        self.sync_count += 1

        # Update node histories
        for node_id, metrics in snapshot["nodes"].items():
            self.node_history[node_id].append(metrics)

        # Update link histories
        for link in snapshot["links"]:
            key = (link["src"], link["dst"])
            if key in self.link_history:
                self.link_history[key].append(link)

        # Track uptime/downtime
        any_down = any(
            m["status"] == "down"
            for m in snapshot["nodes"].values()
        )
        if any_down:
            self.downtime_ticks += 1
        else:
            self.uptime_ticks += 1

    def get_node_feature_vector(self, node_id):
        """
        Returns last 20 ticks of metrics for a node as a list of feature dicts.
        Used by the AI engine for LSTM prediction.
        """
        history = list(self.node_history[node_id])
        return history[-20:] if len(history) >= 1 else []

    def get_current_node_metrics(self, node_id):
        """Returns the latest metric snapshot for a node."""
        h = self.node_history.get(node_id)
        if h and len(h) > 0:
            return h[-1]
        return None

    def get_network_kpis(self):
        """Compute overall network KPI summary."""
        if not self.current_snapshot:
            return {}

        nodes = self.current_snapshot["nodes"]
        links = self.current_snapshot["links"]

        up_nodes = [m for m in nodes.values() if m["status"] == "up"]
        up_links = [l for l in links if l["status"] == "up"]

        avg_cpu = round(sum(m["cpu_usage"] for m in up_nodes) / max(len(up_nodes), 1), 2)
        avg_latency = round(sum(l["latency"] for l in up_links) / max(len(up_links), 1), 3)
        avg_packet_loss = round(sum(m["packet_loss"] for m in up_nodes) / max(len(up_nodes), 1), 4)
        total_throughput = round(sum(m["throughput"] for m in up_nodes), 2)
        total_energy = round(sum(m["energy_consumption"] for m in up_nodes), 2)

        total_ticks = self.uptime_ticks + self.downtime_ticks
        availability = round(self.uptime_ticks / max(total_ticks, 1) * 100, 2)

        return {
            "avg_cpu_usage": avg_cpu,
            "avg_latency_ms": avg_latency,
            "avg_packet_loss_pct": avg_packet_loss,
            "total_throughput_mbps": total_throughput,
            "total_energy_watts": total_energy,
            "network_availability_pct": availability,
            "total_faults_detected": self.total_faults_detected,
            "total_healed": self.total_healed,
            "sync_count": self.sync_count,
            "nodes_up": len(up_nodes),
            "nodes_total": len(nodes),
            "links_up": len(up_links),
            "links_total": len(links),
        }

    def record_fault(self):
        self.total_faults_detected += 1

    def record_heal(self):
        self.total_healed += 1

    def get_topology_state(self):
        """Returns node/link status for dashboard topology graph."""
        if not self.current_snapshot:
            return {"nodes": [], "links": []}

        node_list = []
        for nid, metrics in self.current_snapshot["nodes"].items():
            node_list.append({
                "id": nid,
                "label": metrics["label"],
                "type": metrics["type"],
                "status": metrics["status"],
                "cpu": metrics.get("cpu_usage", 0),
                "memory": metrics.get("memory_usage", 0),
            })

        link_list = []
        for link in self.current_snapshot["links"]:
            link_list.append({
                "source": link["src"],
                "target": link["dst"],
                "status": link["status"],
                "utilization": link.get("utilization", 0),
                "latency": link.get("latency", 0),
            })

        return {"nodes": node_list, "links": link_list}
