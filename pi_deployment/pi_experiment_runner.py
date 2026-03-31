#!/usr/bin/env python3
"""
Pi-based Experiment Runner
Runs self-adaptive experiments on Raspberry Pi with demo board hardware
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from enum import Enum
import traceback

# Add backend modules to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'backend'))

# Setup logging
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'pi_experiments.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Load configuration
config_file = Path(__file__).parent / 'config' / 'config.env'
if config_file.exists():
    load_dotenv(config_file)

class ExperimentMode(Enum):
    """Supported experiment modes"""
    E1_CANDIDATE_SELECTION = 'E1_candidate_selection'
    E2_ACCURACY = 'E2_accuracy'
    E3_LEARNING = 'E3_learning'
    E4_PROACTIVE = 'E4_proactive'
    E5_COST_OPTIMIZATION = 'E5_cost_optimization'

class PiExperimentRunner:
    """Run self-adaptive experiments on Pi hardware"""
    
    def __init__(self):
        self.node_id = int(os.getenv('NODE_ID', '1'))
        self.node_name = os.getenv('NODE_NAME', f'pi-node-{self.node_id}')
        self.backend_host = os.getenv('BACKEND_HOST', 'http://localhost:8000')
        self.api_key = os.getenv('BACKEND_API_KEY', '')
        self.experiment_mode = os.getenv('EXPERIMENT_MODE', 'E1_candidate_selection')
        self.experiment_duration = int(os.getenv('EXPERIMENT_DURATION', '3600'))
        self.fault_injection_enabled = os.getenv('FAULT_INJECTION_ENABLED', 'true').lower() == 'true'
        
        self.results_dir = Path(__file__).parent / 'results'
        self.results_dir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized Pi runner: {self.node_name} (node_id={self.node_id})")
        logger.info(f"Backend: {self.backend_host}")
        logger.info(f"Experiment mode: {self.experiment_mode}")
        logger.info(f"Fault injection: {'enabled' if self.fault_injection_enabled else 'disabled'}")
    
    def check_backend_health(self) -> bool:
        """Check if backend server is healthy"""
        try:
            response = requests.get(f"{self.backend_host}/health", timeout=5)
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.info("✓ Backend connection: OK")
            else:
                logger.warning(f"✗ Backend returned status {response.status_code}")
            return is_healthy
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Cannot connect to backend at {self.backend_host}")
            return False
        except Exception as e:
            logger.error(f"✗ Backend health check failed: {e}")
            return False
    
    def read_temperature(self) -> float:
        """Read temperature from sensor (placeholder)"""
        # TODO: Implement actual sensor reading via GPIO
        # For now, return simulated value
        base_temp = 25.0
        import random
        return base_temp + random.uniform(-2, 2)
    
    def control_fan(self, speed: float) -> bool:
        """Control fan speed (0.0 to 1.0)"""
        # TODO: Implement actual GPIO PWM control
        # For now, just log the action
        logger.info(f"Fan control: {speed*100:.0f}%")
        return True
    
    def run_e1_experiment(self) -> dict:
        """Run E1: Candidate Selection Experiment"""
        logger.info("=" * 80)
        logger.info("EXPERIMENT E1: CANDIDATE SELECTION")
        logger.info("=" * 80)
        
        try:
            # Try to import backend modules
            try:
                from modules.adaptation_engine import AdaptationEngine, SystemState
                from modules.thermal_simulator import ThermalSimulator, ThermalModelParams
                logger.info("✓ Backend modules loaded successfully")
                use_backend = True
            except ImportError as e:
                logger.warning(f"Could not import backend modules: {e}")
                logger.info("Running in simulation-only mode")
                use_backend = False
            
            results = {
                'experiment': 'E1_candidate_selection',
                'timestamp': datetime.now().isoformat(),
                'node_id': self.node_id,
                'trials': [],
                'summary': {}
            }
            
            # Run 3 trials
            for trial_num in range(1, 4):
                logger.info(f"\nTrial {trial_num}/3")
                logger.info("-" * 40)
                
                if use_backend:
                    # Use actual backend engine
                    engine = AdaptationEngine(node_id=self.node_id)
                    
                    # Read current temperature
                    current_temp = self.read_temperature()
                    logger.info(f"Current temperature: {current_temp:.1f}°C")
                    
                    # Simulate fault if enabled
                    if self.fault_injection_enabled:
                        injected_temp = current_temp + 5.0
                        logger.info(f"Fault injected: +5°C → {injected_temp:.1f}°C")
                    else:
                        injected_temp = current_temp
                    
                    # Create system state
                    state = SystemState(
                        node_id=self.node_id,
                        timestamp=datetime.now(),
                        current_temperature=injected_temp,
                        t_ambient=25.0,
                        fan_speed=0.0,
                        is_fault=self.fault_injection_enabled,
                        fault_type='temperature_high' if self.fault_injection_enabled else None
                    )
                    
                    # Run MAPE cycle
                    decision = engine.run_mape_cycle(state)
                    
                    if decision:
                        logger.info(f"Adaptation decision: {decision.action_id}")
                        logger.info(f"Fan speed: {decision.fan_speed*100:.0f}%")
                        logger.info(f"Effectiveness: {decision.predicted_effectiveness:.1%}")
                        
                        # Apply control
                        self.control_fan(decision.fan_speed)
                        
                        trial_result = {
                            'trial': trial_num,
                            'decision': decision.action_id,
                            'fan_speed': decision.fan_speed,
                            'effectiveness': decision.predicted_effectiveness,
                            'cost': decision.predicted_cost,
                            'success': True
                        }
                    else:
                        logger.warning("No decision made")
                        trial_result = {
                            'trial': trial_num,
                            'success': False,
                            'reason': 'no_decision'
                        }
                else:
                    # Simulation-only mode
                    trial_result = {
                        'trial': trial_num,
                        'mode': 'simulation',
                        'success': True
                    }
                
                results['trials'].append(trial_result)
                time.sleep(2)  # Delay between trials
            
            # Calculate summary
            successful = sum(1 for t in results['trials'] if t.get('success'))
            results['summary'] = {
                'total_trials': len(results['trials']),
                'successful': successful,
                'success_rate': successful / len(results['trials']) if results['trials'] else 0
            }
            
            logger.info(f"\nE1 Summary: {successful}/{len(results['trials'])} trials successful")
            return results
            
        except Exception as e:
            logger.error(f"E1 experiment failed: {e}", exc_info=True)
            return {
                'experiment': 'E1_candidate_selection',
                'success': False,
                'error': str(e)
            }
    
    def run_experiment(self) -> dict:
        """Run the selected experiment"""
        start_time = time.time()
        
        try:
            if self.experiment_mode == ExperimentMode.E1_CANDIDATE_SELECTION.value:
                results = self.run_e1_experiment()
            else:
                logger.error(f"Experiment mode not supported: {self.experiment_mode}")
                return {'success': False, 'error': 'Unsupported experiment mode'}
            
            # Add metadata
            results['duration_seconds'] = time.time() - start_time
            results['backend_available'] = self.check_backend_health()
            
            # Save results
            result_file = self.results_dir / f"{self.experiment_mode}_{datetime.now():%Y%m%d_%H%M%S}.json"
            with open(result_file, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to: {result_file}")
            
            # Also save as latest
            latest_file = self.results_dir / 'latest_result.json'
            with open(latest_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            return results
            
        except Exception as e:
            logger.error(f"Experiment execution failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def run_continuous(self, num_cycles: int = None):
        """Run experiments continuously"""
        cycle = 0
        try:
            while True:
                cycle += 1
                if num_cycles and cycle > num_cycles:
                    break
                
                logger.info(f"\n{'='*80}")
                logger.info(f"Experiment Cycle {cycle}")
                logger.info(f"{'='*80}\n")
                
                results = self.run_experiment()
                
                # Log summary
                if results.get('success') != False:
                    logger.info(f"Cycle {cycle} completed successfully")
                else:
                    logger.warning(f"Cycle {cycle} failed: {results.get('error')}")
                
                # Wait before next cycle
                logger.info(f"Waiting {self.experiment_duration}s before next cycle...\n")
                time.sleep(self.experiment_duration)
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Continuous execution failed: {e}", exc_info=True)

def main():
    """Main entry point"""
    try:
        runner = PiExperimentRunner()
        
        # Run single experiment or continuous
        if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
            num_cycles = int(sys.argv[2]) if len(sys.argv) > 2 else None
            runner.run_continuous(num_cycles)
        else:
            results = runner.run_experiment()
            sys.exit(0 if results.get('success') != False else 1)
            
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
