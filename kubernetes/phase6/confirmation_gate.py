#!/usr/bin/env python3
"""
Step 6: Confirmation Gate Logic
Two-consecutive-forecast confirmation to reduce false positives
Phase 8 prerequisite for HPA integration
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import json

class ConfirmationGate:
    """
    Implements two-consecutive-forecast spike confirmation
    Reduces false positives before triggering HPA scaling
    """
    
    def __init__(self, threshold: float = 1.80, window_seconds: int = 60):
        """
        Args:
            threshold: PSI threshold for spike detection (%).
                       Default 1.80 is a project-chosen operating point,
                       not empirically validated. The host experiment
                       (verdict.json) tested cgroup avg10; production feeds
                       a Prometheus deriv() value — a different signal.
                       Recall at T=1.8 on cgroup avg10 was 0.07 (UNDERPOWERED).
            window_seconds: Time window for consecutive predictions
        """
        self.threshold = threshold
        self.window_seconds = window_seconds
        
        # Track last prediction for each pod
        self.last_predictions: Dict[str, Tuple[datetime, bool]] = {}
        
        # Track confirmation state
        self.confirmed_spikes: Dict[str, datetime] = {}
        
        # Statistics
        self.stats = {
            'total_predictions': 0,
            'single_spike_predictions': 0,
            'confirmed_spikes': 0,
            'false_positive_reductions': 0
        }
    
    def check_spike(self, pod: str, psi_value: float, predicted_psi: float, 
                    timestamp: Optional[datetime] = None) -> Tuple[bool, bool, str]:
        """
        Check if spike should be confirmed
        
        Args:
            pod: Pod name
            psi_value: Current PSI value
            predicted_psi: Predicted PSI value (q90)
            timestamp: Prediction timestamp (default: now)
        
        Returns:
            Tuple of (is_spike, is_confirmed, reason)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self.stats['total_predictions'] += 1
        
        # Check if current prediction indicates spike
        is_spike = predicted_psi > self.threshold
        
        if not is_spike:
            # No spike predicted, clear previous state
            if pod in self.last_predictions:
                del self.last_predictions[pod]
            return False, False, "No spike predicted"
        
        self.stats['single_spike_predictions'] += 1
        
        # Check for previous spike prediction
        if pod not in self.last_predictions:
            # First spike prediction for this pod
            self.last_predictions[pod] = (timestamp, is_spike)
            return True, False, "First spike prediction - awaiting confirmation"
        
        # Get previous prediction
        prev_timestamp, prev_spike = self.last_predictions[pod]
        
        # Check if within confirmation window
        time_diff = (timestamp - prev_timestamp).total_seconds()
        
        if time_diff > self.window_seconds:
            # Too much time passed, treat as new prediction
            self.last_predictions[pod] = (timestamp, is_spike)
            return True, False, f"Previous spike expired ({time_diff:.0f}s > {self.window_seconds}s)"
        
        # Check if previous was also a spike
        if prev_spike:
            # CONFIRMED: Two consecutive spike predictions
            self.confirmed_spikes[pod] = timestamp
            self.stats['confirmed_spikes'] += 1
            self.last_predictions[pod] = (timestamp, is_spike)
            return True, True, f"CONFIRMED: Two consecutive spikes within {time_diff:.0f}s"
        else:
            # Previous was not a spike
            self.last_predictions[pod] = (timestamp, is_spike)
            return True, False, "Previous prediction was not a spike"
    
    def would_reduce_false_positive(self, pod: str) -> bool:
        """Check if this would have been a false positive without confirmation"""
        if pod in self.last_predictions:
            _, was_spike = self.last_predictions[pod]
            if not was_spike:
                self.stats['false_positive_reductions'] += 1
                return True
        return False
    
    def get_stats(self) -> dict:
        """Get confirmation gate statistics"""
        total_single = self.stats['single_spike_predictions']
        total_confirmed = self.stats['confirmed_spikes']
        
        return {
            **self.stats,
            'confirmation_rate': (total_confirmed / total_single * 100) if total_single > 0 else 0,
            'reduction_rate': (self.stats['false_positive_reductions'] / total_single * 100) if total_single > 0 else 0
        }
    
    def reset_pod(self, pod: str):
        """Reset confirmation state for a pod"""
        if pod in self.last_predictions:
            del self.last_predictions[pod]
        if pod in self.confirmed_spikes:
            del self.confirmed_spikes[pod]
    
    def to_dict(self) -> dict:
        """Export state to dictionary"""
        return {
            'threshold': self.threshold,
            'window_seconds': self.window_seconds,
            'last_predictions': {
                pod: {'timestamp': ts.isoformat(), 'is_spike': spike}
                for pod, (ts, spike) in self.last_predictions.items()
            },
            'confirmed_spikes': {
                pod: ts.isoformat()
                for pod, ts in self.confirmed_spikes.items()
            },
            'stats': self.get_stats()
        }
    
    def __repr__(self):
        stats = self.get_stats()
        return (f"ConfirmationGate(threshold={self.threshold}%, "
                f"confirmed={stats['confirmed_spikes']}/{stats['single_spike_predictions']}, "
                f"rate={stats['confirmation_rate']:.1f}%)")


