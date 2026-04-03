# StreamDeck Controller UI

A Tauri + React/TypeScript config editor for the physical StreamDeck device. The UI manages `~/.streamdeck/config.json`, which is shared with a Python daemon that handles serial communication and VoiceMeeter control.

---

## Prerequisites

- **Node.js 18+** — [nodejs.org](https://nodejs.org)
- **Rust** — install via [rustup.rs](https://rustup.rs): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Python 3.10+**
- **Python packages:**
  ```
  pip install pyserial keyboard voicemeeterlib watchdog
  ```

---

## Install Dependencies

```bash
cd ui
npm install
```

---

## Run in Development

```bash
npm run tauri dev
```

This starts the Vite dev server on port 5173 and opens the Tauri window. The window hot-reloads on code changes.

---

## Build for Production

```bash
npm run tauri build
```

The compiled binary will be placed in `ui/src-tauri/target/release/`. An installer is also generated in `ui/src-tauri/target/release/bundle/`.

---

## Run the Python Daemon

The UI is purely a config editor — the actual key press dispatching and VoiceMeeter control is handled by the Python daemon. Run it separately from the project root:

```bash
python main.py
```

The daemon reads `~/.streamdeck/config.json` at startup and watches it for changes (via watchdog), so profile switches made in the UI take effect immediately without restarting the daemon.

---

## First Run

On first launch, the UI automatically creates:
- `~/.streamdeck/` directory
- `~/.streamdeck/config.json` with a default 2×6 grid, 4 pots, and 12 pre-assigned buttons

You can then customize button labels, key bindings, pot strip assignments, and hardware pin mappings via the UI.

---

## Flashing the Arduino

The Arduino firmware lives in `arduino/`. Open `arduino/arduino.ino` in the Arduino IDE:

1. Select the correct board (e.g. Arduino Nano or Uno)
2. Select the correct COM port
3. Click Upload

Make sure the COM port in the UI's Advanced Settings matches the one your Arduino is connected to.

---

## Config File

The config is stored at `~/.streamdeck/config.json` (shown in Advanced Settings → Config File). Both the UI and the Python daemon read/write this file. The UI polls for changes every 1.5 seconds so that profile switches triggered by the physical toggle button are reflected in real time.
