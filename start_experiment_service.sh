#!/bin/bash

# Pi Experiment Service - Startup Script
# Place in: /home/pi/digitaltwi/demo-board-hardware-code/
# Run with: bash start_experiment_service.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

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

# Run service with logging
python3 pi_experiment_service.py 2>&1 | tee -a "$LOG_FILE"
