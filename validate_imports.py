#!/usr/bin/env python3
"""
Validation script to verify all experiment classes can be imported.
This validates the fix for the ImportError that occurred when running pi_experiment_service.py
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def validate():
    print("=" * 60)
    print("Validating Pi Experiment Service Imports")
    print("=" * 60)
    
    try:
        print("\n1. Importing experiment classes from experiment_runner...")
        from experiment_runner import (
            E1CandidateSelectionExperiment,
            E2AccuracyImprovementExperiment,
            E3LearningCapabilityExperiment,
            E4ProactiveControlExperiment,
            E5CostOptimizationExperiment
        )
        print("   ✅ E1CandidateSelectionExperiment")
        print("   ✅ E2AccuracyImprovementExperiment")
        print("   ✅ E3LearningCapabilityExperiment")
        print("   ✅ E4ProactiveControlExperiment")
        print("   ✅ E5CostOptimizationExperiment")
        
        print("\n2. Importing FastAPI service...")
        from pi_experiment_service import app
        print("   ✅ FastAPI app loaded")
        
        print("\n3. Instantiating all experiment classes...")
        e1 = E1CandidateSelectionExperiment(trials=1)
        print("   ✅ E1 instantiated")
        e2 = E2AccuracyImprovementExperiment(trials=1)
        print("   ✅ E2 instantiated")
        e3 = E3LearningCapabilityExperiment(trials=1)
        print("   ✅ E3 instantiated")
        e4 = E4ProactiveControlExperiment(trials=1)
        print("   ✅ E4 instantiated")
        e5 = E5CostOptimizationExperiment(trials=1)
        print("   ✅ E5 instantiated")
        
        print("\n" + "=" * 60)
        print("✅ ALL VALIDATIONS PASSED")
        print("=" * 60)
        print("\nThe service is ready to run:")
        print("  bash start_experiment_service.sh")
        return True
        
    except ImportError as e:
        print(f"\n❌ IMPORT ERROR: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
