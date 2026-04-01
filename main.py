"""
StreamDeck – host-side controller
Reads serial from Arduino → Voicemeeter Banana gain + keyboard shortcuts.
"""

import sys
import time
import serial
import serial.tools.list_ports
import keyboard
import voicemeeterlib

# ================================================================
#  CONFIG
# ================================================================
SERIAL_PORT = "COM3"        # change to match your Arduino's port
BAUD_RATE   = 115200
SERIAL_TIMEOUT = 0.05       # seconds — short so the VM push-loop stays timely

# Voicemeeter Banana gain range (dB)
GAIN_MIN   = -60.0
GAIN_MAX   =  12.0
GAIN_RANGE = GAIN_MAX - GAIN_MIN   # 72.0

# How often (seconds) we actually push a pending gain to Voicemeeter.
# Voicemeeter's IPC can get overwhelmed if called hundreds of times per
# second — rate-limiting to 30 Hz gives perfectly smooth fader movement
# without spamming the API.
VM_PUSH_INTERVAL = 1.0 / 30   # ~33 ms

RECONNECT_ATTEMPTS = 30
RECONNECT_DELAY_S  = 2.0

# ================================================================
#  BUTTON MAP
# ================================================================
BUTTON_ACTIONS: dict[int, str] = {
    0:  "ctrl+alt+m",       # mute mic
    1:  "ctrl+shift+s",
    2:  "alt+tab",
    3:  "ctrl+c",
    4:  "ctrl+v",
    5:  "volume up",
    6:  "volume down",
    7:  "play/pause media",
    8:  "next track",
    9:  "previous track",
    10: "win+d",            # show desktop
    11: "win+e",            # file explorer
    12: "win+r",            # run dialog
    13: "ctrl+z",
    14: "ctrl+y",
    15: "f1",
    16: "f2",
    17: "f3",
    18: "f4",
    19: "f5",
}

# ================================================================
#  HELPERS
# ================================================================
def raw_to_gain(raw: int) -> float:
    """Map Arduino ADC value (0–1023) to Voicemeeter gain (-60 to +12 dB)."""
    return (raw / 1023.0) * GAIN_RANGE + GAIN_MIN


def find_arduino_port() -> str | None:
    """
    Scan connected serial ports for a likely Arduino.
    Falls back to SERIAL_PORT if none found.
    """
    for port in serial.tools.list_ports.comports():
        desc = (port.description or "").lower()
        mfr  = (port.manufacturer or "").lower()
        if "arduino" in desc or "arduino" in mfr or "ch340" in desc or "cp210" in desc:
            return port.device
    return None


# ================================================================
#  MAIN CLASS
# ================================================================
class StreamDeck:
    def __init__(self) -> None:
        self._ser: serial.Serial | None = None
        self._vm = voicemeeterlib.api("banana")
        self._vm.login()

        # Rate-limited pot updates:
        #   _pending_gain[i]  – latest target received from serial (None = no update)
        #   _last_push[i]     – monotonic time of last VM API call for this channel
        self._pending_gain: list[float | None] = [None] * 4
        self._last_push:    list[float]         = [0.0]  * 4

        self._running = False

    # ------------------------------------------------------------------
    def _open_serial(self, port: str) -> bool:
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(
                port, BAUD_RATE,
                timeout=SERIAL_TIMEOUT,
                write_timeout=0,
            )
            return True
        except serial.SerialException as exc:
            print(f"  Serial open failed on {port}: {exc}")
            return False

    def _connect(self) -> bool:
        """
        Try the configured port first.  If that fails, scan for an Arduino.
        Returns True once connected.
        """
        if self._open_serial(SERIAL_PORT):
            return True

        found = find_arduino_port()
        if found:
            print(f"  Found device on {found}, trying that instead…")
            if self._open_serial(found):
                return True

        return False

    def _reconnect(self) -> bool:
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            print(f"Reconnecting ({attempt}/{RECONNECT_ATTEMPTS})…")
            if self._connect():
                print("Reconnected.")
                return True
            time.sleep(RECONNECT_DELAY_S)
        return False

    # ------------------------------------------------------------------
    def _push_pending_gains(self) -> None:
        """
        Push each channel's latest pending gain to Voicemeeter, but only
        if enough time has elapsed since the last push for that channel.
        This keeps the VM IPC healthy and the faders silky smooth.
        """
        now = time.monotonic()
        for i in range(4):
            if self._pending_gain[i] is None:
                continue
            if now - self._last_push[i] >= VM_PUSH_INTERVAL:
                self._vm.strip[i].gain = round(self._pending_gain[i], 1)
                self._last_push[i]     = now
                self._pending_gain[i]  = None   # consumed; next serial msg will refill

    def _handle_pot(self, pot_id: int, raw: int) -> None:
        if 0 <= pot_id <= 3:
            # Just record the latest target — _push_pending_gains() applies it
            self._pending_gain[pot_id] = raw_to_gain(raw)

    def _handle_button(self, btn_id: int) -> None:
        action = BUTTON_ACTIONS.get(btn_id)
        if action:
            keyboard.send(action)

    # ------------------------------------------------------------------
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
        elif kind == "B" and val == 1:
            self._handle_button(id_)

    # ------------------------------------------------------------------
    def run(self) -> None:
        print("Waiting for Arduino…")
        while not self._connect():
            print(f"  Could not open {SERIAL_PORT}. Retrying in {RECONNECT_DELAY_S}s…")
            time.sleep(RECONNECT_DELAY_S)

        print(f"Connected to {self._ser.port} at {BAUD_RATE} baud.")
        print("Voicemeeter Banana ready.  Press Ctrl+C to exit.\n")

        self._running = True
        try:
            while self._running:
                # --- Read serial (non-blocking with short timeout) ---
                try:
                    raw = self._ser.readline()
                except serial.SerialException as exc:
                    print(f"\nSerial error: {exc}")
                    if not self._reconnect():
                        print("Could not reconnect. Exiting.")
                        break
                    continue

                if raw:
                    line = raw.decode("ascii", errors="ignore").strip()
                    self._process_line(line)

                # --- Push rate-limited gains every ~33 ms ---
                self._push_pending_gains()

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
