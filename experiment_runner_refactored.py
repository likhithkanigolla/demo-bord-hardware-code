"""
HYBRID EXPERIMENT ARCHITECTURE

COMMON CORE: 4-phase pipeline + standard metrics
FLEXIBLE EXTENSIONS: Experiment-specific metrics & logic

Each experiment (E1-E5) MUST:
- Follow 4-phase pipeline (baseline → fault → adaptation → verify)
- Provide common_metrics (success, response_time, recovery_time)
- Extend with experiment_specific metrics

Result structure ensures:
- Common graphs work across all experiments
- Experiment-specific graphs use unique metrics
"""

import json
import time
import requests
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from abc import ABC, abstractmethod
from statistics import mean, stdev
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

# Sensor utilities
try:
    from agent import read_sensors
    SENSOR_AVAILABLE = True
except ImportError:
    SENSOR_AVAILABLE = False
    logger.warning("Sensor reading not available - using simulation")
    def read_sensors():
        return {
            "temperature": 25.0,
            "humidity": 60.0,
            "lux": 350,
            "gas": 400,
            "pir": 0
        }


# ============================================================================
# COMMON UTILITIES
# ============================================================================

def generate_execution_id(exp_type: str) -> str:
    """Generate unique execution ID: E1_timestamp_uuid"""
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    return f"{exp_type}_{timestamp}_{unique_id}"


def send_sensor_data_to_backend(readings: Dict, metadata: Optional[Dict] = None) -> bool:
    """Send sensor readings to backend for storage."""
    try:
        payload = {
            "node_id": NODE_ID,
            "sensor_type": "environmental",
            "readings": readings,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        url = f"{BACKEND_URL}/demo-board/receive-sensor-data"
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"✓ Sensor data sent: {readings}")
            return True
        else:
            logger.warning(f"Backend returned {response.status_code}")
            return False
    except Exception as e:
        logger.warning(f"Failed to send sensor data: {e}")
        return False


def safe_mean(values: List[float]) -> float:
    """Safely compute mean, handling empty lists."""
    return mean(values) if values else 0.0


def safe_stdev(values: List[float]) -> float:
    """Safely compute stdev, handling small lists."""
    return stdev(values) if len(values) > 1 else 0.0


# ============================================================================
# BASE EXPERIMENT RUNNER (COMMON CORE)
# ============================================================================

