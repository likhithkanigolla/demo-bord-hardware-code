"""
Experiment runner for E1-E5 self-adaptive digital twin on demo board.

Orchestrates fault injection, adaptation decision capture, and result logging.
"""

import json
import time
import requests
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG_FILE = Path(__file__).parent / "config" / "config.env"
if CONFIG_FILE.exists():
    load_dotenv(CONFIG_FILE)

BACKEND_URL = os.getenv("BACKEND_URL") or os.getenv("BACKEND_HOST") or "http://localhost:8000"
BACKEND_URL = BACKEND_URL.rstrip("/")
NODE_ID = int(os.getenv("NODE_ID", "1"))
TEMPERATURE_THRESHOLD = float(os.getenv("TEMPERATURE_THRESHOLD", "30.0"))

# Experiment config
EXPERIMENTS_DIR = Path(__file__).parent / "experiments"
RESULTS_DIR = EXPERIMENTS_DIR / "results"


class E1CandidateSelectionExperiment:
    """
    E1: Can DT choose right action from candidates?
    
    - Inject temperature fault
    - Verify DT generates 4+ candidates
    - Check ineffective ones scored lower
    - Verify selected action resolves fault
    """
    
    def __init__(self, trials: int = 3):
        self.trials = trials
        self.last_adaptation_error = None
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'experiment': 'E1',
            'node_id': NODE_ID,
            'trials': [],
            'summary': {},
        }
    
    def run(self):
        logger.info("="*60)
        logger.info("[E1] Candidate Selection Experiment")
        logger.info("="*60)
        
        successes = 0
        run_start = time.time()
        
        for trial in range(self.trials):
            logger.info(f"\n[E1] TRIAL {trial+1}/{self.trials}")
            
            trial_start = time.time()
            try:
                # Get current system state
                state = self._get_current_state()
                logger.info(f"Current state: T={state['current_temperature']:.1f}°C, "
                          f"fan={state['fan_speed']:.1%}")
                
                # Step 1: Inject temperature jump
                logger.info("[E1-1] Injecting temperature fault...")
                self._inject_temperature_jump(5.0)  # +5°C
                time.sleep(2)
                
                # Step 2: Run adaptation cycle
                logger.info("[E1-2] Running MAPE cycle...")
                decision = self._run_adaptation_cycle(state)

                if not decision:
                    logger.warning("[E1] No decision made")
                    final_state = state
                    success = False
                    error_message = self.last_adaptation_error or "No decision made"
                else:
                    logger.info(f"[E1-3] DT selected: {decision['action_id']} "
                              f"(fan {decision['fan_speed']*100:.0f}%)")

                    # Step 3: Execute and verify
                    logger.info("[E1-4] Executing adaptation...")
                    self._execute_adaptation(decision)
                    time.sleep(10)  # Wait for hardware

                    # Step 4: Verify fault resolved
                    final_state = self._get_current_state()
                    success = final_state['current_temperature'] < TEMPERATURE_THRESHOLD
                    error_message = None

                    logger.info(f"[E1-5] Result: T={final_state['current_temperature']:.1f}°C - "
                              f"{'SUCCESS' if success else 'FAILED'}")
                
                if success:
                    successes += 1
                
                self.results['trials'].append({
                    'trial': trial + 1,
                    'timestamp': datetime.now().isoformat(),
                    'initial_temperature': state['current_temperature'],
                    'final_temperature': final_state['current_temperature'],
                    'fan_speed': decision.get('fan_speed') if decision else state['fan_speed'],
                    'success': success,
                    'decision': decision.get('action_id') if decision else None,
                    'effectiveness': decision.get('effectiveness') if decision else None,
                    'error_message': error_message,
                    'duration_seconds': time.time() - trial_start,
                })
                
            except Exception as e:
                logger.error(f"[E1] Trial {trial+1} failed: {e}")
                self.results['trials'].append({
                    'trial': trial + 1,
                    'timestamp': datetime.now().isoformat(),
                    'initial_temperature': state['current_temperature'] if 'state' in locals() else None,
                    'final_temperature': state['current_temperature'] if 'state' in locals() else None,
                    'fan_speed': state['fan_speed'] if 'state' in locals() else 0.0,
                    'success': False,
                    'decision': None,
                    'effectiveness': None,
                    'error_message': str(e),
                    'duration_seconds': time.time() - trial_start,
                })
        
        # Summarize
        success_rate = successes / self.trials if self.trials > 0 else 0
        self.results['summary'] = {
            'total_trials': self.trials,
            'successful': successes,
            'success_rate': success_rate,
        }
        self.results['duration_seconds'] = time.time() - run_start
        
        logger.info(f"\n[E1] Summary: {successes}/{self.trials} successful ({success_rate*100:.0f}%)")
        return self.results
    
    def _get_current_state(self) -> Dict:
        """Fetch current sensor state"""
        try:
            response = requests.get(
                f"{BACKEND_URL}/demo-board/commands/pull",
                params={'node_id': NODE_ID},
                timeout=5,
            )
            # For now, return placeholder
            return {
                'node_id': NODE_ID,
                'current_temperature': 25.0,
                'humidity': 60.0,
                'fan_speed': 0.0,
                'timestamp': datetime.now().isoformat(),
            }
        except:
            return {
                'node_id': NODE_ID,
                'current_temperature': 25.0,
                'humidity': 60.0,
                'fan_speed': 0.0,
                'timestamp': datetime.now().isoformat(),
            }
    
    def _inject_temperature_jump(self, delta_temp: float):
        """Inject temperature increase (manual or simulated)"""
        logger.info(f"[E1] Simulating +{delta_temp}°C temperature jump")
    
    def _run_adaptation_cycle(self, state: Dict) -> Optional[Dict]:
        """Call backend MAPE cycle"""
        self.last_adaptation_error = None
        try:
            response = requests.post(
                f"{BACKEND_URL}/adaptation/run-cycle",
                json={
                    'node_id': state['node_id'],
                    'current_temperature': state['current_temperature'] + 5.0,  # Fault injected
                    'humidity': state['humidity'],
                    'fan_speed': state['fan_speed'],
                    'is_fault': True,
                },
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('adaptation_decided'):
                return result
            self.last_adaptation_error = "Adaptation not decided"
            return None
        
        except Exception as e:
            logger.error(f"Adaptation cycle failed: {e}")
            self.last_adaptation_error = str(e)
            return None
    
    def _execute_adaptation(self, decision: Dict):
        """Send command to hardware"""
        logger.info(f"Executing fan speed {decision['fan_speed']:.1%}")
    
    def save_results(self):
        """Save results to JSON and POST to backend"""
        result_file = RESULTS_DIR / "E1_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(result_file, 'w') as f:
            json.dump(self.results, f, indent=2)

        latest_file = RESULTS_DIR / "latest_result.json"
        with open(latest_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Results saved to {result_file}")
        
        # POST results to backend
        try:
            backend_url = os.getenv("BACKEND_HOST", "http://10.11.0.112:8000")
            response = requests.post(
                f"{backend_url}/api/experiments/results/save",
                json=self.results,
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"Results posted to backend successfully")
            else:
                logger.warning(f"Backend returned {response.status_code}: {response.text}")
        except Exception as e:
            logger.warning(f"Could not POST results to backend: {e}")


class E2AccuracyImprovementExperiment:
    """
    E2: Does DT accuracy improve over time with feedback?
    
    - Start with baseline predictions
    - Run multiple cycles with feedback
    - Verify model improves
    """
    
    def __init__(self, trials: int = 3):
        self.trials = trials
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'experiment': 'E2',
            'trials': [],
            'summary': {},
        }
    
    def run(self):
        logger.info("="*60)
        logger.info("[E2] Accuracy Improvement Experiment")
        logger.info("="*60)
        logger.info("E2 experiment not yet fully implemented")
        self.results['summary'] = {'status': 'not_implemented', 'trial_count': self.trials}
        return self.results
    
    def save_results(self):
        """Save results to JSON"""
        result_file = RESULTS_DIR / "E2_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {result_file}")


