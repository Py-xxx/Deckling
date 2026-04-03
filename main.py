"""
StreamDeck – Python daemon
Reads serial from Arduino → Voicemeeter Banana + keyboard shortcuts.
Config lives at ~/.streamdeck/config.json and is shared with the Tauri UI.
"""

import json
import os
import sys
import time
import tempfile
from pathlib import Path

import serial
import serial.tools.list_ports
import keyboard
import voicemeeterlib

# ================================================================
#  CONFIG PATH  (must match configStore.ts in the Tauri UI)
# ================================================================
CONFIG_DIR  = Path.home() / ".streamdeck"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "serial_port": "COM3",
    "active_profile": "Default",
    "display": {"grid_rows": 2, "grid_cols": 6, "num_pots": 4},
    "hardware": {
        "row_pins": [2, 3, 4, 5, 6, 7],
        "col_pins": [8, 9, 10, 11],
        "pot_pins": [0, 1, 2, 3],
    },
    "profile_toggle": {"button_id": -1, "mode": "hold", "hold_ms": 500},
    "profiles": {
        "Default": {
            "buttons": {
                "0":  {"label": "Mute Mic",    "action": "ctrl+alt+m"},
                "1":  {"label": "Screenshot",  "action": "ctrl+shift+s"},
                "2":  {"label": "Alt+Tab",     "action": "alt+tab"},
                "3":  {"label": "Copy",        "action": "ctrl+c"},
                "4":  {"label": "Paste",       "action": "ctrl+v"},
                "5":  {"label": "Vol Up",      "action": "volume up"},
                "6":  {"label": "Vol Down",    "action": "volume down"},
                "7":  {"label": "Play/Pause",  "action": "play/pause media"},
                "8":  {"label": "Next",        "action": "next track"},
                "9":  {"label": "Prev",        "action": "previous track"},
                "10": {"label": "Desktop",     "action": "win+d"},
                "11": {"label": "Explorer",    "action": "win+e"},
            },
            "pots": {
                "0": {"label": "HW Input 1", "strip": 0},
                "1": {"label": "HW Input 2", "strip": 1},
                "2": {"label": "Virtual 1",  "strip": 3},
                "3": {"label": "Virtual 2",  "strip": 4},
            },
        }
    },
}

# ================================================================
def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via a temp file (prevents half-writes)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)   # atomic on both POSIX and Windows (same drive)


def _ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        _atomic_write(CONFIG_PATH, DEFAULT_CONFIG)
        print(f"Created default config at {CONFIG_PATH}")


def _load_raw() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


# ================================================================
def raw_to_gain(raw: int) -> int:
    """Map ADC value (0–1023) → integer dB gain (-60 to +12), inverted."""
    return max(-60, min(12, round(((1023 - raw) / 1023.0) * 72 - 60)))


