# SDR Doppler Radar with Speed Alarm

CW Doppler radar on an ADALM-PLUTO SDR at 2.482 GHz. Measures target speed in km/h and sounds an alarm:
louder and higher-pitched for faster targets, faster beeps for closer (stronger) echoes.

It works like a street speed camera: each pass's **peak speed** (one decimal on screen, e.g. `45.3`; whole km/h on this LED module) stays on the
laptop screen and on the Arduino LED display until the next pass. A pass faster than the **speed limit** is
**captured**: shown in red on screen, blinking on the LED, and marked `captured=yes` in `speed_log.csv`
(date, time, speed, direction, limit, captured). The screen also shows the session's capture count and top speed.

## Quick start

1. Plug the Pluto into its **middle** micro-USB port (USB symbol). Plug in the Arduino Nano (optional).
2. Double-click **`START_RADAR.bat`**.
3. The radar starts by itself. Close the plot window to stop.

`START_RADAR.bat` checks Python, installs the Python packages, installs the Pluto drivers if libiio is
missing, finds the Pluto and the Arduino's COM port, and starts the radar with speed limit **50 km/h**.
To change the limit, edit `set "LIMIT=50"` near the top of `START_RADAR.bat` (use 10 for walking tests).

**`TOOLS.bat`** opens a menu for tests and setup:

| Option | What it does |
|---|---|
| 1 | Radar, captures passes over 10 km/h (bench tests, walking, jogging) |
| 2 | Radar, captures passes over 50 km/h (cars); alarm loudest at 60 km/h |
| 3 | Pluto test: peak at +100 kHz means TX and RX work |
| 4 | Arduino display/buzzer test with simulated passes (no Pluto needed) |
| 5 | Upload `speed_alarm.ino` to the Nano (needs Arduino IDE 2 installed) |
| 6 | Install the Pluto USB driver and libiio (first time on a new laptop) |
| 7 | Open `speed_log.csv` |

The radar always uses the laptop speaker as the alarm; when an Arduino is found it also drives the LED display
and buzzer.

## Folder contents

| File | Purpose |
|---|---|
| `START_RADAR.bat` | One-click setup and radar start |
| `TOOLS.bat` | Menu: tests, walking mode, Arduino upload, drivers, speed log |
| `DEPLOY.md` | Step-by-step setup on another laptop |
| `02_doppler_radar.py` | Main radar program (spectrum, speed display, alarm) |
| `01_pluto_test.py` | Hardware check: shows a peak at +100 kHz if TX and RX work |
| `03_alarm_test.py` | Arduino check without the Pluto: `python 03_alarm_test.py auto` (or `COM9`) |
| `arduino_port.py` | Finds the Nano's COM port (CH340 / FTDI / Arduino) |
| `speed_alarm/speed_alarm.ino` | Arduino Nano buzzer alarm + TM1637 LED speed display |
| `speed_log.csv` | Created on first pass: one row per measured pass |
| `requirements.txt` | Python packages |
| `drivers/` | PlutoSDR USB driver and libiio v0.26 installers (Windows) |
| `pluto_recovery/` | Firmware v0.39 files for updating or recovering the Pluto |

## Setup on a new Windows laptop

1. Install **Python 3.10 or newer** from python.org. Tick **"Add Python to PATH"**.
2. Double-click `START_RADAR.bat`. If libiio is missing it runs the two installers in `drivers/`
   (unplug the Pluto first and accept the admin prompts). You can also run them yourself:
   `drivers\PlutoSDR-M2k-USB-Drivers.exe`, then `drivers\libiio-0.26.ga0eca0d2-setup.exe`.
   Use libiio **v0.26**, not v1.x: the Python package is pinned to `pylibiio==0.25` to match it.
3. Plug the Pluto into its **middle** micro-USB port. Wait about 30 s: the Ready LED comes on and a
   `PlutoSDR` drive appears. The launcher then shows `PlutoSDR : connected` and starts the radar.

## Antennas

```
Pluto Tx -- 2.4 GHz dipole (upright)
Pluto Rx -- SMA extension cable (0.5-1 m) -- 2.4 GHz dipole (upright)
```

- The antennas must be **SMA male** (centre pin). Router antennas are often **RP-SMA** (hole, no pin):
  they screw on but make no contact. Use an RP-SMA-female to SMA-male adapter for those.
- The U.FL pigtails that come with router antennas are not needed.
- About 0.5 m between the antennas reduces TX leakage into RX. Without the extension cable the radar
  still works, with less range; bend the antennas apart and lower `--rx-gain` if `CLIPPING` shows.
- The radar measures **radial** speed (along the line of sight). A target moving at an angle reads low
  by cos(angle), so aim along the target's path.

## Arduino buzzer + LED display (optional)

Parts: Arduino Nano, TM1637 4-digit display, **passive** buzzer (an active buzzer has a fixed pitch),
NPN transistor 2N2222 or BC547, 1 kOhm resistor, 1N4148/1N4007 diode, breadboard, jumper wires.

Put the Nano across the breadboard's middle gap (one pin row on each side). Wiring:

