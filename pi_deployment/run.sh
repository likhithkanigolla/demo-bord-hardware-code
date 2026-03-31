#!/bin/bash
################################################################################
# Run Experiment Script
# Simple wrapper to execute experiments
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

# Activate virtual environment
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "Error: Virtual environment not found. Run quickstart.sh first"
    exit 1
fi

# Run the experiment runner with all arguments passed through
cd "$PROJECT_DIR"
python "$SCRIPT_DIR/pi_experiment_runner.py" "$@"
