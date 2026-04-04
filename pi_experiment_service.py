"""
Pi Experiment Service - Runs on Raspberry Pi and listens for experiment requests

This FastAPI service:
1. Receives experiment execution requests from backend
2. Runs the requested experiment locally (E1-E5)
3. Injects faults as requested
4. Reports results back to backend
5. Handles OTA updates

Port: 8001 (internal to Pi network)
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket
from pydantic import BaseModel
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import json
import logging
import time
import os
import sys
import requests
from pathlib import Path
import asyncio
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from experiment_runner import (
    E1CandidateSelectionExperiment,
    E2AccuracyImprovementExperiment,
    E3LearningCapabilityExperiment,
    E4ProactiveControlExperiment,
    E5CostOptimizationExperiment
)

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ============ CUSTOM LOG HANDLER FOR WEBSOCKET STREAMING ============
class WebSocketLogHandler(logging.Handler):
    """Custom handler that broadcasts logs to WebSocket clients"""
    def emit(self, record):
        """Emit a log record"""
        # Extract execution_id from the message if it exists (format: [execution_id] message)
        msg = self.format(record)
        
        # Try to extract execution_id from message
        execution_id = None
        if '[' in msg and ']' in msg:
            try:
                start = msg.find('[')
                end = msg.find(']', start)
                potential_id = msg[start+1:end]
                if '_' in potential_id or potential_id.startswith('E'):
                    execution_id = potential_id
            except:
                pass
        
        # Broadcast if we found an execution_id
        if execution_id:
            level_name = record.levelname
            try:
                asyncio.create_task(broadcast_log(execution_id, level_name, msg))
            except:
                pass

# Add the WebSocket handler to the logger
ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'))
logger.addHandler(ws_handler)

app = FastAPI(title="Pi Experiment Service", version="1.0")
start_time = time.time()  # Track service start time for uptime calculation

# ============ WEBSOCKET & LOG STREAMING ============
# Store active WebSocket connections per execution
active_connections: Dict[str, Set[WebSocket]] = {}
experiment_logs: Dict[str, List[Dict]] = {}  # Store logs for each execution
experiment_results: Dict[str, Dict] = {}  # Store final results

async def broadcast_log(execution_id: str, level: str, message: str):
    """Send log message to all connected WebSocket clients for this execution"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message
    }
    
    # Store log
    if execution_id not in experiment_logs:
        experiment_logs[execution_id] = []
    experiment_logs[execution_id].append(log_entry)
    
    # Broadcast to connected clients
    if execution_id in active_connections:
        disconnected = set()
        for websocket in active_connections[execution_id]:
            try:
                await websocket.send_json(log_entry)
            except:
                disconnected.add(websocket)
        
        # Remove disconnected clients
        active_connections[execution_id] -= disconnected

# ============ WEBSOCKET ENDPOINTS ============

@app.websocket("/ws/experiment/{execution_id}")
async def websocket_experiment_logs(websocket: WebSocket, execution_id: str):
    """WebSocket endpoint for streaming experiment logs and results to frontend"""
    await websocket.accept()
    
    # Add this connection to the set
    if execution_id not in active_connections:
        active_connections[execution_id] = set()
    active_connections[execution_id].add(websocket)
    
    logger_internal = logging.getLogger(__name__)
    logger_internal.info(f"[WS] Client connected to {execution_id}")
    
    try:
        # Send any logs that already exist from before connection
        if execution_id in experiment_logs:
            for log_entry in experiment_logs[execution_id]:
                await websocket.send_json(log_entry)
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            # Echo back for keepalive
            if data == "ping":
                await websocket.send_text("pong")
    except Exception as e:
        logger_internal.error(f"[WS] Error on {execution_id}: {e}")
    finally:
        # Remove this connection
        if execution_id in active_connections:
            active_connections[execution_id].discard(websocket)
        logger_internal.info(f"[WS] Client disconnected from {execution_id}")

@app.get("/api/experiment/{execution_id}/logs")
async def get_experiment_logs(execution_id: str):
    """Get all logs for an execution"""
    return {
        'execution_id': execution_id,
        'logs': experiment_logs.get(execution_id, []),
        'results': experiment_results.get(execution_id, None)
    }

def emit_log(execution_id: str, level: str, message: str):
    """Synchronous wrapper to emit logs to WebSocket clients"""
    try:
        asyncio.create_task(broadcast_log(execution_id, level, message))
    except:
        pass  # Silently fail if no event loop

# ============ PYDANTIC MODELS ============

class FaultInjectionConfig(BaseModel):
    fault_type: str  # "temperature_spike", "gradual_drift", "none"
    magnitude: float
    duration_seconds: int
    start_delay_seconds: int = 5


