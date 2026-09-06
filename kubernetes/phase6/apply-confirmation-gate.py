#!/usr/bin/env python3
"""
Apply Confirmation Gate Retroactively to Prediction Logs
Processes prediction logs and applies two-consecutive-forecast logic
"""

import sys
import re
from datetime import datetime
from pathlib import Path
from confirmation_gate import ConfirmationGate
import json

def parse_prediction_log(log_file):
    """Parse prediction service log and extract predictions"""
    predictions = []
    current_timestamp = None
    current_pod = None
    current_psi = None
    predicted_psi = None
    spike_predicted = None
    
    with open(log_file, 'r') as f:
        for line in f:
            # Extract timestamp
            ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if ts_match:
                current_timestamp = datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S')
            
            # Extract pod name
            if 'Pod workload-app-' in line:
                pod_match = re.search(r'Pod (workload-app-\d+)', line)
                if pod_match:
                    current_pod = pod_match.group(1)
            
            # Extract current PSI
            if 'Current PSI:' in line:
                psi_match = re.search(r'Current PSI:\s+([\d.]+)%', line)
                if psi_match:
                    current_psi = float(psi_match.group(1))
            
            # Extract predicted PSI (q90)
            if 'Predicted q90:' in line:
                pred_match = re.search(r'Predicted q90:\s+([\d.]+)%', line)
                if pred_match:
                    predicted_psi = float(pred_match.group(1))
            
            # Extract spike prediction
            if 'Spike predicted:' in line:
                spike_predicted = 'True' in line
                
                # Save complete prediction
                if all(v is not None for v in [current_timestamp, current_pod, current_psi, predicted_psi]):
                    predictions.append({
                        'timestamp': current_timestamp,
                        'pod': current_pod,
                        'current_psi': current_psi,
                        'predicted_psi': predicted_psi,
                        'spike_predicted': spike_predicted
                    })
                
                # Reset for next prediction
                current_pod = None
                current_psi = None
                predicted_psi = None
                spike_predicted = None
    
    return predictions

def apply_confirmation_gate(predictions, threshold=1.80, window_seconds=60):
    """Apply confirmation gate to predictions"""
    gate = ConfirmationGate(threshold=threshold, window_seconds=window_seconds)
    
    results = []
    for pred in predictions:
        is_spike, is_confirmed, reason = gate.check_spike(
            pod=pred['pod'],
            psi_value=pred['current_psi'],
            predicted_psi=pred['predicted_psi'],
            timestamp=pred['timestamp']
        )
        
        results.append({
            **pred,
            'gate_is_spike': is_spike,
            'gate_is_confirmed': is_confirmed,
            'gate_reason': reason
        })
    
    return results, gate.get_stats()

