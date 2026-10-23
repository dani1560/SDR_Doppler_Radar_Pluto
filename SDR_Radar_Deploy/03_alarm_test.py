"""
Step 3 - Arduino alarm test (no Pluto needed).

Sends simulated passes to the Arduino Nano so you can check the buzzer and LED display:
  1. slow, far   -> quiet, slow beeps
  2. medium      -> louder, faster beeps
  3. fast, close -> loudest, highest pitch, fastest beeps
After each pass the LED display should hold that pass's speed.

Run:  python 03_alarm_test.py COM5
(Close the Arduino IDE Serial Monitor first.)
"""
import sys
import time
import serial

MAX_KMH = 60
PASSES = [            # (description, peak speed km/h, peak proximity %)
    ("slow and far", 15, 20),
    ("medium", 35, 60),
    ("fast and close", 70, 100),
]


def send(port, kmh, proximity, last):
    volume = min(max(kmh / MAX_KMH, 0.1), 1.0) * 100 if proximity > 0 else 0
    port.write(f"S{kmh:.1f},P{proximity:.0f},V{volume:.0f},L{last:.1f}\n".encode())


def main():
    if len(sys.argv) < 2:
        print("Usage: python 03_alarm_test.py COM5")
        sys.exit(1)

    port = serial.Serial(sys.argv[1], 115200, timeout=0)
    time.sleep(2)                       # Nano resets when the port opens (8888 + chirp)
    last = -1.0

    try:
        for desc, peak_kmh, peak_prox in PASSES:
            print(f"Pass: {desc} - up to {peak_kmh} km/h, proximity {peak_prox}%")
            for i in range(40):          # 2 s approach: proximity and speed ramp up
                f = (i + 1) / 40
                send(port, peak_kmh * (0.8 + 0.2 * f), peak_prox * f, last)
                time.sleep(0.05)
            last = float(peak_kmh)
            print(f"  passed -> display should hold {peak_kmh}")
            for _ in range(60):          # 3 s quiet: display holds last speed
                send(port, 0, 0, last)
                time.sleep(0.05)
        print("Done. Display should show", int(last))
    finally:
        port.close()


if __name__ == "__main__":
    main()
