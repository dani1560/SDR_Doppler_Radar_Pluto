# SDR Doppler Radar with Speed Alarm

CW Doppler radar on an ADALM-PLUTO SDR at 2.482 GHz, built in **GNU Radio** (main version) with a
Python version as backup. Measures target speed in km/h and sounds an alarm: louder and higher-pitched
for faster targets, faster beeps for closer (stronger) echoes. Frequency and maximum speed are adjustable.

It works like a street speed camera: each pass's **peak speed** (one decimal on screen, e.g. `45.3`; whole km/h on this LED module) stays on the
laptop screen and on the Arduino LED display until the next pass. A pass faster than the **speed limit** is
**captured**: shown in red on screen, blinking on the LED, and marked `captured=yes` in `speed_log.csv`
(date, time, speed, direction, limit, captured). The screen also shows the session's capture count and top speed.

## Quick start

1. Plug the Pluto into its **middle** micro-USB port (USB symbol). Plug in the Arduino Nano (optional).
2. Double-click **`START_GNURADIO.bat`** (GNU Radio version, main demo).
3. Stand still for 3 s while it learns the background. Close the window to stop (TX is muted automatically).

| File | What it does |
|---|---|
| **`START_GNURADIO.bat`** | Runs the GNU Radio radar (needs radioconda, see `DEPLOY.md`) |
| `EDIT_GNURADIO.bat` | Opens `gnuradio/doppler_radar.grc` in GNU Radio Companion (block diagram) |
| `START_RADAR.bat` | Runs the Python version (backup, no GNU Radio needed) |
| `TOOLS.bat` | Optional: tests, Arduino upload, driver install, speed log |

## GNU Radio version

```
Signal Source (100 kHz tone) --> PlutoSDR Sink (TX, fc)
PlutoSDR Source (RX, fc) --> Frequency Xlating FIR (tone -> 0 Hz, /25) --> FIR Filter (/5, 8 kS/s)
    --> Doppler Speed Camera (embedded Python block) --> live / last speed labels, Arduino, speed_log.csv
    --> QT GUI Frequency Sink (Doppler spectrum) and Waterfall
```

Sliders in the window (they act immediately, no restart):

| Slider | Range | Notes |
|---|---|---|
| Frequency (MHz) | 2400-2483 | The 2.4 GHz antennas and the licence-free band limit it to this range. Changing it re-learns the background (~3 s) |
| Max speed (km/h) | 10-740 | Highest speed searched. The limit is ~740 km/h at 2.48 GHz (3.4 kHz Doppler) |
| Speed limit (km/h) | 5-300 | Passes faster than this are CAPTURED (logged, blinking on the LED) |
| TX attenuation (dB) | 0-89 | Higher = less power = shorter range. Range changes by x1.8 per 10 dB |
| Min signal (dB) | 10-50 | Signal a target needs above the noise. Higher = only closer targets (x0.56 range per +10 dB) |
| RX gain (dB) | 0-70 | Keep as high as possible without `!! CLIPPING` in the LIVE SPEED line |

**Default settings (toy car / indoor):** TX attenuation 20 dB, RX gain 30 dB, Min signal 15 dB,
Max speed 50 km/h, Speed limit 10 km/h. With these, a 90 s room test gave no false detections and caught a
toy car driven straight at the antennas (3-17 km/h, signal up to 47 dB). Earlier measurement (TX attenuation 30): with nobody moving the strongest signal was
19 dB (no false detections); a walking person gave 24-47 dB (median 33 dB) and was detected in every
5-second window of movement. To fine-tune: raise Min signal by 5 dB for a shorter range (closer targets
only), lower it to 15 for a longer range. Speed accuracy is the same at every setting.

**Long range (cars, outdoors):** TX attenuation 10, Min signal 15, Max speed 220, Speed limit 50.
Maximum power: TX attenuation 0 with RX gain 20 (RX gain 30 clips).

The **Doppler Speed Camera** block (`gnuradio/doppler_camera_block.py`) uses `doppler_core.py`, the same
detector as the Python version: clutter map, mirror test, sub-bin peak, pass tracking and capture. The two
versions therefore give identical speeds. The spectrum display is in Hz: km/h = Hz x c / (2 fc) x 3.6
(at 2482 MHz, 1 Hz = 0.2176 km/h).

## Python version

`START_RADAR.bat` checks Python, installs the Python packages, installs the Pluto drivers if libiio is
missing, finds the Pluto and the Arduino's COM port, and starts the radar with speed limit **50 km/h**.
The same short-range defaults apply. To change them, edit `LIMIT`, `MAXKMH`, `FREQ_MHZ`, `MAX_SPEED`,
`TX_GAIN` and `MIN_SIGNAL` near the top of `START_RADAR.bat` (cars: `LIMIT=50`, `MAXKMH=60`,
`MAX_SPEED=220`, `TX_GAIN=-10`, `MIN_SIGNAL=15`).

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
| `START_GNURADIO.bat` | Runs the GNU Radio radar |
| `EDIT_GNURADIO.bat` | Opens the flowgraph in GNU Radio Companion |
| `gnuradio/doppler_radar.grc` | GNU Radio flowgraph (Pluto TX/RX, filters, displays, sliders) |
| `gnuradio/doppler_camera_block.py` | Source of the flowgraph's "Doppler Speed Camera" block |
| `doppler_core.py` | Detection, speed, pass tracking and logging shared by both versions |
| `START_RADAR.bat` | One-click setup and Python radar start |
| `TOOLS.bat` | Menu: tests, walking mode, Arduino upload, drivers, speed log |
| `DEPLOY.md` | Step-by-step setup on another laptop |
| `02_doppler_radar.py` | Python radar program (spectrum, speed display, laptop-speaker alarm) |
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

