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
SERIAL_PORT = "COM3"
BAUD_RATE   = 115200

# Voicemeeter Banana gain range (dB)
GAIN_MIN   = -60.0
GAIN_MAX   =  12.0
GAIN_RANGE = GAIN_MAX - GAIN_MIN   # 72.0

# Max rate we push pot values to Voicemeeter (Hz).
# Flooding the IPC any faster doesn't improve smoothness and causes drops.
VM_PUSH_HZ       = 60
VM_PUSH_INTERVAL = 1.0 / VM_PUSH_HZ   # ~16.6 ms

RECONNECT_ATTEMPTS = 30
RECONNECT_DELAY_S  = 2.0

# ================================================================
#  BUTTON MAP
# ================================================================
BUTTON_ACTIONS: dict[int, str] = {
    0:  "ctrl+alt+m",
    1:  "ctrl+shift+s",
    2:  "alt+tab",
    3:  "ctrl+c",
    4:  "ctrl+v",
    5:  "volume up",
    6:  "volume down",
    7:  "play/pause media",
    8:  "next track",
    9:  "previous track",
    10: "win+d",
    11: "win+e",
    12: "win+r",
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
    return (raw / 1023.0) * GAIN_RANGE + GAIN_MIN


def find_arduino_port() -> str | None:
    for port in serial.tools.list_ports.comports():
        desc = (port.description or "").lower()
        mfr  = (port.manufacturer or "").lower()
        if any(k in desc or k in mfr for k in ("arduino", "ch340", "cp210", "ftdi")):
            return port.device
    return None


# ================================================================
class StreamDeck:
    def __init__(self) -> None:
        self._ser: serial.Serial | None = None
        self._vm = voicemeeterlib.api("banana")
        self._vm.login()

        # Latest gain target per channel (None = no pending update)
        self._pending_gain: list[float | None] = [None] * 4
        # Timestamp of last VM push per channel
        self._last_push: list[float] = [0.0] * 4

        self._running  = False
        self._line_buf = bytearray()

    # ------------------------------------------------------------------
    def _open_serial(self, port: str) -> bool:
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(
                port, BAUD_RATE,
                timeout=0,           # non-blocking reads — we poll in_waiting ourselves
                write_timeout=0,
                dsrdtr=False,        # do NOT toggle DTR on open → stops Arduino resetting
                rtscts=False,        # no hardware flow control
            )
            # Let the Arduino (and Windows USB stack) finish initialising.
            # Without this, the first read may catch mid-bootloader garbage.
            time.sleep(1.5)
            self._ser.reset_input_buffer()
            self._line_buf.clear()
            return True
        except (serial.SerialException, OSError) as exc:
            print(f"  Serial open failed on {port}: {exc}")
            return False

    def _connect(self) -> bool:
        if self._open_serial(SERIAL_PORT):
            return True
        found = find_arduino_port()
        if found:
            print(f"  Trying auto-detected port {found}…")
            if self._open_serial(found):
                return True
        return False

    def _reconnect(self) -> bool:
        # Brief pause so Windows fully releases the handle before we retry
        time.sleep(0.5)
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            print(f"Reconnecting ({attempt}/{RECONNECT_ATTEMPTS})…")
            if self._connect():
                print("Reconnected.")
                return True
            time.sleep(RECONNECT_DELAY_S)
        return False

    # ------------------------------------------------------------------
    def _push_pending_gains(self) -> None:
        now = time.monotonic()
        for i in range(4):
            if self._pending_gain[i] is None:
                continue
            if now - self._last_push[i] >= VM_PUSH_INTERVAL:
                self._vm.strip[i].gain = round(self._pending_gain[i], 1)
                self._last_push[i]    = now
                self._pending_gain[i] = None

    def _handle_pot(self, pot_id: int, raw: int) -> None:
        if 0 <= pot_id <= 3:
            self._pending_gain[pot_id] = raw_to_gain(raw)

    def _handle_button(self, btn_id: int) -> None:
        action = BUTTON_ACTIONS.get(btn_id)
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
        elif kind == "B" and val == 1:
            self._handle_button(id_)

    # ------------------------------------------------------------------
    def _read_available(self) -> None:
        """
        Drain whatever bytes are waiting in the serial buffer right now.
        Using in_waiting + non-blocking read avoids ever holding a pending
        Windows async read operation open — that's what caused the
        GetOverlappedResults / PermissionError 13 crash.
        """
        waiting = self._ser.in_waiting
        if not waiting:
            return

        chunk = self._ser.read(waiting)
        self._line_buf.extend(chunk)

        # Parse out complete lines
        while b"\n" in self._line_buf:
            idx  = self._line_buf.index(b"\n")
            line = self._line_buf[:idx].decode("ascii", errors="ignore").strip()
            del self._line_buf[:idx + 1]
            self._process_line(line)

    # ------------------------------------------------------------------
    def run(self) -> None:
        print("Waiting for Arduino…")
        while not self._connect():
            print(f"  {SERIAL_PORT} not available, retrying in {RECONNECT_DELAY_S}s…")
            time.sleep(RECONNECT_DELAY_S)

        print(f"Connected to {self._ser.port} at {BAUD_RATE} baud.")
        print("Voicemeeter Banana ready.  Press Ctrl+C to exit.\n")

        self._running = True
        try:
            while self._running:
                try:
                    self._read_available()
                except (serial.SerialException, OSError) as exc:
                    print(f"\nSerial error: {exc}")
                    if not self._reconnect():
                        print("Could not reconnect. Exiting.")
                        break
                    continue

                self._push_pending_gains()

                # Without a sleep here the loop would spin at 100% CPU when
                # the pot is idle. 5 ms is short enough to not affect latency.
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