```
TM1637:   CLK --> D2          (follow the labels on your module;
          DIO --> D3           the pin order varies, e.g. CLK DIO GND 5V)
          5V  --> 5V
          GND --> GND

Buzzer:   Nano D9 --[1k]--> NPN base           (buzzer must be on D9: Timer1 hardware PWM)
          NPN emitter --> GND
          NPN collector --> buzzer (-)  and diode anode
          buzzer (+)    --> 5V          and diode cathode (stripe)
```

NPN pins, flat face toward you, legs down: **2N2222 = E B C**, **BC547 = C B E** (reversed).

The display shows the live speed during a pass, then holds the pass's peak speed; it
blinks if that pass was captured (over the limit). `----` means no pass yet.
This 0.56" TM1637 module has only a colon and no decimal points, so it shows **whole km/h** (`  45`);
the screen and `speed_log.csv` keep one decimal. For a decimal point on the LED, use a TM1637 module
**with decimal points** (same wiring) and set `HAS_DOTS = true` in `speed_alarm.ino` (shows `45.3`).

Without a buzzer everything else works; the Nano's on-board LED blinks with the beeps.

Upload the sketch with `TOOLS.bat` option **5**, or in Arduino IDE:

1. For clone Nanos (USB-SERIAL CH340), install the CH340 driver if no COM port appears.
2. Tools -> Manage Libraries -> install **"TM1637" by Avishay Orpaz**.
3. Open `speed_alarm/speed_alarm.ino`. Board: **Arduino Nano**; for clones, Processor:
   **ATmega328P (Old Bootloader)** (fixes `not in sync`).
4. Upload. The display shows `88:88` and the buzzer chirps (wiring OK), then `----`.
5. Close the Arduino IDE before running the radar (it keeps the COM port busy).

## Command-line options

```
python 02_doppler_radar.py [--max-kmh 60] [--limit 50] [--port COM9 | --port auto] [--no-sound] [--rx-gain 30] [--tx-gain -10]
```

| Option | Meaning |
|---|---|
| `--max-kmh` | Speed at which the alarm is loudest. Use 10 indoors, 60+ for cars |
| `--limit` | Speed limit in km/h: faster passes are captured (default: same as `--max-kmh`) |
| `--port` | Arduino COM port, or `auto`; sends `S<kmh>,P<proximity>,V<volume>,L<last kmh>,F<captured>` lines at 115200 baud |
| `--no-sound` | Turn off the laptop-speaker alarm |
| `--rx-gain` | RX gain, 0..70 dB. Lower it if the screen shows `CLIPPING` |
| `--tx-gain` | TX attenuation, 0 (max power) to -89 dB |

On exit (window closed, Ctrl+C, console closed or a startup error) the program destroys the TX buffer
and sets TX attenuation to -89 dB, so the Pluto stops transmitting.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `DATA LOST: computer too slow` | Plug in the charger (on battery Windows slows the CPU) and close other programs |
| Wrong or jumping speeds with several people in view | The radar reports the strongest echo; test with one moving person or vehicle at a time |
| `CLIPPING` on screen | Lower `--rx-gain` (e.g. 20), or separate the TX and RX antennas |
| False targets with no one moving | Turn off ceiling fans; point the antennas away from moving objects |
| Noisy spectrum | Wi-Fi interference. 2.482 GHz sits at the upper edge of Wi-Fi channel 13; change `CENTER_FREQ` if needed |
| `PlutoSDR : NOT FOUND` / `Open unlocked: -16` | Another radar window is still running, or the Pluto is in the power port. Close other windows, use the middle port |
| `Cannot open Arduino port` / `Access is denied` | Close the Arduino IDE / Serial Monitor |
| Upload `not in sync` | Processor: ATmega328P (Old Bootloader) |
| No `PlutoSDR` drive, Ready LED off, LED1 on | Firmware stuck. Hold button **S1** inside the case (next to the data USB port) while plugging in, then flash with `dfu-util` from the driver install folder: `dfu-util -a boot.dfu -D boot.dfu`, `dfu-util -a uboot-env.dfu -D uboot-env.dfu`, `dfu-util -a firmware.dfu -D pluto.dfu` (files in `pluto_recovery/`) |
| Firmware update (Pluto working) | Copy `pluto_recovery/pluto.frm` to the `PlutoSDR` drive, eject it, wait until LED1 stops blinking |

## Radar parameters

| Parameter | Value |
|---|---|
| Carrier | 2.482 GHz (top of the 2.4 GHz ISM band) |
| Waveform | CW tone at +100 kHz offset |
| Sample rate | 1 MS/s, decimated to 8 kS/s |
| FFT | 4096 points (0.5 s), ~1.95 Hz bins (0.42 km/h); parabolic peak interpolation gives 0.1 km/h readout |
| Speed range | about 3.3 to 218 km/h, approaching and receding |
| Clutter rejection | Mirror-peak test (fans) plus 2-frame confirmation |
| Update rate | 64 ms per frame processed; window redrawn every 0.25 s so the loop keeps up on battery |
| Clutter map | Learns the background (Pluto spurs, static clutter) for ~2.5 s at start-up; screen shows `learning background` |
