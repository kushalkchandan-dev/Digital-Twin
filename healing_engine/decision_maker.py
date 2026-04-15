"""
Decision Maker Module
Maps predicted fault types → healing actions.
Implements the closed-loop self-healing logic.
"""

import time
import threading


class DecisionMaker:
    """
    Closed-loop controller:
      1. Receives AI predictions + injector faults every tick
      2. Decides which healing action to apply
      3. Triggers HealingActions accordingly
      4. Records decision history
    """

    FAULT_ACTION_MAP = {
        "Congestion":  "bandwidth_reallocation",
        "LinkFailure": "reroute_traffic",
        "NodeDown":    "node_isolation_restore",
        "high_cpu":    "load_balancing",
        "congestion":  "bandwidth_reallocation",
        "link_failure":"reroute_traffic",
        "node_down":   "node_isolation_restore",
    }

    def __init__(self, healing_actions, failure_injector, twin_state,
                 cooldown_secs=8):
        self.actions = healing_actions
        self.injector = failure_injector
        self.twin = twin_state
        self.cooldown = cooldown_secs
        self.decision_log = []
        self._last_action_time = {}    # node/link → last action timestamp
        self._lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # Main entry: called every tick with AI predictions + injector state
    # ──────────────────────────────────────────────────────────────────────────

    def process(self, ai_predictions: dict):
        """
        ai_predictions: {node_id: {"class": str, "is_fault": bool, ...}}
        Also checks active injector faults for deterministic healing.
        """
        new_actions = []

        with self._lock:
            # 1. Handle injector faults (deterministic)
            for fault in self.injector.get_active_faults():
                action = self._handle_injector_fault(fault)
                if action:
                    new_actions.append(action)

            # 2. Handle AI-predicted faults (AI-driven)
            for node_id, pred in ai_predictions.items():
                if pred.get("is_fault"):
                    action = self._handle_ai_fault(node_id, pred)
                    if action:
                        new_actions.append(action)

            # 3. Periodic energy optimization (every ~60 ticks)
            if self.twin.sync_count % 60 == 0:
                ea = self.actions.energy_optimize()
                if ea:
                    new_actions.append(ea)

        return new_actions

    # ──────────────────────────────────────────────────────────────────────────
    # Injector fault handling
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_injector_fault(self, fault):
        fault_type = fault["type"]
        fault_id = fault.get("id", -1)
        cooldown_key = f"injector_{fault_id}"

        if self._is_cooling_down(cooldown_key):
            return None

        action = None

        if fault_type == "link_failure":
            path = self.actions.reroute_traffic(fault["src"], fault["dst"])
            action = {
                "trigger": "injector",
                "fault_type": fault_type,
                "action": "reroute_traffic",
                "detail": f"Alternate path: {path}",
                "timestamp": time.time(),
                "fault_target": fault["target"],
            }
            # Mark as healed in injector
            self.injector.heal_fault(fault_id)
            self.twin.record_heal()

        elif fault_type == "node_down":
            # Isolate and immediately schedule restore
            result = self.actions.isolate_node(fault["node_id"])
            # Schedule reactivation after short delay
            threading.Timer(
                15.0,
                lambda: self._restore_node_delayed(fault["node_id"], fault_id)
            ).start()
            action = {
                "trigger": "injector",
                "fault_type": fault_type,
                "action": "node_isolation",
                "detail": f"Isolating {fault['target']}, restore in 15s",
                "timestamp": time.time(),
                "fault_target": fault["target"],
            }
            self.twin.record_heal()

        elif fault_type == "congestion":
            result = self.actions.reallocate_bandwidth(fault["src"], fault["dst"])
            action = {
                "trigger": "injector",
                "fault_type": fault_type,
                "action": "bandwidth_reallocation",
                "detail": result["description"] if result else "Reallocation applied",
                "timestamp": time.time(),
                "fault_target": fault["target"],
            }
            self.injector.heal_fault(fault_id)
            self.twin.record_heal()

        elif fault_type == "high_cpu":
            result = self.actions.load_balance(fault["node_id"], self.twin)
            action = {
                "trigger": "injector",
                "fault_type": fault_type,
                "action": "load_balancing",
                "detail": result["description"] if result else "Load balanced",
                "timestamp": time.time(),
                "fault_target": fault["target"],
            }
            self.injector.heal_fault(fault_id)
            self.twin.record_heal()

        if action:
            self._set_cooldown(cooldown_key)
            self._record(action)
        return action

    # ──────────────────────────────────────────────────────────────────────────
    # AI prediction fault handling
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_ai_fault(self, node_id, pred):
        fault_class = pred["class"]
        cooldown_key = f"ai_node_{node_id}"

        if self._is_cooling_down(cooldown_key):
            return None

        action = None

        if fault_class == "Congestion":
            # Find highest-utilized outgoing link
            out_edges = list(self.actions.G.successors(node_id))
            if out_edges:
                tgt = out_edges[0]
                result = self.actions.reallocate_bandwidth(node_id, tgt)
                action = {
                    "trigger": "AI",
                    "fault_type": fault_class,
                    "action": "bandwidth_reallocation",
                    "detail": f"AI predicted congestion on node {node_id} ({pred['confidence']:.0%} confidence)",
                    "timestamp": time.time(),
                    "fault_target": f"Node {node_id}",
                }

        elif fault_class == "LinkFailure":
            out_edges = list(self.actions.G.successors(node_id))
            if out_edges:
                tgt = out_edges[0]
                path = self.actions.reroute_traffic(node_id, tgt)
                action = {
                    "trigger": "AI",
                    "fault_type": fault_class,
                    "action": "reroute_traffic",
                    "detail": f"AI predicted link failure. Alternate path: {path}",
                    "timestamp": time.time(),
                    "fault_target": f"Link from Node {node_id}",
                }

        elif fault_class == "NodeDown":
            result = self.actions.load_balance(node_id, self.twin)
            action = {
                "trigger": "AI",
                "fault_type": fault_class,
                "action": "load_balancing",
                "detail": f"AI predicted node failure. Preemptive load migration applied.",
                "timestamp": time.time(),
                "fault_target": f"Node {node_id}",
            }

        if action:
            self._set_cooldown(cooldown_key)
            self._record(action)
            self.twin.record_fault()
        return action

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _restore_node_delayed(self, node_id, fault_id):
        self.actions.restore_node(node_id)
        self.injector.heal_fault(fault_id)

    def _is_cooling_down(self, key):
        last = self._last_action_time.get(key, 0)
        return (time.time() - last) < self.cooldown

    def _set_cooldown(self, key):
        self._last_action_time[key] = time.time()

    def _record(self, action):
        action["id"] = len(self.decision_log)
        self.decision_log.append(action)

    def get_decision_log(self, last_n=50):
        return self.decision_log[-last_n:]
