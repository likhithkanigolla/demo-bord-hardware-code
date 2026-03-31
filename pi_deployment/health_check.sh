#!/bin/bash
################################################################################
# Pi System Health Check
# Monitors and reports system health for experiment runner
################################################################################

COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_YELLOW='\033[1;33m'
COLOR_BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="${1:-.}"
VENV_DIR="$PROJECT_DIR/venv"

echo -e "${COLOR_BLUE}Digital Twin Pi System Health Check${NC}"
echo "======================================"
echo ""

# Check Python environment
echo -e "${COLOR_YELLOW}1. Python Environment${NC}"
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate" 2>/dev/null
    PYTHON_VERSION=$(python --version 2>&1)
    echo -e "   ${COLOR_GREEN}✓${NC} Virtual environment: Active"
    echo "   $PYTHON_VERSION"
else
    echo -e "   ${COLOR_RED}✗${NC} Virtual environment: NOT FOUND"
fi
echo ""

# Check required Python packages
echo -e "${COLOR_YELLOW}2. Python Packages${NC}"
packages=("fastapi" "uvicorn" "psycopg2" "requests" "scipy" "numpy")
all_ok=true
for pkg in "${packages[@]}"; do
    if python -c "import $pkg" 2>/dev/null; then
        echo -e "   ${COLOR_GREEN}✓${NC} $pkg"
    else
        echo -e "   ${COLOR_RED}✗${NC} $pkg (MISSING)"
        all_ok=false
    fi
done
echo ""

# Check system resources
echo -e "${COLOR_YELLOW}3. System Resources${NC}"
cpu_temp=$(vcgencmd measure_temp 2>/dev/null | grep -oP '\d+\.\d+')
if [ -z "$cpu_temp" ]; then
    cpu_temp="Unknown"
fi
echo "   CPU Temperature: ${cpu_temp}°C"

free_mem=$(free -m | awk 'NR==2 {print $7}')
echo "   Free Memory: ${free_mem}MB"

disk_usage=$(df -h / | awk 'NR==2 {print $5}')
echo "   Disk Usage: $disk_usage"
echo ""

# Check GPIO access
echo -e "${COLOR_YELLOW}4. GPIO Access${NC}"
if python -c "import RPi.GPIO" 2>/dev/null; then
    echo -e "   ${COLOR_GREEN}✓${NC} GPIO library available"
else
    echo -e "   ${COLOR_RED}✗${NC} GPIO library (MISSING)"
fi
echo ""

# Check configuration
echo -e "${COLOR_YELLOW}5. Configuration${NC}"
config_file="$PROJECT_DIR/config/config.env"
if [ -f "$config_file" ]; then
    echo -e "   ${COLOR_GREEN}✓${NC} Configuration file found"
    node_id=$(grep NODE_ID "$config_file" | cut -d= -f2)
    backend_host=$(grep BACKEND_HOST "$config_file" | cut -d= -f2)
    echo "   Node ID: $node_id"
    echo "   Backend: $backend_host"
else
    echo -e "   ${COLOR_RED}✗${NC} Configuration file NOT FOUND"
fi
echo ""

# Check backend connectivity
echo -e "${COLOR_YELLOW}6. Backend Connectivity${NC}"
if [ -f "$config_file" ]; then
    backend_host=$(grep BACKEND_HOST "$config_file" | cut -d= -f2 | tr -d ' ')
    if timeout 2 curl -s "$backend_host/health" > /dev/null 2>&1; then
        echo -e "   ${COLOR_GREEN}✓${NC} Backend reachable: $backend_host"
    else
        echo -e "   ${COLOR_YELLOW}⚠${NC} Backend unreachable: $backend_host"
    fi
fi
echo ""

# Check service status
echo -e "${COLOR_YELLOW}7. Service Status${NC}"
if systemctl is-enabled dt-experiments > /dev/null 2>&1; then
    status=$(systemctl is-active dt-experiments)
    if [ "$status" = "active" ]; then
        echo -e "   ${COLOR_GREEN}✓${NC} Service is running"
    else
        echo -e "   ${COLOR_YELLOW}⚠${NC} Service is $status"
    fi
else
    echo -e "   ${COLOR_YELLOW}⚠${NC} Service not enabled"
fi
echo ""

# Summary
echo "======================================"
if [ "$all_ok" = true ]; then
    echo -e "${COLOR_GREEN}✓ System health: GOOD${NC}"
else
    echo -e "${COLOR_YELLOW}⚠ System health: CHECK REQUIRED${NC}"
fi
echo ""