Buzzer, choose one (D9 and D10 are fixed: Timer1 outputs; D10 is the inverse of D9):
  A) piezo, loudest without parts:   buzzer between D9 and D10   (10 V swing)
  B) simplest:                       buzzer between D9 and GND
  C) magnetic buzzer / 9 V supply:   Nano D9 --[1k]--> NPN base (BC547 middle leg)
                                     NPN emitter   --> GND
                                     NPN collector --> buzzer (-)  and diode anode
                                     buzzer (+)    --> 5 V or 9 V  and diode cathode (stripe)
     With a piezo in C), put a 1 kOhm resistor across the buzzer. With 9 V, join the battery (-) to GND.
```

The buzzer always plays at full volume (50 % square wave). Its pitch rises with speed (1.8-3.6 kHz,
where a passive buzzer is loudest) and it beeps faster for a closer target.

NPN pins, flat face toward you, legs down: **2N2222 = E B C**, **BC547 = C B E** (reversed).

The display shows the live speed during a pass, then holds the pass's peak speed. Every new captured
speed blinks for 5 s and then stays steady; a pass over the speed limit keeps blinking. After a restart
the display shows the last pass from `speed_log.csv`. `----` means no pass yet.
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
python 02_doppler_radar.py [--max-kmh 60] [--limit 50] [--freq-mhz 2482] [--max-speed 220] [--port COM9 | --port auto] [--no-sound] [--rx-gain 30] [--tx-gain -10]
```

| Option | Meaning |
|---|---|
| `--max-kmh` | Speed at which the alarm is loudest. Use 10 indoors, 60+ for cars |
| `--limit` | Speed limit in km/h: faster passes are captured (default: same as `--max-kmh`) |
| `--freq-mhz` | Carrier frequency, 325..3800 MHz (use 2400-2483 with the 2.4 GHz antennas) |
| `--max-speed` | Highest speed searched in km/h (default 50, up to ~740 at 2482 MHz) |
| `--min-signal` | Min target signal in dB (default 35 = close targets only, 15 = longest range) |
| `--port` | Arduino COM port, or `auto`; sends `S<kmh>,P<proximity>,V<volume>,L<last kmh>,F<captured>` lines at 115200 baud |
| `--no-sound` | Turn off the laptop-speaker alarm |
| `--rx-gain` | RX gain, 0..70 dB. Lower it if the screen shows `CLIPPING` |
| `--tx-gain` | TX attenuation, 0 (max power) to -89 dB (default -30 = short range; -10 for long range) |

On exit (window closed, Ctrl+C, console closed or a startup error) the program destroys the TX buffer
and sets TX attenuation to -89 dB, so the Pluto stops transmitting.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `DATA LOST: computer too slow` | Plug in the charger (on battery Windows slows the CPU) and close other programs |
| Wrong or jumping speeds with several people in view | The radar reports the strongest echo; test with one moving person or vehicle at a time |
| `CLIPPING` on screen | Lower `--rx-gain` (e.g. 20), or separate the TX and RX antennas |
| False targets with no one moving | Turn off ceiling fans; point the antennas away from moving objects |
| Noisy spectrum / only strong targets detected | Tighten every SMA connector by hand, keep the Pluto, cables and antennas off the laptop (fan vibration) and away from moving objects. For Wi-Fi interference move the Frequency slider (`--freq-mhz`) |
| GNU Radio window does not open / `No Pluto device found` | Check `pluto_uri` (default `ip:192.168.2.1`) and close other radar windows |
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
| FFT | 2048 points (0.26 s), 3.9 Hz bins (0.85 km/h); parabolic peak interpolation gives a 0.1 km/h readout (measured error below 0.05 km/h) |
| Response | Live speed about 0.15 s after movement starts; held (last) speed about 0.75 s after the target leaves |
| Speed range | about 3.3 km/h up to the max-speed setting (default 220, up to ~740 km/h at 2482 MHz), approaching and receding |
| Frequency | adjustable; 2400-2483 MHz with the 2.4 GHz antennas (Pluto range 325-3800 MHz) |
| Clutter rejection | Mirror-peak test (fans) plus 2-frame confirmation |
| Update rate | 64 ms per frame processed; window redrawn every 0.25 s so the loop keeps up on battery |
| Clutter map | Learns the background (Pluto spurs, static clutter) for ~2.5 s at start-up; screen shows `learning background` |
