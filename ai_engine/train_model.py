"""
LSTM Model Training Module
Builds and trains a PyTorch LSTM classifier for network fault prediction.

Architecture:
  Input  → LSTM (2 layers, hidden=128) → Dropout → FC(64) → ReLU → FC(4)
  Output: 4-class softmax (Normal, Congestion, LinkFailure, NodeDown)
"""

import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

from ai_engine.data_generator import generate_and_save, FEATURE_COLS

MODEL_PATH = "ai_engine/models/lstm_fault_model.pt"
SCALER_PATH = "ai_engine/models/scaler_params.npz"

CLASS_NAMES = ["Normal", "Congestion", "LinkFailure", "NodeDown"]


# ──────────────────────────────────────────────────────────────────────────────
# Model Definition
# ──────────────────────────────────────────────────────────────────────────────

class FaultLSTM(nn.Module):
    def __init__(self, input_size=7, hidden_size=128, num_layers=2,
                 num_classes=4, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )
        self.fc = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        # x: (batch, seq_len, features)
        _, (hn, _) = self.lstm(x)      # hn: (num_layers, batch, hidden)
        out = hn[-1]                   # take last layer's hidden state
        return self.fc(out)


# ──────────────────────────────────────────────────────────────────────────────
# Training
# ──────────────────────────────────────────────────────────────────────────────

def train():
    print("=" * 60)
    print("  LSTM Fault Prediction Model — Training")
    print("=" * 60)

    # 1. Generate / load dataset
    data_dir = "ai_engine"
    X_path = os.path.join(data_dir, "X_train.npy")
    y_path = os.path.join(data_dir, "y_train.npy")

    if not os.path.exists(X_path):
        X, y, feat_min, feat_max = generate_and_save(data_dir)
    else:
        print("[Train] Loading existing dataset...")
        X = np.load(X_path)
        y = np.load(y_path)
        feat_min = np.load(os.path.join(data_dir, "feat_min.npy"))
        feat_max = np.load(os.path.join(data_dir, "feat_max.npy"))

    # 2. Split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    print(f"[Train] Train: {len(X_train)} | Val: {len(X_val)}")

    # 3. PyTorch tensors
    Xt = torch.tensor(X_train, dtype=torch.float32)
    yt = torch.tensor(y_train, dtype=torch.long)
    Xv = torch.tensor(X_val, dtype=torch.float32)
    yv = torch.tensor(y_val, dtype=torch.long)

    train_loader = DataLoader(TensorDataset(Xt, yt), batch_size=64, shuffle=True)
    val_loader = DataLoader(TensorDataset(Xv, yv), batch_size=128)

    # 4. Model, optimizer, loss
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Train] Device: {device}")

    model = FaultLSTM(input_size=len(FEATURE_COLS)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)
    criterion = nn.CrossEntropyLoss()

    # 5. Training loop
    EPOCHS = 30
    best_val_acc = 0
    best_state = None

    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss, correct, total = 0, 0, 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item() * len(yb)
            correct += (logits.argmax(1) == yb).sum().item()
            total += len(yb)

        train_acc = correct / total

        # Validation
        model.eval()
        val_correct, val_total = 0, 0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                preds = model(xb).argmax(1)
                val_correct += (preds == yb).sum().item()
                val_total += len(yb)
        val_acc = val_correct / val_total
        scheduler.step(1 - val_acc)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        print(f"  Epoch {epoch:2d}/{EPOCHS} | "
              f"Loss: {total_loss/total:.4f} | "
              f"Train Acc: {train_acc:.4f} | "
              f"Val Acc: {val_acc:.4f}")

    # 6. Save best model
    os.makedirs("ai_engine/models", exist_ok=True)
    model.load_state_dict(best_state)
    torch.save({
        "model_state": model.state_dict(),
        "input_size": len(FEATURE_COLS),
        "classes": CLASS_NAMES,
    }, MODEL_PATH)
    np.savez(SCALER_PATH, feat_min=feat_min, feat_max=feat_max)

    print(f"\n[Train] [OK] Best Val Accuracy: {best_val_acc:.4f}")
    print(f"[Train] Model saved -> {MODEL_PATH}")

    # 7. Final classification report
    model.eval()
    all_preds, all_true = [], []
    with torch.no_grad():
        for xb, yb in val_loader:
            xb = xb.to(device)
            all_preds.extend(model(xb).argmax(1).cpu().numpy())
            all_true.extend(yb.numpy())

    print("\n" + classification_report(all_true, all_preds, target_names=CLASS_NAMES))
    return model, feat_min, feat_max


if __name__ == "__main__":
    train()
