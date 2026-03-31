#!/bin/bash

MODE=$1

if [ "$MODE" == "minimal" ]; then
    echo "⚡ Switching to MINIMAL MODE..."

    sudo systemctl disable bluetooth hciuart triggerhappy ModemManager cups cups-browsed lightdm
    sudo systemctl stop bluetooth hciuart triggerhappy ModemManager cups cups-browsed lightdm

    sudo systemctl disable apt-daily.timer apt-daily-upgrade.timer

    sudo systemctl set-default multi-user.target

    echo "✅ Minimal mode enabled (fast, no GUI)"
    echo "Reboot recommended"

elif [ "$MODE" == "full" ]; then
    echo "🖥️ Switching to FULL MODE..."

    sudo systemctl enable bluetooth hciuart triggerhappy ModemManager cups cups-browsed lightdm
    sudo systemctl start bluetooth hciuart triggerhappy ModemManager cups cups-browsed lightdm

    sudo systemctl enable apt-daily.timer apt-daily-upgrade.timer
    sudo systemctl start apt-daily.timer apt-daily-upgrade.timer

    sudo systemctl set-default graphical.target

    echo "✅ Full mode enabled (GUI + services)"
    echo "Reboot recommended"

else
    echo "❌ Usage:"
    echo "./mode_switch.sh minimal"
    echo "./mode_switch.sh full"
fi