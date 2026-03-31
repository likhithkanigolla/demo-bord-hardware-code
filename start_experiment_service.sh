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

# Activate virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

# Install dependencies if requirements exist
if [ -f "requirements.txt" ]; then
    echo "Installing/updating dependencies..."
    pip install -q -r requirements.txt
fi

# ============ START SERVICE ==========

echo "Starting experiment service on $PI_SERVICE_HOST:$PI_SERVICE_PORT..."

export PI_SERVICE_PORT=$PI_SERVICE_PORT
export PI_SERVICE_HOST=$PI_SERVICE_HOST
export PYTHONUNBUFFERED=1

# Run service with logging
python3 pi_experiment_service.py 2>&1 | tee -a "$LOG_FILE"