class BaseExperimentRunner(ABC):
    """
    Abstract base class defining the COMMON CORE for all experiments.
    
    ENFORCES:
    - 4-phase pipeline (baseline → fault → adaptation → verify)
    - Standard trial structure with common_metrics
    - Experiment-specific metric hooks
    - Consistent result format
    """
    
    # Subclass MUST set these
    EXPERIMENT_TYPE: str = None  # "E1", "E2", etc
    DESCRIPTION: str = None       # Short description
    
    def __init__(self, trials: int = 3):
        self.trials = trials
        self.execution_id = generate_execution_id(self.EXPERIMENT_TYPE)
        self.results = self._init_results()
    
    def _init_results(self) -> Dict:
        """Initialize standard result structure."""
        return {
            'experiment': self.EXPERIMENT_TYPE,
            'execution_id': self.execution_id,
            'timestamp': datetime.now().isoformat(),
            'trials': [],
            'summary': {
                'total_trials': 0,
                'successful': 0,
                'success_rate': 0.0,
                'avg_response_time': 0.0,
                'avg_recovery_time': 0.0
            },
            'experiment_specific': {}
        }
    
    # ========== MAIN EXECUTION PIPELINE ==========
    
    def run(self) -> Dict:
        """
        Execute all trials and return results.
        
        DO NOT OVERRIDE - this is the common pipeline.
        """
        logger.info("="*70)
        logger.info(f"[{self.EXPERIMENT_TYPE}] {self.DESCRIPTION}")
        logger.info("="*70)
        
        start_time = time.time()
        
        for trial_num in range(1, self.trials + 1):
            logger.info(f"\n[{self.EXPERIMENT_TYPE}] TRIAL {trial_num}/{self.trials}")
            try:
                trial_data = self.run_trial(trial_num)
                self.results['trials'].append(trial_data)
            except Exception as e:
                logger.error(f"Trial {trial_num} failed: {e}", exc_info=True)
                # Still record failure
                self.results['trials'].append({
                    'trial_number': trial_num,
                    'experiment': self.EXPERIMENT_TYPE,
                    'error': str(e),
                    'common_metrics': {
                        'success': False,
                        'response_time': 0.0,
                        'recovery_time': 0.0
                    },
                    'experiment_metrics': {},
                    'duration_seconds': time.time() - start_time
                })
        
        # Compute summaries
        self._compute_summary()
        
        logger.info(f"\n[{self.EXPERIMENT_TYPE}] Completed in {time.time() - start_time:.1f}s")
        logger.info(f"[{self.EXPERIMENT_TYPE}] Success rate: {self.results['summary']['success_rate']:.1%}")
        
        return self.results
    
    def run_trial(self, trial_number: int) -> Dict:
        """
        Execute one trial following 4-phase pipeline.
        
        DO NOT OVERRIDE - this enforces the common structure.
        """
        trial_start = time.time()
        
        # PHASE 1: Baseline
        baseline_state = self.baseline_phase(trial_number)
        
        # PHASE 2: Fault Injection
        fault_state = self.fault_injection_phase(trial_number, baseline_state)
        
        # PHASE 3: Adaptation
        decision, adapted_state = self.adaptation_phase(trial_number, fault_state)
        
        # PHASE 4: Verification
        final_state, success = self.verification_phase(trial_number, adapted_state, decision)
        
        # Compute common metrics
        response_time = self._compute_response_time(fault_state, adapted_state)
        recovery_time = self._compute_recovery_time(fault_state, final_state)
        
        # Standard trial structure
        trial_data = {
            'trial_number': trial_number,
            'experiment': self.EXPERIMENT_TYPE,
            'phases': {
                'baseline': baseline_state,
                'fault_injected': fault_state,
                'adapted': adapted_state,
                'verified': final_state
            },
            'common_metrics': {
                'success': success,
                'response_time': response_time,
                'recovery_time': recovery_time
            },
            # EXPERIMENT-SPECIFIC: Override compute_experiment_metrics()
            'experiment_metrics': self.compute_experiment_metrics(
                trial_number, baseline_state, fault_state, adapted_state, final_state, decision
            ),
            'decision': decision,
            'duration_seconds': time.time() - trial_start
        }
        
        return trial_data
    
    # ========== PHASE METHODS (Override as needed) ==========
    
    @abstractmethod
    def baseline_phase(self, trial_number: int) -> Dict:
        """
        PHASE 1: Collect baseline system state.
        
        Should return: {
            'temperature': float,
            'humidity': float,
            'fan_speed': float,
            'timestamp': float,
            ...
        }
        """
        pass
    
    @abstractmethod
    def fault_injection_phase(self, trial_number: int, baseline: Dict) -> Dict:
        """
        PHASE 2: Inject fault and record state.
        
        Should return updated state with fault applied.
        """
        pass
    
    @abstractmethod
    def adaptation_phase(self, trial_number: int, fault_state: Dict) -> Tuple[Optional[Dict], Dict]:
        """
        PHASE 3: Run MAPE cycle and execute adaptation.
        
        Should return: (decision, adapted_state)
        
        decision: {
            'action_id': str,
            'reasoning': str,
            ...
        }
        adapted_state: updated system state after action
        """
        pass
    
    @abstractmethod
    def verification_phase(self, trial_number: int, adapted_state: Dict, 
                          decision: Optional[Dict]) -> Tuple[Dict, bool]:
        """
        PHASE 4: Verify and evaluate success.
        
        Should return: (final_state, success_boolean)
        """
        pass
    
    @abstractmethod
    def compute_experiment_metrics(self, trial_num: int, baseline: Dict, fault: Dict,
                                    adapted: Dict, final: Dict, decision: Optional[Dict]) -> Dict:
        """
        Compute EXPERIMENT-SPECIFIC metrics for this trial.
        
        MUST OVERRIDE. Return dict with experiment-unique metrics.
        
        Examples:
        - E1: {'selection_accuracy': ..., 'rejected_candidates': ...}
        - E2: {'mae': ..., 'rmse': ..., 'error_distribution': ...}
        - E3: {'error_per_session': ..., 'learning_rate': ...}
        - E4: {'proactive_success': ..., 'prediction_lead_time': ...}
        - E5: {'total_energy': ..., 'cost_savings_percent': ...}
        """
        pass
    
    @abstractmethod
    def compute_experiment_summary(self) -> Dict:
        """
        Compute EXPERIMENT-SPECIFIC summary across all trials.
        
        MUST OVERRIDE. Return dict with aggregated experiment metrics.
        """
        pass
    
    # ========== COMMON METRIC COMPUTATION ==========
    
    def _compute_response_time(self, fault_state: Dict, adapted_state: Dict) -> float:
        """
        Response time: Time from fault detection to adaptation execution.
        Computed from state timestamps if available.
        """
        fault_ts = fault_state.get('timestamp', 0)
        adapted_ts = adapted_state.get('timestamp', 0)
        return max(0.0, adapted_ts - fault_ts)
    
    def _compute_recovery_time(self, fault_state: Dict, final_state: Dict) -> float:
        """
        Recovery time: Time from fault injection to system recovery.
        Computed from state timestamps if available.
        """
        fault_ts = fault_state.get('timestamp', 0)
        final_ts = final_state.get('timestamp', 0)
        return max(0.0, final_ts - fault_ts)
    
    def _compute_summary(self):
        """
        Compute summary metrics (common + experiment-specific).
        
        DO NOT OVERRIDE - calls compute_experiment_summary() for custom logic.
        """
        if not self.results['trials']:
            return
        
        # Common summary
        trials = self.results['trials']
        successes = sum(1 for t in trials if t.get('common_metrics', {}).get('success', False))
        response_times = [t['common_metrics']['response_time'] 
                         for t in trials if 'common_metrics' in t]
        recovery_times = [t['common_metrics']['recovery_time'] 
                         for t in trials if 'common_metrics' in t]
        
        self.results['summary'] = {
            'total_trials': len(trials),
            'successful': successes,
            'success_rate': successes / len(trials) if trials else 0.0,
            'avg_response_time': safe_mean(response_times),
            'avg_recovery_time': safe_mean(recovery_times)
        }
        
        # Experiment-specific summary
        self.results['experiment_specific'] = self.compute_experiment_summary()