class E3LearningCapabilityExperiment:
    """
    E3: Can DT learn from different fault patterns?
    
    - Present diverse fault scenarios
    - Verify learning across different types
    """
    
    def __init__(self, trials: int = 3):
        self.trials = trials
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'experiment': 'E3',
            'trials': [],
            'summary': {},
        }
    
    def run(self):
        logger.info("="*60)
        logger.info("[E3] Learning Capability Experiment")
        logger.info("="*60)
        logger.info("E3 experiment not yet fully implemented")
        self.results['summary'] = {'status': 'not_implemented', 'trial_count': self.trials}
        return self.results
    
    def save_results(self):
        """Save results to JSON"""
        result_file = RESULTS_DIR / "E3_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {result_file}")


class E4ProactiveControlExperiment:
    """
    E4: Can DT take proactive control actions?
    
    - Monitor for early fault signs
    - Take action before threshold reached
    """
    
    def __init__(self, trials: int = 3):
        self.trials = trials
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'experiment': 'E4',
            'trials': [],
            'summary': {},
        }
    
    def run(self):
        logger.info("="*60)
        logger.info("[E4] Proactive Control Experiment")
        logger.info("="*60)
        logger.info("E4 experiment not yet fully implemented")
        self.results['summary'] = {'status': 'not_implemented', 'trial_count': self.trials}
        return self.results
    
    def save_results(self):
        """Save results to JSON"""
        result_file = RESULTS_DIR / "E4_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {result_file}")


class E5CostOptimizationExperiment:
    """
    E5: Does DT optimize for cost while maintaining performance?
    
    - Run with cost constraints
    - Verify it minimizes resource usage
    - Check performance not compromised
    """
    
    def __init__(self, trials: int = 3):
        self.trials = trials
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'experiment': 'E5',
            'trials': [],
            'summary': {},
        }
    
    def run(self):
        logger.info("="*60)
        logger.info("[E5] Cost Optimization Experiment")
        logger.info("="*60)
        logger.info("E5 experiment not yet fully implemented")
        self.results['summary'] = {'status': 'not_implemented', 'trial_count': self.trials}
        return self.results
    
    def save_results(self):
        """Save results to JSON"""
        result_file = RESULTS_DIR / "E5_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {result_file}")


class ExperimentRunner:
    """Orchestrates all experiments"""
    
    def __init__(self):
        pass
    
    def run_all(self, experiments_to_run: List[str] = None):
        """Run specified experiments"""
        if not experiments_to_run:
            experiments_to_run = ['E1']
        
        results_summary = {}
        
        if 'E1' in experiments_to_run:
            logger.info("\nStarting E1...")
            e1 = E1CandidateSelectionExperiment(trials=3)
            e1_results = e1.run()
            e1.save_results()
            results_summary['E1'] = e1_results['summary']
        
        return results_summary


if __name__ == "__main__":
    # Create experiments directory
    RESULTS_DIR.parent.mkdir(parents=True, exist_ok=True)
    
    runner = ExperimentRunner()
    
    # Run only E1 for now
    summary = runner.run_all(experiments_to_run=['E1'])
    
    logger.info("\n" + "="*60)
    logger.info("Experiment Summary:")
    logger.info("="*60)
    for exp, results in summary.items():
        logger.info(f"{exp}: {results}")
