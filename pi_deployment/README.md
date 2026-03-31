# Pi Deployment Scripts

This directory contains all scripts and configuration needed to deploy and run self-adaptive experiments on a Raspberry Pi.

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Run this on your Raspberry Pi
bash pi_deployment/quickstart.sh

# Then run an experiment
bash pi_deployment/run.sh
```

### Option 2: Manual Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp pi_deployment/config_template.env config/config.env
nano config/config.env  # Edit with your settings

# 4. Run
python pi_deployment/pi_experiment_runner.py
```

## Files Overview

| File | Purpose |
|------|---------|
| `setup.sh` | Full system setup with systemd service (run once) |
| `quickstart.sh` | Quick environment setup without systemd |
| `run.sh` | Simple wrapper to execute experiments |
| `pi_experiment_runner.py` | Main experiment execution engine |
| `health_check.sh` | System health monitoring |
| `config_template.env` | Configuration template |

## Usage Examples

### Run Single Experiment

```bash
bash pi_deployment/run.sh
```

Output:
```
2026-03-31 13:05:42,123 - __main__ - INFO - Initialized Pi runner: demo-board-01
================================================================================
EXPERIMENT E1: CANDIDATE SELECTION
================================================================================
...
```

### Run Continuous Experiments

```bash
bash pi_deployment/run.sh --continuous
```

This will run experiments repeatedly with configured interval between cycles.

### Check System Health

```bash
bash pi_deployment/health_check.sh /home/pi/dt-experiments
```

Output:
```
Digital Twin Pi System Health Check
======================================
1. Python Environment
   ✓ Virtual environment: Active
   Python 3.9.2

2. Python Packages
   ✓ fastapi
   ✓ uvicorn
   ...
```

### View Live Logs

```bash
tail -f config/logs/pi_experiments.log
```

### Monitor Results

```bash
# View latest result
cat results/latest_result.json | jq '.'

# List all results
ls -lh results/

# Watch for new results
watch ls -lh results/
```

## Configuration

Edit `config/config.env`:

```bash
nano config/config.env
```

Key settings:
- `BACKEND_HOST` - Digital Twin backend URL
- `NODE_ID` - Unique node identifier
- `EXPERIMENT_MODE` - Which experiment to run (E1-E5)
- `FAULT_INJECTION_ENABLED` - Enable fault testing
- `EXPERIMENT_DURATION` - Duration between cycles

## Systemd Service (after setup.sh)

```bash
# Start service
sudo systemctl start dt-experiments

# Stop service
sudo systemctl stop dt-experiments

# View logs
sudo journalctl -u dt-experiments -f

# Enable auto-start
sudo systemctl enable dt-experiments

# Disable auto-start
sudo systemctl disable dt-experiments
```

## Troubleshooting

### Python: Command not found
```bash
# Use python3 explicitly
python3 -m venv venv
```

### Permission denied on .sh files
```bash
# Make scripts executable
chmod +x pi_deployment/*.sh
```

### Virtual environment not found
```bash
# Create it manually
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Backend connection failed
```bash
# Check network connectivity
ping <backend_ip>

# Verify backend is running
curl http://<backend_ip>:8000/health
```

### Import errors
```bash
# Ensure backend modules are in path
export PYTHONPATH=$PWD/backend:$PYTHONPATH

# Or verify relative imports in runner
python -c "import sys; print(sys.path)"
```

## Development

### Adding New Experiments

1. Implement experiment method: `def run_e{n}_experiment(self) -> dict:`
2. Add to `ExperimentMode` enum
3. Update `run_experiment()` method to call new experiment
4. Update config `EXPERIMENT_MODE` value

Example:
```python
def run_e2_experiment(self) -> dict:
    """Run E2: Accuracy Improvement Experiment"""
    logger.info("=" * 80)
    logger.info("EXPERIMENT E2: ACCURACY IMPROVEMENT")
    logger.info("=" * 80)
    
    # Implementation here
    results = {
        'experiment': 'E2_accuracy',
        'trials': [],
        'summary': {}
    }
    return results
```

### Testing Locally

Before deploying to Pi, test on your machine:

```bash
# Set mock mode
export PI_MOCK=true

# Run experiments
python pi_deployment/pi_experiment_runner.py
```

### Performance Optimization

For better thermal management:

```bash
# Reduce GPU memory usage in /boot/config.txt
gpu_mem=64

# Disable unnecessary services
sudo systemctl disable avahi-daemon
sudo systemctl disable bluetooth

# Set CPU frequency cap
sudo nano /boot/config.txt
# Add or modify: arm_freq=1800
```

## File Structure

```
demo-board-hardware-code/
├── pi_deployment/
│   ├── setup.sh                    # Full setup with systemd
│   ├── quickstart.sh               # Quick environment setup
│   ├── run.sh                      # Simple run wrapper
│   ├── health_check.sh             # System health check
│   ├── pi_experiment_runner.py     # Main experiment engine
│   ├── config_template.env         # Configuration template
│   └── README.md                   # This file
├── config/
│   └── config.env                  # Your configuration (created by setup)
├── logs/
│   └── pi_experiments.log          # Experiment logs
└── results/
    ├── E1_*.json                   # Experiment results
    └── latest_result.json          # Most recent result
```

## Next Steps

1. ✅ Deploy to Pi using `setup.sh` or `quickstart.sh`
2. ✅ Configure `config/config.env` with your settings
3. ✅ Test first experiment with `run.sh`
4. ✅ Monitor with `health_check.sh`
5. ✅ View results in `results/` directory
6. ✅ Enable auto-start with systemd

## Support

- Check logs: `tail -f logs/pi_experiments.log`
- System health: `bash pi_deployment/health_check.sh`
- Configuration: Edit `config/config.env`
- Backend issues: Test with `curl http://<backend>:8000/health`

## References

- **Main Deployment Guide**: `PI_DEPLOYMENT_GUIDE.md`
- **Backend Integration**: `../../backend/routes/adaptation.py`
- **Thermal Model**: `../../backend/modules/thermal_simulator.py`
- **MAPE-K Engine**: `../../backend/modules/adaptation_engine.py`
