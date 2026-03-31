# Pi Deployment Verification Checklist

This document provides a step-by-step checklist to verify your Pi deployment is fully functional.

## Pre-Deployment Checklist

- [ ] Raspberry Pi 4B with Raspberry Pi OS installed
- [ ] Network connection (ethernet or WiFi)
- [ ] SSH access to Pi
- [ ] SSH key authentication configured (recommended)
- [ ] Demo board hardware connected and tested
- [ ] Backend server running and accessible from Pi's network

## Deployment Steps Verification

### Step 1: Copy Files to Pi

```bash
# From your dev machine
scp -r pi_deployment/* pi@<pi_ip>:~/dt-experiments/

# Verify files were copied
ssh pi@<pi_ip> ls -la ~/dt-experiments/
```

**Checklist:**
- [ ] setup.sh present (6KB+)
- [ ] quickstart.sh present (3KB+)
- [ ] pi_experiment_runner.py present (10KB+)
- [ ] config_template.env present
- [ ] health_check.sh present
- [ ] run.sh present

### Step 2: Run Setup Script

```bash
# SSH into Pi
ssh pi@<pi_ip>

# Run setup (15-20 minutes)
bash ~/dt-experiments/setup.sh

# Check for success message
```

**Checklist:**
- [ ] System packages updated
- [ ] Python 3.9+ installed
- [ ] Virtual environment created
- [ ] Python packages installed
- [ ] config/config.env created
- [ ] logs directory created
- [ ] results directory created
- [ ] systemd service installed

### Step 3: Configure Environment

```bash
# Edit configuration
nano ~/dt-experiments/config/config.env

# Key edits:
# - Set BACKEND_HOST to your backend IP
# - Verify NODE_ID and NODE_NAME
# - Enable/disable FAULT_INJECTION_ENABLED
```

**Checklist:**
- [ ] BACKEND_HOST points to correct server (test with `curl`)
- [ ] NODE_ID is unique (1 for single node)
- [ ] EXPERIMENT_MODE set to desired experiment
- [ ] FAULT_INJECTION_ENABLED matches your use case

### Step 4: Test Health Check

```bash
bash ~/dt-experiments/health_check.sh
```

Expected output:
```
Digital Twin Pi System Health Check
======================================
1. Python Environment
   ✓ Virtual environment: Active
2. Python Packages
   ✓ fastapi
   ✓ uvicorn
   ...more packages...
3. System Resources
   CPU Temperature: 45.2°C
   Free Memory: 3500MB
   Disk Usage: 15%
4. GPIO Access
   ✓ GPIO library available
5. Configuration
   ✓ Configuration file found
6. Backend Connectivity
   ✓ Backend reachable
7. Service Status
   ✓ Service is running
```

**Checklist:**
- [ ] All packages show ✓
- [ ] CPU temperature < 80°C
- [ ] Free memory > 1GB
- [ ] Backend connectivity shows ✓
- [ ] No ✗ marks (except for optional items)

### Step 5: Run Test Experiment

```bash
# Run single experiment (5-10 minutes)
bash ~/dt-experiments/pi_deployment/run.sh
```

Expected output:
```
Initialized Pi runner: demo-board-01 (node_id=1)
Backend: http://192.168.1.100:8000
Experiment mode: E1_candidate_selection
================================================================================
EXPERIMENT E1: CANDIDATE SELECTION
...
E1 Summary: 3/3 trials successful
Results saved to: /home/pi/dt-experiments/results/E1_...json
```

**Checklist:**
- [ ] Script starts without errors
- [ ] Backend connection successful
- [ ] All trials complete (3/3)
- [ ] Success rate > 0%
- [ ] Results file created in results/

### Step 6: Verify Results

```bash
# List results
ls -lh ~/dt-experiments/results/

# View latest result
cat ~/dt-experiments/results/latest_result.json | jq '.'

# Expected structure:
# {
#   "experiment": "E1_candidate_selection",
#   "timestamp": "2026-03-31T13:05:42.123456",
#   "node_id": 1,
#   "trials": [...],
#   "summary": {
#     "total_trials": 3,
#     "successful": 3,
#     "success_rate": 1.0
#   }
# }
```

**Checklist:**
- [ ] Result file is valid JSON
- [ ] Experiment matches what was configured
- [ ] All trials present
- [ ] Summary shows > 0% success rate
- [ ] Timestamp is recent