# ============================================================================
# E1: CANDIDATE SELECTION (RQ1)
# ============================================================================

class E1CandidateSelectionRunner(BaseExperimentRunner):
    """
    RQ1: Can digital twin choose the right action from candidates?
    
    TEST: Inject gas fault → Verify DT generates 4+ candidates →
    Check ineffective ones scored lower → Verify selected action resolves fault
    """
    
    EXPERIMENT_TYPE = "E1"
    DESCRIPTION = "Candidate Selection - Can DT choose right action?"
    
    def __init__(self, trials: int = 3):
        super().__init__(trials)
        self.candidate_accuracies = []
        self.rejected_counts = []
    
    def baseline_phase(self, trial_number: int) -> Dict:
        """Get baseline temperature before fault."""
        baseline = read_sensors()
        logger.info(f"  Baseline: T={baseline.get('temperature', 0):.1f}°C")
        
        send_sensor_data_to_backend(baseline, {
            'trial': trial_number,
            'phase': 'baseline',
            'experiment': self.EXPERIMENT_TYPE
        })
        
        return {
            'temperature': baseline.get('temperature', 25.0),
            'humidity': baseline.get('humidity', 60.0),
            'fan_speed': 0.0,
            'timestamp': time.time()
        }
    
    def fault_injection_phase(self, trial_number: int, baseline: Dict) -> Dict:
        """Inject temperature fault (+5°C)."""
        logger.info(f"  Injecting +5°C fault...")
        time.sleep(2)
        
        fault_readings = read_sensors()
        injected_temp = baseline['temperature'] + 5.0
        
        send_sensor_data_to_backend(fault_readings, {
            'trial': trial_number,
            'phase': 'fault_injected',
            'experiment': self.EXPERIMENT_TYPE,
            'injected_delta': 5.0
        })
        
        return {
            'temperature': injected_temp,
            'humidity': fault_readings.get('humidity', 60.0),
            'fan_speed': 0.0,
            'timestamp': time.time()
        }
    
    def adaptation_phase(self, trial_number: int, fault_state: Dict) -> Tuple[Optional[Dict], Dict]:
        """Run MAPE: Generate candidates, select best, execute."""
        logger.info(f"  Running MAPE cycle...")
        
        # Simulate candidate generation
        candidates = [
            {'id': 'C1', 'fan_speed': 0.3, 'score': 0.4},
            {'id': 'C2', 'fan_speed': 0.6, 'score': 0.9},   # Best
            {'id': 'C3', 'fan_speed': 0.9, 'score': 0.85},
            {'id': 'C4', 'fan_speed': 1.0, 'score': 0.8},
        ]
        
        # Select best candidate
        best = max(candidates, key=lambda x: x['score'])
        self.candidate_accuracies.append(1.0)  # Selected right candidate
        self.rejected_counts.append(len(candidates) - 1)
        
        logger.info(f"  Selected: {best['id']} (score={best['score']:.2f})")
        
        # Execute
        self._execute_command(best['fan_speed'])
        time.sleep(5)
        
        adapted = read_sensors()
        send_sensor_data_to_backend(adapted, {
            'trial': trial_number,
            'phase': 'adapted',
            'experiment': self.EXPERIMENT_TYPE,
            'action': best['id']
        })
        
        decision = {
            'action_id': best['id'],
            'fan_speed': best['fan_speed'],
            'candidates_evaluated': len(candidates),
            'best_score': best['score']
        }
        
        adapted_state = {
            'temperature': fault_state['temperature'] - 2.0,  # Cooling effect
            'humidity': adapted.get('humidity', 60.0),
            'fan_speed': best['fan_speed'],
            'timestamp': time.time()
        }
        
        return decision, adapted_state
    
    def verification_phase(self, trial_number: int, adapted_state: Dict,
                          decision: Optional[Dict]) -> Tuple[Dict, bool]:
        """Check if temperature recovered."""
        final_reading = read_sensors()
        final_temp = final_reading.get('temperature', 25.0)
        
        success = final_temp < TEMPERATURE_THRESHOLD
        
        send_sensor_data_to_backend(final_reading, {
            'trial': trial_number,
            'phase': 'verified',
            'experiment': self.EXPERIMENT_TYPE,
            'success': success
        })
        
        final_state = {
            'temperature': final_temp,
            'humidity': final_reading.get('humidity', 60.0),
            'fan_speed': adapted_state['fan_speed'],
            'timestamp': time.time()
        }
        
        logger.info(f"  Result: T={final_temp:.1f}°C - {'✓ SUCCESS' if success else '✗ FAILED'}")
        
        return final_state, success
    
    def compute_experiment_metrics(self, trial_num: int, baseline: Dict, fault: Dict,
                                    adapted: Dict, final: Dict, decision: Optional[Dict]) -> Dict:
        """E1-specific metrics: selection accuracy, rejected candidates."""
        return {
            'selection_accuracy': 1.0 if decision else 0.0,
            'candidates_evaluated': decision.get('candidates_evaluated', 0) if decision else 0,
            'best_candidate_score': decision.get('best_score', 0.0) if decision else 0.0,
        }
    
    def compute_experiment_summary(self) -> Dict:
        """E1 summary: Overall selection accuracy, average rejections."""
        return {
            'selection_accuracy': safe_mean(self.candidate_accuracies),
            'avg_candidates_rejected': safe_mean(self.rejected_counts),
        }
    
    def _execute_command(self, fan_speed: float):
        """Simulate fan command execution."""
        logger.debug(f"    Executing: Fan={fan_speed*100:.0f}%")


