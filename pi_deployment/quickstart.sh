#!/bin/bash
################################################################################
# Quick Start Script for Pi Experiments
# One-command setup and start for rapid deployment
################################################################################

set -e

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${COLOR_BLUE}"
echo "╔════════════════════════════════════════════════╗"
echo "║  Digital Twin Pi Experiments - Quick Start     ║"
echo "╚════════════════════════════════════════════════╝"
echo -e "${NC}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo ""
echo -e "${COLOR_YELLOW}1. Setting up environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo -e "   ${COLOR_GREEN}✓ Virtual environment created${NC}"
else
    echo -e "   ${COLOR_GREEN}✓ Virtual environment exists${NC}"
fi

echo ""
echo -e "${COLOR_YELLOW}2. Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"
echo -e "   ${COLOR_GREEN}✓ Activated${NC}"

echo ""
echo -e "${COLOR_YELLOW}3. Installing dependencies...${NC}"
pip install -q --upgrade pip setuptools wheel
pip install -q \
    fastapi \
    uvicorn \
    psycopg2-binary \
    requests \
    pydantic \
    scipy \
    numpy \
    python-dotenv

# Install hardware-specific packages only on Raspberry Pi
if grep -q "arm" /proc/cpuinfo 2>/dev/null; then
    echo "   Installing Raspberry Pi hardware support..."
    pip install -q \
        RPi.GPIO \
        adafruit_blinka \
        adafruit_circuitpython_sgp30 \
        adafruit_circuitpython_si7021 \
        adafruit_circuitpython_veml7700
    echo -e "   ${COLOR_GREEN}✓ Pi hardware support installed${NC}"
else
    echo -e "   ${COLOR_YELLOW}⚠️  Skipping Pi-specific hardware packages (not on RPi)${NC}"
fi

echo -e "   ${COLOR_GREEN}✓ Core dependencies installed${NC}"

echo ""
echo -e "${COLOR_YELLOW}4. Checking configuration...${NC}"
config_file="$PROJECT_DIR/config/config.env"
if [ ! -f "$config_file" ]; then
    echo "   Creating default configuration..."
    mkdir -p "$PROJECT_DIR/config"
    cp "$SCRIPT_DIR/config_template.env" "$config_file" 2>/dev/null || {
        # Create minimal config if template not found
        cat > "$config_file" << 'EOF'
BACKEND_HOST=http://localhost:8000
NODE_ID=1
EXPERIMENT_MODE=E1_candidate_selection
EXPERIMENT_DURATION=3600
FAULT_INJECTION_ENABLED=true
LOG_LEVEL=INFO
EOF
    }
    echo -e "   ${COLOR_GREEN}✓ Default configuration created${NC}"
    echo "   Edit: nano $config_file"
else
    echo -e "   ${COLOR_GREEN}✓ Configuration found${NC}"
fi

echo ""
echo -e "${COLOR_YELLOW}5. Preparing directories...${NC}"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/results"
chmod 755 "$SCRIPT_DIR"/*.sh
echo -e "   ${COLOR_GREEN}✓ Directories ready${NC}"

echo ""
echo "╔════════════════════════════════════════════════╗"
echo -e "${COLOR_GREEN}✓ Setup Complete!${NC}"
echo "╚════════════════════════════════════════════════╝"
echo ""

echo "Quick Commands:"
echo "  Run experiment once:"
echo "    $SCRIPT_DIR/run.sh"
echo ""
echo "  Run continuously:"
echo "    $SCRIPT_DIR/run.sh --continuous"
echo ""
echo "  Check system health:"
echo "    bash $SCRIPT_DIR/health_check.sh $PROJECT_DIR"
echo ""
echo "  View live logs:"
echo "    tail -f $PROJECT_DIR/logs/pi_experiments.log"
echo ""
echo "  View configuration:"
echo "    nano $config_file"
echo ""