### Step 7: Enable Auto-Start Service

```bash
# Start the service
sudo systemctl start dt-experiments

# Verify it's running
sudo systemctl status dt-experiments

# Enable auto-start
sudo systemctl enable dt-experiments

# Check logs
sudo journalctl -u dt-experiments -n 20
```

**Checklist:**
- [ ] Service status shows "active (running)"
- [ ] No errors in service logs
- [ ] Service enabled in system
- [ ] Service restarts on Pi reboot (test with reboot)

### Step 8: Continuous Operation Test

```bash
# Start continuous mode (will run for specified EXPERIMENT_DURATION)
bash ~/dt-experiments/pi_deployment/run.sh --continuous &

# Monitor in another terminal
tail -f ~/dt-experiments/logs/pi_experiments.log

# Check resource usage
watch free -h
```

**Checklist:**
- [ ] Process runs without errors
- [ ] Logs accumulate over time
- [ ] Memory usage stable (< 500MB)
- [ ] CPU temperature stable (< 70°C)
- [ ] New result files created each cycle

## Post-Deployment Verification

### Network Stability

```bash
# Test with ping
ping -c 5 <backend_ip>

# Connection recovery test
# Disconnect network for 30 seconds
# Reconnect and verify experiment continues
```

**Checklist:**
- [ ] No packet loss on ping
- [ ] Service recovers after network interruption
- [ ] Logs show reconnection attempts

### Hardware Integration

```bash
# Check GPIO access
python -c "import RPi.GPIO; print('GPIO OK')"

# Monitor fan control (if connected)
# Observe fan speed changes with different settings
```

**Checklist:**
- [ ] GPIO library imports successfully
- [ ] Fan responds to control signals
- [ ] Temperature sensor reads valid values
- [ ] No GPIO permission errors

### Data Integrity

```bash
# Verify result files
cd ~/dt-experiments/results
for f in *.json; do python -m json.tool "$f" > /dev/null && echo "✓ $f"; done

# Check for corrupt files
find . -size 0 -type f -name "*.json"
```

**Checklist:**
- [ ] All JSON files are valid
- [ ] No empty result files
- [ ] All expected fields present in results
- [ ] No data corruption in logs

## Common Issues and Fixes

### Issue: "Virtual environment not found"
```bash
# Solution: Run quickstart.sh
bash ~/dt-experiments/pi_deployment/quickstart.sh
```

### Issue: "Backend unreachable"
```bash
# Check network
ping <backend_ip>

# Check firewall
ssh <backend_ip> 'sudo ufw status' | grep 8000

# Verify BACKEND_HOST in config.env
cat ~/dt-experiments/config/config.env | grep BACKEND_HOST
```

### Issue: "Permission denied" on GPIO
```bash
# Add user to GPIO group
sudo usermod -a -G gpio pi

# Reboot to apply
sudo reboot
```

### Issue: "Insufficient disk space"
```bash
# Check disk usage
df -h

# Clean old results if needed
rm ~/dt-experiments/results/E1_*_old.json
```

## Performance Benchmarks

Expected performance metrics:

| Metric | Expected Value |
|--------|----------------|
| Python startup time | < 2 seconds |
| E1 experiment duration | 3-5 minutes |
| API response time | < 500ms |
| CPU usage per cycle | 30-50% |
| Memory usage | 200-400MB |
| Disk write per cycle | 100-200KB |
| Temperature increase | +5-10°C from ambient |

## Success Criteria

✅ **Deployment is successful if:**
- All health check items show ✓
- First experiment runs with 100% success rate
- Service auto-starts and recovers from interruptions
- Results are saved and valid
- System remains stable under continuous operation
- Temperature stays within safe limits

## Final Sign-Off

- [ ] All above items verified
- [ ] System ready for production
- [ ] Documentation reviewed
- [ ] Team notified of deployment
- [ ] Backup procedures established

**Date Deployed:** _______________
**Deployed By:** _______________
**Approved By:** _______________

## Next Steps

1. Monitor first 24 hours of operation closely
2. Collect baseline performance metrics
3. Establish alerting thresholds
4. Document any custom modifications
5. Schedule regular maintenance checks
6. Archive results periodically