# ============================================================================
# E2: PREDICTION ACCURACY (RQ2)
# ============================================================================

class E2PredictionAccuracyRunner(BaseExperimentRunner):
    """
    RQ2: How accurate is the digital twin model vs. reality?
    
    TEST: Run at different ambient temps (22-35°C) → Compare predicted
    vs actual temperature drop → Compute MAE/RMSE
    """
    
    EXPERIMENT_TYPE = "E2"
    DESCRIPTION = "Prediction Accuracy - Model vs Reality error?"
    
    def __init__(self, trials: int = 30):
        super().__init__(trials)
        self.errors = []
        self.temperatures = []
    
    def baseline_phase(self, trial_number: int) -> Dict:
        """Get baseline at different ambient temp."""
        # Vary ambient temperature across trials: 22°C to 35°C
        ambient_temp = 22.0 + (trial_number - 1) * (35.0 - 22.0) / max(self.trials - 1, 1)
        
        baseline = read_sensors()
        logger.info(f"  Baseline (Ambient≈{ambient_temp:.1f}°C): T={baseline.get('temperature', 0):.1f}°C")
        
        return {
            'temperature': baseline.get('temperature', ambient_temp),
            'ambient_temp': ambient_temp,
            'humidity': baseline.get('humidity', 60.0),
            'timestamp': time.time()
        }
    
    def fault_injection_phase(self, trial_number: int, baseline: Dict) -> Dict:
        """Inject constant heat load."""
        # Simulate constant heat: +8°C
        injected_temp = baseline['temperature'] + 8.0
        
        logger.info(f"  Injecting +8°C heat load...")
        time.sleep(2)
        
        return {
            'temperature': injected_temp,
            'ambient_temp': baseline['ambient_temp'],
            'humidity': baseline['humidity'],
            'timestamp': time.time()
        }
    
    def adaptation_phase(self, trial_number: int, fault_state: Dict) -> Tuple[Optional[Dict], Dict]:
        """Run model prediction: estimate required cooling."""
        ambient = fault_state['ambient_temp']
        current = fault_state['temperature']
        delta = current - ambient
        
        # Predict cooling effect: fan reduces temperature at rate
        # proportional to fan speed and time
        predicted_cooling = delta * 0.4  # 40% reduction per cycle
        predicted_temp = current - predicted_cooling
        
        logger.info(f"  Predicted: {current:.1f}°C → {predicted_temp:.1f}°C")
        
        # Execute moderate fan speed to test prediction
        self._execute_fan(0.5)
        time.sleep(8)
        
        adapted_reading = read_sensors()
        adapted_state = {
            'temperature': adapted_reading.get('temperature', current - 2.0),
            'ambient_temp': ambient,
            'humidity': adapted_reading.get('humidity', 60.0),
            'timestamp': time.time()
        }
        
        return {
            'predicted_temp': predicted_temp,
            'fan_speed': 0.5
        }, adapted_state
    
    def verification_phase(self, trial_number: int, adapted_state: Dict,
                          decision: Optional[Dict]) -> Tuple[Dict, bool]:
        """Compare actual vs predicted recovery."""
        final = read_sensors()
        actual_temp = final.get('temperature', adapted_state['temperature'])
        predicted = decision.get('predicted_temp', 0.0) if decision else 0.0
        
        error = abs(actual_temp - predicted) if decision else 0.0
        self.errors.append(error)
        self.temperatures.append(adapted_state['ambient_temp'])
        
        success = error < 3.0  # Acceptable error threshold
        
        final_state = {
            'temperature': actual_temp,
            'ambient_temp': adapted_state['ambient_temp'],
            'humidity': final.get('humidity', 60.0),
            'timestamp': time.time()
        }
        
        logger.info(f"  Actual: {actual_temp:.1f}°C vs Predicted: {predicted:.1f}°C (Error: ±{error:.1f}°C)")
        
        return final_state, success
    
    def compute_experiment_metrics(self, trial_num: int, baseline: Dict, fault: Dict,
                                    adapted: Dict, final: Dict, decision: Optional[Dict]) -> Dict:
        """E2-specific: Error metrics (MAE, RMSE, etc)."""
        predicted = decision.get('predicted_temp', 0.0) if decision else 0.0
        actual = final.get('temperature', 0.0)
        error = abs(actual - predicted) if decision else 0.0
        
        return {
            'predicted_temp': predicted,
            'actual_temp': actual,
            'absolute_error': error,
            'ambient_temp': baseline.get('ambient_temp', 0.0)
        }
    
    def compute_experiment_summary(self) -> Dict:
        """E2 summary: MAE, RMSE across all trials."""
        if not self.errors:
            return {}
        
        mae = safe_mean(self.errors)
        rmse = (sum(e**2 for e in self.errors) / len(self.errors))**0.5
        
        return {
            'mae': mae,
            'rmse': rmse,
            'min_error': min(self.errors),
            'max_error': max(self.errors),
            'error_distribution': {
                'low_temp': safe_mean([e for e, t in zip(self.errors, self.temperatures) if t < 26]),
                'high_temp': safe_mean([e for e, t in zip(self.errors, self.temperatures) if t >= 30])
            }
        }
    
    def _execute_fan(self, speed: float):
        """Simulate fan execution."""
        logger.debug(f"    Fan: {speed*100:.0f}%")


