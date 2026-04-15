"""
Training Dataset Generator
Generates a labeled synthetic dataset for LSTM training.

Features (per timestep):
  - cpu_usage         (%)
  - memory_usage      (%)
  - packet_loss       (%)
  - throughput        (Mbps)
  - link_utilization  (0-1)
  - latency           (ms)
  - jitter            (ms)

Labels (fault class):
  0 = Normal
  1 = Congestion
  2 = Link Failure
  3 = Node Down (High CPU + Zero Throughput)

Sequence length: 20 timesteps
"""

import numpy as np
import pandas as pd
import os

SEQUENCE_LENGTH = 20
SAMPLES_PER_CLASS = 1200
FEATURE_COLS = ["cpu_usage", "memory_usage", "packet_loss",
                "throughput", "link_utilization", "latency", "jitter"]


def _generate_normal(n):
    """Normal operating conditions."""
    cpu = np.clip(np.random.normal(30, 8, (n, SEQUENCE_LENGTH)), 5, 65)
    mem = np.clip(np.random.normal(40, 10, (n, SEQUENCE_LENGTH)), 10, 70)
    loss = np.clip(np.random.normal(0.3, 0.2, (n, SEQUENCE_LENGTH)), 0, 2)
    tput = np.clip(np.random.normal(800, 100, (n, SEQUENCE_LENGTH)), 400, 1200)
    util = np.clip(np.random.normal(0.3, 0.08, (n, SEQUENCE_LENGTH)), 0.05, 0.6)
    lat = np.clip(np.random.normal(5, 1.5, (n, SEQUENCE_LENGTH)), 1, 12)
    jit = np.abs(np.random.normal(0, 0.5, (n, SEQUENCE_LENGTH)))
    return np.stack([cpu, mem, loss, tput, util, lat, jit], axis=2)


def _generate_congestion(n):
    """High utilization, rising latency, some packet loss."""
    cpu = np.clip(np.random.normal(55, 10, (n, SEQUENCE_LENGTH)), 30, 90)
    mem = np.clip(np.random.normal(60, 8, (n, SEQUENCE_LENGTH)), 40, 85)
    loss = np.clip(np.random.normal(5, 2, (n, SEQUENCE_LENGTH)), 1, 20)
    tput = np.clip(np.random.normal(300, 80, (n, SEQUENCE_LENGTH)), 50, 600)
    util = np.clip(np.random.normal(0.88, 0.06, (n, SEQUENCE_LENGTH)), 0.7, 1.0)
    lat = np.clip(np.random.normal(50, 15, (n, SEQUENCE_LENGTH)), 20, 120)
    jit = np.abs(np.random.normal(0, 8, (n, SEQUENCE_LENGTH)))
    return np.stack([cpu, mem, loss, tput, util, lat, jit], axis=2)


def _generate_link_failure(n):
    """Link goes down: zero/near-zero throughput, 100% packet loss, max latency."""
    cpu = np.clip(np.random.normal(25, 5, (n, SEQUENCE_LENGTH)), 5, 50)
    mem = np.clip(np.random.normal(35, 8, (n, SEQUENCE_LENGTH)), 10, 60)
    loss = np.full((n, SEQUENCE_LENGTH), 100.0) + np.random.normal(0, 0.5, (n, SEQUENCE_LENGTH))
    tput = np.clip(np.random.normal(0, 5, (n, SEQUENCE_LENGTH)), 0, 15)
    util = np.zeros((n, SEQUENCE_LENGTH))
    lat = np.full((n, SEQUENCE_LENGTH), 9999.0)
    jit = np.zeros((n, SEQUENCE_LENGTH))
    return np.stack([cpu, mem, loss, tput, util, lat, jit], axis=2)


def _generate_node_down(n):
    """Node goes unresponsive: all metrics drop to zero."""
    cpu = np.zeros((n, SEQUENCE_LENGTH))
    mem = np.zeros((n, SEQUENCE_LENGTH))
    loss = np.full((n, SEQUENCE_LENGTH), 100.0)
    tput = np.zeros((n, SEQUENCE_LENGTH))
    util = np.zeros((n, SEQUENCE_LENGTH))
    lat = np.full((n, SEQUENCE_LENGTH), 9999.0)
    jit = np.zeros((n, SEQUENCE_LENGTH))
    return np.stack([cpu, mem, loss, tput, util, lat, jit], axis=2)


def generate_and_save(output_dir="ai_engine"):
    print("[DataGen] Generating training dataset...")

    X_normal = _generate_normal(SAMPLES_PER_CLASS)
    X_congestion = _generate_congestion(SAMPLES_PER_CLASS)
    X_link_failure = _generate_link_failure(SAMPLES_PER_CLASS)
    X_node_down = _generate_node_down(SAMPLES_PER_CLASS)

    X = np.concatenate([X_normal, X_congestion, X_link_failure, X_node_down], axis=0)
    y = np.array(
        [0] * SAMPLES_PER_CLASS +
        [1] * SAMPLES_PER_CLASS +
        [2] * SAMPLES_PER_CLASS +
        [3] * SAMPLES_PER_CLASS
    )

    # Shuffle
    idx = np.random.permutation(len(X))
    X, y = X[idx], y[idx]

    # Normalize each feature to [0, 1]
    X_flat = X.reshape(-1, len(FEATURE_COLS))
    feat_min = X_flat.min(axis=0)
    feat_max = X_flat.max(axis=0)
    feat_range = np.where(feat_max - feat_min == 0, 1, feat_max - feat_min)
    X_norm = (X - feat_min) / feat_range

    os.makedirs(output_dir, exist_ok=True)
    np.save(os.path.join(output_dir, "X_train.npy"), X_norm)
    np.save(os.path.join(output_dir, "y_train.npy"), y)
    np.save(os.path.join(output_dir, "feat_min.npy"), feat_min)
    np.save(os.path.join(output_dir, "feat_max.npy"), feat_max)

    print(f"[DataGen] Dataset saved: {len(X)} samples, shape {X_norm.shape}")
    print(f"[DataGen] Class distribution: Normal={SAMPLES_PER_CLASS}, "
          f"Congestion={SAMPLES_PER_CLASS}, "
          f"LinkFailure={SAMPLES_PER_CLASS}, "
          f"NodeDown={SAMPLES_PER_CLASS}")
    return X_norm, y, feat_min, feat_max


if __name__ == "__main__":
    generate_and_save()