# Example usage and testing
if __name__ == '__main__':
    print("=" * 70)
    print(" Confirmation Gate - Unit Tests")
    print("=" * 70)
    print()
    
    gate = ConfirmationGate(threshold=1.80, window_seconds=60)
    
    # Test Case 1: Single spike prediction (not confirmed)
    print("Test 1: Single spike prediction")
    is_spike, confirmed, reason = gate.check_spike('pod-0', 1.5, 2.0)
    print(f"  Spike: {is_spike}, Confirmed: {confirmed}")
    print(f"  Reason: {reason}")
    assert is_spike == True
    assert confirmed == False
    print("  ✅ Pass")
    print()
    
    # Test Case 2: Second spike within window (confirmed)
    print("Test 2: Second spike within window")
    is_spike, confirmed, reason = gate.check_spike('pod-0', 1.6, 2.1, 
                                                     timestamp=datetime.now() + timedelta(seconds=30))
    print(f"  Spike: {is_spike}, Confirmed: {confirmed}")
    print(f"  Reason: {reason}")
    assert is_spike == True
    assert confirmed == True
    print("  ✅ Pass")
    print()
    
    # Test Case 3: Second spike outside window (not confirmed, new prediction)
    print("Test 3: Second spike outside window")
    gate.reset_pod('pod-1')
    gate.check_spike('pod-1', 1.5, 2.0)
    is_spike, confirmed, reason = gate.check_spike('pod-1', 1.6, 2.1,
                                                     timestamp=datetime.now() + timedelta(seconds=90))
    print(f"  Spike: {is_spike}, Confirmed: {confirmed}")
    print(f"  Reason: {reason}")
    assert is_spike == True
    assert confirmed == False
    print("  ✅ Pass")
    print()
    
    # Test Case 4: No spike (cleared state)
    print("Test 4: No spike prediction")
    gate.check_spike('pod-2', 1.5, 2.0)
    is_spike, confirmed, reason = gate.check_spike('pod-2', 1.3, 1.4)
    print(f"  Spike: {is_spike}, Confirmed: {confirmed}")
    print(f"  Reason: {reason}")
    assert is_spike == False
    assert confirmed == False
    print("  ✅ Pass")
    print()
    
    # Test Case 5: Spike -> No Spike -> Spike (not confirmed, broken chain)
    print("Test 5: Broken spike chain")
    gate.reset_pod('pod-3')
    gate.check_spike('pod-3', 1.5, 2.0)
    gate.check_spike('pod-3', 1.3, 1.4, timestamp=datetime.now() + timedelta(seconds=20))
    is_spike, confirmed, reason = gate.check_spike('pod-3', 1.6, 2.1,
                                                     timestamp=datetime.now() + timedelta(seconds=40))
    print(f"  Spike: {is_spike}, Confirmed: {confirmed}")
    print(f"  Reason: {reason}")
    assert is_spike == True
    assert confirmed == False
    print("  ✅ Pass")
    print()
    
    # Statistics
    print("=" * 70)
    print(" Confirmation Gate Statistics")
    print("=" * 70)
    stats = gate.get_stats()
    print(json.dumps(stats, indent=2))
    print()
    
    print(f"Confirmation Rate: {stats['confirmation_rate']:.1f}%")
    print(f"  (Confirmed spikes / Total spike predictions)")
    print()
    
    print("✅ All tests passed")
    print()
    
    # Export state
    print("=" * 70)
    print(" Exportable State")
    print("=" * 70)
    print(json.dumps(gate.to_dict(), indent=2))
