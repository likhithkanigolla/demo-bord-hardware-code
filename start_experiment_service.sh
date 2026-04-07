#!/bin/bash

# Pi Experiment Service - Startup Script with Auto-Restart Support
# Place in: /home/pi/digitaltwi/demo-board-hardware-code/
# 
# Usage:
#   sudo bash start_experiment_service.sh                    # Normal mode (no restart)
#   sudo bash start_experiment_service.sh --watch            # Auto-restart on code changes
#   sudo bash start_experiment_service.sh --watch-realtime   # Real-time auto-restart (inotify)

set -e

# ============ PARSE ARGUMENTS ==========
WATCH_MODE=false
WATCH_REALTIME=false

for arg in "$@"; do
    case $arg in
        --watch) WATCH_MODE=true ;;
        --watch-realtime) WATCH_REALTIME=true; WATCH_MODE=true ;;
        *) echo "Unknown option: $arg" ;;
    esac
done

# Check for root privileges (required for GPIO access)
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: This script must be run as root (required for GPIO access)"
    echo "Try: sudo bash start_experiment_service.sh"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Cleanup handler - kills background processes on exit
cleanup() {
    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Shutting down services..."
    if [ -n "$AGENT_LOG_TAIL_PID" ] && ps -p $AGENT_LOG_TAIL_PID > /dev/null 2>&1; then
        echo "Stopping Agent log stream (PID: $AGENT_LOG_TAIL_PID)..."
        kill $AGENT_LOG_TAIL_PID 2>/dev/null || true
    fi
    if [ -n "$AGENT_PID" ] && ps -p $AGENT_PID > /dev/null 2>&1; then
        echo "Stopping Agent (PID: $AGENT_PID)..."
        kill $AGENT_PID 2>/dev/null || true
    fi
    echo "Services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

# ============ CONFIGURATION ==========
PI_SERVICE_PORT=${PI_SERVICE_PORT:-8001}
PI_SERVICE_HOST=${PI_SERVICE_HOST:-0.0.0.0}
VENV_PATH="${SCRIPT_DIR}/.venv"
LOG_FILE="${SCRIPT_DIR}/logs/pi_experiment_service.log"

# ============ SETUP ==========

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Pi Experiment Service..."

# Create logs directory
mkdir -p "${SCRIPT_DIR}/logs"

# Choose Python interpreter (avoid 3.13 due to pydantic-core build issues)
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: No Python 3 interpreter found. Install python3.12 (or 3.11/3.10/3.9) and the matching -venv package."
    exit 1
fi

PY_VERSION=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$PY_VERSION" = "3.13" ]; then
    echo "WARNING: Python 3.13 detected. Proceeding with unpinned requirements."
    echo "If pydantic-core build fails, install python3.12 (or 3.11/3.10/3.9) and rerun."
fi

# Activate virtual environment
if [ -d "$VENV_PATH" ]; then
    VENV_VERSION=$($VENV_PATH/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [ "$VENV_VERSION" = "3.13" ]; then
        echo "WARNING: Existing venv uses Python 3.13. If pydantic-core build fails, remove $VENV_PATH and rerun with Python 3.12 (or 3.11/3.10/3.9)."
    fi
else
    echo "Creating virtual environment with $PYTHON_BIN..."
    "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

PY_CMD="$VENV_PATH/bin/python"
PIP_CMD="$VENV_PATH/bin/pip"

if [ ! -x "$PY_CMD" ]; then
    echo "ERROR: Python executable not found in virtual environment: $PY_CMD"
    exit 1
fi

# Install dependencies if requirements exist
if [ -f "requirements.txt" ]; then
    echo "Installing/updating dependencies..."
    "$PIP_CMD" install -U pip setuptools wheel
    "$PIP_CMD" install -r requirements.txt
fi

# Validate runtime before starting long-running services.
preflight_checks() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running preflight checks..."

    if [ ! -f "pi_experiment_service.py" ]; then
        echo "ERROR: Missing pi_experiment_service.py"
        return 1
    fi
    if [ ! -f "experiment_runner_refactored.py" ]; then
        echo "ERROR: Missing experiment_runner_refactored.py"
        return 1
    fi

    "$PY_CMD" - <<'PY'
from experiment_runner_refactored import create_experiment_runner

for exp in ("E1", "E2", "E3", "E4", "E5"):
    create_experiment_runner(exp, trials=1)

print("Preflight OK: experiment runners E1-E5 can be constructed")
PY
}

# ============ START SERVICE ==========

# ============ START SERVICE ==========

start_services() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Experiment Service..."
    
    export PI_SERVICE_PORT=$PI_SERVICE_PORT
    export PI_SERVICE_HOST=$PI_SERVICE_HOST
    export PYTHONUNBUFFERED=1
    export LOG_LEVEL=${LOG_LEVEL:-INFO}
    export DT_ALLOW_BOOTSTRAP_PARAMS=${DT_ALLOW_BOOTSTRAP_PARAMS:-0}
    export E2_FAULT_SETTLE_SECONDS=${E2_FAULT_SETTLE_SECONDS:-5}
    export E2_VERIFY_WINDOW_SECONDS=${E2_VERIFY_WINDOW_SECONDS:-8}

    preflight_checks

    # Start agent in background (continuous sensor collection)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Pi Agent in background (LOG_LEVEL=$LOG_LEVEL)..."
    nohup "$PY_CMD" agent.py > "${SCRIPT_DIR}/logs/pi_agent.log" 2>&1 &
    AGENT_PID=$!
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Agent PID: $AGENT_PID (logs: ${SCRIPT_DIR}/logs/pi_agent.log)"

    # Stream agent logs to this terminal so Pi dispatch evidence is visible live.
    if [ "${STREAM_AGENT_LOGS:-1}" = "1" ]; then
        if [ -n "$AGENT_LOG_TAIL_PID" ] && ps -p $AGENT_LOG_TAIL_PID > /dev/null 2>&1; then
            kill $AGENT_LOG_TAIL_PID 2>/dev/null || true
        fi
        tail -n 0 -F "${SCRIPT_DIR}/logs/pi_agent.log" &
        AGENT_LOG_TAIL_PID=$!
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Streaming agent logs to console (PID: $AGENT_LOG_TAIL_PID)"
    fi

    sleep 2  # Give agent time to initialize

    # Run service with logging
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Experiment Service..."
    "$PY_CMD" pi_experiment_service.py 2>&1 | tee -a "$LOG_FILE"
}

