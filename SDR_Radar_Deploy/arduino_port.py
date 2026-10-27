"""Find the Arduino Nano's COM port (CH340 clones, FTDI and genuine Arduino boards)."""
from serial.tools import list_ports

ARDUINO_IDS = ("CH340", "CH341", "FTDI", "FT232", "ARDUINO", "USB-SERIAL", "USB SERIAL")


def find_arduino_port():
    """Return the first COM port that looks like an Arduino, or None."""
    for p in list_ports.comports():
        text = f"{p.description} {p.manufacturer or ''}".upper()
        if "PLUTO" not in text and any(k in text for k in ARDUINO_IDS):
            return p.device
    return None


if __name__ == "__main__":
    print(find_arduino_port() or "")