# ================================================================
class StreamDeck:
    def __init__(self) -> None:
        _ensure_config()
        self._config: dict        = {}
        self._config_mtime: float = 0.0
        self._last_sent: list     = [None] * 8   # one slot per pot (up to 8)
        self._btn_press_time: dict[int, float] = {}
        self._line_buf             = bytearray()
        self._ser: serial.Serial | None = None
        self._running              = False

        self._vm = voicemeeterlib.api("banana")
        self._vm.login()

        self._reload_config()

    # ------------------------------------------------------------------
    #  Config management
    # ------------------------------------------------------------------
    def _reload_config(self) -> None:
        try:
            self._config      = _load_raw()
            self._config_mtime = CONFIG_PATH.stat().st_mtime
            self._last_sent    = [None] * 8   # force re-sync after any config change
            print(f"  Config loaded. Active profile: '{self._config.get('active_profile')}'")
        except Exception as exc:
            print(f"  Config reload error: {exc}")

    def _check_reload(self) -> None:
        try:
            mtime = CONFIG_PATH.stat().st_mtime
            if mtime != self._config_mtime:
                self._reload_config()
        except Exception:
            pass

    @property
    def _profile(self) -> dict:
        name = self._config.get("active_profile", "Default")
        return self._config.get("profiles", {}).get(name, {"buttons": {}, "pots": {}})

    def _cycle_profile(self) -> None:
        profiles = sorted(self._config.get("profiles", {}).keys())
        if not profiles:
            return
        current = self._config.get("active_profile", profiles[0])
        idx = profiles.index(current) if current in profiles else 0
        next_name = profiles[(idx + 1) % len(profiles)]
        self._config["active_profile"] = next_name
        # Update mtime stamp so we don't re-trigger our own reload
        _atomic_write(CONFIG_PATH, self._config)
        self._config_mtime = CONFIG_PATH.stat().st_mtime
        self._last_sent    = [None] * 8
        print(f"  Profile → '{next_name}'")

    # ------------------------------------------------------------------
    #  Input handling
    # ------------------------------------------------------------------
    def _handle_pot(self, pot_id: int, raw: int) -> None:
        pot_cfg = self._profile.get("pots", {}).get(str(pot_id))
        if not pot_cfg:
            return
        strip_id = pot_cfg.get("strip", -1)
        if strip_id < 0:
            return
        gain = raw_to_gain(raw)
        if gain == self._last_sent[pot_id]:
            return
        try:
            self._vm.strip[strip_id].gain = float(gain)
            self._last_sent[pot_id] = gain
        except Exception as exc:
            print(f"  VM error strip[{strip_id}]: {exc}")

    def _handle_button(self, btn_id: int, val: int) -> None:
        toggle_cfg  = self._config.get("profile_toggle", {})
        toggle_btn  = toggle_cfg.get("button_id", -1)
        toggle_mode = toggle_cfg.get("mode", "hold")
        hold_ms     = toggle_cfg.get("hold_ms", 500)

        # Profile toggle button
        if toggle_btn >= 0 and btn_id == toggle_btn:
            if val == 1:                                    # press
                self._btn_press_time[btn_id] = time.monotonic()
                if toggle_mode == "tap":
                    self._cycle_profile()
            elif val == 0 and toggle_mode == "hold":        # release (hold mode)
                elapsed_ms = (time.monotonic() - self._btn_press_time.get(btn_id, 0)) * 1000
                if elapsed_ms >= hold_ms:
                    self._cycle_profile()
            return   # toggle button never fires a keybind

        # Normal button — only act on press
        if val != 1:
            return
        action = self._profile.get("buttons", {}).get(str(btn_id), {}).get("action", "")
        if action:
            keyboard.send(action)

    def _process_line(self, line: str) -> None:
        if len(line) < 3:
            return
        try:
            colon = line.index(":")
            kind  = line[0]
            id_   = int(line[1:colon])
            val   = int(line[colon + 1:])
        except (ValueError, IndexError):
            return
        if kind == "P":
            self._handle_pot(id_, val)
        elif kind == "B":
            self._handle_button(id_, val)

    # ------------------------------------------------------------------
    #  Serial I/O
    # ------------------------------------------------------------------
    def _read_available(self) -> None:
        waiting = self._ser.in_waiting
        if not waiting:
            return
        self._line_buf.extend(self._ser.read(waiting))
        while b"\n" in self._line_buf:
            idx  = self._line_buf.index(b"\n")
            line = self._line_buf[:idx].decode("ascii", errors="ignore").strip()
            del self._line_buf[:idx + 1]
            self._process_line(line)

    def _open_serial(self, port: str) -> bool:
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            s          = serial.Serial()
            s.port     = port
            s.baudrate = 115200
            s.timeout  = 0        # non-blocking — we poll in_waiting
            s.dsrdtr   = False    # don't toggle DTR (prevents Arduino auto-reset)
            s.rtscts   = False
            s.open()
            time.sleep(2.0)       # wait for Arduino sketch to start
            s.reset_input_buffer()
            self._line_buf.clear()
            self._ser = s
            return True
        except (serial.SerialException, OSError) as exc:
            print(f"  Cannot open {port}: {exc}")
            return False

    def _wait_for_connection(self) -> None:
        port = self._config.get("serial_port", "COM3")
        while True:
            if self._open_serial(port):
                self._last_sent = [None] * 8
                print(f"Connected on {self._ser.port}.")
                return
            for p in serial.tools.list_ports.comports():
                desc = (p.description or "").lower()
                mfr  = (p.manufacturer or "").lower()
                if any(k in desc or k in mfr for k in ("arduino", "ch340", "cp210", "ftdi")):
                    if self._open_serial(p.device):
                        self._last_sent = [None] * 8
                        print(f"Auto-detected on {p.device}.")
                        return
            time.sleep(2.0)

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        print(f"Config: {CONFIG_PATH}")
        print("Waiting for Arduino…")
        self._wait_for_connection()
        print("Voicemeeter Banana ready. Press Ctrl+C to exit.\n")

        self._running    = True
        reload_countdown = 0

        try:
            while self._running:
                # Config reload check every ~200 ticks = ~1s
                reload_countdown += 1
                if reload_countdown >= 200:
                    self._check_reload()
                    reload_countdown = 0

                try:
                    self._read_available()
                except (serial.SerialException, OSError) as exc:
                    print(f"Serial error: {exc}\nWaiting for Arduino…")
                    self._wait_for_connection()
                    print("Resumed.")
                    continue

                time.sleep(0.005)

        except KeyboardInterrupt:
            print("\nShutting down…")
        finally:
            self._running = False
            self._vm.logout()
            if self._ser and self._ser.is_open:
                self._ser.close()
            print("Disconnected cleanly.")


# ================================================================
if __name__ == "__main__":
    StreamDeck().run()
