"""
Real-Time Fault Predictor
Loads the trained LSTM and runs inference on live Digital Twin data.
"""

import os
import numpy as np
import torch
import torch.nn as nn

MODEL_PATH = "ai_engine/models/lstm_fault_model.pt"
SCALER_PATH = "ai_engine/models/scaler_params.npz"
SEQUENCE_LENGTH = 20
FEATURE_COLS = ["cpu_usage", "memory_usage", "packet_loss",
                "throughput", "link_utilization", "latency", "jitter"]
CLASS_NAMES = ["Normal", "Congestion", "LinkFailure", "NodeDown"]


class FaultLSTM(nn.Module):
    def __init__(self, input_size=7, hidden_size=128, num_layers=2,
                 num_classes=4, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size,
                            num_layers=num_layers, batch_first=True, dropout=dropout)
        self.fc = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        _, (hn, _) = self.lstm(x)
        return self.fc(hn[-1])


class FaultPredictor:
    FAULT_THRESHOLDS = {
        "Congestion":  0.60,
        "LinkFailure": 0.70,
        "NodeDown":    0.70,
        "Normal":      0.00,
    }

    def __init__(self):
        self.model = None
        self.feat_min = None
        self.feat_max = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load_model()

    def _load_model(self):
        if not os.path.exists(MODEL_PATH):
            print("[Predictor] WARNING: No trained model found. Run train_model.py first.")
            return
        checkpoint = torch.load(MODEL_PATH, map_location=self.device, weights_only=False)
        self.model = FaultLSTM(input_size=len(FEATURE_COLS))
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.to(self.device)
        self.model.eval()

        scaler = np.load(SCALER_PATH)
        self.feat_min = scaler["feat_min"]
        self.feat_max = scaler["feat_max"]
        print("[Predictor] [OK] LSTM model loaded.")

    def is_ready(self):
        return self.model is not None

    def _extract_features(self, node_history, link_history_avg):
        """
        Converts node history (list of metric dicts) into
        a normalized feature sequence of shape (seq_len, n_features).
        """
        rows = []
        for h in node_history:
            row = [
                h.get("cpu_usage", 0.0),
                h.get("memory_usage", 0.0),
                h.get("packet_loss", 0.0),
                h.get("throughput", 0.0),
                link_history_avg.get("utilization", 0.0),
                link_history_avg.get("latency", 0.0),
                link_history_avg.get("jitter", 0.0),
            ]
            rows.append(row)

        # Pad to SEQUENCE_LENGTH if needed
        while len(rows) < SEQUENCE_LENGTH:
            rows.insert(0, [0.0] * len(FEATURE_COLS))
        rows = rows[-SEQUENCE_LENGTH:]

        arr = np.array(rows, dtype=np.float32)

        # Normalize
        feat_range = np.where(self.feat_max - self.feat_min == 0, 1,
                              self.feat_max - self.feat_min)
        arr = (arr - self.feat_min) / feat_range
        arr = np.clip(arr, 0, 1)
        return arr

    def predict_node(self, node_history, link_metrics_avg):
        """
        Predict fault class for a single node.
        Returns:
            {
              "class": "Congestion",
              "class_id": 1,
              "confidence": 0.87,
              "is_fault": True,
              "probabilities": [p0, p1, p2, p3]
            }
        """
        if not self.is_ready() or len(node_history) < 3:
            return {"class": "Normal", "class_id": 0, "confidence": 1.0,
                    "is_fault": False, "probabilities": [1, 0, 0, 0]}

        features = self._extract_features(node_history, link_metrics_avg)
        tensor = torch.tensor(features, dtype=torch.float32).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze().cpu().numpy()

        class_id = int(np.argmax(probs))
        class_name = CLASS_NAMES[class_id]
        confidence = float(probs[class_id])

        threshold = self.FAULT_THRESHOLDS.get(class_name, 0.5)
        is_fault = (class_name != "Normal") and (confidence >= threshold)

        return {
            "class": class_name,
            "class_id": class_id,
            "confidence": round(confidence, 4),
            "is_fault": is_fault,
            "probabilities": [round(float(p), 4) for p in probs],
        }

    def predict_all_nodes(self, twin_state):
        """
        Runs prediction for every node using Digital Twin history.
        Returns a dict: {node_id: prediction_result}
        """
        if not self.is_ready():
            return {}

        results = {}
        # Compute average link metrics for context
        link_avg = self._avg_link_metrics(twin_state)

        for node_id in twin_state.G.nodes if hasattr(twin_state, "G") else twin_state.node_history:
            history = list(twin_state.node_history.get(node_id, []))
            results[node_id] = self.predict_node(history, link_avg)

        return results

    def _avg_link_metrics(self, twin_state):
        """Compute average link metrics from current snapshot for context."""
        if not twin_state.current_snapshot:
            return {"utilization": 0, "latency": 0, "jitter": 0}
        links = [l for l in twin_state.current_snapshot.get("links", [])
                 if l.get("status") == "up"]
        if not links:
            return {"utilization": 0, "latency": 0, "jitter": 0}
        return {
            "utilization": sum(l.get("utilization", 0) for l in links) / len(links),
            "latency": sum(l.get("latency", 0) for l in links) / len(links),
            "jitter": sum(l.get("jitter", 0) for l in links) / len(links),
        }