class ExperimentRequest(BaseModel):
    experiment_type: str  # E1, E2, E3, E4, E5
    trials: int
    execution_id: str
    fault_injection: Optional[FaultInjectionConfig] = None


class ExperimentProgress(BaseModel):
    execution_id: str
    experiment_type: str
    status: str  # "running", "completed", "failed"
    trials_completed: int
    trials_total: int
    current_trial: int
    current_message: str


class TrialResultData(BaseModel):
    trial_number: int
    success: bool
    temperature_readings: List[float]
    fan_speeds: List[float]
    adaptation_decision: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    duration_seconds: float


class ExperimentResultData(BaseModel):
    execution_id: str
    experiment_type: str
    trials: List[TrialResultData]
    summary: Dict[str, Any]


# ============ IN-MEMORY STATE ==========
active_experiments = {}  # execution_id -> experiment_state


class ExperimentState:
    def __init__(self, execution_id: str, experiment_type: str):
        self.execution_id = execution_id
        self.experiment_type = experiment_type
        self.status = "running"
        self.trials_completed = 0
        self.trials_total = 0
        self.current_message = "Starting experiment..."
        self.results = None
        self.error = None


# ============ CONSTANTS ==========
COMPLETION_MESSAGE = "Experiment completed successfully"

# Backend API endpoint to receive results
BACKEND_HOST = os.getenv("BACKEND_HOST", "https://smartcitylivinglab.iiit.ac.in/smartcitydigitaltwin-api").rstrip("/")
BACKEND_RESULTS_ENDPOINT = f"{BACKEND_HOST}/experiments/results/save"

# ============ HELPER FUNCTIONS ==========

def _send_results_to_backend(execution_id: str, experiment_type: str, results: dict):
    """Send completed experiment results back to backend"""
    try:
        payload = {
            'execution_id': execution_id,
            'experiment_type': experiment_type,
            'trials': results.get('trials', []),
            'summary': results.get('summary', {}),
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"[{execution_id}] Sending results to backend: {BACKEND_RESULTS_ENDPOINT}")
        asyncio.create_task(broadcast_log(execution_id, "INFO", f"Sending results to backend..."))
        
        response = requests.post(BACKEND_RESULTS_ENDPOINT, json=payload, timeout=10)
        
        if response.ok:
            msg = f"✓ Results sent to backend successfully (HTTP {response.status_code})"
            logger.info(f"[{execution_id}] {msg}")
            asyncio.create_task(broadcast_log(execution_id, "SUCCESS", msg))
            # Store results for later retrieval
            experiment_results[execution_id] = payload
        else:
            msg = f"⚠️  Failed to send results to backend: HTTP {response.status_code}"
            logger.warning(f"[{execution_id}] {msg}")
            asyncio.create_task(broadcast_log(execution_id, "WARNING", msg))
    except Exception as e:
        msg = f"❌ Error sending results to backend: {e}"
        logger.error(f"[{execution_id}] {msg}", exc_info=True)
        asyncio.create_task(broadcast_log(execution_id, "ERROR", msg))

def _run_e1_experiment(execution_id: str, state: ExperimentState, req: ExperimentRequest):
    """Run E1 experiment and update state"""
    try:
        state.trials_total = req.trials
        logger.info(f"[{execution_id}] Starting E1 with {req.trials} trials")
        emit_log(execution_id, "INFO", f"Starting E1 experiment with {req.trials} trials...")
        
        experiment = E1CandidateSelectionExperiment(trials=req.trials)
        
        # Run experiment (this is blocking, so it needs to be handled carefully)
        experiment.run()
        
        state.results = {
            'trials': experiment.results.get('trials', []),
            'summary': experiment.results.get('summary', {})
        }
        state.trials_completed = len(state.results['trials'])
        state.status = "completed"
        state.current_message = COMPLETION_MESSAGE
        
        logger.info(f"[{execution_id}] E1 completed with {state.trials_completed} trials")
        emit_log(execution_id, "SUCCESS", f"E1 completed: {state.trials_completed}/{req.trials} trials successful")
        
        # Send results back to backend
        _send_results_to_backend(execution_id, "E1", state.results)
    
    except Exception as e:
        logger.error(f"[{execution_id}] E1 failed: {e}", exc_info=True)
        emit_log(execution_id, "ERROR", f"E1 failed: {str(e)}")
        state.status = "failed"
        state.error = str(e)
        state.current_message = f"Error: {str(e)}"


