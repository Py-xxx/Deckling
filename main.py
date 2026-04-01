"""
StreamDeck – host-side controller
Reads serial from Arduino, maps potentiometers → Voicemeeter Banana gain
and buttons → keyboard shortcuts.
"""

import sys
import time
import serial
import keyboard
import voicemeeterlib

# ================================================================
#  CONFIG  –  edit these to suit your setup
# ================================================================
SERIAL_PORT = "COM3"
BAUD_RATE   = 115200
SERIAL_TIMEOUT = 0.1        # seconds; keeps shutdown responsive

# Voicemeeter Banana gain range (dB)
GAIN_MIN   = -60.0
GAIN_MAX   =  12.0
GAIN_RANGE = GAIN_MAX - GAIN_MIN   # 72.0

# Minimum gain change (dB) before pushing to Voicemeeter — avoids
# redundant IPC calls when the pot is resting on the noise floor.
DEAD_ZONE  = 0.15

# Reconnect behaviour
RECONNECT_ATTEMPTS = 20
RECONNECT_DELAY_S  =  2.0

# ================================================================
#  BUTTON MAP  –  btn_id → action
# ================================================================
BUTTON_ACTIONS: dict[int, str] = {
    0:  "ctrl+alt+m",          # mute mic
    1:  "ctrl+shift+s",
    2:  "alt+tab",
    3:  "ctrl+c",
    4:  "ctrl+v",
    5:  "volume up",
    6:  "volume down",
    7:  "play/pause media",
    8:  "next track",
    9:  "previous track",
    10: "win+d",               # show desktop
    11: "win+e",               # file explorer
    12: "win+r",               # run dialog
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


# ================================================================
#  MAIN CLASS
# ================================================================
class StreamDeck:
    def __init__(self) -> None:
        self._ser: serial.Serial | None = None
        self._vm  = voicemeeterlib.api("banana")
        self._vm.login()

        # Track last-sent gain per strip to skip redundant IPC calls
        self._last_gain: list[float | None] = [None, None, None, None]

        self._running = False

    # ------------------------------------------------------------------
    def _open_serial(self) -> bool:
        """Open (or re-open) the serial port. Returns True on success."""
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(
                SERIAL_PORT, BAUD_RATE,
                timeout=SERIAL_TIMEOUT,
                write_timeout=0,
            )
            return True
        except serial.SerialException as exc:
            print(f"  Serial open failed: {exc}")
            return False

    def _reconnect(self) -> bool:
        """Try to reconnect. Returns True if successful."""
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            print(f"Reconnecting ({attempt}/{RECONNECT_ATTEMPTS})…")
            if self._open_serial():
                print("Reconnected.")
                return True
            time.sleep(RECONNECT_DELAY_S)
        return False

    # ------------------------------------------------------------------
    def _handle_pot(self, pot_id: int, raw: int) -> None:
        if not (0 <= pot_id <= 3):
            return

        gain = raw_to_gain(raw)
        last = self._last_gain[pot_id]

        if last is None or abs(gain - last) > DEAD_ZONE:
            self._vm.strip[pot_id].gain = round(gain, 1)
            self._last_gain[pot_id] = gain

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
            return   # malformed — ignore silently

        if kind == "P":
            self._handle_pot(id_, val)
        elif kind == "B" and val == 1:
            self._handle_button(id_)

    # ------------------------------------------------------------------
    def run(self) -> None:
        if not self._open_serial():
            print(f"Could not open {SERIAL_PORT}. Exiting.")
            self._vm.logout()
            sys.exit(1)

        print(f"Connected to {SERIAL_PORT} at {BAUD_RATE} baud.")
        print("Voicemeeter Banana ready.  Press Ctrl+C to exit.\n")

        self._running = True

        try:
            while self._running:
                try:
                    raw = self._ser.readline()
                except serial.SerialException as exc:
                    print(f"\nSerial error: {exc}")
                    if not self._reconnect():
                        print("Could not reconnect. Exiting.")
                        break
                    continue

                if not raw:
                    continue   # timeout — loop again

                line = raw.decode("ascii", errors="ignore").strip()
                self._process_line(line)

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
