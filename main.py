"""
Main Entry Point
Self-Healing Network Using AI-Integrated Digital Twins
Focus: Resource Optimization

Run order:
  Step 1 (first time only): python main.py --train
  Step 2 (always):          python main.py
"""

import sys
import os

# Ensure project root is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def train():
    """Train the LSTM model before running the dashboard."""
    print("\n" + "=" * 60)
    print("  STEP 1: Training LSTM Fault Prediction Model")
    print("=" * 60 + "\n")
    from ai_engine.train_model import train as run_train
    run_train()
    print("\n[OK] Training complete! Now run:  python main.py\n")


def run_dashboard():
    """Start the full self-healing system + web dashboard."""
    print("\n" + "=" * 60)
    print("  Self-Healing Network — AI Digital Twin System")
    print("  Resource Optimization | Real-Time Dashboard")
    print("=" * 60)

    model_path = "ai_engine/models/lstm_fault_model.pt"
    if not os.path.exists(model_path):
        print("\n[!] No trained model found!")
        print("   Run first: python main.py --train\n")
        ans = input("   Train now? (y/n): ").strip().lower()
        if ans == 'y':
            train()
        else:
            print("   Starting without AI predictions (rule-based healing only).\n")

    print("\n  Open your browser at: http://127.0.0.1:5000\n")

    from dashboard.app import start
    start()


if __name__ == "__main__":
    if "--train" in sys.argv:
        train()
    else:
        run_dashboard()