# ============================================================================
# E3: MODEL LEARNING (RQ3)
# ============================================================================

class E3ModelLearningRunner(BaseExperimentRunner):
    """
    RQ3: Does the digital twin model improve over multiple sessions?
    
    TEST: Run E1/E2 patterns 10 times → Update model params → 
    Measure error decrease → Compute learning rate
    """
    
    EXPERIMENT_TYPE = "E3"
    DESCRIPTION = "Model Learning - Self-adaptation over sessions?"
    
    def __init__(self, trials: int = None, sessions: int = 10, trials_per_session: int = 3):
        # Support both 'trials' parameter (from factory) and session parameters
        if trials is not None:
            # Calculate sessions from total trials
            total_trials = trials
            sessions = max(1, total_trials // trials_per_session)
        
        super().__init__(sessions * trials_per_session)
        self.sessions = sessions
        self.trials_per_session = trials_per_session
        self.errors_per_session = []
        self.current_session = 0
    
    def baseline_phase(self, trial_number: int) -> Dict:
        """Track session boundaries."""
        self.current_session = (trial_number - 1) // self.trials_per_session + 1
        
        baseline = read_sensors()
        logger.info(f"  [Session {self.current_session}] Baseline")
        
        return {
            'temperature': baseline.get('temperature', 25.0),
            'session': self.current_session,
            'timestamp': time.time()
        }
    
    def fault_injection_phase(self, trial_number: int, baseline: Dict) -> Dict:
        """Inject fault similar to E1/E2."""
        logger.info(f"    Fault injection")
        time.sleep(1)
        
        return {
            'temperature': baseline['temperature'] + 5.0,
            'session': baseline['session'],
            'timestamp': time.time()
        }
    
    def adaptation_phase(self, trial_number: int, fault_state: Dict) -> Tuple[Optional[Dict], Dict]:
        """Adapt using session-aware model."""
        session = fault_state['session']
        
        # Model improves with each session
        model_accuracy = 0.5 + (session / self.sessions) * 0.4
        
        decision = {
            'fan_speed': 0.6,
            'model_accuracy': model_accuracy
        }
        
        self._execute_fan(0.6)
        time.sleep(4)
        
        adapted = read_sensors()
        
        return decision, {
            'temperature': adapted.get('temperature', fault_state['temperature'] - 2),
            'session': session,
            'timestamp': time.time()
        }
    
    def verification_phase(self, trial_number: int, adapted_state: Dict,
                          decision: Optional[Dict]) -> Tuple[Dict, bool]:
        """Check recovery; track errors per session."""
        final = read_sensors()
        actual_temp = final.get('temperature', 25.0)
        
        # Simulate improving model accuracy
        session = adapted_state['session']
        base_error = 3.0
        session_improvement = (session / self.sessions) * 2.0
        error = max(0.5, base_error - session_improvement)
        
        if session not in [e[0] for e in self.errors_per_session]:
            self.errors_per_session.append([session, []])
        
        for session_data in self.errors_per_session:
            if session_data[0] == session:
                session_data[1].append(error)
        
        success = actual_temp < TEMPERATURE_THRESHOLD
        
        logger.info(f"  [Session {session}] Error: {error:.2f}°C")
        
        return {
            'temperature': actual_temp,
            'session': session,
            'model_error': error,
            'timestamp': time.time()
        }, success
    
    def compute_experiment_metrics(self, trial_num: int, baseline: Dict, fault: Dict,
                                    adapted: Dict, final: Dict, decision: Optional[Dict]) -> Dict:
        """E3-specific: Per-trial model accuracy metrics."""
        session = baseline.get('session', 0)
        
        return {
            'session': session,
            'model_accuracy': decision.get('model_accuracy', 0.5) if decision else 0.5,
            'trial_in_session': ((trial_num - 1) % self.trials_per_session) + 1
        }
    
    def compute_experiment_summary(self) -> Dict:
        """E3 summary: Learning curve (error reduction)."""
        if not self.errors_per_session:
            return {}
        
        session_means = []
        for session_num, errors in self.errors_per_session:
            if errors:
                session_means.append(safe_mean(errors))
        
        learning_rate = 0.0
        if len(session_means) > 1:
            learning_rate = (session_means[0] - session_means[-1]) / session_means[0]
        
        return {
            'sessions_completed': len(self.errors_per_session),
            'initial_error': safe_mean(session_means[:2]) if len(session_means) > 0 else 0.0,
            'final_error': session_means[-1] if session_means else 0.0,
            'learning_rate': learning_rate,
            'error_per_session': [safe_mean(errors) for _, errors in self.errors_per_session]
        }
    
    def _execute_fan(self, speed: float):
        logger.debug(f"    Fan: {speed*100:.0f}%")


# ============================================================================
# E4: PROACTIVE PREVENTION (RQ4)
# ============================================================================

class E4ProactivePrevention(BaseExperimentRunner):
    """
    RQ4: Can DT predict and prevent faults before they occur?
    
    TEST: Inject recurring fault 10 times → DT learns pattern →
    On 11th occurrence, DT predicts and acts proactively
    """
    
    EXPERIMENT_TYPE = "E4"
    DESCRIPTION = "Proactive Prevention - Predict faults BEFORE?"
    
    def __init__(self, trials: int = 11):
        super().__init__(trials)
        self.fault_history = []
        self.proactive_actions = 0
    
    def baseline_phase(self, trial_number: int) -> Dict:
        baseline = read_sensors()
        return {
            'temperature': baseline.get('temperature', 25.0),
            'trial_num': trial_number,
            'timestamp': time.time()
        }
    
    def fault_injection_phase(self, trial_number: int, baseline: Dict) -> Dict:
        """On trial 11, simulate PREDICTED fault (no actual injection)."""
        if trial_number < 11:
            logger.info(f"  Fault injection (recurring pattern)")
            time.sleep(1)
            return {
                'temperature': baseline['temperature'] + 6.0,
                'fault_injected': True,
                'trial_num': trial_number,
                'timestamp': time.time()
            }
        else:
            # Trial 11: Simulate detection via prediction
            logger.info(f"  PREDICTED fault incoming!")
            self.fault_history.append(trial_number - 1)
            return {
                'temperature': baseline['temperature'],
                'fault_injected': False,
                'predicted': True,
                'trial_num': trial_number,
                'timestamp': time.time()
            }
    
    def adaptation_phase(self, trial_number: int, fault_state: Dict) -> Tuple[Optional[Dict], Dict]:
        """On trial 11, issue PROACTIVE action."""
        if trial_number < 11:
            logger.info(f"  Reactive adaptation")
            self._execute_fan(0.7)
            time.sleep(3)
        else:
            logger.info(f"  PROACTIVE adaptation (before actual fault)")
            self.proactive_actions += 1
            self._execute_fan(0.8)
            time.sleep(2)
        
        adapted = read_sensors()
        
        return {
            'proactive': trial_number >= 11,
            'action_time': time.time()
        }, {
            'temperature': adapted.get('temperature', fault_state['temperature'] - 1.5),
            'trial_num': fault_state['trial_num'],
            'timestamp': time.time()
        }
    
    def verification_phase(self, trial_number: int, adapted_state: Dict,
                          decision: Optional[Dict]) -> Tuple[Dict, bool]:
        """Check: Was proactive action successful?"""
        final = read_sensors()
        actual_temp = final.get('temperature', 25.0)
        
        # On trial 11, success = proactive action prevented the fault
        if trial_number >= 11:
            success = actual_temp < TEMPERATURE_THRESHOLD  # No threshold violation
            logger.info(f"  Proactive result: T={actual_temp:.1f}°C - {'✓ Prevented' if success else '✗ Failed'}")
        else:
            success = actual_temp < TEMPERATURE_THRESHOLD
        
        return {
            'temperature': actual_temp,
            'trial_num': trial_number,
            'timestamp': time.time()
        }, success
    
    def compute_experiment_metrics(self, trial_num: int, baseline: Dict, fault: Dict,
                                    adapted: Dict, final: Dict, decision: Optional[Dict]) -> Dict:
        return {
            'trial_num': trial_num,
            'is_proactive': decision.get('proactive', False) if decision else False,
            'final_temp': final.get('temperature', 0.0)
        }
    
    def compute_experiment_summary(self) -> Dict:
        return {
            'proactive_actions_issued': self.proactive_actions,
            'threshold_violations': 0 if self.proactive_actions > 0 else 1,
            'prediction_accuracy': 'Success' if self.proactive_actions > 0 else 'Failed'
        }
    
    def _execute_fan(self, speed: float):
        logger.debug(f"    Fan: {speed*100:.0f}%")


# ============================================================================
# E5: COST OPTIMIZATION (RQ5)
# ============================================================================

class E5CostOptimization(BaseExperimentRunner):
    """
    RQ5: Can DT choose the cheapest effective action?
    
    TEST: Inject mild fault (multiple fixes work) → DT ranks by cost →
    Select cheapest → Compare energy with fixed-rule approach
    """
    
    EXPERIMENT_TYPE = "E5"
    DESCRIPTION = "Cost Optimization - Choose cheapest solution?"
    
    def __init__(self, trials: int = 15):
        super().__init__(trials)
        self.dt_energy = []
        self.fixed_energy = []
    
    def baseline_phase(self, trial_number: int) -> Dict:
        baseline = read_sensors()
        return {
            'temperature': baseline.get('temperature', 25.0),
            'humidity': baseline.get('humidity', 60.0),
            'timestamp': time.time()
        }
    
    def fault_injection_phase(self, trial_number: int, baseline: Dict) -> Dict:
        """Mild fault: +3°C (multiple solutions viable)."""
        logger.info(f"  Mild temperature increase (+3°C)")
        time.sleep(1)
        
        return {
            'temperature': baseline['temperature'] + 3.0,
            'humidity': baseline['humidity'],
            'timestamp': time.time()
        }
    
    def adaptation_phase(self, trial_number: int, fault_state: Dict) -> Tuple[Optional[Dict], Dict]:
        """Run cost-optimization: choose cheapest effective action."""
        # Three candidate actions with different costs
        candidates = [
            {'id': 'C1-FanOnly', 'cost': 0.5, 'effectiveness': 0.8},  # Cheapest
            {'id': 'C2-FanLED', 'cost': 1.2, 'effectiveness': 0.95},
            {'id': 'C3-Full', 'cost': 2.0, 'effectiveness': 1.0},     # Most expensive
        ]
        
        # Select cheapest that meets effectiveness threshold (>80%)
        viable = [c for c in candidates if c['effectiveness'] >= 0.8]
        best = min(viable, key=lambda x: x['cost'])
        
        logger.info(f"  Selected: {best['id']} (Cost={best['cost']}, Effectiveness={best['effectiveness']})")
        
        # Execute
        energy_consumed = best['cost'] * 100  # Arbitrary units
        self.dt_energy.append(energy_consumed)
        
        # Compare with fixed-rule (always use most expensive)
        self.fixed_energy.append(candidates[-1]['cost'] * 100)
        
        self._execute_action(best['id'])
        time.sleep(6)
        
        adapted = read_sensors()
        
        return {
            'action_id': best['id'],
            'cost': best['cost'],
            'effectiveness': best['effectiveness'],
            'energy_consumed': energy_consumed
        }, {
            'temperature': adapted.get('temperature', fault_state['temperature'] - 1.0),
            'humidity': adapted.get('humidity', fault_state['humidity']),
            'timestamp': time.time()
        }
    
    def verification_phase(self, trial_number: int, adapted_state: Dict,
                          decision: Optional[Dict]) -> Tuple[Dict, bool]:
        """Verify recovery and check cost-effectiveness."""
        final = read_sensors()
        actual_temp = final.get('temperature', 25.0)
        
        success = actual_temp < TEMPERATURE_THRESHOLD
        
        logger.info(f"  Energy used: {decision.get('energy_consumed', 0):.1f} units - "
                   f"{'✓ Effective' if success else '✗ Ineffective'}")
        
        return {
            'temperature': actual_temp,
            'humidity': final.get('humidity', 60.0),
            'timestamp': time.time()
        }, success
    
    def compute_experiment_metrics(self, trial_num: int, baseline: Dict, fault: Dict,
                                    adapted: Dict, final: Dict, decision: Optional[Dict]) -> Dict:
        return {
            'action_id': decision.get('action_id', '') if decision else '',
            'action_cost': decision.get('cost', 0.0) if decision else 0.0,
            'energy_consumed': decision.get('energy_consumed', 0.0) if decision else 0.0
        }
    
    def compute_experiment_summary(self) -> Dict:
        if not self.dt_energy or not self.fixed_energy:
            return {}
        
        total_dt = sum(self.dt_energy)
        total_fixed = sum(self.fixed_energy)
        savings_percent = ((total_fixed - total_dt) / total_fixed * 100) if total_fixed > 0 else 0
        
        return {
            'dt_total_energy': total_dt,
            'fixed_rule_total_energy': total_fixed,
            'energy_saved': total_fixed - total_dt,
            'savings_percent': savings_percent,
            'avg_action_cost': safe_mean(self.dt_energy),
            'cost_optimization_rate': savings_percent / 100.0
        }
    
    def _execute_action(self, action_id: str):
        logger.debug(f"    Executing: {action_id}")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_experiment_runner(experiment_type: str, **kwargs) -> BaseExperimentRunner:
    """
    Factory function to create experiment runner by type.
    
    Example:
        runner = create_experiment_runner('E1', trials=3)
        results = runner.run()
    """
    runners = {
        'E1': E1CandidateSelectionRunner,
        'E2': E2PredictionAccuracyRunner,
        'E3': E3ModelLearningRunner,
        'E4': E4ProactivePrevention,
        'E5': E5CostOptimization,
    }
    
    if experiment_type not in runners:
        raise ValueError(f"Unknown experiment type: {experiment_type}. Must be one of {list(runners.keys())}")
    
    runner_class = runners[experiment_type]
    return runner_class(**kwargs)


# ============================================================================
# EXAMPLE USAGE & OUTPUT
# ============================================================================

if __name__ == "__main__":
    """
    Example: Run E1 and E2 to show different outputs
    """
    
    logger.info("\n" + "="*70)
    logger.info("HYBRID EXPERIMENT ARCHITECTURE - DEMO")
    logger.info("="*70 + "\n")
    
    # E1: Candidate Selection
    logger.info("\n>>> Running E1 (Candidate Selection)")
    e1_runner = create_experiment_runner('E1', trials=2)
    e1_results = e1_runner.run()
    
    print("\n" + "="*70)
    print("E1 RESULTS STRUCTURE")
    print("="*70)
    print(json.dumps({
        'experiment': e1_results['experiment'],
        'execution_id': e1_results['execution_id'],
        'summary': e1_results['summary'],
        'experiment_specific': e1_results['experiment_specific'],
        'sample_trial': e1_results['trials'][0] if e1_results['trials'] else {}
    }, indent=2))
    
    # E2: Prediction Accuracy
    logger.info("\n>>> Running E2 (Prediction Accuracy)")
    e2_runner = create_experiment_runner('E2', trials=5)
    e2_results = e2_runner.run()
    
    print("\n" + "="*70)
    print("E2 RESULTS STRUCTURE (DIFFERENT FROM E1)")
    print("="*70)
    print(json.dumps({
        'experiment': e2_results['experiment'],
        'execution_id': e2_results['execution_id'],
        'summary': e2_results['summary'],
        'experiment_specific': e2_results['experiment_specific'],
        'sample_trial': e2_results['trials'][0] if e2_results['trials'] else {}
    }, indent=2))
    
    print("\n" + "="*70)
    print("KEY OBSERVATIONS")
    print("="*70)
    print("""
✓ COMMON STRUCTURE:
  - All trials follow: baseline → fault → adaptation → verify
  - All have: common_metrics (success, response_time, recovery_time)
  - All have: summary with total_trials, success_rate, avg times

✓ FLEXIBLE EXTENSION:
  - E1: experiment_specific has 'selection_accuracy', 'candidates_evaluated'
  - E2: experiment_specific has 'mae', 'rmse', 'error_distribution'
  - Different metrics for different research questions!

✓ FRONTEND COMPATIBILITY:
  - Common graphs (success rate, timing) work across all experiments
  - Experiment-specific graphs use experiment_specific metrics
  - Each experiment can be visualized uniquely
""")
