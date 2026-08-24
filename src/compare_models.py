"""
Quick comparison between original and improved models
Shows the key differences without full retraining
"""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"

print("=" * 70)
print("PRESYNC MODEL COMPARISON")
print("=" * 70)

# Check model files
original_model = MODEL_DIR / "tft_psi_model.ckpt"
improved_model = MODEL_DIR / "tft_psi_model_improved.ckpt"

print("\nModel Files:")
print(f"  Original: {original_model.exists()} - {original_model}")
print(f"  Improved: {improved_model.exists()} - {improved_model}")

# Load data statistics
train_df = pd.read_csv(DATA_DIR / "train.csv")
val_df = pd.read_csv(DATA_DIR / "validation.csv")
test_df = pd.read_csv(DATA_DIR / "test.csv")

SPIKE_THRESHOLD = 2.0
TARGET = "psi_some_avg10"

# Spike statistics
train_spikes = (train_df[TARGET] >= SPIKE_THRESHOLD).sum()
val_spikes = (val_df[TARGET] >= SPIKE_THRESHOLD).sum()
test_spikes = (test_df[TARGET] >= SPIKE_THRESHOLD).sum()

print("\n" + "=" * 70)
print("DATASET STATISTICS")
print("=" * 70)
print(f"\nRows:")
print(f"  Train: {len(train_df):,}")
print(f"  Val:   {len(val_df):,}")
print(f"  Test:  {len(test_df):,}")

print(f"\nSpike Timesteps (PSI >= {SPIKE_THRESHOLD}):")
print(f"  Train: {train_spikes:4d} ({100*train_spikes/len(train_df):5.2f}%)")
print(f"  Val:   {val_spikes:4d} ({100*val_spikes/len(val_df):5.2f}%)")
print(f"  Test:  {test_spikes:4d} ({100*test_spikes/len(test_df):5.2f}%)")

print("\n" + "=" * 70)
print("CONFIGURATION COMPARISON")
print("=" * 70)

configs = [
    ("Hidden Size", "8", "64", "8x increase"),
    ("Attention Heads", "2", "4", "2x increase"),
    ("Gradient Clip", "0.1", "1.0", "10x less aggressive"),
    ("Early Stop Patience", "3", "6", "2x more patient"),
    ("Max Epochs", "3", "20", "6.7x more training"),
    ("Spike Weighting", "None", "5.0x", "Class imbalance fix"),
    ("Derivative Features", "No", "Yes", "+4 features"),
    ("CQR Calibration", "No", "Yes", "Post-hoc fix"),
]

print(f"\n{'Parameter':<22} {'Original':<12} {'Improved':<12} {'Change'}")
print("-" * 70)
for param, orig, improved, change in configs:
    print(f"{param:<22} {orig:<12} {improved:<12} {change}")

print("\n" + "=" * 70)
print("EXPECTED IMPROVEMENTS")
print("=" * 70)

improvements = [
    ("Recall", "60.2%", "85-95%", "✓ Main goal"),
    ("Precision", "96.9%", "90-97%", "Should maintain"),
    ("Interval Coverage", "68.8%", "75-82%", "With CQR"),
    ("F1 Score", "74.3%", "87-95%", "Better balance"),
]

print(f"\n{'Metric':<20} {'Original':<12} {'Expected':<12} {'Status'}")
print("-" * 70)
for metric, orig, expected, status in improvements:
    print(f"{metric:<20} {orig:<12} {expected:<12} {status}")

print("\n" + "=" * 70)
print("ROOT CAUSES ADDRESSED")
print("=" * 70)

root_causes = [
    ("✓", "Model too small (hidden_size=8)", "Increased to 64"),
    ("✓", "Aggressive gradient clip (0.1)", "Relaxed to 1.0"),
    ("✓", "Class imbalance (no weighting)", "5x weight for spikes"),
    ("✓", "Early stopping too tight", "Patience increased to 6"),
    ("✓", "No leading indicators", "Added derivative features"),
    ("✓", "Coverage under-calibrated", "CQR calibration added"),
]

for status, cause, fix in root_causes:
    print(f"\n{status} {cause}")
    print(f"   → {fix}")

print("\n" + "=" * 70)
print("NEXT STEPS")
print("=" * 70)

if improved_model.exists():
    print("\n✓ Improved model exists - ready for evaluation")
    print(f"  Run: python src/predict_tft_improved.py")
else:
    print("\n⚠ Improved model not trained yet")
    print(f"  Run: python src/train_tft_improved.py")
    print(f"  Expected training time: 30-45 minutes on CPU")

# Check if original predictions exist
original_pred = DATA_DIR / "tft_predictions.csv"
improved_pred = DATA_DIR / "tft_predictions_improved.csv"

print("\nPrediction Files:")
if original_pred.exists():
    orig_df = pd.read_csv(original_pred)
    print(f"  ✓ Original predictions: {len(orig_df):,} rows")
else:
    print(f"  ✗ Original predictions not found")
    
if improved_pred.exists():
    imp_df = pd.read_csv(improved_pred)
    print(f"  ✓ Improved predictions: {len(imp_df):,} rows")
else:
    print(f"  ✗ Improved predictions not found (run predict_tft_improved.py)")

print("\n" + "=" * 70)
