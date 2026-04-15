"""
Sync Engine Module
Bridges telemetry from the physical (simulated) network → Digital Twin.
Runs the main data pipeline loop.
"""

import time
import threading


class SyncEngine:
    def __init__(self, telemetry_engine, twin_state, interval=1.0):
        """
        Args:
            telemetry_engine: TelemetryEngine (network simulator)
            twin_state: DigitalTwinState (the mirror)
            interval: sync interval in seconds
        """
        self.telemetry = telemetry_engine
        self.twin = twin_state
        self.interval = interval
        self._running = False
        self._thread = None
        self.on_snapshot_callbacks = []   # listeners (AI engine, dashboard)

    def register_callback(self, fn):
        """Register a function to be called after every sync with the snapshot."""
        self.on_snapshot_callbacks.append(fn)

    def start(self):
        """Start the sync loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            start = time.time()
            try:
                snapshot = self.telemetry.get_full_snapshot()
                self.twin.update(snapshot)
                for cb in self.on_snapshot_callbacks:
                    try:
                        cb(snapshot)
                    except Exception as e:
                        print(f"[SyncEngine] Callback error: {e}")
            except Exception as e:
                print(f"[SyncEngine] Sync error: {e}")

            elapsed = time.time() - start
            sleep_time = max(0, self.interval - elapsed)
            time.sleep(sleep_time)