def _run_e2_experiment(execution_id: str, state: ExperimentState, req: ExperimentRequest):
    """Run E2 experiment and update state"""
    try:
        state.trials_total = req.trials
        logger.info(f"[{execution_id}] Starting E2 with {req.trials} trials")
        
        experiment = E2AccuracyImprovementExperiment(trials=req.trials)
        experiment.run()
        
        state.results = {
            'trials': experiment.results.get('trials', []),
            'summary': experiment.results.get('summary', {})
        }
        state.trials_completed = len(state.results['trials'])
        state.status = "completed"
        state.current_message = COMPLETION_MESSAGE
        
        logger.info(f"[{execution_id}] E2 completed with {state.trials_completed} trials")
        
        # Send results back to backend
        _send_results_to_backend(execution_id, "E2", state.results)
    
    except Exception as e:
        logger.error(f"[{execution_id}] E2 failed: {e}", exc_info=True)
        state.status = "failed"
        state.error = str(e)


def _run_e3_experiment(execution_id: str, state: ExperimentState, req: ExperimentRequest):
    """Run E3 experiment and update state"""
    try:
        state.trials_total = req.trials
        logger.info(f"[{execution_id}] Starting E3 with {req.trials} trials")
        
        experiment = E3LearningCapabilityExperiment(trials=req.trials)
        experiment.run()
        
        state.results = {
            'trials': experiment.results.get('trials', []),
            'summary': experiment.results.get('summary', {})
        }
        state.trials_completed = len(state.results['trials'])
        state.status = "completed"
        state.current_message = COMPLETION_MESSAGE
        
        logger.info(f"[{execution_id}] E3 completed with {state.trials_completed} trials")
        
        # Send results back to backend
        _send_results_to_backend(execution_id, "E3", state.results)
    
    except Exception as e:
        logger.error(f"[{execution_id}] E3 failed: {e}", exc_info=True)
        state.status = "failed"
        state.error = str(e)


def _run_e4_experiment(execution_id: str, state: ExperimentState, req: ExperimentRequest):
    """Run E4 experiment and update state"""
    try:
        state.trials_total = req.trials
        logger.info(f"[{execution_id}] Starting E4 with {req.trials} trials")
        
        experiment = E4ProactiveControlExperiment(trials=req.trials)
        experiment.run()
        
        state.results = {
            'trials': experiment.results.get('trials', []),
            'summary': experiment.results.get('summary', {})
        }
        state.trials_completed = len(state.results['trials'])
        state.status = "completed"
        state.current_message = COMPLETION_MESSAGE
        
        logger.info(f"[{execution_id}] E4 completed with {state.trials_completed} trials")
        
        # Send results back to backend
        _send_results_to_backend(execution_id, "E4", state.results)
    
    except Exception as e:
        logger.error(f"[{execution_id}] E4 failed: {e}", exc_info=True)
        state.status = "failed"
        state.error = str(e)


def _run_e5_experiment(execution_id: str, state: ExperimentState, req: ExperimentRequest):
    """Run E5 experiment and update state"""
    try:
        state.trials_total = req.trials
        logger.info(f"[{execution_id}] Starting E5 with {req.trials} trials")
        
        experiment = E5CostOptimizationExperiment(trials=req.trials)
        experiment.run()
        
        state.results = {
            'trials': experiment.results.get('trials', []),
            'summary': experiment.results.get('summary', {})
        }
        state.trials_completed = len(state.results['trials'])
        state.status = "completed"
        state.current_message = COMPLETION_MESSAGE
        
        logger.info(f"[{execution_id}] E5 completed with {state.trials_completed} trials")
        
        # Send results back to backend
        _send_results_to_backend(execution_id, "E5", state.results)
    
    except Exception as e:
        logger.error(f"[{execution_id}] E5 failed: {e}", exc_info=True)
        state.status = "failed"
        
        logger.info(f"[{execution_id}] E5 completed with {state.trials_completed} trials")
    
    except Exception as e:
        logger.error(f"[{execution_id}] E5 failed: {e}", exc_info=True)
        state.status = "failed"
        state.error = str(e)


# ============ ENDPOINTS ============

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'pi-experiment-service',
        'active_experiments': len([e for e in active_experiments.values() if e.status == 'running'])
    }


@app.post("/run-experiment")
async def run_experiment(req: ExperimentRequest, background_tasks: BackgroundTasks):
    """
    Receive and execute an experiment on the Pi hardware.
    
    This endpoint:
    1. Validates the request
    2. Creates an experiment state
    3. Starts the experiment in background
    4. Returns immediately with execution_id
    
    Backend polls /progress/{execution_id} to monitor status
    """
    
    try:
        execution_id = req.execution_id
        experiment_type = req.experiment_type
        
        logger.info(f"[{execution_id}] Received experiment request: {experiment_type}, {req.trials} trials")
        
        # Create state
        state = ExperimentState(execution_id, experiment_type)
        active_experiments[execution_id] = state
        
        # Schedule background task based on experiment type
        if experiment_type == "E1":
            background_tasks.add_task(_run_e1_experiment, execution_id, state, req)
        elif experiment_type == "E2":
            background_tasks.add_task(_run_e2_experiment, execution_id, state, req)
        elif experiment_type == "E3":
            background_tasks.add_task(_run_e3_experiment, execution_id, state, req)
        elif experiment_type == "E4":
            background_tasks.add_task(_run_e4_experiment, execution_id, state, req)
        elif experiment_type == "E5":
            background_tasks.add_task(_run_e5_experiment, execution_id, state, req)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown experiment type: {experiment_type}")
        
        return {
            'execution_id': execution_id,
            'experiment_type': experiment_type,
            'status': 'accepted',
            'message': f'Experiment {experiment_type} queued for execution'
        }
    
    except Exception as e:
        logger.error(f"Error starting experiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/progress/{execution_id}")