def calculate_metrics(predictions, confirmed_predictions, threshold=1.80):
    """Calculate metrics for raw and gated predictions"""
    
    # Raw predictions
    raw_tp = sum(1 for p in predictions if p['spike_predicted'] and p['current_psi'] > threshold)
    raw_fp = sum(1 for p in predictions if p['spike_predicted'] and p['current_psi'] <= threshold)
    raw_fn = sum(1 for p in predictions if not p['spike_predicted'] and p['current_psi'] > threshold)
    raw_tn = sum(1 for p in predictions if not p['spike_predicted'] and p['current_psi'] <= threshold)
    
    raw_precision = raw_tp / (raw_tp + raw_fp) if (raw_tp + raw_fp) > 0 else 0
    raw_recall = raw_tp / (raw_tp + raw_fn) if (raw_tp + raw_fn) > 0 else 0
    raw_f1 = 2 * (raw_precision * raw_recall) / (raw_precision + raw_recall) if (raw_precision + raw_recall) > 0 else 0
    
    # Gated predictions
    gate_tp = sum(1 for p in confirmed_predictions if p['gate_is_confirmed'] and p['current_psi'] > threshold)
    gate_fp = sum(1 for p in confirmed_predictions if p['gate_is_confirmed'] and p['current_psi'] <= threshold)
    gate_fn = sum(1 for p in confirmed_predictions if not p['gate_is_confirmed'] and p['current_psi'] > threshold)
    gate_tn = sum(1 for p in confirmed_predictions if not p['gate_is_confirmed'] and p['current_psi'] <= threshold)
    
    gate_precision = gate_tp / (gate_tp + gate_fp) if (gate_tp + gate_fp) > 0 else 0
    gate_recall = gate_tp / (gate_tp + gate_fn) if (gate_tp + gate_fn) > 0 else 0
    gate_f1 = 2 * (gate_precision * gate_recall) / (gate_precision + gate_recall) if (gate_precision + gate_recall) > 0 else 0
    
    return {
        'raw': {
            'true_positives': raw_tp,
            'false_positives': raw_fp,
            'false_negatives': raw_fn,
            'true_negatives': raw_tn,
            'precision': raw_precision * 100,
            'recall': raw_recall * 100,
            'f1_score': raw_f1 * 100
        },
        'gated': {
            'true_positives': gate_tp,
            'false_positives': gate_fp,
            'false_negatives': gate_fn,
            'true_negatives': gate_tn,
            'precision': gate_precision * 100,
            'recall': gate_recall * 100,
            'f1_score': gate_f1 * 100
        }
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 apply-confirmation-gate.py <prediction-log-file>")
        print("\nExample:")
        print("  python3 apply-confirmation-gate.py prediction-logs-*/predictions.log")
        sys.exit(1)
    
    log_file = sys.argv[1]
    
    print("=" * 70)
    print(" Confirmation Gate Analysis")
    print("=" * 70)
    print()
    
    # Parse log
    print(f"Parsing log: {log_file}")
    predictions = parse_prediction_log(log_file)
    print(f"✅ Parsed {len(predictions)} predictions")
    print()
    
    # Apply gate
    print("Applying confirmation gate...")
    confirmed_predictions, gate_stats = apply_confirmation_gate(predictions)
    print(f"✅ Processed with confirmation gate")
    print()
    
    # Calculate metrics
    print("=" * 70)
    print(" Comparison: Raw vs Gated Predictions")
    print("=" * 70)
    print()
    
    metrics = calculate_metrics(predictions, confirmed_predictions)
    
    print("RAW PREDICTIONS (no confirmation):")
    print(f"  True Positives:  {metrics['raw']['true_positives']}")
    print(f"  False Positives: {metrics['raw']['false_positives']}")
    print(f"  False Negatives: {metrics['raw']['false_negatives']}")
    print(f"  Precision: {metrics['raw']['precision']:.2f}%")
    print(f"  Recall:    {metrics['raw']['recall']:.2f}%")
    print(f"  F1 Score:  {metrics['raw']['f1_score']:.2f}%")
    print()
    
    print("GATED PREDICTIONS (two-consecutive confirmation):")
    print(f"  True Positives:  {metrics['gated']['true_positives']}")
    print(f"  False Positives: {metrics['gated']['false_positives']}")
    print(f"  False Negatives: {metrics['gated']['false_negatives']}")
    print(f"  Precision: {metrics['gated']['precision']:.2f}%")
    print(f"  Recall:    {metrics['gated']['recall']:.2f}%")
    print(f"  F1 Score:  {metrics['gated']['f1_score']:.2f}%")
    print()
    
    print("GATE STATISTICS:")
    print(f"  Total predictions: {gate_stats['total_predictions']}")
    print(f"  Single spike predictions: {gate_stats['single_spike_predictions']}")
    print(f"  Confirmed spikes: {gate_stats['confirmed_spikes']}")
    print(f"  Confirmation rate: {gate_stats['confirmation_rate']:.1f}%")
    print()
    
    # Improvement
    fp_reduction = metrics['raw']['false_positives'] - metrics['gated']['false_positives']
    if fp_reduction > 0:
        print(f"✅ FALSE POSITIVE REDUCTION: {fp_reduction} ({fp_reduction / metrics['raw']['false_positives'] * 100:.1f}%)")
    
    precision_improvement = metrics['gated']['precision'] - metrics['raw']['precision']
    if precision_improvement > 0:
        print(f"✅ PRECISION IMPROVEMENT: +{precision_improvement:.2f}%")
    
    print()
    
    # Save results
    output_file = Path(log_file).parent / "confirmation-gate-analysis.json"
    with open(output_file, 'w') as f:
        json.dump({
            'metrics': metrics,
            'gate_stats': gate_stats,
            'total_predictions': len(predictions),
            'confirmed_spikes': gate_stats['confirmed_spikes']
        }, f, indent=2)
    
    print(f"✅ Results saved to: {output_file}")
    print()
    
    print("=" * 70)
    print(" Recommendation for Paper")
    print("=" * 70)
    print()
    print("Report BOTH metrics separately:")
    print()
    print(f"1. Raw prediction performance: {metrics['raw']['precision']:.1f}% precision, {metrics['raw']['recall']:.1f}% recall")
    print(f"2. Gated prediction (production): {metrics['gated']['precision']:.1f}% precision, {metrics['gated']['recall']:.1f}% recall")
    print()
    print("The gated version represents what will actually ship to production,")
    print("with confirmation logic to reduce false positives.")
    print()

if __name__ == '__main__':
    main()
