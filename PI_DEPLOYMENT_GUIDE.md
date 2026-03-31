# Raspberry Pi Deployment Guide

This guide walks you through deploying the self-adaptive digital twin experiments to a Raspberry Pi.

> **Note**: For information about cross-platform deployment (macOS/Linux development and Raspberry Pi), see [PI_DEPLOYMENT_FIX.md](PI_DEPLOYMENT_FIX.md)

## Hardware Requirements

- **Raspberry Pi 4B** (4GB+ RAM recommended)
- **Operating System**: Raspberry Pi OS (Bullseye or newer)
- **Storage**: 32GB microSD card
- **Power**: 5V 3A USB-C power supply
- **Demo Board Hardware**: Connected via GPIO pins

## Deployment Steps

### Step 1: Prepare the Raspberry Pi

```bash
# SSH into your Pi
ssh pi@<pi_ip_address>

# Download the deployment script
curl -O https://raw.githubusercontent.com/likhithkanigolla/dt-hardware/main/pi_deployment/setup.sh
chmod +x setup.sh

# Run the setup script (this will take 10-15 minutes)
./setup.sh
```

The setup script will:
- Update system packages
- Install Python 3.9 and dependencies
- Create a Python virtual environment
- Install required Python packages
- Configure GPIO access
- Create systemd service for auto-startup

### Step 2: Configure the Environment

After setup, configure your deployment:

```bash
# Edit the configuration file
nano ~/dt-experiments/config/config.env
```

Key configuration options:

| Variable | Description | Example |
|----------|-------------|---------|
| `BACKEND_HOST` | Digital Twin backend API URL | `http://192.168.1.100:8000` |
| `BACKEND_API_KEY` | API authentication token | `sk_live_xxxxx` |
| `NODE_ID` | Unique node identifier | `1` |
| `NODE_NAME` | Human-readable node name | `demo-board-01` |
| `TEMP_SENSOR_PIN` | GPIO pin for temperature sensor | `17` |
| `FAN_CONTROL_PIN` | GPIO pin for fan control | `27` |
| `EXPERIMENT_MODE` | Which experiment to run | `E1_candidate_selection` |
| `EXPERIMENT_DURATION` | Experiment duration in seconds | `3600` |
| `FAULT_INJECTION_ENABLED` | Enable fault injection testing | `true` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

### Step 3: Test the Setup

```bash
# Activate the virtual environment
source ~/dt-experiments/venv/bin/activate

# Test the experiment runner
cd ~/dt-experiments
python run_experiments.py
```

Expected output:
```
2026-03-31 13:05:42,123 - __main__ - INFO - Initialized Pi runner for node 1
2026-03-31 13:05:42,456 - __main__ - INFO - Starting experiments in E1_candidate_selection mode
```

### Step 4: Enable Auto-Start

```bash
# Start the service
sudo systemctl start dt-experiments

# Enable auto-start on boot
sudo systemctl enable dt-experiments

# Check service status
sudo systemctl status dt-experiments

# View live logs
journalctl -u dt-experiments -f
```

### Step 5: Monitor Experiments

View experiment logs:

```bash
# Stream live logs
tail -f ~/dt-experiments/logs/experiment.log

# View specific number of lines
tail -n 100 ~/dt-experiments/logs/experiment.log

# Search for errors
grep ERROR ~/dt-experiments/logs/experiment.log
```

Monitor results:

```bash
# Check results directory
ls -la ~/dt-experiments/results/

# View latest result
cat ~/dt-experiments/results/latest_result.json | jq '.'
```

## GPIO Pin Configuration

The demo board uses the following GPIO pins:

| Function | GPIO Pin | BCM | Description |
|----------|----------|-----|-------------|
| Temperature Sensor | 11 | 17 | DHT22/BME280 sensor |
| Fan Control | 13 | 27 | PWM signal to relay/MOSFET |
| Status LED | 15 | 22 | Optional status indicator |
| Debug Serial | 8/10 | 14/15 | UART for debugging |

## Troubleshooting

### Issue: Permission Denied on GPIO

**Solution**: Ensure the user is in GPIO group
```bash
sudo usermod -a -G gpio pi
# Reboot or reload group membership
newgrp gpio
```

### Issue: Backend Connection Failed

**Solution**: Check network connectivity and API endpoint
```bash
# Test backend API
curl http://<backend_ip>:8000/health

# Check firewall rules on backend machine
sudo ufw status
```

### Issue: Sensor Not Reading / Temperature = 0

**Solution**: Check GPIO connections and sensor type
```bash
# Test GPIO pin
python -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(17, GPIO.IN); print(GPIO.input(17))"

# Verify sensor is connected
i2cdetect -y 1
```

### Issue: Service Won't Start

**Solution**: Check logs and configuration
```bash
# View service error logs
journalctl -u dt-experiments -n 50

# Validate Python syntax
python -m py_compile ~/dt-experiments/run_experiments.py

# Check file permissions
ls -la ~/dt-experiments/run_experiments.py
chmod +x ~/dt-experiments/run_experiments.py
```

## Network Configuration

### Connecting to Backend Server

The Pi needs network access to the backend server. Options:

**Option 1: Same Network (Recommended)**
```bash
# Ping the backend server
ping <backend_ip>

# Update config with backend IP
BACKEND_HOST=http://192.168.1.100:8000
```

**Option 2: Remote VPN Connection**
```bash
# Install OpenVPN client
sudo apt-get install openvpn

# Configure VPN connection
sudo nano /etc/openvpn/client.conf

# Start VPN
sudo systemctl start openvpn@client
sudo systemctl enable openvpn@client
```

## Performance Optimization

For optimal experiment performance on Pi:

1. **Disable unnecessary services**:
   ```bash
   sudo systemctl disable avahi-daemon
   sudo systemctl disable bluetooth
   ```

2. **Increase memory**:
   Edit `/boot/config.txt`:
   ```ini
   gpu_mem=64  # Reduce GPU memory if not needed
   ```

3. **Boost GPU**:
   ```bash
   sudo nano /boot/config.txt
   # Add: arm_freq=2000 (caution: may increase heat)
   ```

## Updating the Framework

To pull the latest changes:

```bash
cd ~/dt-experiments

# Fetch latest code
git pull origin main

# Restart service
sudo systemctl restart dt-experiments
```

## SSH Tunneling (for remote monitoring)

```bash
# Local monitoring from your dev machine
ssh -L 8000:localhost:8000 pi@<pi_ip>

# Then access Pi logs from your machine
# The experiments will be accessible at http://localhost:8000
```

## Performance Monitoring

Monitor resource usage:

```bash
# CPU and memory usage
top

# Disk space
df -h

# Temperature
vcgencmd measure_temp

# GPU clock frequency
vcgencmd measure_clock arm
```

## Backup and Recovery

Backup experiment results:

```bash
# Backup results to desktop
rsync -avz pi@<pi_ip>:~/dt-experiments/results/ ./pi_results_backup/

# Restore from backup
rsync -avz ./pi_results_backup/ pi@<pi_ip>:~/dt-experiments/results/
```

## Next Steps

1. ✅ Run individual experiments (E1-E5)
2. ✅ Monitor real-time results
3. ✅ Adjust parameters based on results
4. ✅ Deploy to production environment
5. ✅ Archive results for analysis

## Support

For issues or questions:
- Check the [troubleshooting section](#troubleshooting)
- Review logs: `tail -f ~/dt-experiments/logs/experiment.log`
- GitHub Issues: https://github.com/likhithkanigolla/dt-hardware/issues