def get_progress(execution_id: str):
    """
    Get current progress of an experiment execution.
    
    Returns:
    - status: "running", "completed", "failed"
    - trials_completed, trials_total
    - current_message
    """
    
    if execution_id not in active_experiments:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    
    state = active_experiments[execution_id]
    
    return ExperimentProgress(
        execution_id=execution_id,
        experiment_type=state.experiment_type,
        status=state.status,
        trials_completed=state.trials_completed,
        trials_total=state.trials_total,
        current_trial=state.trials_completed,
        current_message=state.current_message
    ).dict()


@app.get("/results/{execution_id}")
def get_results(execution_id: str):
    """
    Get final results of an experiment execution.
    
    Only available after experiment completes.
    """
    
    if execution_id not in active_experiments:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    
    state = active_experiments[execution_id]
    
    if state.status == "running":
        raise HTTPException(status_code=202, detail="Experiment still running")
    
    if state.status == "failed":
        raise HTTPException(status_code=500, detail=f"Experiment failed: {state.error}")
    
    if not state.results:
        raise HTTPException(status_code=500, detail="No results available")
    
    return {
        'execution_id': execution_id,
        'experiment_type': state.experiment_type,
        'status': state.status,
        'trials': state.results.get('trials', []),
        'summary': state.results.get('summary', {})
    }


@app.post("/inject-fault")
def inject_fault(fault_config: FaultInjectionConfig):
    """
    Inject a fault into the system for testing.
    
    Fault types:
    - temperature_spike: Sudden temperature increase
    - gradual_drift: Slow temperature increase
    - none: No fault
    """
    
    try:
        logger.info(f"Injecting fault: {fault_config.fault_type} (+{fault_config.magnitude}°C)")
        
        # Fault injection is handled by ThermalSimulator.simulate_fault() in backend
        # This function confirms fault reception on Pi side
        
        return {
            'success': True,
            'fault_type': fault_config.fault_type,
            'magnitude': fault_config.magnitude,
            'duration_seconds': fault_config.duration_seconds,
            'message': 'Fault injection initiated'
        }
    
    except Exception as e:
        logger.error(f"Fault injection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update-code")
def update_code(code_content: dict):
    """
    Receive updated code for OTA deployment.
    
    Expects:
    - module_name: which module to update (e.g., "experiment_runner.py")
    - content: new code content
    """
    
    try:
        module_name = code_content.get('module_name')
        content = code_content.get('content')
        
        if not module_name or not content:
            raise ValueError("Missing module_name or content")
        
        # Save to temporary file first
        temp_path = Path(__file__).parent / f"{module_name}.new"
        with open(temp_path, 'w') as f:
            f.write(content)
        
        # Backup original
        original_path = Path(__file__).parent / module_name
        if original_path.exists():
            backup_path = Path(__file__).parent / f"{module_name}.bak"
            original_path.rename(backup_path)
        
        # Move new file into place
        temp_path.rename(original_path)
        
        logger.info(f"Updated {module_name} successfully")
        
        return {
            'success': True,
            'module_name': module_name,
            'message': f'Code updated successfully for {module_name}'
        }
    
    except Exception as e:
        logger.error(f"Code update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
def service_status():
    """Get overall service status"""
    
    running_count = len([e for e in active_experiments.values() if e.status == 'running'])
    completed_count = len([e for e in active_experiments.values() if e.status == 'completed'])
    failed_count = len([e for e in active_experiments.values() if e.status == 'failed'])
    
    return {
        'service': 'pi-experiment-service',
        'status': 'running',
        'uptime': time.time() - start_time,  # Service uptime in seconds since process start
        'total_experiments': len(active_experiments),
        'running_experiments': running_count,
        'completed_experiments': completed_count,
        'failed_experiments': failed_count,
        'timestamp': datetime.now().isoformat(),
        'version': '1.0'
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv('PI_SERVICE_PORT', '8001'))
    host = os.getenv('PI_SERVICE_HOST', '0.0.0.0')
    
    logger.info(f"Starting Pi Experiment Service on {host}:{port}")
    
    uvicorn.run(app, host=host, port=port, log_level="info")
