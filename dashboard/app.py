"""
Flask Web Dashboard — Backend
Real-time WebSocket server that streams network state to the browser.
"""

import os
import sys
import io
import time
import json
import threading

# Force UTF-8 stdout so Windows cp1252 terminal never breaks on special chars
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Make sure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

from network_simulator.topology import create_topology
from network_simulator.telemetry import TelemetryEngine
from network_simulator.failure_injector import FailureInjector
from digital_twin.twin_state import DigitalTwinState
from digital_twin.sync_engine import SyncEngine
from ai_engine.predict import FaultPredictor
from healing_engine.actions import HealingActions
from healing_engine.decision_maker import DecisionMaker

# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "selfheal-dt-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ──────────────────────────────────────────────────────────────────────────────
# System Bootstrap
# ──────────────────────────────────────────────────────────────────────────────

print("[App] Initializing Self-Healing Network System...")

G = create_topology()
telemetry = TelemetryEngine(G)
twin = DigitalTwinState(G)
twin.G = G    # attach graph reference to twin

injector = FailureInjector(G, telemetry, min_interval=20, max_interval=45)
predictor = FaultPredictor()
heal_actions = HealingActions(G, telemetry)
decision_maker = DecisionMaker(heal_actions, injector, twin, cooldown_secs=10)

sync_engine = SyncEngine(telemetry, twin, interval=1.0)

# Buffer for real-time event streaming
_event_buffer = []
_buffer_lock = threading.Lock()

def _on_new_snapshot(snapshot):
    """Called every second by sync engine after new telemetry arrives."""
    # 1. Check for new injector faults
    new_fault = injector.tick()
    if new_fault:
        twin.record_fault()
        with _buffer_lock:
            _event_buffer.append({
                "event": "fault_detected",
                "data": {
                    "fault": new_fault,
                    "timestamp": time.time(),
                }
            })

    # 2. Run AI predictions every 3 ticks (to avoid overload)
    ai_results = {}
    if twin.sync_count % 3 == 0 and predictor.is_ready():
        ai_results = predictor.predict_all_nodes(twin)

    # 3. Decision maker — heal faults
    new_decisions = decision_maker.process(ai_results)
    if new_decisions:
        with _buffer_lock:
            for d in new_decisions:
                _event_buffer.append({
                    "event": "healing_action",
                    "data": d,
                })

    # 4. Push full state to dashboard
    kpis = twin.get_network_kpis()
    topo = twin.get_topology_state()

    # Format AI predictions for dashboard
    ai_summary = {}
    for nid, pred in ai_results.items():
        ai_summary[str(nid)] = pred

    with _buffer_lock:
        _event_buffer.append({
            "event": "network_state",
            "data": {
                "tick": snapshot["tick"],
                "kpis": kpis,
                "topology": topo,
                "ai_predictions": ai_summary,
                "nodes": {str(k): v for k, v in snapshot["nodes"].items()},
            }
        })

sync_engine.register_callback(_on_new_snapshot)


# ──────────────────────────────────────────────────────────────────────────────
# Background SocketIO broadcaster
# ──────────────────────────────────────────────────────────────────────────────

def _broadcast_loop():
    """Drains event buffer and emits to all connected clients."""
    while True:
        with _buffer_lock:
            events = list(_event_buffer)
            _event_buffer.clear()

        for ev in events:
            try:
                socketio.emit(ev["event"], ev["data"])
            except Exception:
                pass

        time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "status": "running",
        "sync_count": twin.sync_count,
        "model_ready": predictor.is_ready(),
        "kpis": twin.get_network_kpis(),
        "active_faults": injector.get_active_faults(),
        "recent_actions": decision_maker.get_decision_log(last_n=10),
    })


@app.route("/api/fault_history")
def api_fault_history():
    return jsonify(injector.get_fault_history())


@app.route("/api/action_log")
def api_action_log():
    return jsonify(decision_maker.get_decision_log(last_n=100))


@app.route("/api/topology")
def api_topology():
    return jsonify(twin.get_topology_state())


# ──────────────────────────────────────────────────────────────────────────────
# SocketIO events
# ──────────────────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    print("[WS] Client connected")
    emit("system_info", {
        "message": "Connected to Self-Healing Network Dashboard",
        "model_ready": predictor.is_ready(),
        "nodes": len(G.nodes),
        "links": len(G.edges),
    })


@socketio.on("disconnect")
def on_disconnect():
    print("[WS] Client disconnected")


# ──────────────────────────────────────────────────────────────────────────────
# Launch
# ──────────────────────────────────────────────────────────────────────────────

def start():
    sync_engine.start()

    bcast_thread = threading.Thread(target=_broadcast_loop, daemon=True)
    bcast_thread.start()

    print("[App] [OK] System started. Dashboard at http://127.0.0.1:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    start()
