# Deckling

A custom macro pad controller with Arduino hardware and a Tauri desktop app for Windows.

## Features

- **Button Matrix** — Configure keyboard shortcuts, mouse clicks, media keys, or app launchers
- **Potentiometers** — Control Voicemeeter Banana strip gains
- **Multiple Profiles** — Switch between different configurations
- **Auto-Connect** — Automatically connect to Arduino on startup
- **Launch on Startup** — Start with Windows
- **Pin Mapping** — Assign physical buttons to UI positions

## Quick Start

1. Flash the Arduino firmware (`arduino/arduino.ino`)
2. Install and run the app
3. Select your COM port in Settings and click Connect
4. Configure your buttons and pots

## Building

```bash
cd ui
npm install
npm run tauri build
```

The installer will be in `ui/src-tauri/target/release/bundle/`.

## Requirements

- Windows 10/11
- [Voicemeeter Banana](https://vb-audio.com/Voicemeeter/banana.htm) (optional, for pot controls)
- Arduino Nano/Uno with the firmware flashed

## Arduino Wiring

See `arduino/arduino.ino` for pin assignments. Default configuration:
- **Button Matrix**: 3 rows × 4 columns (pins 2-8)
- **Potentiometers**: 4 pots on A0-A3
