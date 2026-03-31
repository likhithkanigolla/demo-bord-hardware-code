# Raspberry Pi Mode Setup

## Purpose

Switch between:

* Minimal Mode → Fast, no GUI
* Full Mode → GUI + services

---

## Folder Structure

```
digital_twin/
└── pi_setup/
    ├── mode_switch.sh
    └── PI_SETUP.md
```

---

## Script File

Location:

```
~/Desktop/digital_twin/pi_setup/mode_switch.sh
```

---

## Minimal Mode

Disables:

* Bluetooth
* Modem services
* Printing (cups)
* GUI (lightdm)
* Auto updates

Run:

```
./mode_switch.sh minimal
```

---

## Full Mode

Enables:

* GUI
* Bluetooth
* Printing
* Auto updates

Run:

```
./mode_switch.sh full
```

---

## First Time Setup

Make script executable:

```
chmod +x ~/Desktop/digital_twin/pi_setup/mode_switch.sh
```

---

## Alias (Shortcut Command)

Create shortcut to run from anywhere:

Open config:

```
nano ~/.bashrc
```

Add:

```
alias pi-mode='~/Desktop/digital_twin/pi_setup/mode_switch.sh'
```

Reload:

```
source ~/.bashrc
```

---

## Usage (Shortcut)

Minimal mode:

```
pi-mode minimal
```

Full mode:

```
pi-mode full
```

---

## Reboot

After switching:

```
sudo reboot
```

---

## Notes

* SSH always works
* raspberrypi.local works (avahi)
* UART and GPIO not affected
* Fully reversible setup

---

## Usage Summary

Minimal:

```
pi-mode minimal
```

Full:

```
pi-mode full
```