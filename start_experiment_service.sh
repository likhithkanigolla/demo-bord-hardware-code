#!/bin/bash

# Pi Experiment Service - Startup Script
# Place in: /home/pi/digitaltwi/demo-board-hardware-code/
# Run with: sudo bash start_experiment_service.sh

set -e

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

# Install dependencies if requirements exist
if [ -f "requirements.txt" ]; then
    echo "Installing/updating dependencies..."
    pip install -U pip setuptools wheel
    pip install -r requirements.txt
fi

# ============ START SERVICE ==========

echo "Starting experiment service on $PI_SERVICE_HOST:$PI_SERVICE_PORT..."

export PI_SERVICE_PORT=$PI_SERVICE_PORT
export PI_SERVICE_HOST=$PI_SERVICE_HOST
export PYTHONUNBUFFERED=1
export LOG_LEVEL=${LOG_LEVEL:-INFO}

# Start agent in background (continuous sensor collection)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Pi Agent in background (LOG_LEVEL=$LOG_LEVEL)..."
nohup python3 agent.py > "${SCRIPT_DIR}/logs/pi_agent.log" 2>&1 &
AGENT_PID=$!
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Agent PID: $AGENT_PID (logs: ${SCRIPT_DIR}/logs/pi_agent.log)"

sleep 2  # Give agent time to initialize

# Run service with logging
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Experiment Service..."
python3 pi_experiment_service.py 2>&1 | tee -a "$LOG_FILE"
