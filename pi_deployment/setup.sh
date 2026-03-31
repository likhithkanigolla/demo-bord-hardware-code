#!/bin/bash
################################################################################
# Raspberry Pi Self-Adaptive Digital Twin Deployment Setup
# 
# This script configures a Raspberry Pi to run self-adaptive experiments
# Installs dependencies, creates virtual environment, and configures hardware
################################################################################

set -e  # Exit on error

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PI_USERNAME="${PI_USERNAME:-pi}"
PROJECT_DIR="/home/$PI_USERNAME/dt-experiments"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_VERSION="3.9"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Digital Twin Pi Deployment Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running on Raspberry Pi
IS_PI=false
if grep -q "arm" /proc/cpuinfo 2>/dev/null; then
    IS_PI=true
else
    echo -e "${YELLOW}⚠️  Warning: This doesn't appear to be a Raspberry Pi${NC}"
    echo -e "${YELLOW}Some features (GPIO, systemd service) will be skipped${NC}"
fi

if [ "$IS_PI" = true ]; then
    echo -e "${YELLOW}1. Updating system packages...${NC}"
    sudo apt-get update
    sudo apt-get upgrade -y
    echo -e "${GREEN}✓ System packages updated${NC}"
    echo ""
else
    echo -e "${YELLOW}1. Skipping system package update (not on Pi)${NC}"
    echo ""
fi

if [ "$IS_PI" = true ]; then
    echo -e "${YELLOW}2. Installing Python and system dependencies...${NC}"
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        libssl-dev \
        libffi-dev \
        git \
        curl \
        wget \
        build-essential \
        libjpeg-dev \
        zlib1g-dev
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${YELLOW}2. Skipping system dependency install (not on Pi, use Homebrew or apt as needed)${NC}"
fi
echo ""

echo -e "${YELLOW}3. Creating project directory...${NC}"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
echo -e "${GREEN}✓ Project directory: $PROJECT_DIR${NC}"
echo ""

echo -e "${YELLOW}4. Creating Python virtual environment...${NC}"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
echo -e "${GREEN}✓ Virtual environment created${NC}"
echo ""

echo -e "${YELLOW}5. Installing Python packages...${NC}"
pip install --upgrade pip setuptools wheel
pip install \
    fastapi \
    uvicorn \
    psycopg2-binary \
    requests \
    pydantic \
    scipy \
    numpy \
    python-dotenv

echo -e "${GREEN}✓ Python packages installed${NC}"
echo ""

if [ "$IS_PI" = true ]; then
    echo -e "${YELLOW}6. Setting up GPIO and hardware access...${NC}"
    # Add user to GPIO groups
    sudo usermod -a -G gpio "$PI_USERNAME"
    sudo usermod -a -G spi "$PI_USERNAME"
    sudo usermod -a -G i2c "$PI_USERNAME"

    # Install GPIO control library and hardware packages
    pip install \
        RPi.GPIO \
        adafruit_blinka \
        adafruit_circuitpython_sgp30 \
        adafruit_circuitpython_si7021 \
        adafruit_circuitpython_veml7700

    echo -e "${GREEN}✓ Hardware access configured${NC}"
else
    echo -e "${YELLOW}6. Skipping GPIO setup (not on Pi)${NC}"
fi
echo ""

echo -e "${YELLOW}7. Creating configuration directory...${NC}"
mkdir -p "$PROJECT_DIR/config"
mkdir -p "$PROJECT_DIR/logs"

# Create default config
cat > "$PROJECT_DIR/config/config.env" << 'EOF'
# Self-Adaptive Digital Twin - Pi Configuration

# Backend API configuration
BACKEND_HOST=http://localhost:8000
BACKEND_API_KEY=your_api_key_here

# Node configuration
NODE_ID=1
NODE_NAME=demo-board-01

# Sensor configuration
TEMP_SENSOR_PIN=17
FAN_CONTROL_PIN=27
SENSOR_POLL_INTERVAL=5

# Experiment configuration
EXPERIMENT_MODE=E1_candidate_selection
EXPERIMENT_DURATION=3600
FAULT_INJECTION_ENABLED=true

# Logging
LOG_LEVEL=INFO
LOG_FILE=/home/pi/dt-experiments/logs/experiment.log
EOF

echo -e "${GREEN}✓ Configuration template created at config/config.env${NC}"
echo ""

if [ "$IS_PI" = true ]; then
    echo -e "${YELLOW}8. Setting up systemd service...${NC}"
    sudo tee /etc/systemd/system/dt-experiments.service > /dev/null << EOF
[Unit]
Description=Digital Twin Self-Adaptive Experiments
After=network.target

[Service]
Type=simple
User=$PI_USERNAME
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python $PROJECT_DIR/run_experiments.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    echo -e "${GREEN}✓ Systemd service created (dt-experiments)${NC}"
else
    echo -e "${YELLOW}8. Skipping systemd service (not on Pi)${NC}"
fi
echo ""

echo -e "${YELLOW}9. Creating experiment runner script...${NC}"
cat > "$PROJECT_DIR/run_experiments.py" << 'PYEOF'
#!/usr/bin/env python3
"""
Experiment Runner for Raspberry Pi
Executes self-adaptive experiments and reports results
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load configuration
config_dir = Path(__file__).parent / 'config'
load_dotenv(config_dir / 'config.env')

# Setup logging
log_dir = Path(os.getenv('LOG_FILE', './logs')).parent
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE', 'experiment.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class PiExperimentRunner:
    """Run experiments on Pi hardware"""
    
    def __init__(self):
        self.node_id = int(os.getenv('NODE_ID', '1'))
        self.backend_host = os.getenv('BACKEND_HOST', 'http://localhost:8000')
        self.experiment_mode = os.getenv('EXPERIMENT_MODE', 'E1_candidate_selection')
        logger.info(f"Initialized Pi runner for node {self.node_id}")
    
    def run(self):
        """Main experiment loop"""
        try:
            logger.info(f"Starting experiments in {self.experiment_mode} mode")
            
            # Placeholder - replace with actual experiment logic
            results = {
                'timestamp': datetime.now().isoformat(),
                'node_id': self.node_id,
                'experiment_mode': self.experiment_mode,
                'status': 'running'
            }
            
            logger.info(f"Experiment results: {json.dumps(results, indent=2)}")
            return results
            
        except Exception as e:
            logger.error(f"Experiment failed: {e}", exc_info=True)
            raise

if __name__ == '__main__':
    try:
        runner = PiExperimentRunner()
        runner.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
PYEOF

chmod +x "$PROJECT_DIR/run_experiments.py"
echo -e "${GREEN}✓ Experiment runner created${NC}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Edit the configuration file:"
echo "   nano $PROJECT_DIR/config/config.env"
echo ""
echo "2. Test the setup:"
echo "   source $VENV_DIR/bin/activate"
echo "   cd $PROJECT_DIR && python run_experiments.py"
echo ""
echo "3. Start the systemd service:"
echo "   sudo systemctl start dt-experiments"
echo "   sudo systemctl status dt-experiments"
echo ""
echo "4. View logs:"
echo "   tail -f $PROJECT_DIR/logs/experiment.log"
echo ""