stop_services() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stopping services..."
    if [ -n "$AGENT_LOG_TAIL_PID" ] && ps -p $AGENT_LOG_TAIL_PID > /dev/null 2>&1; then
        echo "Stopping Agent log stream (PID: $AGENT_LOG_TAIL_PID)..."
        kill $AGENT_LOG_TAIL_PID 2>/dev/null || true
        sleep 1
    fi
    AGENT_LOG_TAIL_PID=""
    if [ -n "$AGENT_PID" ] && ps -p $AGENT_PID > /dev/null 2>&1; then
        echo "Stopping Agent (PID: $AGENT_PID)..."
        kill $AGENT_PID 2>/dev/null || true
        sleep 1
    fi
    AGENT_PID=""
}

# ============ AUTO-WATCH MODE ==========

get_file_hash() {
    find "$SCRIPT_DIR" -type f \( -name "*.py" -o -name "config.env" \) \
        -not -path "*/\.*" -not -path "*/__pycache__/*" -not -path "*/logs/*" \
        -exec md5sum {} \; 2>/dev/null | sort | md5sum | awk '{print $1}'
}

watch_and_restart() {
    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] AUTO-WATCH MODE ENABLED"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Services will restart on code changes"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Press Ctrl+C to stop"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========================================="
    echo ""
    
    LAST_HASH=""
    CHECK_INTERVAL=2
    
    while true; do
        sleep $CHECK_INTERVAL
        current_hash=$(get_file_hash)
        
        if [ -z "$LAST_HASH" ]; then
            LAST_HASH="$current_hash"
            continue
        fi
        
        if [ "$LAST_HASH" != "$current_hash" ]; then
            echo ""
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  CODE CHANGES DETECTED!"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting services..."
            echo ""
            
            stop_services
            sleep 1
            start_services
            
            LAST_HASH="$current_hash"
        fi
    done
}

watch_and_restart_realtime() {
    if ! command -v inotifywait &> /dev/null; then
        echo "ERROR: inotifywait not found"
        echo "Install with: sudo apt-get install inotify-tools"
        echo "Or use: sudo bash start_experiment_service.sh --watch (polling mode)"
        exit 1
    fi
    
    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] AUTO-WATCH MODE (Real-time) ENABLED"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Using inotifywait for instant restarts"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Press Ctrl+C to stop"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========================================="
    echo ""
    
    inotifywait -m -r -e modify,create,delete \
        "$SCRIPT_DIR/*.py" \
        "$SCRIPT_DIR/config/config.env" \
        "$SCRIPT_DIR/pi_deployment/*.py" 2>/dev/null | while read -r dir action file; do
        
        # Skip cache files
        if [[ "$file" =~ \.pyc$ ]] || [[ "$file" =~ __pycache__ ]] || [[ "$file" =~ \.swp$ ]]; then
            continue
        fi
        
        echo ""
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  CODE CHANGES DETECTED: $dir$file"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting services..."
        echo ""
        
        stop_services
        sleep 1
        start_services
    done
}

# ============ MAIN ==========

echo "Starting experiment service on $PI_SERVICE_HOST:$PI_SERVICE_PORT..."

if [ "$WATCH_REALTIME" = true ]; then
    watch_and_restart_realtime
elif [ "$WATCH_MODE" = true ]; then
    watch_and_restart
else
    start_services
fi
